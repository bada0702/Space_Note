"""본문 인라인 #태그 추출 — 마크다운 헤딩(# 뒤에 공백)과는 정규식으로 구분된다."""
import re

from services.textnorm import norm_name

_TAG_RE = re.compile(r"(?<!\S)#([A-Za-z0-9가-힣_-]+)")


def extract_tags(content: str) -> list[str]:
    """본문에서 태그를 원문 표기 그대로, norm 기준 중복 제거해 순서대로 반환."""
    seen: dict[str, str] = {}
    for m in _TAG_RE.finditer(content or ""):
        tag = m.group(1)
        seen.setdefault(norm_name(tag), tag)
    return list(seen.values())
