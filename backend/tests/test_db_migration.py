import sqlite3
import pytest


def test_init_db_migrates_missing_norm_column(monkeypatch, tmp_path):
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "legacy.db"))
    from config import settings
    settings.reload()

    conn = sqlite3.connect(settings.DB_PATH)
    conn.execute(
        "CREATE TABLE entities (id TEXT PRIMARY KEY, note_id TEXT NOT NULL, "
        "name TEXT NOT NULL, type TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO entities (id, note_id, name, type, created_at) VALUES (?,?,?,?,?)",
        ("e1", "n1", "OLLAMA", "concept", "now"),
    )
    conn.commit()
    conn.close()

    from db import init_db
    init_db()

    from services.textnorm import norm_name
    conn = sqlite3.connect(settings.DB_PATH)
    row = conn.execute("SELECT norm FROM entities WHERE id='e1'").fetchone()
    conn.close()
    assert row[0] == norm_name("OLLAMA")


def test_init_db_migrates_note_flags_and_routes_table(monkeypatch, tmp_path):
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "legacy2.db"))
    from config import settings
    settings.reload()

    # 플래그 컬럼이 없는 구버전 notes 테이블
    conn = sqlite3.connect(settings.DB_PATH)
    conn.execute(
        "CREATE TABLE notes (id TEXT PRIMARY KEY, path TEXT NOT NULL, "
        "title TEXT NOT NULL, content TEXT NOT NULL DEFAULT '', category_id TEXT, "
        "tags TEXT NOT NULL DEFAULT '[]', word_count INTEGER NOT NULL DEFAULT 0, "
        "analysis_status TEXT NOT NULL DEFAULT 'pending', "
        "created_at TEXT NOT NULL, modified_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO notes (id, path, title, created_at, modified_at) "
        "VALUES ('n1', '/p', 't', 'now', 'now')"
    )
    conn.commit()
    conn.close()

    from db import init_db
    init_db()

    conn = sqlite3.connect(settings.DB_PATH)
    row = conn.execute("SELECT is_favorite, is_archived FROM notes WHERE id='n1'").fetchone()
    assert row == (0, 0)
    # routes 테이블이 생성됐고 UNIQUE 제약이 동작한다
    conn.execute("INSERT INTO routes (id, note_a, note_b, created_at) VALUES ('r1','a','b','now')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO routes (id, note_a, note_b, created_at) VALUES ('r2','a','b','now')")
    conn.close()
