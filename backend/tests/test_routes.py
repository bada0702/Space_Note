import services.anthropic_client as ac
from conftest import AUTH


def _mock_extract(monkeypatch, entities):
    monkeypatch.setattr(ac, "extract_entities", lambda content: entities)
    monkeypatch.setattr(ac, "has_api_key", lambda: True)


def _create(client, title, content=""):
    r = client.post("/notes", json={"title": title, "content": content}, headers=AUTH)
    assert r.status_code == 200
    return r.json()


def test_confirm_route_normalizes_and_flags(client, monkeypatch):
    _mock_extract(monkeypatch, [{"name": "Docker", "type": "tech"}])
    a = _create(client, "노트A", "Docker 공부")
    b = _create(client, "노트B", "Docker 배포")
    lo, hi = sorted([a["id"], b["id"]])

    # 역순으로 보내도 정규화되어 저장된다
    r = client.post("/routes", json={"note_a": hi, "note_b": lo}, headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"note_a": lo, "note_b": hi, "confirmed": True}

    # 중복 승인은 무해
    assert client.post("/routes", json={"note_a": lo, "note_b": hi}, headers=AUTH).status_code == 200

    routes = client.get("/discoveries/routes", headers=AUTH).json()
    assert routes == [
        {"note_a": lo, "note_b": hi, "shared_entities": ["Docker"], "confirmed": True}
    ]

    # 해제
    r = client.delete(f"/routes?note_a={hi}&note_b={lo}", headers=AUTH)
    assert r.status_code == 204
    routes = client.get("/discoveries/routes", headers=AUTH).json()
    assert routes[0]["confirmed"] is False


def test_confirmed_route_survives_without_discovery(client, monkeypatch):
    _mock_extract(monkeypatch, [])
    a = _create(client, "무관한 A", "내용")
    b = _create(client, "무관한 B", "내용")
    lo, hi = sorted([a["id"], b["id"]])

    client.post("/routes", json={"note_a": lo, "note_b": hi}, headers=AUTH)
    routes = client.get("/discoveries/routes", headers=AUTH).json()
    assert routes == [
        {"note_a": lo, "note_b": hi, "shared_entities": [], "confirmed": True}
    ]


def test_route_validation_and_cleanup(client, monkeypatch):
    _mock_extract(monkeypatch, [])
    a = _create(client, "홀로 노트", "내용")

    r = client.post("/routes", json={"note_a": a["id"], "note_b": a["id"]}, headers=AUTH)
    assert r.status_code == 400
    r = client.post("/routes", json={"note_a": a["id"], "note_b": "없는id"}, headers=AUTH)
    assert r.status_code == 404

    b = _create(client, "지워질 노트", "내용")
    client.post("/routes", json={"note_a": a["id"], "note_b": b["id"]}, headers=AUTH)
    client.delete(f"/notes/{b['id']}", headers=AUTH)
    assert client.get("/discoveries/routes", headers=AUTH).json() == []


def test_confirmed_route_hidden_when_note_archived(client, monkeypatch):
    _mock_extract(monkeypatch, [])
    a = _create(client, "활성 노트", "내용")
    b = _create(client, "보관될 노트", "내용")
    client.post("/routes", json={"note_a": a["id"], "note_b": b["id"]}, headers=AUTH)
    client.patch(f"/notes/{b['id']}", json={"is_archived": True}, headers=AUTH)
    assert client.get("/discoveries/routes", headers=AUTH).json() == []
