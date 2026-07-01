import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Response, UploadFile, File
from fastapi.responses import FileResponse

from db import get_conn
from models import LinkCreate, MemoCreate, AttachmentOut
from services import attachments as svc

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(r) -> dict:
    return dict(r)


def _require_note(conn, note_id: str) -> None:
    if conn.execute("SELECT 1 FROM notes WHERE id = ?", (note_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="note not found")


def _next_sort(conn, note_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM attachments WHERE note_id = ?",
        (note_id,),
    ).fetchone()
    return int(row["n"])


def _insert(conn, note_id, type_, name, file_path, mime, size, url, text_content) -> dict:
    aid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO attachments (id, note_id, type, name, file_path, mime, size, "
        "url, text_content, sort_order, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (aid, note_id, type_, name, file_path, mime, size, url, text_content,
         _next_sort(conn, note_id), _now()),
    )
    return _row(conn.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone())


@router.get("/notes/{note_id}/attachments", response_model=list[AttachmentOut])
def list_attachments(note_id: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM attachments WHERE note_id = ? ORDER BY sort_order, created_at",
            (note_id,),
        ).fetchall()
    return [_row(r) for r in rows]


@router.get("/attachments", response_model=list[AttachmentOut])
def list_all_attachments():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM attachments ORDER BY note_id, sort_order, created_at"
        ).fetchall()
    return [_row(r) for r in rows]


@router.post("/notes/{note_id}/attachments/memo", response_model=AttachmentOut)
def add_memo(note_id: str, body: MemoCreate):
    with get_conn() as conn:
        _require_note(conn, note_id)
        out = _insert(conn, note_id, "memo", body.name, None, None, 0, None, body.text)
    return out


@router.post("/notes/{note_id}/attachments/link", response_model=AttachmentOut)
def add_link(note_id: str, body: LinkCreate):
    text = body.name + ("\n" + body.description if body.description else "")
    with get_conn() as conn:
        _require_note(conn, note_id)
        out = _insert(conn, note_id, "link", body.name, None, None, 0, body.url, text)
    return out


@router.post("/notes/{note_id}/attachments/file", response_model=AttachmentOut)
def add_file(note_id: str, file: UploadFile = File(...)):
    data = file.file.read()
    filename = file.filename or "file"
    with get_conn() as conn:
        _require_note(conn, note_id)
        rel, mime, size = svc.save_file(note_id, filename, data)
        text = svc.extract_text(filename, data)
        out = _insert(conn, note_id, "file", filename, rel, mime, size, None, text)
    return out


@router.get("/attachments/{aid}/download")
def download(aid: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
    if row is None or not row["file_path"]:
        raise HTTPException(status_code=404, detail="file not found")
    try:
        path = svc.abs_path(row["file_path"])
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="file missing")
    return FileResponse(str(path), media_type=row["mime"] or "application/octet-stream",
                        filename=row["name"])


@router.delete("/attachments/{aid}", status_code=204)
def delete_attachment(aid: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
        if row is not None:
            svc.delete_file(row["file_path"])
            conn.execute("DELETE FROM attachments WHERE id = ?", (aid,))
    return Response(status_code=204)
