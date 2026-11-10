import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse

from config import settings
from db import get_conn
from models import AttachmentOut, LinkCreate, MemoCreate
from services import attachments as svc

# 업로드(쓰기)는 인증 필요, 다운로드는 <img>/링크에서 접근하므로 공개
router = APIRouter()
public_router = APIRouter()

_STORED_NAME = re.compile(r"^[0-9a-f]{32}(\.[A-Za-z0-9]{1,10})?$")
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# 브라우저가 안전하게 그대로 렌더링할 수 있는 타입만 inline 응답.
# 그 외(.html/.svg/.js 등 실행 가능한 콘텐츠 포함)는 공개 다운로드 라우트에서
# 저장형 XSS로 이어지지 않도록 강제 다운로드(Content-Disposition: attachment) +
# nosniff 처리한다.
_INLINE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".pdf", ".mp3", ".wav", ".ogg", ".mp4", ".webm", ".mov"}


def _attachments_dir() -> Path:
    d = Path(settings.VAULT_DIR) / "attachments"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/attachments")
async def upload(request: Request, filename: str = "file"):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다 (최대 20MB)")

    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일은 업로드할 수 없습니다")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다 (최대 20MB)")

    # 원본 이름에서 확장자만 취해 서버 생성 이름으로 저장 (경로 조작 차단)
    ext = Path(filename).suffix
    if not re.fullmatch(r"\.[A-Za-z0-9]{1,10}", ext or ""):
        ext = ""
    stored = f"{uuid.uuid4().hex}{ext.lower()}"
    (_attachments_dir() / stored).write_bytes(data)
    return {"name": Path(filename).name, "url": f"/attachments/file/{stored}"}


@public_router.get("/attachments/file/{stored}")
def download(stored: str):
    if not _STORED_NAME.match(stored):
        raise HTTPException(status_code=404, detail="Not found")
    path = _attachments_dir() / stored
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    media, _ = mimetypes.guess_type(stored)
    headers = {"X-Content-Type-Options": "nosniff"}
    if path.suffix.lower() not in _INLINE_EXTS:
        headers["Content-Disposition"] = "attachment"
    return FileResponse(path, media_type=media or "application/octet-stream", headers=headers)


# ── 위성(Satellite) — 노트에 종속되는 첨부 자료(파일·링크·메모) ─────────────────
# 다운로드는 <a href>로 열리므로 공개하되, id가 uuid4라 추측할 수 없다 (위 /attachments/file과 같은 방식)

def _reindex(note_id: str, bg: BackgroundTasks) -> None:
    """위성 변경 시 소속 노트를 재추출 대기로 돌리고 백그라운드 추출 예약."""
    from routers.notes import _run_extraction
    with get_conn() as conn:
        row = conn.execute("SELECT content FROM notes WHERE id = ?", (note_id,)).fetchone()
        conn.execute(
            "UPDATE notes SET analysis_status = 'pending' WHERE id = ?", (note_id,)
        )
    if row is not None:
        bg.add_task(_run_extraction, note_id, row["content"])


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
def add_memo(note_id: str, body: MemoCreate, bg: BackgroundTasks):
    with get_conn() as conn:
        _require_note(conn, note_id)
        out = _insert(conn, note_id, "memo", body.name, None, None, 0, None, body.text)
    _reindex(note_id, bg)
    return out


@router.post("/notes/{note_id}/attachments/link", response_model=AttachmentOut)
def add_link(note_id: str, body: LinkCreate, bg: BackgroundTasks):
    text = body.name + ("\n" + body.description if body.description else "")
    with get_conn() as conn:
        _require_note(conn, note_id)
        out = _insert(conn, note_id, "link", body.name, None, None, 0, body.url, text)
    _reindex(note_id, bg)
    return out


@router.post("/notes/{note_id}/attachments/file", response_model=AttachmentOut)
def add_file(note_id: str, bg: BackgroundTasks, file: UploadFile = File(...)):
    data = file.file.read(_MAX_UPLOAD_BYTES + 1)
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다 (최대 20MB)")
    filename = file.filename or "file"
    with get_conn() as conn:
        _require_note(conn, note_id)
        rel, mime, size = svc.save_file(note_id, filename, data)
        text = svc.extract_text(filename, data)
        out = _insert(conn, note_id, "file", filename, rel, mime, size, None, text)
    _reindex(note_id, bg)
    return out


@public_router.get("/attachments/{aid}/download")
def download_satellite(aid: str):
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
    # 공개 경로이므로 실행 가능한 콘텐츠(.html/.svg 등)가 렌더링되지 않게 강제 다운로드 + nosniff
    return FileResponse(str(path), media_type=row["mime"] or "application/octet-stream",
                        filename=row["name"], headers={"X-Content-Type-Options": "nosniff"})


@router.delete("/attachments/{aid}", status_code=204)
def delete_attachment(aid: str, bg: BackgroundTasks):
    note_id = None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
        if row is not None:
            note_id = row["note_id"]
            svc.delete_file(row["file_path"])
            conn.execute("DELETE FROM attachments WHERE id = ?", (aid,))
    if note_id:
        _reindex(note_id, bg)
    return Response(status_code=204)
