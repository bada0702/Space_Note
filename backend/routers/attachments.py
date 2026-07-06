import mimetypes
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from config import settings

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
