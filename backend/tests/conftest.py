import pytest
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SPACENOTE_TOKEN", "test-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_ORIGIN", "http://localhost:1420")

    from config import settings
    settings.reload()
    from db import init_db
    init_db()
    from main import app
    return TestClient(app)
