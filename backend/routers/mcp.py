"""MCP 서버 — 외부 에이전트(aibot 등)가 노트를 검색·조회(·작성)하는 도구 제공.

전송 방식: Streamable HTTP의 무상태 JSON 응답 모드 (POST /mcp, 세션 ID·SSE 없음).
인증: 앱 토큰과 별개인 MCP 전용 토큰(Bearer). 설정창에서 켜고 끄며, 토큰을 재발급할 수 있다.
"""
import json
import logging
import secrets
import threading
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from db import get_conn

router = APIRouter()  # 앱 토큰으로 보호되는 설정 API
public_router = APIRouter()  # MCP 토큰으로 직접 인증하는 /mcp
logger = logging.getLogger(__name__)

SERVER_NAME = "spacenote"
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
LIST_LIMIT_MAX = 100


# ── 설정 ────────────────────────────────────────────────────────────────

def _mcp_settings() -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT mcp_enabled, mcp_allow_write, mcp_token, mcp_aibot_config FROM settings WHERE id = 1"
        ).fetchone()
    return dict(row)


def _ensure_token() -> str:
    s = _mcp_settings()
    if s["mcp_token"]:
        return s["mcp_token"]
    token = secrets.token_urlsafe(32)
    with get_conn() as conn:
        conn.execute("UPDATE settings SET mcp_token = ? WHERE id = 1", (token,))
    return token


def _endpoint(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/mcp"


def _server_entry(url: str, token: str) -> dict:
    return {"url": url, "headers": {"Authorization": f"Bearer {token}"}}


def _aibot_registered(path: str, url: str) -> bool:
    try:
        servers = json.loads(Path(path).read_text(encoding="utf-8")).get("mcpServers", {})
    except (OSError, ValueError):
        return False
    return (servers.get(SERVER_NAME) or {}).get("url") == url


def _config_view(request: Request) -> dict:
    s = _mcp_settings()
    url = _endpoint(request)
    entry = _server_entry(url, s["mcp_token"]) if s["mcp_token"] else None
    return {
        "enabled": bool(s["mcp_enabled"]),
        "allow_write": bool(s["mcp_allow_write"]),
        "token": s["mcp_token"],
        "url": url,
        "tools": [t["name"] for t in _visible_tools(bool(s["mcp_allow_write"]))],
        "client_config": {"mcpServers": {SERVER_NAME: entry}} if entry else None,
        "aibot_config": s["mcp_aibot_config"],
        "aibot_registered": _aibot_registered(s["mcp_aibot_config"], url) if s["mcp_aibot_config"] else False,
    }


class McpConfigPatch(BaseModel):
    enabled: Optional[bool] = None
    allow_write: Optional[bool] = None
    aibot_config: Optional[str] = None


@router.get("/mcp/config")
def get_config(request: Request):
    return _config_view(request)


@router.patch("/mcp/config")
def patch_config(body: McpConfigPatch, request: Request):
    cols = {"enabled": "mcp_enabled", "allow_write": "mcp_allow_write", "aibot_config": "mcp_aibot_config"}
    fields = body.model_dump(exclude_unset=True)
    if "aibot_config" in fields:
        fields["aibot_config"] = fields["aibot_config"].strip()
    if fields:
        with get_conn() as conn:
            for k, v in fields.items():
                conn.execute(
                    f"UPDATE settings SET {cols[k]} = ? WHERE id = 1",
                    (int(v) if isinstance(v, bool) else v,),
                )
    if fields.get("enabled"):
        _ensure_token()
    return _config_view(request)


@router.post("/mcp/token/rotate")
def rotate_token(request: Request):
    with get_conn() as conn:
        conn.execute("UPDATE settings SET mcp_token = ? WHERE id = 1", (secrets.token_urlsafe(32),))
    return _config_view(request)


@router.post("/mcp/register-aibot")
def register_aibot(request: Request):
    """aibot의 mcp_servers.json에 spacenote 항목을 추가/갱신한다 (다른 서버 항목은 보존)."""
    s = _mcp_settings()
    path = Path(s["mcp_aibot_config"] or "")
    if path.suffix != ".json" or not path.is_absolute():
        raise HTTPException(status_code=400, detail="aibot 설정 파일은 .json 절대경로여야 합니다")
    if not path.parent.is_dir():
        raise HTTPException(status_code=400, detail=f"폴더가 없습니다: {path.parent}")
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8")) or {}
        except ValueError:
            raise HTTPException(status_code=400, detail="기존 설정 파일이 올바른 JSON이 아닙니다")
    token = _ensure_token()
    data.setdefault("mcpServers", {})[SERVER_NAME] = _server_entry(_endpoint(request), token)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _config_view(request)


# ── 도구 ────────────────────────────────────────────────────────────────

def _tool_search_notes(query: str, category_id: Optional[str] = None) -> str:
    from routers.ai import _retrieve_notes
    with get_conn() as conn:
        notes = _retrieve_notes(conn, query, category_id, None, fallback_recent=False)
    if not notes:
        return "관련 노트를 찾지 못했습니다."
    return json.dumps(notes, ensure_ascii=False)


def _tool_get_note(note_id: Optional[str] = None, title: Optional[str] = None) -> str:
    if not note_id and not title:
        raise ValueError("note_id 또는 title 중 하나가 필요합니다")
    with get_conn() as conn:
        if note_id:
            row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM notes WHERE title = ? ORDER BY modified_at DESC LIMIT 1", (title,)
            ).fetchone()
    if row is None:
        raise ValueError("노트를 찾을 수 없습니다")
    return json.dumps({
        "id": row["id"], "title": row["title"], "category_id": row["category_id"],
        "modified_at": row["modified_at"], "content": row["content"] or "",
    }, ensure_ascii=False)


