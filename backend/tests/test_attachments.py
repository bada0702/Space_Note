from conftest import AUTH


def test_attachments_table_exists(client):
    # DB가 초기화되면 attachments 테이블이 존재해야 한다.
    from db import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='attachments'"
        ).fetchall()
    assert len(rows) == 1


def test_link_and_memo_models_importable():
    from models import LinkCreate, MemoCreate, AttachmentOut
    lc = LinkCreate(url="https://x.com", name="X", description="d")
    assert lc.url == "https://x.com"
    mc = MemoCreate(name="m", text="t")
    assert mc.text == "t"
    out = AttachmentOut(
        id="1", note_id="n", type="memo", name="m", file_path=None,
        mime=None, size=0, url=None, text_content="t", sort_order=0,
        created_at="2026-07-01T00:00:00+00:00",
    )
    assert out.type == "memo"


def _make_note(client, monkeypatch):
    import services.anthropic_client as ac
    monkeypatch.setattr(ac, "extract_entities", lambda content: [])
    return client.post("/notes", json={"title": "행성", "content": "본문"}, headers=AUTH).json()


def test_memo_link_file_crud(client, monkeypatch):
    note = _make_note(client, monkeypatch)
    nid = note["id"]

    # 메모
    r = client.post(f"/notes/{nid}/attachments/memo",
                    json={"name": "토큰메모", "text": "토큰은 조각"}, headers=AUTH)
    assert r.status_code == 200
    memo = r.json()
    assert memo["type"] == "memo"
    assert memo["text_content"] == "토큰은 조각"

    # 링크
    r = client.post(f"/notes/{nid}/attachments/link",
                    json={"url": "https://a.com", "name": "A", "description": "설명"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["url"] == "https://a.com"
    assert "설명" in r.json()["text_content"]

    # 파일
    r = client.post(f"/notes/{nid}/attachments/file",
                    files={"file": ("code.py", b"print(1)", "text/x-python")}, headers=AUTH)
    assert r.status_code == 200
    f = r.json()
    assert f["type"] == "file"
    assert f["size"] == 8
    assert f["text_content"] == "print(1)"

    # 목록
    r = client.get(f"/notes/{nid}/attachments", headers=AUTH)
    assert len(r.json()) == 3

    # 다운로드
    r = client.get(f"/attachments/{f['id']}/download", headers=AUTH)
    assert r.status_code == 200
    assert r.content == b"print(1)"

    # 삭제
    r = client.delete(f"/attachments/{memo['id']}", headers=AUTH)
    assert r.status_code == 204
    assert len(client.get(f"/notes/{nid}/attachments", headers=AUTH).json()) == 2


def test_bulk_attachments(client, monkeypatch):
    note = _make_note(client, monkeypatch)
    client.post(f"/notes/{note['id']}/attachments/memo",
                json={"name": "m", "text": "t"}, headers=AUTH)
    r = client.get("/attachments", headers=AUTH)
    assert r.status_code == 200
    assert any(a["note_id"] == note["id"] for a in r.json())


def test_note_delete_cascades_attachments(client, monkeypatch):
    note = _make_note(client, monkeypatch)
    nid = note["id"]
    client.post(f"/notes/{nid}/attachments/file",
                files={"file": ("a.txt", b"data", "text/plain")}, headers=AUTH)
    from config import settings
    root = settings.VAULT_DIR / "attachments" / nid
    assert root.exists()

    client.delete(f"/notes/{nid}", headers=AUTH)
    from db import get_conn
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM attachments WHERE note_id=?", (nid,)).fetchall()
    assert rows == []
