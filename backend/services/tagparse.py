"""본문 인라인 #태그 추출 — 마크다운 헤딩(# 뒤에 공백)과는 정규식으로 구분된다.

붙여넣은 코드·설정·색상표가 태그로 잡히지 않도록 걸러낸다:
코드 블록/인라인 코드, 숫자만(#1), 색상 코드(#fff, #007bff), 주석 처리된 설정·코드
(#password = …, #include <…>, #load_dotenv(), 줄 맨 앞 #echo Starting… 처럼 뒤에 한글 없는 문장이 이어지는 경우).
"""
import re

from services.textnorm import norm_name

_TAG_CHARS = r"A-Za-z0-9가-힣_-"
# 태그 단어를 끝까지 읽은 뒤 판단해야 한다 — 그렇지 않으면 정규식이 글자를 덜어내며
# (#password = → #passwor) 뒤쪽 조건을 피해 간다
_TAG_RE = re.compile(rf"(?<!\S)#([{_TAG_CHARS}]+)(?![{_TAG_CHARS}])(?!\s*[=:<(\"'])")
_FENCE_RE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$", re.S | re.M)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_HEX_RE = re.compile(r"^(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_HAS_LETTER_RE = re.compile(r"[A-Za-z가-힣]")
_ONLY_TAGS_RE = re.compile(rf"^(?:\s*#[{_TAG_CHARS}]+)*\s*$")
_HANGUL_RE = re.compile(r"[가-힣]")


def _is_noise(tag: str) -> bool:
    return not _HAS_LETTER_RE.search(tag) or bool(_HEX_RE.match(tag))


def extract_tags(content: str) -> list[str]:
    """본문에서 태그를 원문 표기 그대로, norm 기준 중복 제거해 순서대로 반환."""
    text = _INLINE_CODE_RE.sub("", _FENCE_RE.sub("", content or ""))
    seen: dict[str, str] = {}
    for line in text.splitlines():
        for m in _TAG_RE.finditer(line):
            tag = m.group(1)
            if _is_noise(tag):
                continue
            # 줄 맨 앞 #단어 뒤에 한글 없는 문장이 이어지면 주석 처리된 명령/코드로 본다
            # (#echo Starting…, #vi sqlnet.ora) — "#AIX 작업 중" 같은 한국어 메모는 태그로 유지
            rest = line[m.end():]
            if not line[:m.start()].strip() and not _ONLY_TAGS_RE.match(rest) and not _HANGUL_RE.search(rest):
                continue
            seen.setdefault(norm_name(tag), tag)
    return list(seen.values())
