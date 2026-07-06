"""엔티티 이름 정규화 — 표기 차이(대소문자/공백/기호)를 흡수하는 매칭 키.

db.py에서도 사용하므로 다른 services 모듈(순환 import 위험)을 참조하지 않는다.
"""
import re
import unicodedata

_STRIP = re.compile(r"[\s\-_./·]+")


def norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKC", name or "")
    s = _STRIP.sub("", s)
    return s.casefold()
