"""성도 연결선 평가 — 표본 노트의 상위 항로가 납득되는 연결인지 판정해 정밀도@5를 낸다.

사용법 (backend 디렉터리에서):
  venv/bin/python -m graph_eval.links export     # 판정 안 된 쌍을 local/links_labels.csv에 추가
  venv/bin/python -m graph_eval.links score      # 판정 결과로 정밀도 보고서 작성
  venv/bin/python -m graph_eval.links score --hub-share 0.1 --min-score 5

표본(local/links_sample.json)은 처음 실행할 때 고정 시드로 뽑아 저장하고 이후 재사용한다.
판정 파일의 label 열: 1 = 관련 있음, 0 = 무관, 빈칸 = 미판정.
DB에는 아무것도 쓰지 않는다. 실제 노트에서 나온 표본·판정은 local/(git 제외)에만 둔다.
"""
import argparse
import csv
import json
import random
from datetime import datetime
from pathlib import Path

from graph_eval.audit import open_ro

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "local"
TUNE_SIZE = 20  # 표본 앞 20개는 파라미터 조정용, 나머지는 과적합 확인용
FIELDS = ["note_a", "note_b", "title_a", "title_b", "kind", "evidence", "label", "comment"]


def sample_notes(conn, n: int = 30, seed: int = 20261110) -> list[str]:
    ids = sorted(r[0] for r in conn.execute("SELECT id FROM notes WHERE is_archived = 0"))
    return random.Random(seed).sample(ids, min(n, len(ids)))


def top_routes(conn) -> dict[str, list[dict]]:
    """노트 id → 그 노트의 상위 항로 [{other, score, kind, evidence}] (성도와 같은 순위)."""
    from routers.search import _PairEvidence, ranked_routes

    ev = _PairEvidence(conn)
    rejected = {(r[0], r[1]) for r in conn.execute("SELECT note_a, note_b FROM routes WHERE status = 'rejected'")}
    out: dict[str, list[dict]] = {}
    for note_id, keys in ranked_routes(ev, rejected).items():
        rows = []
        for k in keys:
            f = ev.fields(k)
            evidence = "; ".join([*f["shared_concepts"], *f["relations"], *f["shared_entities"]])
            rows.append({"other": k[1] if k[0] == note_id else k[0], "score": ev.score(k),
                         "kind": f["kind"], "evidence": evidence})
        out[note_id] = rows
    return out


def _read_labels(path: Path) -> dict[tuple[str, str], str]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {(r["note_a"], r["note_b"]): (r["label"] or "").strip() for r in csv.DictReader(f)}


def _titles(conn) -> dict[str, str]:
    return {r[0]: r[1] for r in conn.execute("SELECT id, title FROM notes WHERE is_archived = 0")}


