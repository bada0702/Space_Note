from tests.conftest import AUTH


def test_upload_and_download_roundtrip(client):
    data = b"\x89PNG fake image bytes"
    r = client.post(
        "/attachments?filename=photo.png",
        content=data,
        headers={**AUTH, "Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "photo.png"
    assert body["url"].startswith("/attachments/file/")

    # 다운로드는 <img>/링크에서 쓰이므로 인증 헤더 없이 동작해야 한다
    dl = client.get(body["url"])
    assert dl.status_code == 200
    assert dl.content == data
    assert dl.headers["content-type"].startswith("image/png")


def test_upload_requires_auth(client):
    r = client.post("/attachments?filename=a.txt", content=b"x")
    assert r.status_code in (401, 403)


def test_upload_sanitizes_traversal_filename(client):
    r = client.post(
        "/attachments?filename=../../etc/passwd",
        content=b"x",
        headers={**AUTH, "Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 200
    # 저장 파일명은 서버가 생성한 uuid 기반이어야 하며 경로 조각이 없어야 한다
    assert ".." not in r.json()["url"]
    assert "/etc/" not in r.json()["url"]


def test_download_rejects_bad_name(client):
    r = client.get("/attachments/file/..%2F..%2Fetc%2Fpasswd")
    assert r.status_code in (400, 404)


def test_upload_empty_body_400(client):
    r = client.post(
        "/attachments?filename=a.txt",
        content=b"",
        headers={**AUTH, "Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 400
