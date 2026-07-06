from conftest import AUTH


def _make_note(client, title, content=""):
    r = client.post("/notes", json={"title": title, "content": content}, headers=AUTH)
    assert r.status_code == 200
    return r.json()


def test_search_matches_title_and_content(client):
    _make_note(client, "우주여행", "은하수를 건너")
    _make_note(client, "다른 글", "상관없음")

    r = client.get("/search?q=은하수", headers=AUTH)
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
    assert results[0]["title"] == "우주여행"
    assert results[0]["content_preview"].startswith("은하수를 건너")


def test_search_empty_query_returns_empty_list(client):
    assert client.get("/search", headers=AUTH).json() == []


def test_search_requires_auth(client):
    assert client.get("/search?q=x").status_code == 401


def test_entities_endpoint_returns_extracted_entities(client, monkeypatch):
    from routers import notes as notes_router

    monkeypatch.setattr(notes_router.extraction, "has_api_key", lambda: True)
    monkeypatch.setattr(
        notes_router.extraction, "extract_entities",
        lambda c: [{"name": "Claude", "type": "개념"}],
    )
    note = _make_note(client, "n", "본문")
    r = client.get(f"/entities/{note['id']}", headers=AUTH)
    assert r.status_code == 200
    assert [e["name"] for e in r.json()] == ["Claude"]


def test_entities_endpoint_empty_for_unknown_note(client):
    assert client.get("/entities/does-not-exist", headers=AUTH).json() == []
