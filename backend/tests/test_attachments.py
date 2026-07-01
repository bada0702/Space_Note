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
