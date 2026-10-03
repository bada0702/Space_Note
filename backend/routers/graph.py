"""지식 그래프 관리 API — 일괄 분석 시작, 실패 재시도, 진행 상황."""
from fastapi import APIRouter

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
