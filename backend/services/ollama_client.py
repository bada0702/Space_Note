"""로컬 Ollama REST API 클라이언트 (httpx 사용, SDK 의존성 없음)."""
import json
from typing import Iterator

import httpx

from config import settings
from db import get_conn
from services.anthropic_client import _EXTRACT_PROMPT, parse_entities

# 채팅 모델 값은 'ollama:<이름>'이 정식 표기 — 'gpt-oss' 같은 로컬 모델이 클라우드 모델 접두사와 겹치지 않게 한다.
PREFIX = "ollama:"


def is_ollama_model(model: str) -> bool:
    # 접두사 없이 저장된 예전 값도 클라우드 모델이 아니면 Ollama로 본다
    return model.startswith(PREFIX) or not model.startswith(("claude", "gemini", "gpt"))


def model_name(model: str) -> str:
    return model.removeprefix(PREFIX)


def base_url() -> str:
    """설정 화면에서 지정한 서버 주소, 비어 있으면 환경변수 OLLAMA_BASE_URL."""
    with get_conn() as conn:
        row = conn.execute("SELECT ollama_base_url FROM settings WHERE id = 1").fetchone()
    url = (row["ollama_base_url"] if row else "") or settings.OLLAMA_BASE_URL
    return url.rstrip("/")


def chat_json(model: str, prompt: str) -> str:
    """JSON 출력을 강제한 단발 요청 (지식 그래프 추출용). 응답 텍스트를 돌려준다."""
    resp = httpx.post(
        f"{base_url()}/api/chat",
        json={
            "model": model_name(model),
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
        },
        timeout=600.0,
    )
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


def list_models() -> list[dict]:
    """설치된 모델 목록 (`ollama list` 상당). 서버 미기동/접속 불가면 빈 목록."""
    try:
        resp = httpx.get(f"{base_url()}/api/tags", timeout=3)
        resp.raise_for_status()
    except httpx.HTTPError:
        return []
    return [{"name": m["name"]} for m in resp.json().get("models", [])]


def extract_entities(content: str, model: str) -> list[dict]:
    if not content.strip():
        return []
    resp = httpx.post(
        f"{base_url()}/api/chat",
        json={
            "model": model_name(model),
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
        f"{base_url()}/api/chat",
        json={"model": model_name(model), "messages": payload_messages, "stream": True},
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
