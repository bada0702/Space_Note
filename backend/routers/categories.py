from fastapi import APIRouter

router = APIRouter()


@router.get("/categories")
def list_categories():
    from db import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM categories ORDER BY sort_order, created_at"
        ).fetchall()
    return [dict(r) for r in rows]
