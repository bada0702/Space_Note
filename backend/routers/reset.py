"""노트 초기화 — 설정(API 키 등)만 남기고 노트·은하·분석 데이터·채팅 기록과 vault의 노트 파일을 지운다.

vault 경로는 사용자가 아무 폴더로나 바꿀 수 있으므로 폴더를 통째로 지우지 않는다.
.md 파일과 attachments/만 지우고, 그 결과 비게 된 하위 폴더만 정리한다.
"""
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import settings
from db import get_conn

router = APIRouter()

CONFIRM_TEXT = "초기화"

# settings를 뺀 모든 데이터 테이블
_TABLES = (
    "notes", "categories", "entities", "tags", "routes",
    "concepts", "concept_aliases", "note_concepts", "relations",
    "conversations", "conversation_messages",
)


class ResetRequest(BaseModel):
    confirm: str


def _note_files(vault: Path) -> list[Path]:
    files = list(vault.rglob("*.md"))
    attachments = vault / "attachments"
    if attachments.is_dir():
        files += [p for p in attachments.rglob("*") if p.is_file() and p.suffix != ".md"]
    return files


@router.get("/reset/preview")
def reset_preview():
    with get_conn() as conn:
        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("notes", "categories", "conversations")
        }
    return {**counts, "files": len(_note_files(settings.VAULT_DIR)), "vault_dir": str(settings.VAULT_DIR)}


@router.post("/reset")
def reset(body: ResetRequest):
    if body.confirm != CONFIRM_TEXT:
        raise HTTPException(status_code=400, detail=f"확인 문구 '{CONFIRM_TEXT}'가 일치하지 않습니다")

    with get_conn() as conn:
        for t in _TABLES:
            conn.execute(f"DELETE FROM {t}")

    vault = settings.VAULT_DIR
    for p in vault.rglob("*.md"):
        p.unlink(missing_ok=True)
    shutil.rmtree(vault / "attachments", ignore_errors=True)
    # 깊은 폴더부터 비어 있으면 지운다 (은하 폴더 정리). 다른 파일이 남은 폴더는 그대로 둔다.
    for d in sorted((p for p in vault.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    return {"ok": True}
