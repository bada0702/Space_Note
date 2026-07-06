import pytest

from services import gemini_client


class _FakeResp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def json(self):
        return self._payload


def test_extract_entities_retries_on_429_then_succeeds(client, monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 2:
            return _FakeResp(429)
        return _FakeResp(200, {
            "candidates": [{"content": {"parts": [{"text": '[{"name":"A","type":"개념"}]'}]}}]
        })

    monkeypatch.setattr(gemini_client.httpx, "post", fake_post)
    monkeypatch.setattr(gemini_client.time, "sleep", lambda s: None)
    monkeypatch.setattr(gemini_client, "_api_key", lambda: "fake-key")

    out = gemini_client.extract_entities("내용")
    assert out == [{"name": "A", "type": "개념"}]
    assert calls["n"] == 2


def test_extract_entities_raises_on_non_429_error(client, monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return _FakeResp(500)

    monkeypatch.setattr(gemini_client.httpx, "post", fake_post)
    monkeypatch.setattr(gemini_client, "_api_key", lambda: "fake-key")

    with pytest.raises(RuntimeError):
        gemini_client.extract_entities("내용")


def test_stream_chat_rejects_unknown_model():
    with pytest.raises(ValueError):
        list(gemini_client.stream_chat("not-a-real-model", "sys", []))


def test_stream_chat_raises_without_key(client):
    assert gemini_client.has_api_key() is False
    with pytest.raises(ValueError):
        list(gemini_client.stream_chat("gemini-2.5-flash", "sys", [{"role": "user", "content": "hi"}]))
