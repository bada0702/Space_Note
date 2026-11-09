import json

from conftest import AUTH


def _enable(client, **extra):
    r = client.patch("/mcp/config", json={"enabled": True, **extra}, headers=AUTH)
    assert r.status_code == 200
    return r.json()


def _rpc(client, token, method, params=None, msg_id=1):
    body = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers={"Authorization": f"Bearer {token}"})


def test_config_requires_app_token(client):
    assert client.get("/mcp/config").status_code == 401


def test_disabled_by_default(client):
    cfg = client.get("/mcp/config", headers=AUTH).json()
    assert cfg["enabled"] is False and cfg["token"] == "" and cfg["client_config"] is None
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 403


def test_enable_issues_token_and_rejects_wrong_one(client):
    cfg = _enable(client)
    assert cfg["token"]
    assert cfg["client_config"]["mcpServers"]["spacenote"]["url"].endswith("/mcp")
    assert _rpc(client, "wrong", "ping").status_code == 401
    # 앱 토큰으로는 MCP에 접근할 수 없다
    assert _rpc(client, "test-token", "ping").status_code == 401
    assert _rpc(client, cfg["token"], "ping").json()["result"] == {}


def test_rotate_token_invalidates_old(client):
    old = _enable(client)["token"]
    new = client.post("/mcp/token/rotate", headers=AUTH).json()["token"]
    assert new != old
    assert _rpc(client, old, "ping").status_code == 401
    assert _rpc(client, new, "ping").status_code == 200


def test_initialize_and_notification(client):
    token = _enable(client)["token"]
    r = _rpc(client, token, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                             "clientInfo": {"name": "t", "version": "1"}})
    res = r.json()["result"]
    assert res["protocolVersion"] == "2025-06-18"
    assert res["serverInfo"]["name"] == "spacenote"
    r = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 202


def test_write_tool_hidden_until_allowed(client):
    token = _enable(client)["token"]
    names = [t["name"] for t in _rpc(client, token, "tools/list").json()["result"]["tools"]]
    assert "search_notes" in names and "create_note" not in names
    r = _rpc(client, token, "tools/call", {"name": "create_note", "arguments": {"title": "x"}})
    assert r.json()["error"]["code"] == -32602

    _enable(client, allow_write=True)
    names = [t["name"] for t in _rpc(client, token, "tools/list").json()["result"]["tools"]]
    assert "create_note" in names


def test_create_get_search_notes(client):
    token = _enable(client, allow_write=True)["token"]
    r = _rpc(client, token, "tools/call", {"name": "create_note", "arguments": {
        "title": "도커 정리", "content": "Docker 컨테이너 네트워크 설정 메모"}})
    res = r.json()["result"]
    assert res["isError"] is False
    created = json.loads(res["content"][0]["text"])

    r = _rpc(client, token, "tools/call", {"name": "get_note", "arguments": {"note_id": created["id"]}})
    note = json.loads(r.json()["result"]["content"][0]["text"])
    assert "컨테이너" in note["content"]

    r = _rpc(client, token, "tools/call", {"name": "search_notes", "arguments": {"query": "Docker 네트워크"}})
    found = json.loads(r.json()["result"]["content"][0]["text"])
    assert found[0]["id"] == created["id"]

    r = _rpc(client, token, "tools/call", {"name": "list_notes", "arguments": {}})
    assert created["id"] in r.json()["result"]["content"][0]["text"]


def test_tool_error_is_reported_not_raised(client):
    token = _enable(client)["token"]
    r = _rpc(client, token, "tools/call", {"name": "get_note", "arguments": {"note_id": "nope"}})
    res = r.json()["result"]
    assert res["isError"] is True
    r = _rpc(client, token, "tools/call", {"name": "get_note", "arguments": {"bogus": 1}})
    assert r.json()["result"]["isError"] is True


def test_register_aibot_preserves_other_servers(client, tmp_path):
    path = tmp_path / "mcp_servers.json"
    path.write_text(json.dumps({"mcpServers": {"fs": {"command": "npx"}}}))
    cfg = _enable(client, aibot_config=str(path))
    assert cfg["aibot_registered"] is False

    cfg = client.post("/mcp/register-aibot", headers=AUTH).json()
    assert cfg["aibot_registered"] is True
    servers = json.loads(path.read_text())["mcpServers"]
    assert servers["fs"] == {"command": "npx"}
    assert servers["spacenote"]["headers"]["Authorization"] == f"Bearer {cfg['token']}"


def test_register_aibot_rejects_bad_path(client):
    _enable(client, aibot_config="relative/path.txt")
    assert client.post("/mcp/register-aibot", headers=AUTH).status_code == 400


def test_graph_neighbors_and_path(client):
    from tests.test_graph import _note, _store, _store_onto
    token = _enable(client)["token"]
    a = _note(client, "도커", "x")
    b = _note(client, "리눅스", "y")
    _store(a["id"], [("Docker", "도구", 3, ["도커"]), ("Linux", "기술", 2, ())], [("Docker", "사용한다", "Linux")])
    _store(b["id"], [("Linux", "기술", 3, ()), ("cgroups", "기술", 2, ())], [("Linux", "사용한다", "cgroups")])

    r = _rpc(client, token, "tools/call", {"name": "graph_neighbors", "arguments": {"concept": "도커"}})
    res = json.loads(r.json()["result"]["content"][0]["text"])
    assert res["concept"]["name"] == "Docker"
    assert res["relations"] == [{"s": "Docker", "p": "사용한다", "o": "Linux", "note": "도커"}]

    r = _rpc(client, token, "tools/call", {"name": "graph_path", "arguments": {"source": "cgroups", "target": "Docker"}})
    path = json.loads(r.json()["result"]["content"][0]["text"])["path"]
    assert [(e["s"], e["o"]) for e in path] == [("Linux", "cgroups"), ("Docker", "Linux")]

    r = _rpc(client, token, "tools/call", {"name": "graph_neighbors", "arguments": {"concept": "dock"}})
    assert json.loads(r.json()["result"]["content"][0]["text"])["concept"]["name"] == "Docker"

    # literal(값) 노드는 개념으로 찾지 않는다
    _store_onto(b["id"], [("Linux", "instance"), ("6.8", "literal")], [("Linux", "버전", "6.8")])
    r = _rpc(client, token, "tools/call", {"name": "graph_neighbors", "arguments": {"concept": "6.8"}})
    assert r.json()["result"]["isError"] is True

    r = _rpc(client, token, "tools/call", {"name": "graph_neighbors", "arguments": {"concept": "없는개념"}})
    assert r.json()["result"]["isError"] is True
