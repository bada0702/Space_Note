"""지식 그래프 관리 API — 일괄 분석 시작, 실패 재시도, 진행 상황."""
from fastapi import APIRouter, BackgroundTasks, HTTPException

from db import get_conn
from services import graph_extraction, graph_worker

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
        failures = [
            dict(r) for r in conn.execute(
                "SELECT id, title, graph_error AS error FROM notes "
                "WHERE graph_status = 'failed' AND is_archived = 0 ORDER BY modified_at DESC LIMIT 20"
            )
        ]
    remaining = counts["pending"]
    return {
        **counts,
        "total": sum(counts.values()),
        "concepts": concepts,
        "relations": relations,
        "failures": failures,
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


@router.post("/graph/cancel")
def graph_cancel():
    """대기 중인 분석을 모두 취소한다 (미분석으로 되돌림). 지금 모델 응답을 기다리는 노트는 결과를 버린다."""
    with get_conn() as conn:
        cancelled = conn.execute(
            "UPDATE notes SET graph_status = 'idle' WHERE graph_status = 'pending' AND is_archived = 0"
        ).rowcount
    return {"cancelled": cancelled}


@router.post("/graph/analyze")
def graph_analyze_missing():
    """아직 그래프가 없거나(idle) 실패한 노트만 대기열에 넣는다 — 다 된 노트는 다시 부르지 않는다."""
    reason = graph_extraction.model_ready()
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    with get_conn() as conn:
        queued = conn.execute(
            "UPDATE notes SET graph_status = 'pending' "
            "WHERE graph_status IN ('idle', 'failed') AND is_archived = 0"
        ).rowcount
    graph_worker.start()
    return {"queued": queued}


@router.post("/graph/notes/{note_id}")
def graph_analyze_note(note_id: str, bg: BackgroundTasks):
    """노트 하나를 작업자의 대기 시간·속도 제한 없이 바로 추출한다 (항로 분석 버튼용)."""
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM notes WHERE id = ?", (note_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Note not found")
    reason = graph_extraction.model_ready()
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    with get_conn() as conn:
        conn.execute("UPDATE notes SET graph_status = 'pending' WHERE id = ?", (note_id,))
    bg.add_task(graph_extraction.process_note, note_id)
    return {"queued": 1}


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


CONSTELLATION_GRAPH_MAX_NODES = 24
# literal(값)은 노트마다 따로 있는 노드라 관계도에서 뺀다
_GRAPH_RELATIONS = (
    "SELECT r.subj_id AS s, r.pred AS p, r.obj_id AS o, r.evidence, n.id AS note_id, n.title AS note_title "
    "FROM relations r JOIN notes n ON n.id = r.note_id AND n.is_archived = 0 "
    "JOIN concepts cs ON cs.id = r.subj_id AND cs.kind != 'literal' "
    "JOIN concepts co ON co.id = r.obj_id AND co.kind != 'literal' "
)


@router.get("/constellations/{cid}/graph")
def constellation_graph(cid: str):
    """별자리 개념, 관계로 이어진 이웃 개념, 그 사이의 관계(근거 문장 포함)."""
    with get_conn() as conn:
        center = conn.execute("SELECT id, name, type FROM concepts WHERE id = ?", (cid,)).fetchone()
        if not center:
            raise HTTPException(status_code=404, detail="constellation not found")
        rels = conn.execute(
            _GRAPH_RELATIONS + "WHERE r.subj_id = ? OR r.obj_id = ? ORDER BY n.modified_at DESC",
            (cid, cid),
        ).fetchall()
        degree: dict[str, int] = {}
        for r in rels:
            other = r["o"] if r["s"] == cid else r["s"]
            degree[other] = degree.get(other, 0) + 1
        ids = [cid, *sorted(degree, key=lambda k: -degree[k])[:CONSTELLATION_GRAPH_MAX_NODES]]
        marks = ",".join("?" * len(ids))
        nodes = conn.execute(f"SELECT id, name, type FROM concepts WHERE id IN ({marks})", ids).fetchall()
        rels += conn.execute(
            _GRAPH_RELATIONS + f"WHERE r.subj_id IN ({marks}) AND r.obj_id IN ({marks}) "
            "AND r.subj_id != ? AND r.obj_id != ? ORDER BY n.modified_at DESC",
            (*ids, *ids, cid, cid),
        ).fetchall()
    kept = set(ids)
    edges: dict[tuple, dict] = {}
    for r in rels:
        if r["s"] not in kept or r["o"] not in kept:
            continue
        e = edges.setdefault((r["s"], r["p"], r["o"]), {
            "source": r["s"], "pred": r["p"], "target": r["o"], "evidence": None, "notes": [],
        })
        e["evidence"] = e["evidence"] or r["evidence"]
        if all(n["id"] != r["note_id"] for n in e["notes"]):
            e["notes"].append({"id": r["note_id"], "title": r["note_title"]})
    return {"center": dict(center), "nodes": [dict(n) for n in nodes], "edges": list(edges.values())}
