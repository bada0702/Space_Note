import sqlite3


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
