import pytest


def test_no_keys_raises(client):
    from services import extraction

    assert extraction.has_api_key() is False
    with pytest.raises(ValueError):
        extraction.extract_entities("내용")


def test_prefers_anthropic_when_both_keys(client, monkeypatch):
    from services import extraction, anthropic_client, gemini_client

    monkeypatch.setattr(anthropic_client, "has_api_key", lambda: True)
    monkeypatch.setattr(gemini_client, "has_api_key", lambda: True)
    monkeypatch.setattr(
        anthropic_client, "extract_entities", lambda c: [{"name": "A", "type": "개념"}]
    )
    monkeypatch.setattr(
        gemini_client, "extract_entities", lambda c: [{"name": "G", "type": "개념"}]
    )
    assert extraction.extract_entities("x")[0]["name"] == "A"


def test_falls_back_to_gemini(client, monkeypatch):
    from services import extraction, anthropic_client, gemini_client

    monkeypatch.setattr(anthropic_client, "has_api_key", lambda: False)
    monkeypatch.setattr(gemini_client, "has_api_key", lambda: True)
    monkeypatch.setattr(
        gemini_client, "extract_entities", lambda c: [{"name": "G", "type": "개념"}]
    )
    assert extraction.has_api_key() is True
    assert extraction.extract_entities("x")[0]["name"] == "G"


def test_gemini_chat_payload_roles():
    from services import gemini_client

    payload = gemini_client._chat_payload(
        "시스템 지침",
        [
            {"role": "user", "content": "안녕"},
            {"role": "assistant", "content": "안녕하세요"},
            {"role": "user", "content": "질문"},
        ],
    )
    assert payload["systemInstruction"]["parts"][0]["text"] == "시스템 지침"
    roles = [c["role"] for c in payload["contents"]]
    assert roles == ["user", "model", "user"]
    assert payload["contents"][2]["parts"][0]["text"] == "질문"