def export_unlabeled(conn, labels: Path, sample: list[str]) -> int:
    """표본 노트의 상위 항로 중 판정 파일에 없는 쌍을 추가하고, 추가한 행 수를 돌려준다."""
    known = _read_labels(labels)
    titles = _titles(conn)
    routes = top_routes(conn)
    new_rows = []
    for note_id in sample:
        for r in routes.get(note_id, []):
            a, b = sorted((note_id, r["other"]))
            if (a, b) in known:
                continue
            known[(a, b)] = ""
            new_rows.append({"note_a": a, "note_b": b, "title_a": titles.get(a, ""), "title_b": titles.get(b, ""),
                             "kind": r["kind"], "evidence": r["evidence"], "label": "", "comment": ""})
    if not new_rows:
        return 0
    labels.parent.mkdir(parents=True, exist_ok=True)
    first = not labels.exists()
    # 새 파일만 BOM(utf-8-sig)으로 시작한다 — 이어 쓸 때 BOM이 중간에 끼면 안 된다
    with labels.open("w" if first else "a", encoding="utf-8-sig" if first else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if first:
            w.writeheader()
        w.writerows(new_rows)
    return len(new_rows)


def _part(note_ids: list[str], routes: dict, known: dict) -> dict:
    judged = positive = unlabeled = without = 0
    for note_id in note_ids:
        rows = routes.get(note_id, [])
        if not rows:
            without += 1
        for r in rows:
            label = known.get(tuple(sorted((note_id, r["other"]))), "")
            if label in ("0", "1"):
                judged += 1
                positive += label == "1"
            else:
                unlabeled += 1
    return {"precision": positive / judged if judged else None, "judged": judged,
            "unlabeled": unlabeled, "notes_without_lines": without}


def score(conn, labels: Path, sample: list[str]) -> dict:
    active = set(_titles(conn))
    present = [n for n in sample if n in active]
    routes = top_routes(conn)
    known = _read_labels(labels)
    tune = [n for n in sample[:TUNE_SIZE] if n in active]
    holdout = [n for n in sample[TUNE_SIZE:] if n in active]
    return {"tune": _part(tune, routes, known), "holdout": _part(holdout, routes, known),
            "all": _part(present, routes, known), "missing_notes": len(sample) - len(present)}


def _load_sample(conn, path: Path) -> list[str]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    sample = sample_notes(conn)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sample, ensure_ascii=False, indent=1), encoding="utf-8")
    return sample


def _pct(v) -> str:
    return "-" if v is None else f"{v * 100:.1f}%"


def markdown(result: dict, meta: dict) -> str:
    lines = [f"# 성도 연결선 평가 — {meta['started']}", "", f"- 파라미터: {meta['params']}",
             f"- 표본에서 사라진 노트: {result['missing_notes']}개", "",
             "| 구분 | 정밀도@5 | 판정 | 미판정 | 선 없는 노트 |", "|---|---|---|---|---|"]
    for key, label in (("tune", "조정용"), ("holdout", "확인용"), ("all", "전체")):
        p = result[key]
        lines.append(f"| {label} | {_pct(p['precision'])} | {p['judged']} | {p['unlabeled']} | "
                     f"{p['notes_without_lines']} |")
    if result["all"]["unlabeled"]:
        lines += ["", "미판정 쌍이 남아 있다 — export 후 판정을 채운 다음 다시 실행한다."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["export", "score"])
    ap.add_argument("--db", help="DB 경로 (기본: 설정의 DB_PATH)")
    ap.add_argument("--hub-share", type=float, help="routers.search._HUB_SHARE를 이번 실행에서만 바꾼다")
    ap.add_argument("--min-score", type=float, help="routers.search._MIN_ROUTE_SCORE를 이번 실행에서만 바꾼다")
    ap.add_argument("--labels", type=Path, default=LOCAL / "links_labels.csv")
    ap.add_argument("--sample", type=Path, default=LOCAL / "links_sample.json")
    ap.add_argument("--out", type=Path, default=HERE / "reports")
    args = ap.parse_args(argv)

    from routers import search
    if args.hub_share is not None:
        search._HUB_SHARE = args.hub_share
    if args.min_score is not None:
        search._MIN_ROUTE_SCORE = args.min_score
    params = {"hub_share": search._HUB_SHARE, "min_score": search._MIN_ROUTE_SCORE}

    conn = open_ro(args.db)
    try:
        sample = _load_sample(conn, args.sample)
        if args.command == "export":
            print(f"판정할 쌍 {export_unlabeled(conn, args.labels, sample)}개 추가: {args.labels}")
            return
        result = score(conn, args.labels, sample)
    finally:
        conn.close()
    started = datetime.now()
    meta = {"started": started.isoformat(timespec="seconds"), "params": params}
    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"{started:%Y%m%d-%H%M%S}-links"
    stem.with_suffix(".json").write_text(json.dumps({"meta": meta, "result": result}, ensure_ascii=False,
                                                    indent=1), encoding="utf-8")
    md = markdown(result, meta)
    stem.with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)
    print(f"보고서: {stem}.md")


if __name__ == "__main__":
    main()
