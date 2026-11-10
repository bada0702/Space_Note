"""운영 DB 진단 — 지식 그래프와 항로의 구조 지표를 읽기 전용으로 집계한다.

사용법 (backend 디렉터리에서):
  venv/bin/python -m graph_eval.audit             # 설정의 DB_PATH
  venv/bin/python -m graph_eval.audit --db 경로

DB에는 아무것도 쓰지 않는다. 보고서는 graph_eval/reports/에 JSON과 Markdown으로 남는다.
"""
import argparse
import json
import sqlite3
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

from config import settings
from services.textnorm import norm_name

HERE = Path(__file__).resolve().parent
LONG_NOTE_CHARS = 40_000  # graph_extraction.MAX_INPUT_CHARS와 같은 기준


def open_ro(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path or settings.DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _one(conn, sql: str, *params):
    return conn.execute(sql, params).fetchone()[0]


def _ratio(a, b) -> float | None:
    return a / b if b else None


def _tail_concepts(conn) -> int:
    """긴 노트에서 이름·동의어가 앞 40,000자에는 없고 그 뒤에만 나오는 개념 수."""
    long_notes = conn.execute(
        "SELECT id, content FROM notes WHERE is_archived = 0 AND length(content) > ?", (LONG_NOTE_CHARS,)
    ).fetchall()
    count = 0
    for note in long_notes:
        head = norm_name(note["content"][:LONG_NOTE_CHARS])
        tail = norm_name(note["content"][LONG_NOTE_CHARS:])
        rows = conn.execute(
            "SELECT c.id, c.norm, a.norm AS alias FROM note_concepts nc JOIN concepts c ON c.id = nc.concept_id "
            "LEFT JOIN concept_aliases a ON a.concept_id = c.id "
            "WHERE nc.note_id = ? AND c.kind != 'literal'",
            (note["id"],),
        ).fetchall()
        names: dict[str, set[str]] = {}
        for r in rows:
            names.setdefault(r["id"], {r["norm"]}).add(r["alias"] or r["norm"])
        for forms in names.values():
            if not any(f in head for f in forms) and any(f in tail for f in forms):
                count += 1
    return count


def _struct_violations(conn, pred: str, rule: str) -> int:
    return _one(
        conn,
        "SELECT COUNT(*) FROM relations r JOIN concepts cs ON cs.id = r.subj_id "
        f"JOIN concepts co ON co.id = r.obj_id WHERE r.pred = ? AND NOT ({rule})",
        pred,
    )


def audit(conn) -> dict:
    from routers.search import _PairEvidence, ranked_routes

    concepts = conn.execute(
        "SELECT c.name, COUNT(nc.note_id) AS n FROM concepts c JOIN note_concepts nc ON nc.concept_id = c.id "
        "WHERE c.kind != 'literal' GROUP BY c.id"
    ).fetchall()
    rel_total, rel_evidence = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(evidence IS NOT NULL AND evidence != ''), 0) FROM relations"
    ).fetchone()
    obj_total, obj_generic = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(r.pred = '관련있다'), 0) FROM relations r "
        "JOIN concepts co ON co.id = r.obj_id WHERE co.kind != 'literal'"
    ).fetchone()

    ev = _PairEvidence(conn)
    rejected = {(r[0], r[1]) for r in conn.execute("SELECT note_a, note_b FROM routes WHERE status = 'rejected'")}
    lines: set[tuple[str, str]] = set()
    for keys in ranked_routes(ev, rejected).values():
        lines.update(keys)
    degree: Counter = Counter()
    for a, b in lines:
        degree[a] += 1
        degree[b] += 1
    active = _one(conn, "SELECT COUNT(*) FROM notes WHERE is_archived = 0")
    scores = sorted(ev.score(k) for k in lines)

    return {
        "notes_active": active,
        "graph_status": dict(conn.execute(
            "SELECT graph_status, COUNT(*) FROM notes WHERE is_archived = 0 GROUP BY 1").fetchall()),
        "relations": rel_total,
        "evidence_rate": _ratio(rel_evidence, rel_total),
        "generic_rate": _ratio(obj_generic, obj_total),
        "concepts": len(concepts),
        "singleton_rate": _ratio(sum(r["n"] == 1 for r in concepts), len(concepts)),
        "long_name_rate": _ratio(sum(len(r["name"].split()) >= 3 for r in concepts), len(concepts)),
        "kind_violations": {
            "인스턴스이다": _struct_violations(conn, "인스턴스이다", "cs.kind = 'instance' AND co.kind = 'class'"),
            "하위클래스이다": _struct_violations(conn, "하위클래스이다", "cs.kind = 'class' AND co.kind = 'class'"),
        },
        "long_notes": _one(conn, "SELECT COUNT(*) FROM notes WHERE is_archived = 0 AND length(content) > ?",
                           LONG_NOTE_CHARS),
        "tail_concepts": _tail_concepts(conn),
        "pairs": len(ev.keys()),
        "lines": len(lines),
        "line_kinds": dict(Counter(ev.kind(k) for k in lines)),
        "max_degree": max(degree.values(), default=0),
        "notes_without_lines": active - len(degree),
        "hubs": len(ev.hubs),
        "line_score_p25": statistics.quantiles(scores, n=4)[0] if len(scores) >= 2 else None,
    }


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.3f}"
    if isinstance(v, dict):
        return ", ".join(f"{k} {_fmt(x)}" for k, x in v.items())
    return "-" if v is None else str(v)


def markdown(result: dict, started: str) -> str:
    lines = [f"# 지식 그래프 DB 진단 — {started}", "", "| 항목 | 값 |", "|---|---|"]
    lines += [f"| {k} | {_fmt(v)} |" for k, v in result.items()]
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="DB 경로 (기본: 설정의 DB_PATH)")
    ap.add_argument("--out", type=Path, default=HERE / "reports")
    args = ap.parse_args(argv)
    conn = open_ro(args.db)
    try:
        result = audit(conn)
    finally:
        conn.close()
    started = datetime.now()
    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"{started:%Y%m%d-%H%M%S}-audit"
    stem.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    md = markdown(result, started.isoformat(timespec="seconds"))
    stem.with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)
    print(f"보고서: {stem}.md")


if __name__ == "__main__":
    main()
