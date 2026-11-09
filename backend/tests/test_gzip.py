from tests.conftest import AUTH

GZIP = {**AUTH, "Accept-Encoding": "gzip"}


def test_note_response_is_gzipped(client):
    body = "압축 대상 본문 " * 500
    nid = client.post("/notes", json={"title": "큰 노트", "content": body}, headers=AUTH).json()["id"]

    r = client.get(f"/notes/{nid}", headers=GZIP)

    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"
    assert r.json()["content"].strip() == body.strip()


def test_chat_stream_is_not_gzipped(client):
    # gzip 버퍼에 막히면 답변이 끝날 때까지 화면에 나오지 않는다
    r = client.post(
        "/ai/chat",
        json={"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "hi"}]},
        headers=GZIP,
    )

    assert r.status_code == 200
    assert "content-encoding" not in r.headers


def test_attachment_download_is_not_gzipped(client):
    data = b"a" * 5000
    url = client.post("/attachments?filename=a.txt", content=data, headers=AUTH).json()["url"]

    r = client.get(url, headers={"Accept-Encoding": "gzip"})

    assert r.status_code == 200
    assert "content-encoding" not in r.headers
    assert r.content == data
