"""OpenAI Responses API 클라이언트 (httpx 사용, SDK 의존성 없음)."""
import json
import os
from typing import Iterator

import httpx

from db import get_conn

# 2026-10 기준 OpenAI 권장 텍스트 모델 (https://developers.openai.com/api/docs/models)
ALLOWED_CHAT_MODELS = {"gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna"}
_URL = "https://api.openai.com/v1/responses"


def _api_key() -> str:
    """settings(DB) 우선, 없으면 env."""
    with get_conn() as conn:
        row = conn.execute("SELECT openai_api_key FROM settings WHERE id = 1").fetchone()
    db_key = row["openai_api_key"] if row else ""
    return db_key or os.getenv("OPENAI_API_KEY", "")


def has_api_key() -> bool:
    return bool(_api_key())


def _error_message(body: bytes, status: int) -> str:
    try:
        return json.loads(body)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return f"OpenAI API 오류 ({status})"


def stream_chat(model: str, system: str, messages: list[dict]) -> Iterator[str]:
    """텍스트 델타를 순차 yield. 모델/키 검증 실패 시 예외."""
    if model not in ALLOWED_CHAT_MODELS:
        raise ValueError(f"현재 지원하는 OpenAI 모델이 아닙니다. (지원: {', '.join(sorted(ALLOWED_CHAT_MODELS))})")
    key = _api_key()
    if not key:
        raise ValueError("OpenAI API 키가 설정되지 않았습니다")

    payload: dict = {
        "model": model,
        "input": [{"role": m["role"], "content": m["content"]} for m in messages],
        "stream": True,
    }
    if system:
        payload["instructions"] = system

    with httpx.stream(
        "POST",
        _URL,
        headers={"Authorization": f"Bearer {key}"},
        json=payload,
        timeout=httpx.Timeout(120.0, connect=10.0),
    ) as resp:
        if resp.status_code >= 400:
            raise ValueError(_error_message(resp.read(), resp.status_code))
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            kind = event.get("type")
            if kind == "response.output_text.delta":
                yield event.get("delta", "")
            elif kind == "error":
                raise ValueError(event.get("message") or "OpenAI 스트리밍 오류")
            elif kind == "response.failed":
                err = (event.get("response") or {}).get("error") or {}
                raise ValueError(err.get("message") or "OpenAI 응답 생성 실패")


def complete_json(model: str, prompt: str) -> str:
    """JSON 출력을 강제한 단발 요청 (지식 그래프 추출용). 응답 텍스트를 돌려준다."""
    if model not in ALLOWED_CHAT_MODELS:
        raise ValueError(f"현재 지원하는 OpenAI 모델이 아닙니다. (지원: {', '.join(sorted(ALLOWED_CHAT_MODELS))})")
    key = _api_key()
    if not key:
        raise ValueError("OpenAI API 키가 설정되지 않았습니다")
    resp = httpx.post(
        _URL,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "input": [{"role": "user", "content": prompt}],
            "text": {"format": {"type": "json_object"}},
        },
        timeout=httpx.Timeout(300.0, connect=10.0),
    )
    if resp.status_code >= 400:
        raise ValueError(_error_message(resp.content, resp.status_code))
    # output에는 추론 요약 등 다른 항목도 섞이므로 message의 output_text만 모은다
    return "".join(
        c.get("text", "")
        for item in resp.json().get("output", [])
        if item.get("type") == "message"
        for c in item.get("content", [])
        if c.get("type") == "output_text"
    )
