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


def test_init_db_resyncs_noisy_tags_once(monkeypatch, tmp_path):
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "tags.db"))
    from config import settings
    settings.reload()
    from db import init_db
    init_db()

    # 옛 규칙으로 쌓인 잡음 태그(#1, 색상 코드)를 흉내 낸다
    conn = sqlite3.connect(settings.DB_PATH)
    conn.execute(
        "INSERT INTO notes (id, path, title, content, created_at, modified_at) VALUES (?,?,?,?,?,?)",
        ("n1", "p", "t", "#1 색상 #007bff 그리고 #아이디어 메모", "now", "now"),
    )
    conn.executemany(
        "INSERT INTO tags (id, note_id, tag, norm, created_at) VALUES (?,?,?,?,?)",
        [("t1", "n1", "1", "1", "now"), ("t2", "n1", "007bff", "007bff", "now")],
    )
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()

    init_db()
    conn = sqlite3.connect(settings.DB_PATH)
    assert [r[0] for r in conn.execute("SELECT tag FROM tags")] == ["아이디어"]
    # 두 번째 실행부터는 다시 계산하지 않는다
    conn.execute("INSERT INTO tags (id, note_id, tag, norm, created_at) VALUES ('t9','n1','수동','수동','now')")
    conn.commit()
    conn.close()
    init_db()
    conn = sqlite3.connect(settings.DB_PATH)
    assert sorted(r[0] for r in conn.execute("SELECT tag FROM tags")) == ["수동", "아이디어"]
    conn.close()


def _legacy_graph_db(monkeypatch, tmp_path):
    """kind 컬럼이 없던 user_version 1 시절의 지식 그래프 DB를 만든다."""
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "graph.db"))
    from config import settings
    settings.reload()
    from db import init_db
    init_db()
    conn = sqlite3.connect(settings.DB_PATH)
    if "kind" in {r[1] for r in conn.execute("PRAGMA table_info(concepts)")}:
        conn.execute("ALTER TABLE concepts DROP COLUMN kind")
    conn.execute("PRAGMA user_version = 1")
    for cid, name, ctype in [("c1", "RAG", "기술"), ("c2", "검색기법", "개념"), ("c3", "FAISS", "도구"),
                             ("c4", "벡터DB", "도구"), ("c5", "검색기법2", "개념")]:
        conn.execute("INSERT INTO concepts (id, name, norm, type, created_at) VALUES (?,?,?,?, 'now')",
                     (cid, name, name.lower(), ctype))
    for rid, s, p, o in [("r1", "c1", "일종이다", "c2"), ("r2", "c2", "일종이다", "c5"),
                         ("r3", "c3", "일종이다", "c4"), ("r4", "c1", "사용한다", "c3")]:
        conn.execute("INSERT INTO relations (id, subj_id, pred, obj_id, note_id) VALUES (?,?,?,?, 'n1')",
                     (rid, s, p, o))
    conn.execute("INSERT INTO notes (id, path, title, created_at, modified_at, graph_hash) "
                 "VALUES ('n1', '/p', 't', 'now', 'now', 'h')")
    conn.commit()
    conn.close()
    return settings.DB_PATH


def test_migration_v2_converts_concepts_to_ontology(monkeypatch, tmp_path):
    path = _legacy_graph_db(monkeypatch, tmp_path)
    from db import init_db
    init_db()
    conn = sqlite3.connect(path)
    kinds = dict(conn.execute("SELECT name, kind FROM concepts WHERE name != '검색기법2'"))
    preds = set(conn.execute(
        "SELECT cs.name, r.pred, co.name FROM relations r "
        "JOIN concepts cs ON cs.id = r.subj_id JOIN concepts co ON co.id = r.obj_id"))
    graph_hash = conn.execute("SELECT graph_hash FROM notes WHERE id = 'n1'").fetchone()[0]
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    # instance → instance '일종이다'의 목적어(벡터DB)는 class로 승격
    assert kinds == {"RAG": "instance", "검색기법": "class", "FAISS": "instance", "벡터DB": "class"}
    assert preds == {("RAG", "인스턴스이다", "검색기법"), ("검색기법", "하위클래스이다", "검색기법2"),
                     ("FAISS", "인스턴스이다", "벡터DB"), ("RAG", "사용한다", "FAISS")}
    assert graph_hash is None
    assert version == 2


def test_migration_v2_runs_once(monkeypatch, tmp_path):
    path = _legacy_graph_db(monkeypatch, tmp_path)
    from db import init_db
    init_db()
    conn = sqlite3.connect(path)
    conn.execute("UPDATE notes SET graph_hash = 'new'")
    conn.commit()
    conn.close()
    init_db()
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT graph_hash FROM notes").fetchone()[0] == "new"
    conn.close()


def test_settings_has_graph_model_columns(monkeypatch, tmp_path):
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "fresh.db"))
    from config import settings
    settings.reload()
    from db import init_db
    init_db()
    conn = sqlite3.connect(settings.DB_PATH)
    row = conn.execute("SELECT graph_model, ollama_custom_models FROM settings").fetchone()
    conn.close()
    assert row == ("gemini-3.1-flash-lite", "[]")
