from conftest import AUTH


def test_ai_settings_requires_auth(client):
    assert client.get("/ai/settings").status_code == 401


def test_get_and_patch_ai_settings(client):
    r = client.get("/ai/settings", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["default_model"] == "claude-sonnet-4-6"
    assert "id" not in r.json()

    r = client.patch("/ai/settings", json={"anthropic_api_key": "sk-test"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["anthropic_api_key"] == "sk-test"

    # 부분 patch: 다른 필드는 유지되어야 한다
    r = client.patch("/ai/settings", json={"default_model": "claude-haiku-4-5"}, headers=AUTH)
    assert r.json()["anthropic_api_key"] == "sk-test"
    assert r.json()["default_model"] == "claude-haiku-4-5"


def test_chat_requires_auth(client):
    r = client.post(
        "/ai/chat",
        json={"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 401


def test_chat_stream_reports_error_without_key(client):
    r = client.post(
        "/ai/chat",
        json={"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "hi"}]},
        headers=AUTH,
    )
    assert r.status_code == 200
    assert "error" in r.text


def test_chat_builds_system_context_from_note(client, monkeypatch):
    from routers import ai as ai_router

    note = client.post(
        "/notes", json={"title": "컨텍스트 노트", "content": "본문 내용"}, headers=AUTH
    ).json()

    captured = {}

    def fake_stream_chat(model, system, messages):
        captured["system"] = system
        yield "안녕"

    monkeypatch.setattr(ai_router.anthropic_client, "stream_chat", fake_stream_chat)

    r = client.post(
        "/ai/chat",
        json={
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "hi"}],
            "context_note_id": note["id"],
        },
        headers=AUTH,
    )
    assert r.status_code == 200
    assert "컨텍스트 노트" in captured["system"]
    assert "본문 내용" in captured["system"]


def test_ollama_models_requires_auth(client):
    assert client.get("/ai/ollama/models").status_code == 401


def test_ollama_models_endpoint(client, monkeypatch):
    from routers import ai as ai_router

    monkeypatch.setattr(
        ai_router.ollama_client, "list_models", lambda: [{"name": "llama3:8b"}]
    )
    r = client.get("/ai/ollama/models", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == [{"name": "llama3:8b"}]


def test_ollama_list_models_unavailable(client, monkeypatch):
    # 서버가 안 떠 있으면(연결 거부) 오류 대신 빈 목록
    from services import ollama_client

    monkeypatch.setattr(ollama_client.settings, "OLLAMA_BASE_URL", "http://127.0.0.1:9")
    assert ollama_client.list_models() == []


def test_chat_routes_ollama_prefix_to_ollama_client(client, monkeypatch):
    from routers import ai as ai_router

    captured = {}

    def fake_stream_chat(model, system, messages):
        captured["model"] = model
        yield "로컬 응답"

    monkeypatch.setattr(ai_router.ollama_client, "stream_chat", fake_stream_chat)

    r = client.post(
        "/ai/chat",
        json={
            "model": "ollama:llama3:8b",
            "messages": [{"role": "user", "content": "hi"}],
        },
        headers=AUTH,
    )
    assert r.status_code == 200
    assert "로컬 응답" in r.text
    assert captured["model"] == "llama3:8b"
