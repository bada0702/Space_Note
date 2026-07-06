import sqlite3
from contextlib import contextmanager
from config import settings
from services.textnorm import norm_name

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
  id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  category_id TEXT,
  tags TEXT NOT NULL DEFAULT '[]',
  word_count INTEGER NOT NULL DEFAULT 0,
  analysis_status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  modified_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  note_id TEXT NOT NULL,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  norm TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tags (
  id TEXT PRIMARY KEY,
  note_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  norm TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  anthropic_api_key TEXT NOT NULL DEFAULT '',
  openai_api_key TEXT NOT NULL DEFAULT '',
  google_api_key TEXT NOT NULL DEFAULT '',
  default_model TEXT NOT NULL DEFAULT 'claude-sonnet-4-6'
);
"""


def init_db() -> None:
    conn = sqlite3.connect(settings.DB_PATH)
    try:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
        # 마이그레이션: 기존 entities 테이블에 norm 컬럼 추가 + 백필
        cols = {r[1] for r in conn.execute("PRAGMA table_info(entities)")}
        if "norm" not in cols:
            conn.execute("ALTER TABLE entities ADD COLUMN norm TEXT")
        for eid, name in conn.execute(
            "SELECT id, name FROM entities WHERE norm IS NULL"
        ).fetchall():
            conn.execute(
                "UPDATE entities SET norm = ? WHERE id = ?", (norm_name(name), eid)
            )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_conn():
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
