import services.extraction as ac
from tests.conftest import AUTH


def _make_note(client):
    return client.post("/notes", json={"title": "행성", "content": "행성 본문"},
                       headers=AUTH).json()


def test_extraction_includes_attachment_text(client, monkeypatch):
    captured = {}

    def fake_extract(content):
        captured["content"] = content
        return [{"name": "토큰", "type": "concept"}]

    monkeypatch.setattr(ac, "extract_entities", fake_extract)

    note = _make_note(client)
    nid = note["id"]
    # 메모 위성 추가 → 재추출 트리거되어 위성 텍스트가 추출 입력에 포함
    client.post(f"/notes/{nid}/attachments/memo",
                json={"name": "메모", "text": "토큰 윈도우 설명"}, headers=AUTH)

    assert "토큰 윈도우 설명" in captured.get("content", "")
    assert "행성 본문" in captured["content"]

    # 노트 analysis_status가 재추출로 갱신됨
    r = client.get(f"/notes/{nid}", headers=AUTH)
    assert r.json()["analysis_status"] in ("analyzed", "pending")


def test_search_matches_attachment_text(client, monkeypatch):
    monkeypatch.setattr(ac, "extract_entities", lambda c: [])
    note = _make_note(client)
    client.post(f"/notes/{note['id']}/attachments/memo",
                json={"name": "메모", "text": "엠베딩 벡터"}, headers=AUTH)

    # 노트 본문/제목에는 없고 위성 텍스트에만 있는 단어로 검색
    r = client.get("/search?q=엠베딩", headers=AUTH)
    ids = [x["id"] for x in r.json()]
    assert note["id"] in ids
