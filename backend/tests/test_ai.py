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


def _capture_system(client, monkeypatch, body):
    from routers import ai as ai_router

    captured = {}

    def fake_stream_chat(model, system, messages):
        captured["system"] = system
        yield "ok"

    monkeypatch.setattr(ai_router.anthropic_client, "stream_chat", fake_stream_chat)
    r = client.post("/ai/chat", json={"model": "claude-sonnet-4-6", **body}, headers=AUTH)
    assert r.status_code == 200
    return captured["system"]


def test_rag_selects_notes_relevant_to_question(client, monkeypatch):
    client.post(
        "/notes",
        json={"title": "Agent Loop 구현 방법", "content": "도구 호출 결과를 다시 모델에 넣는 루프"},
        headers=AUTH,
    )
    for i in range(6):
        client.post(
            "/notes", json={"title": f"최근 잡담 {i}", "content": "점심 메뉴 방법"}, headers=AUTH
        )

    system = _capture_system(client, monkeypatch, {
        "messages": [{"role": "user", "content": "작년에 정리한 Agent Loop 구현 방법 알려줘"}],
        "use_rag": True,
    })
    ctx = system.split("[참고 노트]", 1)[1]
    assert ctx.strip().startswith("# Agent Loop 구현 방법")
    assert "도구 호출 결과" in ctx


def test_rag_excludes_archived_and_falls_back_to_recent(client, monkeypatch):
    note = client.post(
        "/notes", json={"title": "XRDP 세션 로그", "content": "세션 종료"}, headers=AUTH
    ).json()
    client.post("/notes", json={"title": "다른 노트", "content": "무관한 내용"}, headers=AUTH)
    from db import get_conn
    with get_conn() as conn:
        conn.execute("UPDATE notes SET is_archived = 1 WHERE id = ?", (note["id"],))

    system = _capture_system(client, monkeypatch, {
        "messages": [{"role": "user", "content": "XRDP 세션 문제"}],
        "use_rag": True,
    })
    assert "XRDP 세션 로그" not in system
    assert "다른 노트" in system


def test_rag_excerpt_centers_on_keyword(client, monkeypatch):
    content = "서론 " * 1000 + "핵심키워드 설명 본문"
    client.post("/notes", json={"title": "긴 노트", "content": content}, headers=AUTH)

    system = _capture_system(client, monkeypatch, {
        "messages": [{"role": "user", "content": "핵심키워드"}],
        "use_rag": True,
    })
    assert "핵심키워드 설명 본문" in system
