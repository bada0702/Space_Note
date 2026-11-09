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
  kind TEXT NOT NULL DEFAULT 'instance',
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
  evidence TEXT,
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
  vault_dir TEXT NOT NULL DEFAULT '',
  graph_model TEXT NOT NULL DEFAULT 'gemini-3.1-flash-lite',
  ollama_custom_models TEXT NOT NULL DEFAULT '[]'
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
        # 마이그레이션: 사용자가 거부한 항로 (기존 행은 모두 확정)
        route_cols = {r[1] for r in conn.execute("PRAGMA table_info(routes)")}
        if "status" not in route_cols:
            conn.execute("ALTER TABLE routes ADD COLUMN status TEXT NOT NULL DEFAULT 'confirmed'")
        # 마이그레이션: 그래프 추출이 실패한 이유 (사용자에게 표시)
        if "graph_error" not in note_cols:
            conn.execute("ALTER TABLE notes ADD COLUMN graph_error TEXT")
        # 마이그레이션: 관계의 근거 문장 (기존 관계는 근거 없음)
        relation_cols = {r[1] for r in conn.execute("PRAGMA table_info(relations)")}
        if "evidence" not in relation_cols:
            conn.execute("ALTER TABLE relations ADD COLUMN evidence TEXT")
        
        # settings 테이블 마이그레이션
        settings_cols = {r[1] for r in conn.execute("PRAGMA table_info(settings)")}
        if "ollama_base_url" not in settings_cols:
            conn.execute("ALTER TABLE settings ADD COLUMN ollama_base_url TEXT NOT NULL DEFAULT 'http://127.0.0.1:11434'")
        if "autology_path" not in settings_cols:
            conn.execute("ALTER TABLE settings ADD COLUMN autology_path TEXT NOT NULL DEFAULT 'http://127.0.0.1:8000'")
        if "vault_dir" not in settings_cols:
            conn.execute("ALTER TABLE settings ADD COLUMN vault_dir TEXT NOT NULL DEFAULT ''")
        # 지식 그래프 추출 모델과 직접 추가한 Ollama 모델(JSON 배열)
        if "graph_model" not in settings_cols:
            conn.execute(
                "ALTER TABLE settings ADD COLUMN graph_model TEXT NOT NULL DEFAULT 'gemini-3.1-flash-lite'"
            )
        if "ollama_custom_models" not in settings_cols:
            conn.execute("ALTER TABLE settings ADD COLUMN ollama_custom_models TEXT NOT NULL DEFAULT '[]'")
        # MCP 서버(외부 에이전트 연동) 설정 — 기본은 꺼짐, 쓰기 도구도 꺼짐
        if "mcp_enabled" not in settings_cols:
            conn.execute("ALTER TABLE settings ADD COLUMN mcp_enabled INTEGER NOT NULL DEFAULT 0")
        if "mcp_allow_write" not in settings_cols:
            conn.execute("ALTER TABLE settings ADD COLUMN mcp_allow_write INTEGER NOT NULL DEFAULT 0")
        if "mcp_token" not in settings_cols:
            conn.execute("ALTER TABLE settings ADD COLUMN mcp_token TEXT NOT NULL DEFAULT ''")
        if "mcp_aibot_config" not in settings_cols:
            conn.execute(
                "ALTER TABLE settings ADD COLUMN mcp_aibot_config TEXT NOT NULL "
                "DEFAULT '/root/aibot/data/mcp_servers.json'"
            )
        # 왼쪽 위에 보이는 앱 이름·로고(이미지 data URL) — 비어 있으면 기본값
        if "app_title" not in settings_cols:
            conn.execute("ALTER TABLE settings ADD COLUMN app_title TEXT NOT NULL DEFAULT ''")
        if "app_logo" not in settings_cols:
            conn.execute("ALTER TABLE settings ADD COLUMN app_logo TEXT NOT NULL DEFAULT ''")

        # 마이그레이션(user_version 1): 태그 추출 규칙 강화(코드·색상·숫자 제외)에 맞춰 기존 태그 재계산
        if conn.execute("PRAGMA user_version").fetchone()[0] < 1:
            _resync_all_tags(conn)
            conn.execute("PRAGMA user_version = 1")

        # 마이그레이션(user_version 2): 지식 그래프를 Class/Instance/Literal 온톨로지로
        if "kind" not in {r[1] for r in conn.execute("PRAGMA table_info(concepts)")}:
            conn.execute("ALTER TABLE concepts ADD COLUMN kind TEXT NOT NULL DEFAULT 'instance'")
        if conn.execute("PRAGMA user_version").fetchone()[0] < 2:
            _migrate_to_ontology(conn)
            conn.execute("PRAGMA user_version = 2")

        conn.commit()
    finally:
        conn.close()


def _migrate_to_ontology(conn: sqlite3.Connection) -> None:
    """기존 개념·관계를 온톨로지 형식으로 근사 변환. 정확한 결과는 [AI 항로분석] 재추출로 얻는다."""
    conn.execute("UPDATE concepts SET kind = CASE WHEN type = '개념' THEN 'class' ELSE 'instance' END")
    # instance가 instance의 '일종'이면 목적어는 사실상 분류(class)다
    conn.execute(
        "UPDATE concepts SET kind = 'class' WHERE id IN ("
        " SELECT r.obj_id FROM relations r JOIN concepts s ON s.id = r.subj_id "
        " WHERE r.pred = '일종이다' AND s.kind = 'instance')"
    )
    conn.execute(
        "UPDATE OR IGNORE relations SET pred = CASE "
        " (SELECT kind FROM concepts WHERE id = relations.subj_id) "
        " WHEN 'class' THEN '하위클래스이다' ELSE '인스턴스이다' END "
        "WHERE pred = '일종이다'"
    )
    conn.execute("DELETE FROM relations WHERE pred = '일종이다'")  # UNIQUE 충돌로 남은 중복
    # 다음 [AI 항로분석]에서 새 형식으로 다시 추출되도록 (그동안은 변환된 그래프를 그대로 쓴다)
    conn.execute("UPDATE notes SET graph_hash = NULL")


def _resync_all_tags(conn: sqlite3.Connection) -> None:
    import uuid
    from datetime import datetime, timezone
    from services.tagparse import extract_tags

    now = datetime.now(timezone.utc).isoformat()
    conn.execute("DELETE FROM tags")
    for nid, content in conn.execute("SELECT id, content FROM notes").fetchall():
        conn.executemany(
            "INSERT INTO tags (id, note_id, tag, norm, created_at) VALUES (?, ?, ?, ?, ?)",
            [(str(uuid.uuid4()), nid, t, norm_name(t), now) for t in extract_tags(content)],
        )


@contextmanager
def get_conn():
    conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
