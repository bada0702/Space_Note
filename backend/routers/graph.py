"""지식 그래프 관리 API — 일괄 분석 시작, 실패 재시도, 진행 상황."""
from fastapi import APIRouter, HTTPException

from db import get_conn
from services import graph_worker

router = APIRouter()

_STATUSES = ("idle", "pending", "done", "failed")


def _counts(conn) -> dict:
    counts = {s: 0 for s in _STATUSES}
    for r in conn.execute(
        "SELECT graph_status, COUNT(*) AS n FROM notes WHERE is_archived = 0 GROUP BY graph_status"
    ):
        if r["graph_status"] in counts:
            counts[r["graph_status"]] = r["n"]
    return counts


@router.get("/graph/status")
def graph_status():
    with get_conn() as conn:
        counts = _counts(conn)
        concepts = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
        relations = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
    remaining = counts["pending"]
    return {
        **counts,
        "total": sum(counts.values()),
        "concepts": concepts,
        "relations": relations,
        "rate_per_minute": graph_worker.RATE_PER_MINUTE,
        "eta_minutes": -(-remaining // graph_worker.RATE_PER_MINUTE),  # 올림
    }


@router.post("/graph/rebuild")
def graph_rebuild():
    """보관되지 않은 모든 노트를 다시 분석 대기열에 넣는다 (해시를 지워 강제 재추출)."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE notes SET graph_status = 'pending', graph_hash = NULL WHERE is_archived = 0"
        )
        counts = _counts(conn)
    graph_worker.start()
    return counts


@router.post("/graph/retry-failed")
def graph_retry_failed():
    with get_conn() as conn:
        conn.execute(
            "UPDATE notes SET graph_status = 'pending' WHERE graph_status = 'failed' AND is_archived = 0"
        )
        counts = _counts(conn)
    graph_worker.start()
    return counts


# ── 별자리: 여러 노트에 걸친 지식 그래프 개념 ──────────────────

CONSTELLATION_MIN_NOTES = 3


@router.get("/constellations")
def constellations(limit: int = 100):
    """노트 CONSTELLATION_MIN_NOTES개 이상이 공유하는 개념을 노트 수 내림차순으로."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT c.id, c.name, c.type, COUNT(DISTINCT n.id) AS note_count, "
            "COUNT(DISTINCT n.category_id) AS galaxy_count "
            "FROM concepts c "
            "JOIN note_concepts nc ON nc.concept_id = c.id "
            "JOIN notes n ON n.id = nc.note_id AND n.is_archived = 0 "
            "GROUP BY c.id HAVING note_count >= ? "
            "ORDER BY note_count DESC, c.name LIMIT ?",
            (CONSTELLATION_MIN_NOTES, limit),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/constellations/{cid}/notes")
def constellation_notes(cid: str):
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM concepts WHERE id = ?", (cid,)).fetchone():
            raise HTTPException(status_code=404, detail="constellation not found")
        rows = conn.execute(
            "SELECT n.id, n.title, n.category_id, n.modified_at "
            "FROM note_concepts nc JOIN notes n ON n.id = nc.note_id "
            "WHERE nc.concept_id = ? AND n.is_archived = 0 "
            "ORDER BY nc.weight DESC, n.modified_at DESC",
            (cid,),
        ).fetchall()
    return [dict(r) for r in rows]
