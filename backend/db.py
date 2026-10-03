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
  is_favorite INTEGER NOT NULL DEFAULT 0,
  is_archived INTEGER NOT NULL DEFAULT 0,
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
CREATE TABLE IF NOT EXISTS routes (
  id TEXT PRIMARY KEY,
  note_a TEXT NOT NULL,
  note_b TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(note_a, note_b)
);
CREATE TABLE IF NOT EXISTS concepts (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  norm TEXT NOT NULL UNIQUE,
  type TEXT NOT NULL DEFAULT '개념',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS concept_aliases (
  norm TEXT PRIMARY KEY,
  alias TEXT NOT NULL,
  concept_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_concept_aliases_concept ON concept_aliases(concept_id);
CREATE TABLE IF NOT EXISTS note_concepts (
  note_id TEXT NOT NULL,
  concept_id TEXT NOT NULL,
  weight INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (note_id, concept_id)
);
CREATE INDEX IF NOT EXISTS idx_note_concepts_concept ON note_concepts(concept_id);
CREATE TABLE IF NOT EXISTS relations (
  id TEXT PRIMARY KEY,
  subj_id TEXT NOT NULL,
  pred TEXT NOT NULL,
  obj_id TEXT NOT NULL,
  note_id TEXT NOT NULL,
  UNIQUE(subj_id, pred, obj_id, note_id)
);
CREATE INDEX IF NOT EXISTS idx_relations_subj ON relations(subj_id);
CREATE INDEX IF NOT EXISTS idx_relations_obj ON relations(obj_id);
CREATE INDEX IF NOT EXISTS idx_relations_note ON relations(note_id);
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  model TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversation_messages (
  conversation_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  sources TEXT NOT NULL DEFAULT '[]',
  error TEXT,
  PRIMARY KEY (conversation_id, seq)
);
CREATE TABLE IF NOT EXISTS settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  anthropic_api_key TEXT NOT NULL DEFAULT '',
  openai_api_key TEXT NOT NULL DEFAULT '',
  google_api_key TEXT NOT NULL DEFAULT '',
  default_model TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
  ollama_base_url TEXT NOT NULL DEFAULT 'http://127.0.0.1:11434',
  autology_path TEXT NOT NULL DEFAULT 'http://127.0.0.1:8000',
  vault_dir TEXT NOT NULL DEFAULT ''
);
"""


def init_db() -> None:
    conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
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
        # 마이그레이션: notes 테이블에 즐겨찾기/보관 플래그 추가
        note_cols = {r[1] for r in conn.execute("PRAGMA table_info(notes)")}
        if "is_favorite" not in note_cols:
            conn.execute(
                "ALTER TABLE notes ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0"
            )
        if "is_archived" not in note_cols:
            conn.execute(
                "ALTER TABLE notes ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0"
            )
        # 마이그레이션: 지식 그래프 추출 상태 (기존 노트는 idle — 사용자가 일괄 분석을 눌러야 처리)
        if "graph_status" not in note_cols:
            conn.execute(
                "ALTER TABLE notes ADD COLUMN graph_status TEXT NOT NULL DEFAULT 'idle'"
            )
        if "graph_hash" not in note_cols:
            conn.execute("ALTER TABLE notes ADD COLUMN graph_hash TEXT")
        
        # settings 테이블 마이그레이션
        settings_cols = {r[1] for r in conn.execute("PRAGMA table_info(settings)")}
        if "ollama_base_url" not in settings_cols:
            conn.execute("ALTER TABLE settings ADD COLUMN ollama_base_url TEXT NOT NULL DEFAULT 'http://127.0.0.1:11434'")
        if "autology_path" not in settings_cols:
            conn.execute("ALTER TABLE settings ADD COLUMN autology_path TEXT NOT NULL DEFAULT 'http://127.0.0.1:8000'")
        if "vault_dir" not in settings_cols:
            conn.execute("ALTER TABLE settings ADD COLUMN vault_dir TEXT NOT NULL DEFAULT ''")
            
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_conn():
    conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
