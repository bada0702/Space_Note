"""AI 채팅 대화 기록 — 프론트가 한 번 주고받을 때마다 대화 전체를 저장(upsert)한다."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response

from db import get_conn
from models import ConversationSave

router = APIRouter()

TITLE_MAX = 40


def _auto_title(body: ConversationSave) -> str:
    first = next((m.content for m in body.messages if m.role == "user"), "")
    first = " ".join(first.split())
    if not first:
        return "새 대화"
    return first if len(first) <= TITLE_MAX else first[:TITLE_MAX] + "…"


@router.get("/conversations")
def list_conversations():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, model, created_at, updated_at FROM conversations "
            "ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/conversations/{cid}")
def get_conversation(cid: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (cid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found")
        msgs = conn.execute(
            "SELECT role, content, sources, error FROM conversation_messages "
            "WHERE conversation_id = ? ORDER BY seq",
            (cid,),
        ).fetchall()
    return {
        **dict(row),
        "messages": [
            {"role": m["role"], "content": m["content"],
             "sources": json.loads(m["sources"]), "error": m["error"]}
            for m in msgs
        ],
    }


@router.put("/conversations/{cid}")
def save_conversation(cid: str, body: ConversationSave):
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        row = conn.execute("SELECT title FROM conversations WHERE id = ?", (cid,)).fetchone()
        # 한 번 정해진 제목은 유지 (명시적으로 넘기면 변경)
        title = body.title or (row["title"] if row else _auto_title(body))
        if row:
            conn.execute(
                "UPDATE conversations SET title = ?, model = ?, updated_at = ? WHERE id = ?",
                (title, body.model, now, cid),
            )
        else:
            conn.execute(
                "INSERT INTO conversations (id, title, model, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (cid, title, body.model, now, now),
            )
        conn.execute("DELETE FROM conversation_messages WHERE conversation_id = ?", (cid,))
        conn.executemany(
            "INSERT INTO conversation_messages (conversation_id, seq, role, content, sources, error) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (cid, i, m.role, m.content,
                 json.dumps([s.model_dump() for s in m.sources], ensure_ascii=False), m.error)
                for i, m in enumerate(body.messages)
            ],
        )
    return {"id": cid, "title": title, "model": body.model, "updated_at": now}


@router.delete("/conversations/{cid}", status_code=204)
def delete_conversation(cid: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM conversation_messages WHERE conversation_id = ?", (cid,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (cid,))
    return Response(status_code=204)