def _tool_list_notes(category_id: Optional[str] = None, limit: int = 20) -> str:
    limit = max(1, min(int(limit), LIST_LIMIT_MAX))
    sql = "SELECT id, title, category_id, modified_at FROM notes WHERE is_archived = 0"
    params: list = []
    if category_id:
        sql += " AND category_id = ?"
        params.append(category_id)
    with get_conn() as conn:
        rows = conn.execute(sql + " ORDER BY modified_at DESC LIMIT ?", (*params, limit)).fetchall()
    return json.dumps([dict(r) for r in rows], ensure_ascii=False)


def _tool_list_categories() -> str:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name FROM categories ORDER BY sort_order, created_at"
        ).fetchall()
    return json.dumps([dict(r) for r in rows], ensure_ascii=False)


def _tool_create_note(title: str, content: str = "", category_id: Optional[str] = None) -> str:
    from models import NoteCreate
    from routers.notes import _unique_title, create_note
    from services import vault
    if not title.strip():
        raise ValueError("title이 비어 있습니다")
    bg = BackgroundTasks()
    note = create_note(
        NoteCreate(title=_unique_title(vault.safe_filename(title.strip())),
                   content=content, category_id=category_id),
        bg,
    )
    # 엔티티 추출 등 후처리는 응답을 막지 않도록 별도 스레드에서
    for task in bg.tasks:
        threading.Thread(target=task.func, args=task.args, kwargs=task.kwargs, daemon=True).start()
    return json.dumps({"id": note["id"], "title": note["title"]}, ensure_ascii=False)


_CATEGORY = {"type": "string", "description": "카테고리(은하) ID. list_categories로 조회"}

