"""Google Gemini REST API 클라이언트 (httpx 사용, SDK 의존성 없음)."""
import json
import os
import time
from typing import Iterator

import httpx

from db import get_conn
from services.anthropic_client import _EXTRACT_PROMPT, parse_entities

# gemini-2.0-flash는 무료 등급 할당량이 0(limit: 0)인 프로젝트가 많아 2.5를 기본으로
ALLOWED_CHAT_MODELS = {"gemini-2.5-flash", "gemini-2.0-flash"}
EXTRACT_MODEL = "gemini-2.5-flash"
_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _api_key() -> str:
    """settings(DB) 우선, 없으면 env."""
    with get_conn() as conn:
        row = conn.execute("SELECT google_api_key FROM settings WHERE id = 1").fetchone()
    db_key = row["google_api_key"] if row else ""
    return db_key or os.getenv("GOOGLE_API_KEY", "")


def has_api_key() -> bool:
    return bool(_api_key())


def _chat_payload(system: str, messages: list[dict]) -> dict:
    contents = [
        {
            "role": "model" if m["role"] == "assistant" else "user",
            "parts": [{"text": m["content"]}],
        }
        for m in messages
    ]
    payload: dict = {"contents": contents}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    return payload


def extract_entities(content: str) -> list[dict]:
    key = _api_key()
    if not key:
        raise ValueError("Google API 키가 설정되지 않았습니다")
    if not content.strip():
        return []
    # 무료 등급 분당 한도(429) 대응: 지수 백오프로 최대 4회 재시도
    delays = [0, 8, 16, 32]
    resp = None
    for delay in delays:
        if delay:
            time.sleep(delay)
        resp = httpx.post(
            f"{_BASE}/{EXTRACT_MODEL}:generateContent",
            headers={"x-goog-api-key": key},
            json=_chat_payload(
                "", [{"role": "user", "content": _EXTRACT_PROMPT + content}]
            ),
            timeout=60,
        )
        if resp.status_code != 429:
            break
    resp.raise_for_status()
    data = resp.json()
    text = "".join(
        part.get("text", "")
        for cand in data.get("candidates", [])
        for part in cand.get("content", {}).get("parts", [])
    )
    return parse_entities(text)


def stream_chat(model: str, system: str, messages: list[dict]) -> Iterator[str]:
    """텍스트 델타를 순차 yield. 모델/키 검증 실패 시 예외."""
    if model not in ALLOWED_CHAT_MODELS:
        raise ValueError("현재 Gemini 모델(gemini-2.5-flash, gemini-2.0-flash)만 지원합니다")
    key = _api_key()
    if not key:
        raise ValueError("Google API 키가 설정되지 않았습니다")

    # 무료 등급 분당 한도(429) 대응: 아직 응답을 하나도 스트리밍하지 않은
    # 상태에서만 재시도 — 첫 청크가 나간 뒤에는 재요청 시 내용이 중복될 수 있다.
    delays = [0, 8, 16, 32]
    for i, delay in enumerate(delays):
        if delay:
            time.sleep(delay)
        with httpx.stream(
            "POST",
            f"{_BASE}/{model}:streamGenerateContent",
            params={"alt": "sse"},
            headers={"x-goog-api-key": key},
            json=_chat_payload(system, messages),
            timeout=120,
        ) as resp:
            if resp.status_code == 429:
                if i == len(delays) - 1:
                    raise ValueError("Gemini API 요청 한도(429)를 초과했습니다 — 잠시 후 다시 시도하세요")
                continue
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                chunk = line[6:].strip()
                if not chunk or chunk == "[DONE]":
                    continue
                obj = json.loads(chunk)
                for cand in obj.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        if part.get("text"):
                            yield part["text"]
            return
