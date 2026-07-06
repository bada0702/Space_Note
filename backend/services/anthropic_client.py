import json
import re
from typing import Iterator

from anthropic import Anthropic

from config import settings
from db import get_conn

ALLOWED_CHAT_MODELS = {"claude-sonnet-4-6", "claude-haiku-4-5"}

_EXTRACT_PROMPT = (
    "다음 노트에서 핵심 엔티티(인물/개념/장소/조직 등)를 추출해 "
    'JSON 배열로만 답하라. 각 항목은 {"name": str, "type": str} 형식. '
    "표기 규칙: 소프트웨어/기술/제품 등 영문 고유명사는 한글 음차 대신 "
    "널리 쓰이는 공식 영문 표기를 사용하라(예: 올라마 → Ollama, 도커 → Docker). "
    "다른 설명 없이 JSON만 출력.\n\n노트:\n"
)


def _api_key() -> str:
    """settings(DB) 우선, 없으면 env."""
    with get_conn() as conn:
        row = conn.execute("SELECT anthropic_api_key FROM settings WHERE id = 1").fetchone()
    db_key = row["anthropic_api_key"] if row else ""
    return db_key or settings.ANTHROPIC_API_KEY


def parse_entities(text: str) -> list[dict]:
    """모델 응답 텍스트에서 엔티티 JSON 배열을 안전 파싱."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, dict) and "name" in item and "type" in item:
            out.append({"name": str(item["name"]), "type": str(item["type"])})
    return out


def has_api_key() -> bool:
    return bool(_api_key())


def extract_entities(content: str) -> list[dict]:
    key = _api_key()
    if not key:
        raise ValueError("Anthropic API 키가 설정되지 않았습니다")
    if not content.strip():
        return []
    client = Anthropic(api_key=key)
    msg = client.messages.create(
        model=settings.EXTRACT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": _EXTRACT_PROMPT + content}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    return parse_entities(text)


def stream_chat(model: str, system: str, messages: list[dict]) -> Iterator[str]:
    """텍스트 델타를 순차 yield. 모델/키 검증 실패 시 예외."""
    if model not in ALLOWED_CHAT_MODELS:
        raise ValueError("현재 Anthropic 모델(claude-sonnet-4-6, claude-haiku-4-5)만 지원합니다")
    key = _api_key()
    if not key:
        raise ValueError("Anthropic API 키가 설정되지 않았습니다")
    client = Anthropic(api_key=key)
    with client.messages.stream(
        model=model,
        max_tokens=4096,
        system=system or "You are SpaceNote's helpful assistant.",
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text
