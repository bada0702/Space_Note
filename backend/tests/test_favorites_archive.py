import services.anthropic_client as ac
from conftest import AUTH


def _mock_extract(monkeypatch, entities):
    monkeypatch.setattr(ac, "extract_entities", lambda content: entities)


def _create(client, title, content=""):
    r = client.post("/notes", json={"title": title, "content": content}, headers=AUTH)
    assert r.status_code == 200
    return r.json()


def test_favorite_toggle_keeps_modified_at(client, monkeypatch):
    _mock_extract(monkeypatch, [])
    note = _create(client, "즐겨찾기 노트", "내용")
    r = client.patch(f"/notes/{note['id']}", json={"is_favorite": True}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["is_favorite"] is True
    assert body["is_archived"] is False
    assert body["modified_at"] == note["modified_at"]  # 플래그만 변경 — 정렬 불변

    r = client.patch(f"/notes/{note['id']}", json={"is_favorite": False}, headers=AUTH)
    assert r.json()["is_favorite"] is False


def test_archive_excludes_from_default_list_and_search(client, monkeypatch):
    _mock_extract(monkeypatch, [])
    note = _create(client, "보관될 노트", "찾을내용")
    _create(client, "남는 노트", "다른내용")

    r = client.patch(f"/notes/{note['id']}", json={"is_archived": True}, headers=AUTH)
    assert r.json()["is_archived"] is True

    titles = [n["title"] for n in client.get("/notes", headers=AUTH).json()]
    assert titles == ["남는 노트"]

    archived = client.get("/notes?archived=true", headers=AUTH).json()
    assert [n["title"] for n in archived] == ["보관될 노트"]

    results = client.get("/search?q=찾을내용", headers=AUTH).json()
    assert results == []


def test_archive_excludes_from_discoveries_and_routes(client, monkeypatch):
    _mock_extract(monkeypatch, [{"name": "Ollama", "type": "tech"}])
    monkeypatch.setattr(ac, "has_api_key", lambda: True)

    import time
    a = _create(client, "노트A", "Ollama 이야기")
    b = _create(client, "노트B", "Ollama 정리")
    time.sleep(0.1)  # 백그라운드 추출이 완료될 때까지 대기

    routes = client.get("/discoveries/routes", headers=AUTH).json()
    assert len(routes) == 1

    client.patch(f"/notes/{b['id']}", json={"is_archived": True}, headers=AUTH)

    assert client.get("/discoveries/routes", headers=AUTH).json() == []
    assert client.get(f"/discoveries?note_id={a['id']}", headers=AUTH).json() == []


def test_archive_excludes_from_analyze_queue(client, monkeypatch):
    # 추출이 실패하는 노트 → analysis_status 'failed' → 분석 대상 후보가 됨
    def _raise(content):
        raise RuntimeError("extraction failed")
    monkeypatch.setattr(ac, "extract_entities", _raise)
    c = _create(client, "실패 노트", "내용 있음")

    import services.extraction as extraction
    monkeypatch.setattr(extraction, "has_api_key", lambda: True)

    client.patch(f"/notes/{c['id']}", json={"is_archived": True}, headers=AUTH)
    assert client.post("/notes/analyze", headers=AUTH).json()["queued"] == 0

    client.patch(f"/notes/{c['id']}", json={"is_archived": False}, headers=AUTH)
    assert client.post("/notes/analyze", headers=AUTH).json()["queued"] == 1
