import uuid
from pathlib import Path
from typing import Optional

from config import settings

# 텍스트로 추출·인덱싱할 확장자
TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".json", ".csv", ".tsv", ".html", ".htm", ".css", ".scss", ".java",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".go", ".rs", ".rb", ".php",
    ".sh", ".bash", ".zsh", ".yml", ".yaml", ".toml", ".ini", ".xml",
    ".sql", ".swift", ".kt", ".dart", ".r", ".lua", ".pl",
}

# 확장자 → MIME (최소 매핑; 없으면 application/octet-stream)
_MIME = {
    ".txt": "text/plain", ".md": "text/markdown", ".json": "application/json",
    ".csv": "text/csv", ".html": "text/html", ".css": "text/css",
    ".py": "text/x-python", ".js": "text/javascript", ".ts": "text/typescript",
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def _attachments_root() -> Path:
    return settings.VAULT_DIR / "attachments"


def guess_mime(filename: str) -> str:
    return _MIME.get(_ext(filename), "application/octet-stream")


def extract_text(filename: str, data: bytes) -> str:
    """텍스트 계열 파일이면 UTF-8로 디코드(에러 무시). 바이너리는 빈 문자열."""
    if _ext(filename) not in TEXT_EXTS:
        return ""
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def save_file(note_id: str, filename: str, data: bytes) -> tuple[str, str, int]:
    """파일을 VAULT_DIR/attachments/<note_id>/<uuid><ext>에 저장.
    (VAULT_DIR 기준 상대경로, mime, 바이트수) 반환."""
    ext = _ext(filename)
    safe_note = uuid.uuid5(uuid.NAMESPACE_URL, note_id).hex if "/" in note_id or "\\" in note_id else note_id
    target_dir = _attachments_root() / safe_note
    target_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{ext}"
    path = (target_dir / fname).resolve()
    root = settings.VAULT_DIR.resolve()
    if root not in path.parents:
        raise ValueError("path escapes vault")
    path.write_bytes(data)
    rel = str(path.relative_to(root))
    return rel, guess_mime(filename), len(data)


def abs_path(rel_path: str) -> Path:
    """상대경로를 VAULT_DIR 내부 절대경로로 변환(이탈 검증)."""
    root = settings.VAULT_DIR.resolve()
    path = (root / rel_path).resolve()
    if root not in path.parents and path != root:
        raise ValueError("path escapes vault")
    return path


def delete_file(rel_path: Optional[str]) -> None:
    if not rel_path:
        return
    try:
        p = abs_path(rel_path)
    except ValueError:
        return
    if p.exists() and p.is_file():
        p.unlink()


def indexable_context(conn, note_id: str) -> str:
    """인덱싱 대상 위성 텍스트를 [위성: name] 헤더와 함께 결합."""
    rows = conn.execute(
        "SELECT name, text_content FROM attachments "
        "WHERE note_id = ? AND text_content != '' "
        "ORDER BY sort_order, created_at",
        (note_id,),
    ).fetchall()
    return "".join(
        f"\n\n[위성: {r['name']}]\n{r['text_content']}" for r in rows
    )
