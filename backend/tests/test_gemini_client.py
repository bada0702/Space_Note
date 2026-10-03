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


class _FakeStream:
    """httpx.stream(...) 컨텍스트 매니저 대역."""
    def __init__(self, status_code, body=b"", lines=()):
        self.status_code = status_code
        self._body = body
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def iter_lines(self):
        return iter(self._lines)


def _quota_body(retry_delay):
    import json
    return json.dumps({"error": {"code": 429, "details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay},
    ]}}).encode()


def test_stream_chat_fails_fast_when_daily_quota_exhausted(client, monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def fake_stream(*a, **kw):
        calls["n"] += 1
        return _FakeStream(429, _quota_body("45532s"))

    monkeypatch.setattr(gemini_client.httpx, "stream", fake_stream)
    monkeypatch.setattr(gemini_client.time, "sleep", sleeps.append)
    monkeypatch.setattr(gemini_client, "_api_key", lambda: "fake-key")

    with pytest.raises(ValueError) as e:
        list(gemini_client.stream_chat("gemini-3.5-flash", "sys", [{"role": "user", "content": "hi"}]))
    # 하루 한도 소진(재시도 대기 12시간대)이면 기다리지 않고 바로 알린다
    assert calls["n"] == 1 and sleeps == []
    assert "12시간" in str(e.value)


def test_stream_chat_retries_short_rate_limit(client, monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def fake_stream(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeStream(429, _quota_body("5s"))
        return _FakeStream(200, lines=['data: {"candidates":[{"content":{"parts":[{"text":"hi"}]}}]}'])

    monkeypatch.setattr(gemini_client.httpx, "stream", fake_stream)
    monkeypatch.setattr(gemini_client.time, "sleep", sleeps.append)
    monkeypatch.setattr(gemini_client, "_api_key", lambda: "fake-key")

    out = list(gemini_client.stream_chat("gemini-3.5-flash", "sys", [{"role": "user", "content": "hi"}]))
    assert out == ["hi"]
    assert sleeps == [5.0]
