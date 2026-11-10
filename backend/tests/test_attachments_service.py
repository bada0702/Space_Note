import importlib
import pytest


def _svc(monkeypatch, tmp_path):
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    from config import settings
    settings.reload()
    svc = importlib.import_module("services.attachments")
    return importlib.reload(svc)


def test_save_file_inside_vault(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    rel, mime, size = svc.save_file("note1", "hello.txt", b"hi there")
    assert rel.startswith("attachments/note1/")
    assert rel.endswith(".txt")
    assert size == 8
    from config import settings
    assert (settings.VAULT_DIR / rel).exists()


def test_extract_text_for_text_files(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    assert svc.extract_text("a.py", b"print(1)") == "print(1)"
    assert svc.extract_text("a.md", b"# title") == "# title"
    # 바이너리(PDF/이미지)는 추출하지 않는다
    assert svc.extract_text("a.pdf", b"%PDF-1.4 binary") == ""
    assert svc.extract_text("a.png", b"\x89PNG\r\n") == ""


def test_abs_path_rejects_escape(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        svc.abs_path("../../etc/passwd")


def test_indexable_context_joins_text_attachments(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    from config import settings
    settings.reload()
    from db import init_db, get_conn
    init_db()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO attachments (id, note_id, type, name, text_content, "
            "sort_order, created_at) VALUES "
            "('a1','n1','memo','메모1','토큰 내용',0,'2026-07-01T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO attachments (id, note_id, type, name, text_content, "
            "sort_order, created_at) VALUES "
            "('a2','n1','file','빈파일','',1,'2026-07-01T00:00:00+00:00')"
        )
    with get_conn() as conn:
        ctx = svc.indexable_context(conn, "n1")
    assert "메모1" in ctx
    assert "토큰 내용" in ctx
    assert "빈파일" not in ctx  # text_content 비어있으면 제외
