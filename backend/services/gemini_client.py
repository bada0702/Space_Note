"""Google Gemini REST API 클라이언트 (httpx 사용, SDK 의존성 없음)."""
import json
import os
import time
from typing import Iterator

import httpx

from db import get_conn
from services.anthropic_client import _EXTRACT_PROMPT, parse_entities

# gemini-2.x는 신규 사용자/프로젝트에 더 이상 제공되지 않으므로(404 Not Found) 3.6-flash 이상 지원
ALLOWED_CHAT_MODELS = {
    "gemini-4-argon",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash",
}
# 토큰 소모가 적은 경량 모델로 추출
EXTRACT_MODEL = "gemini-3.1-flash-lite"
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


MAX_CHAT_RETRIES = 3
MAX_CHAT_RETRY_WAIT = 30.0  # 이보다 오래 기다려야 하면 재시도하지 않는다


def _retry_delay(body: bytes) -> float | None:
    """429 응답 본문의 RetryInfo.retryDelay("45s")를 초 단위로."""
    try:
        details = json.loads(body).get("error", {}).get("details", [])
    except (ValueError, AttributeError):
        return None
    for d in details:
        if d.get("@type", "").endswith("RetryInfo"):
            try:
                return float(str(d.get("retryDelay", "")).rstrip("s"))
            except ValueError:
                return None
    return None


def _human_wait(seconds: float) -> str:
    h, m = int(seconds // 3600), int(seconds % 3600 // 60)
    if h:
        return f"약 {h}시간 {m}분"
    return f"약 {max(m, 1)}분"


def stream_chat(model: str, system: str, messages: list[dict]) -> Iterator[str]:
    """텍스트 델타를 순차 yield. 모델/키 검증 실패 시 예외."""
    if model not in ALLOWED_CHAT_MODELS:
        raise ValueError(f"현재 지원하는 Gemini 모델이 아닙니다. (지원: {', '.join(sorted(ALLOWED_CHAT_MODELS))})")
    key = _api_key()
    if not key:
        raise ValueError("Google API 키가 설정되지 않았습니다")

    # 무료 등급 분당 한도(429) 대응: 아직 응답을 하나도 스트리밍하지 않은
    # 상태에서만 재시도 — 첫 청크가 나간 뒤에는 재요청 시 내용이 중복될 수 있다.
    # 응답의 retryDelay가 길면(하루 한도 소진 등) 기다리지 않고 바로 알린다.
    for attempt in range(MAX_CHAT_RETRIES + 1):
        with httpx.stream(
            "POST",
            f"{_BASE}/{model}:streamGenerateContent",
            params={"alt": "sse"},
            headers={"x-goog-api-key": key},
            json=_chat_payload(system, messages),
            timeout=120,
        ) as resp:
            if resp.status_code == 429:
                delay = _retry_delay(resp.read())
                if delay is not None and delay > MAX_CHAT_RETRY_WAIT:
                    raise ValueError(
                        f"{model} 무료 사용 한도를 모두 썼습니다 — {_human_wait(delay)} 후 다시 시도하거나 "
                        "다른 모델(예: Flash-Lite)을 선택하세요"
                    )
                if attempt == MAX_CHAT_RETRIES:
                    raise ValueError("Gemini API 요청 한도(429)를 초과했습니다 — 잠시 후 다시 시도하세요")
                time.sleep(delay if delay is not None else 8.0 * (attempt + 1))
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
