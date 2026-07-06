import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response

from db import get_conn
from models import CategoryCreate, CategoryPatch

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/categories")
def list_categories():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM categories ORDER BY sort_order, created_at"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/categories")
def create_category(body: CategoryCreate):
    cid = str(uuid.uuid4())
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO categories (id, name, color, sort_order, created_at) "
            "VALUES (?, ?, ?, 0, ?)",
            (cid, body.name, body.color, now),
        )
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone()
    return dict(row)


@router.patch("/categories/{cid}")
def update_category(cid: str, body: CategoryPatch):
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="category not found")
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE categories SET {sets} WHERE id = ?",
                (*fields.values(), cid),
            )
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone()
    return dict(row)


@router.delete("/categories/{cid}", status_code=204)
def delete_category(cid: str):
    with get_conn() as conn:
        conn.execute("UPDATE notes SET category_id = NULL WHERE category_id = ?", (cid,))
        conn.execute("DELETE FROM categories WHERE id = ?", (cid,))
    return Response(status_code=204)
