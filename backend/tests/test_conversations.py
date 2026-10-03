from tests.conftest import AUTH


def _save(client, cid, messages, title=None, model="gemini-3.5-flash-lite"):
    body = {"model": model, "messages": messages}
    if title is not None:
        body["title"] = title
    return client.put(f"/conversations/{cid}", json=body, headers=AUTH)


MSGS = [
    {"role": "user", "content": "블랙홀이 뭐야?"},
    {"role": "assistant", "content": "중력이 매우 강한 천체입니다.",
     "sources": [{"id": "n1", "title": "우주", "path": "키워드 '블랙홀' 일치"}]},
]


def test_conversations_require_auth(client):
    assert client.get("/conversations").status_code == 401


def test_save_and_get_conversation(client):
    r = _save(client, "c1", MSGS)
    assert r.status_code == 200
    # 제목을 안 주면 첫 사용자 메시지로 만든다
    assert r.json()["title"] == "블랙홀이 뭐야?"

    got = client.get("/conversations/c1", headers=AUTH).json()
    assert got["model"] == "gemini-3.5-flash-lite"
    assert [m["role"] for m in got["messages"]] == ["user", "assistant"]
    assert got["messages"][1]["sources"][0]["id"] == "n1"


def test_save_replaces_messages_and_keeps_title(client):
    _save(client, "c1", MSGS[:1], title="내 제목")
    _save(client, "c1", MSGS)
    got = client.get("/conversations/c1", headers=AUTH).json()
    assert got["title"] == "내 제목"
    assert len(got["messages"]) == 2


def test_long_first_message_title_is_truncated(client):
    r = _save(client, "c1", [{"role": "user", "content": "가" * 100}])
    assert len(r.json()["title"]) <= 41


def test_list_newest_first(client):
    _save(client, "old", MSGS)
    _save(client, "new", MSGS)
    _save(client, "old", MSGS)  # 다시 저장하면 맨 위로
    ids = [c["id"] for c in client.get("/conversations", headers=AUTH).json()]
    assert ids == ["old", "new"]


def test_delete_conversation(client):
    _save(client, "c1", MSGS)
    assert client.delete("/conversations/c1", headers=AUTH).status_code == 204
    assert client.get("/conversations/c1", headers=AUTH).status_code == 404
    assert client.get("/conversations", headers=AUTH).json() == []
