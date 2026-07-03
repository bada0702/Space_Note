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


def _attachments_dir() -> Path:
    d = Path(settings.VAULT_DIR) / "attachments"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/attachments")
async def upload(request: Request, filename: str = "file"):
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일은 업로드할 수 없습니다")
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
    return FileResponse(path, media_type=media or "application/octet-stream")
