import services.anthropic_client as ac
from conftest import AUTH


def _mock_extract(monkeypatch, entities):
    monkeypatch.setattr(ac, "extract_entities", lambda content: entities)


def test_create_get_update_delete_note(client, monkeypatch):
    _mock_extract(monkeypatch, [{"name": "테스트", "type": "concept"}])

    r = client.post(
        "/notes",
        json={"title": "첫 노트", "vault_path": "/ignored/path", "content": "본문 내용"},
        headers=AUTH,
    )
    assert r.status_code == 200
    note = r.json()
    assert note["title"] == "첫 노트"
    assert note["content"] == "본문 내용"
    assert note["tags"] == []
    assert note["word_count"] == 2
    assert note["analysis_status"] in ("analyzed", "pending")
    assert note["path"].endswith("첫 노트.md")
    nid = note["id"]

    with open(note["path"], encoding="utf-8") as f:
        assert "본문 내용" in f.read()

    r = client.get(f"/notes/{nid}", headers=AUTH)
    assert r.json()["content"] == "본문 내용"

    r = client.get("/notes", headers=AUTH)
    assert len(r.json()) == 1

    r = client.patch(f"/notes/{nid}", json={"content": "수정 본문", "tags": ["a", "b"]}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["content"] == "수정 본문"
    assert r.json()["tags"] == ["a", "b"]

    r = client.delete(f"/notes/{nid}", headers=AUTH)
    assert r.status_code == 204
    assert client.get("/notes", headers=AUTH).json() == []


def test_list_filter_by_category(client, monkeypatch):
    _mock_extract(monkeypatch, [])
    cat = client.post("/categories", json={"name": "C"}, headers=AUTH).json()
    client.post("/notes", json={"title": "n1", "category_id": cat["id"]}, headers=AUTH)
    client.post("/notes", json={"title": "n2"}, headers=AUTH)

    r = client.get(f"/notes?category_id={cat['id']}", headers=AUTH)
    assert len(r.json()) == 1
    assert r.json()[0]["title"] == "n1"


def test_get_missing_note_404(client):
    assert client.get("/notes/nope", headers=AUTH).status_code == 404
