import json

import pytest

from services import openai_client


class _FakeStream:
    def __init__(self, status_code, lines=(), body=b""):
        self.status_code = status_code
        self._lines = lines
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body

    def iter_lines(self):
        return iter(self._lines)


def _sse(event: dict) -> str:
    return "data: " + json.dumps(event)


def test_stream_chat_rejects_unknown_model():
    with pytest.raises(ValueError):
        list(openai_client.stream_chat("gpt-not-real", "", [{"role": "user", "content": "hi"}]))


def test_stream_chat_raises_without_key(client):
    with pytest.raises(ValueError):
        list(openai_client.stream_chat("gpt-6-luna", "", [{"role": "user", "content": "hi"}]))


def test_stream_chat_yields_text_deltas(client, monkeypatch):
    captured = {}

    def fake_stream(method, url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeStream(200, [
            "event: response.created",
            _sse({"type": "response.created"}),
            _sse({"type": "response.output_text.delta", "delta": "안녕"}),
            _sse({"type": "response.output_text.delta", "delta": "하세요"}),
            _sse({"type": "response.completed"}),
        ])

    monkeypatch.setattr(openai_client.httpx, "stream", fake_stream)
    monkeypatch.setattr(openai_client, "_api_key", lambda: "sk-test")

    out = list(openai_client.stream_chat("gpt-6-luna", "시스템", [{"role": "user", "content": "hi"}]))
    assert out == ["안녕", "하세요"]
    assert captured["json"]["instructions"] == "시스템"
    assert captured["json"]["input"] == [{"role": "user", "content": "hi"}]


def test_stream_chat_surfaces_api_error_message(client, monkeypatch):
    body = b'{"error": {"message": "Incorrect API key provided"}}'
    monkeypatch.setattr(openai_client.httpx, "stream", lambda *a, **k: _FakeStream(401, body=body))
    monkeypatch.setattr(openai_client, "_api_key", lambda: "sk-bad")

    with pytest.raises(ValueError, match="Incorrect API key"):
        list(openai_client.stream_chat("gpt-6-luna", "", [{"role": "user", "content": "hi"}]))
