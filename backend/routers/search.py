from typing import Optional

from fastapi import APIRouter

from db import get_conn

router = APIRouter()


@router.get("/search")
def search(q: str = ""):
    term = (q or "").strip()
    if not term:
        return []
    like = f"%{term}%"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, content, category_id, modified_at FROM notes "
            "WHERE title LIKE ? OR content LIKE ? ORDER BY modified_at DESC LIMIT 50",
            (like, like),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "content_preview": (r["content"] or "")[:200],
            "category_id": r["category_id"],
            "modified_at": r["modified_at"],
        }
        for r in rows
    ]


@router.get("/discoveries")
def discoveries(note_id: Optional[str] = None):
    """엔티티를 공유하는 노트들을 발견(discovery)으로 반환.

    note_id가 주어지면 해당 노트와 엔티티를 공유하는 다른 노트들을,
    없으면 엔티티가 추출된 모든 노트를 엔티티 수 기준으로 반환한다.
    """
    with get_conn() as conn:
        if note_id:
            # 표기 차이를 흡수한 정규화 키(norm)로 매칭
            mine = conn.execute(
                "SELECT DISTINCT norm FROM entities WHERE note_id = ?", (note_id,)
            ).fetchall()
            norms = [r["norm"] for r in mine if r["norm"]]
            if not norms:
                return []
            placeholders = ",".join("?" for _ in norms)
            rows = conn.execute(
                f"SELECT e.note_id AS note_id, e.name AS name, e.norm AS norm, "
                f"n.title AS title, "
                f"n.category_id AS category_id, n.modified_at AS modified_at "
                f"FROM entities e JOIN notes n ON n.id = e.note_id "
                f"WHERE e.norm IN ({placeholders}) AND e.note_id != ?",
                (*norms, note_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT e.note_id AS note_id, e.name AS name, e.norm AS norm, "
                "n.title AS title, "
                "n.category_id AS category_id, n.modified_at AS modified_at "
                "FROM entities e JOIN notes n ON n.id = e.note_id"
            ).fetchall()

    agg: dict[str, dict] = {}
    for r in rows:
        d = agg.setdefault(
            r["note_id"],
            {
                "note_id": r["note_id"],
                "title": r["title"],
                "category_id": r["category_id"],
                "modified_at": r["modified_at"],
                "_entities": {},
            },
        )
        # 같은 norm은 하나로 취급, 표시는 최초 등장 이름으로
        d["_entities"].setdefault(r["norm"], r["name"])

    out = []
    for d in agg.values():
        ents = sorted(d["_entities"].values())
        out.append(
            {
                "note_id": d["note_id"],
                "title": d["title"],
                "category_id": d["category_id"],
                "shared_count": len(ents),
                "shared_entities": ents,
                "modified_at": d["modified_at"],
            }
        )
    out.sort(key=lambda x: (x["shared_count"], x["modified_at"]), reverse=True)
    return out


@router.get("/entities/{note_id}")
def entities(note_id: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM entities WHERE note_id = ? ORDER BY created_at",
            (note_id,),
        ).fetchall()
    return [dict(r) for r in rows]
