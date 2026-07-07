import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response

from db import get_conn
from models import RouteCreate

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ordered(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


@router.post("/routes")
def confirm_route(body: RouteCreate):
    """미개척 항로를 확정 항로로 승격. 쌍은 note_a < note_b로 정규화 저장."""
    if body.note_a == body.note_b:
        raise HTTPException(status_code=400, detail="same note")
    a, b = _ordered(body.note_a, body.note_b)
    with get_conn() as conn:
        for nid in (a, b):
            if conn.execute("SELECT 1 FROM notes WHERE id = ?", (nid,)).fetchone() is None:
                raise HTTPException(status_code=404, detail="note not found")
        conn.execute(
            "INSERT OR IGNORE INTO routes (id, note_a, note_b, created_at) "
            "VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), a, b, _now()),
        )
    return {"note_a": a, "note_b": b, "confirmed": True}


@router.delete("/routes", status_code=204)
def unconfirm_route(note_a: str, note_b: str):
    a, b = _ordered(note_a, note_b)
    with get_conn() as conn:
        conn.execute("DELETE FROM routes WHERE note_a = ? AND note_b = ?", (a, b))
    return Response(status_code=204)