TOOLS: list[dict] = [
    {
        "name": "search_notes",
        "description": "SpaceNote에서 질문과 관련된 노트를 찾는다 (지식 그래프 + 키워드). 노트 ID, 제목, 관련 발췌, 선택 근거를 반환.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "검색할 질문이나 키워드"},
                           "category_id": _CATEGORY},
            "required": ["query"],
        },
        "fn": _tool_search_notes,
    },
    {
        "name": "get_note",
        "description": "노트 하나의 전체 본문을 가져온다. note_id 또는 정확한 title로 지정.",
        "inputSchema": {
            "type": "object",
            "properties": {"note_id": {"type": "string"}, "title": {"type": "string"}},
        },
        "fn": _tool_get_note,
    },
    {
        "name": "list_notes",
        "description": "최근 수정된 노트 목록(ID, 제목, 카테고리, 수정 시각).",
        "inputSchema": {
            "type": "object",
            "properties": {"category_id": _CATEGORY,
                           "limit": {"type": "integer", "minimum": 1, "maximum": LIST_LIMIT_MAX, "default": 20}},
        },
        "fn": _tool_list_notes,
    },
    {
        "name": "list_categories",
        "description": "노트 카테고리(은하) 목록.",
        "inputSchema": {"type": "object", "properties": {}},
        "fn": _tool_list_categories,
    },
    {
        "name": "create_note",
        "description": "SpaceNote에 새 노트를 만든다 (마크다운 본문). 같은 제목이 있으면 _2 등을 붙인다.",
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "content": {"type": "string"},
                           "category_id": _CATEGORY},
            "required": ["title"],
        },
        "fn": _tool_create_note,
        "write": True,
    },
]


def _visible_tools(allow_write: bool) -> list[dict]:
    return [t for t in TOOLS if allow_write or not t.get("write")]


# ── JSON-RPC 엔드포인트 ─────────────────────────────────────────────────

def _result(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


async def _handle(msg: dict, allow_write: bool) -> Optional[dict]:
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
        return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request")
    method, msg_id, params = msg["method"], msg.get("id"), msg.get("params") or {}
    if "id" not in msg:  # 알림(notifications/initialized 등)은 응답하지 않는다
        return None

    if method == "initialize":
        requested = params.get("protocolVersion")
        return _result(msg_id, {
            "protocolVersion": requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[1],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": "1.0.0"},
            "instructions": "SpaceNote 개인 노트 저장소. 사용자의 기록·지식을 물으면 search_notes로 찾고 get_note로 본문을 읽는다.",
        })
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        return _result(msg_id, {"tools": [
            {k: t[k] for k in ("name", "description", "inputSchema")} for t in _visible_tools(allow_write)
        ]})
    if method == "tools/call":
        tool: Optional[dict] = next(
            (t for t in _visible_tools(allow_write) if t["name"] == params.get("name")), None
        )
        if tool is None:
            return _error(msg_id, -32602, f"Unknown tool: {params.get('name')}")
        fn: Callable[..., str] = tool["fn"]
        args = params.get("arguments") or {}
        try:
            text = await run_in_threadpool(fn, **args)
            is_error = False
        except TypeError as e:
            text, is_error = f"잘못된 인자: {e}", True
        except Exception as e:  # noqa: BLE001 - 도구 오류는 isError 결과로 에이전트에 전달
            logger.warning("MCP tool %s failed: %s", tool["name"], e)
            text, is_error = str(e), True
        return _result(msg_id, {"content": [{"type": "text", "text": text}], "isError": is_error})
    return _error(msg_id, -32601, f"Method not found: {method}")


@public_router.post("/mcp")
async def mcp_endpoint(request: Request):
    s = await run_in_threadpool(_mcp_settings)
    if not s["mcp_enabled"]:
        raise HTTPException(status_code=403, detail="MCP 서버가 꺼져 있습니다 (SpaceNote 설정에서 켜세요)")
    auth = request.headers.get("authorization") or ""
    if not s["mcp_token"] or not secrets.compare_digest(auth, f"Bearer {s['mcp_token']}"):
        raise HTTPException(status_code=401, detail="Invalid or missing MCP token")

    try:
        body = await request.json()
    except ValueError:
        return JSONResponse(_error(None, -32700, "Parse error"), status_code=400)

    allow_write = bool(s["mcp_allow_write"])
    if isinstance(body, list):
        replies = [r for r in [await _handle(m, allow_write) for m in body] if r is not None]
        return JSONResponse(replies) if replies else Response(status_code=202)
    reply = await _handle(body, allow_write)
    return JSONResponse(reply) if reply is not None else Response(status_code=202)


@public_router.get("/mcp")
@public_router.delete("/mcp")
def mcp_no_stream():
    # 무상태 서버: 서버→클라이언트 SSE 스트림과 세션 종료를 지원하지 않는다
    return Response(status_code=405, headers={"Allow": "POST"})
