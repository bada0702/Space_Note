"""로컬 Ollama REST API 클라이언트 (httpx 사용, SDK 의존성 없음)."""
import json
from typing import Iterator

import httpx

from config import settings
from services.anthropic_client import _EXTRACT_PROMPT, parse_entities

OLLAMA_BASE_URL = "http://127.0.0.1:11434"

def list_models() -> list[dict]:
    """설치된 모델 목록 (`ollama list` 상당). 서버 미기동/접속 불가면 빈 목록."""
    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        resp.raise_for_status()
    except httpx.HTTPError:
        return []
    return [{"name": m["name"]} for m in resp.json().get("models", [])]


def extract_entities(content: str, model: str) -> list[dict]:
    if not content.strip():
        return []
    resp = httpx.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": _EXTRACT_PROMPT + content}],
            "stream": False
        },
        timeout=600.0
    )
    resp.raise_for_status()
    text = resp.json().get("message", {}).get("content", "")
    return parse_entities(text)


def stream_chat(model: str, system: str, messages: list[dict]) -> Iterator[str]:
    payload_messages: list[dict] = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages += messages
    with httpx.stream(
        "POST",
        f"{OLLAMA_BASE_URL}/api/chat",
        json={"model": model, "messages": payload_messages, "stream": True},
        timeout=httpx.Timeout(120.0, connect=5.0),
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            text = data.get("message", {}).get("content", "")
            if text:
                yield text
            if data.get("done"):
                break
