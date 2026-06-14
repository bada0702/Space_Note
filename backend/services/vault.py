import re
from pathlib import Path

from config import settings

_SAFE = re.compile(r"[^\w \-]", re.UNICODE)


def safe_filename(title: str) -> str:
    """파일명 안전화: 영숫자(유니코드)/공백/하이픈만 허용, 경로 구분자 제거."""
    cleaned = _SAFE.sub("", title).strip()
    return cleaned or "untitled"


def md_path(title: str) -> Path:
    return settings.VAULT_DIR / f"{safe_filename(title)}.md"


def write_md(title: str, content: str, tags: list[str]) -> str:
    """노트를 .md로 내보내기 (Obsidian 호환 frontmatter). 절대경로 문자열 반환."""
    settings.VAULT_DIR.mkdir(parents=True, exist_ok=True)
    path = md_path(title)
    # 항상 VAULT_DIR 내부인지 보장
    resolved = path.resolve()
    if settings.VAULT_DIR.resolve() not in resolved.parents and resolved != (
        settings.VAULT_DIR.resolve() / path.name
    ):
        raise ValueError("path escapes vault")
    tag_line = ", ".join(tags)
    frontmatter = f"---\ntags: [{tag_line}]\n---\n\n"
    path.write_text(frontmatter + content, encoding="utf-8")
    return str(path)


def delete_md(title: str) -> None:
    path = md_path(title)
    if path.exists():
        path.unlink()
