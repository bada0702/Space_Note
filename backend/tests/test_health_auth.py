from conftest import AUTH


def test_health_no_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "default_vault" in body


def test_categories_requires_auth(client):
    r = client.get("/categories")
    assert r.status_code == 401


def test_categories_with_auth_ok(client):
    r = client.get("/categories", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []


def test_missing_token_config_returns_500(client, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "SPACENOTE_TOKEN", "")
    r = client.get("/categories", headers=AUTH)
    assert r.status_code == 500
    assert "not configured" in r.json()["detail"]
