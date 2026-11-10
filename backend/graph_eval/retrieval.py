"""AI 채팅 검색 평가 — 질문마다 정답 노트가 상위 5개 안에 드는지(적중률@5)와 MRR을 낸다.

사용법 (backend 디렉터리에서):
  venv/bin/python -m graph_eval.retrieval      # local/questions.json

질문 파일 형식: [{"q": "질문", "answers": ["노트 id", ...]}]
DB에는 아무것도 쓰지 않는다. 실제 노트에서 만든 질문은 local/(git 제외)에만 둔다.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from graph_eval.audit import open_ro

HERE = Path(__file__).resolve().parent


def load_questions(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate(conn, questions: list[dict]) -> dict:
    from routers.ai import _retrieve_notes

    active = {r[0] for r in conn.execute("SELECT id FROM notes WHERE is_archived = 0")}
    rows, missing, hits, rr = [], 0, 0, 0.0
    for item in questions:
        answers = [a for a in item["answers"] if a in active]
        missing += len(item["answers"]) - len(answers)
        top = [n["id"] for n in _retrieve_notes(conn, item["q"], None, None, fallback_recent=False)]
        ranks = [top.index(a) + 1 if a in top else None for a in answers]
        rows.append({"q": item["q"], "ranks": ranks, "top": top})
        if not answers:  # 정답 노트가 모두 사라진 질문은 채점하지 않는다
            continue
        found = [r for r in ranks if r is not None]
        hits += bool(found)
        rr += 1 / min(found) if found else 0.0
    scored = sum(bool(r["ranks"]) for r in rows)
    return {"hit_at_5": hits / scored if scored else None, "mrr": rr / scored if scored else None,
            "missing_answers": missing, "rows": rows}


def _pct(v) -> str:
    return "-" if v is None else f"{v * 100:.1f}%"


def markdown(result: dict, started: str) -> str:
    lines = [f"# AI 채팅 검색 평가 — {started}", "",
             f"- 적중률@5: {_pct(result['hit_at_5'])}", f"- MRR: {_pct(result['mrr'])}",
             f"- 사라진 정답 노트: {result['missing_answers']}개", "", "| 질문 | 정답 순위 |", "|---|---|"]
    for r in result["rows"]:
        ranks = ", ".join("-" if x is None else str(x) for x in r["ranks"]) or "(정답 없음)"
        lines.append(f"| {r['q']} | {ranks} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="DB 경로 (기본: 설정의 DB_PATH)")
    ap.add_argument("--questions", type=Path, default=HERE / "local" / "questions.json")
    ap.add_argument("--out", type=Path, default=HERE / "reports")
    args = ap.parse_args(argv)
    conn = open_ro(args.db)
    try:
        result = evaluate(conn, load_questions(args.questions))
    finally:
        conn.close()
    started = datetime.now()
    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"{started:%Y%m%d-%H%M%S}-retrieval"
    stem.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    md = markdown(result, started.isoformat(timespec="seconds"))
    stem.with_suffix(".md").write_text(md, encoding="utf-8")
    print(md.split("| 질문")[0])
    print(f"보고서: {stem}.md")


if __name__ == "__main__":
    main()
