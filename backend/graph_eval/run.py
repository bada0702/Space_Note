"""지식 그래프 추출 정확도 평가 — 정답 세트로 추출 모델을 채점해 보고서를 남긴다.

사용법 (backend 디렉터리에서):
  venv/bin/python -m graph_eval.run                         # 기본 추출 모델(Gemini), 2회
  venv/bin/python -m graph_eval.run --model gemini-3.1-flash --runs 3
  venv/bin/python -m graph_eval.run --model ollama:gemma4:e2b --cases SAMPLE_DOCKER
  venv/bin/python -m graph_eval.run --cases-dir /경로/정답세트   # 직접 만든 정답 세트

DB에는 아무것도 쓰지 않는다. 보고서는 graph_eval/reports/에 JSON과 Markdown으로 남는다.
"""
import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

from graph_eval import scoring
from services import graph_extraction as ge

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases"
OLLAMA_URL = os.getenv("SPACENOTE_EVAL_OLLAMA_URL", "http://127.0.0.1:11434")

LABELS = {
    "precision": "관계 정밀도",
    "recall": "관계 재현율",
    "f1": "F1",
    "pair_precision": "연결 정밀도",
    "pair_recall": "연결 재현율",
    "concept_recall": "개념 재현율",
    "kind_accuracy": "kind 정확도",
    "type_accuracy": "유형 정확도",
    "generic_rate": "'관련있다' 비율",
    "evidence_rate": "근거 문장 비율",
}


def load_cases(names: list[str] | None, cases_dir: Path = CASES) -> list[dict]:
    cases = []
    for path in sorted(cases_dir.glob("*.json")):
        if names and path.stem not in names:
            continue
        case = json.loads(path.read_text(encoding="utf-8"))
        case["id"] = path.stem
        case["text"] = (cases_dir / case["note"]).read_text(encoding="utf-8")
        cases.append(case)
    return cases


def validate(case: dict) -> list[str]:
    """정답 세트가 현재 추출 어휘를 벗어나면 그 관계·유형은 절대 맞힐 수 없으므로 미리 알린다."""
    problems = []
    known = case.get("known_concepts", [])
    if not isinstance(known, list) or not all(isinstance(k, str) for k in known):
        problems.append(f"{case['id']}: known_concepts는 문자열 목록이어야 함")
    kinds = {c["name"]: c.get("kind") for c in case["concepts"]}
    for c in case["concepts"]:
        if c.get("kind") and c["kind"] not in ge.KINDS:
            problems.append(f"{case['id']}: 개념 '{c['name']}'의 kind '{c['kind']}'이 어휘에 없음")
        for t in scoring._as_list(c.get("type")):
            if t not in (*ge.CONCEPT_TYPES, ge.LITERAL_TYPE):
                problems.append(f"{case['id']}: 개념 '{c['name']}'의 유형 '{t}'이 어휘에 없음")
    for r in case["relations"] + case.get("acceptable", []):
        if r["s"] not in kinds or r["o"] not in kinds:
            problems.append(f"{case['id']}: 관계 {r}의 개념이 concepts에 없음")
            continue
        for p in scoring._as_list(r["p"]):
            if kinds[r["o"]] == "literal":  # 데이터 속성은 이름이 자유롭지만 길이 제한이 있다
                if len(p) > ge.MAX_DATA_PROPERTY_CHARS:
                    problems.append(f"{case['id']}: 데이터 속성 '{p}'이 너무 김")
            elif p not in (*ge.STRUCT_PREDICATES, *ge.OBJECT_PREDICATES):
                problems.append(f"{case['id']}: 관계 '{p}'이 어휘에 없음")
    return problems


def model_fn(model: str):
    """모델 이름 → (호출 함수, 표시 이름). 설정 화면의 추출 모델과 상관없이 고른 모델을 직접 부른다."""
    if model.startswith("gemini"):
        name = ge.GRAPH_MODEL if model == "gemini" else model
        return (lambda content, known=(): ge._call_gemini(name, ge.build_prompt(content, known))), name
    if model.startswith("ollama:"):
        name = model.split(":", 1)[1]

        def call(content: str, known=()) -> str:
            resp = httpx.post(f"{OLLAMA_URL}/api/chat", timeout=900, json={
                "model": name,
                "messages": [{"role": "user", "content": ge.build_prompt(content, known)}],
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.1},
            })
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        return call, name
    raise SystemExit(f"알 수 없는 모델: {model} (gemini, gemini-<이름> 또는 ollama:<이름>)")


def run(cases: list[dict], call, runs: int) -> list[dict]:
    """runs × cases 결과. 응답을 JSON으로 읽지 못하면 빈 그래프로 채점하고 실패로 센다."""
    out = []
    for i in range(runs):
        for case in cases:
            started = time.monotonic()
            error = None
            try:
                graph = ge.parse_graph(call(case["text"], case.get("known_concepts", [])), case["text"])
            except Exception as e:  # 모델 오류도 평가 결과의 일부로 남긴다
                error = f"{type(e).__name__}: {e}"[:300]
                graph = {"concepts": [], "relations": []}
            res = scoring.score_case(case, graph)
            res.update(run=i + 1, case=case["id"], seconds=round(time.monotonic() - started, 1), error=error)
            out.append(res)
            m = scoring.metrics(res)
            print(f"[{i + 1}/{runs}] {case['id']}: 관계 {res['predicted']}개, 정밀도 {_pct(m['precision'])}, "
                  f"재현율 {_pct(m['recall'])}, {res['seconds']}초" + (f", 오류 {error}" if error else ""),
                  file=sys.stderr, flush=True)
    return out


def summarize(results: list[dict], runs: int) -> dict:
    per_run = [scoring.metrics(scoring.total([r for r in results if r["run"] == i + 1])) for i in range(runs)]
    summary = {}
    for key in LABELS:
        vals = [m[key] for m in per_run if m[key] is not None]
        summary[key] = {"mean": statistics.mean(vals), "min": min(vals), "max": max(vals)} if vals else None
    by_case = {}
    for cid in dict.fromkeys(r["case"] for r in results):
        by_case[cid] = scoring.metrics(scoring.total([r for r in results if r["case"] == cid]))
    return {"overall": summary, "by_case": by_case, "per_run": per_run}


def _pct(v) -> str:
    return "-" if v is None else f"{v * 100:.0f}%"


def _rel(r: dict) -> str:
    return f"{r['s']} –{'|'.join(scoring._as_list(r['p']))}→ {r['o']}"


def markdown(meta: dict, summary: dict, results: list[dict]) -> str:
    lines = [
        f"# 지식 그래프 추출 정확도 — {meta['model']}",
        "",
        f"- 실행: {meta['started']} · 사례 {len(meta['cases'])}개 × {meta['runs']}회 · 정답 세트 상태: {meta['gold_status']}",
        f"- 모델 오류(응답 파싱 실패 포함): {meta['errors']}건",
        "",
        "## 전체 (관계 단위 합산, 실행별 평균과 범위)",
        "",
        "| 지표 | 평균 | 최저 | 최고 |",
        "|---|---|---|---|",
    ]
    for key, label in LABELS.items():
        s = summary["overall"][key]
        lines.append(f"| {label} | {_pct(s and s['mean'])} | {_pct(s and s['min'])} | {_pct(s and s['max'])} |")
    lines += ["", "## 사례별 (모든 실행 합산)", "",
              "| 사례 | 정밀도 | 재현율 | F1 | 연결 재현율 | kind 정확도 | 유형 정확도 | '관련있다' |",
              "|---|---|---|---|---|---|---|---|"]
    for cid, m in summary["by_case"].items():
        lines.append(f"| {cid} | {_pct(m['precision'])} | {_pct(m['recall'])} | {_pct(m['f1'])} | "
                     f"{_pct(m['pair_recall'])} | {_pct(m['kind_accuracy'])} | {_pct(m['type_accuracy'])} | "
                     f"{_pct(m['generic_rate'])} |")
    lines += ["", "## 지표 정의", "",
              "- 관계 정밀도: 추출한 관계 중 정답(필수+허용)과 주어·관계·목적어·방향이 모두 맞은 비율",
              "- 관계 재현율: 필수 정답 관계 중 맞힌 비율 (실행마다 따로 계산)",
              "- 연결 정밀도·재현율: 관계 이름과 방향은 보지 않고 두 개념이 이어졌는지만 본 값",
              "- kind 정확도: 정답 개념과 대응된 추출 개념 중 class/instance/literal 구분이 맞은 비율",
              "- 유형 정확도: 정답 개념과 대응된 추출 개념 중 유형이 정답이거나 그 하위 유형인 비율",
              "- 정답 세트에 없는 관계는 틀린 것으로 센다. 실제로 맞는데 빠진 관계는 아래 '검토 대상'에서 골라 정답 세트에 추가한다.",
              "", "## 검토 대상", ""]
    for cid in summary["by_case"]:
        rs = [r for r in results if r["case"] == cid]
        missed: dict[str, int] = {}
        for r in rs:
            for g in r["missed"]:
                missed[_rel(g)] = missed.get(_rel(g), 0) + 1
        wrong: dict[str, dict] = {}
        for r in rs:
            for w in r["unmatched"]:
                k = _rel(w)
                e = wrong.setdefault(k, {"n": 0, "known": w["known"], "evidence": w["evidence"]})
                e["n"] += 1
                e["evidence"] = e["evidence"] or w["evidence"]
        lines += [f"### {cid}", "", f"놓친 필수 관계 ({len(rs)}회 중 놓친 횟수):"]
        lines += [f"- {k} ({n}회)" for k, n in sorted(missed.items(), key=lambda x: -x[1])] or ["- 없음"]
        lines += ["", "정답에 없는 추출 관계 (맞으면 정답 세트에 추가):"]
        for k, e in sorted(wrong.items(), key=lambda x: -x[1]["n"]):
            tag = "" if e["known"] else " [정답 세트에 없는 개념]"
            ev = f" — 근거: \"{e['evidence'][:80]}\"" if e["evidence"] else ""
            lines.append(f"- {k} ({e['n']}회){tag}{ev}")
        if not wrong:
            lines.append("- 없음")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="gemini", help="gemini 또는 ollama:<모델 이름>")
    ap.add_argument("--runs", type=int, default=2, help="모델 출력이 매번 달라서 여러 번 돌려 범위를 본다")
    ap.add_argument("--cases", nargs="*", help="일부 사례만 (파일 이름, 확장자 제외)")
    ap.add_argument("--cases-dir", type=Path, default=CASES, help="정답 세트 디렉터리")
    ap.add_argument("--out", type=Path, default=HERE / "reports")
    args = ap.parse_args(argv)

    cases = load_cases(args.cases, args.cases_dir)
    if not cases:
        raise SystemExit("평가할 사례가 없습니다")
    problems = [p for c in cases for p in validate(c)]
    if problems:
        raise SystemExit("정답 세트 오류:\n" + "\n".join(problems))
    call, model_name = model_fn(args.model)
    started = datetime.now()
    results = run(cases, call, args.runs)
    summary = summarize(results, args.runs)
    meta = {
        "model": f"{args.model} ({model_name})" if args.model == "gemini" else args.model,
        "started": started.isoformat(timespec="seconds"),
        "runs": args.runs,
        "cases": [c["id"] for c in cases],
        "gold_status": ", ".join(sorted({c.get("status", "?") for c in cases})),
        "ontology": str(ge.ONTOLOGY_PATH),
        "errors": sum(bool(r["error"]) for r in results),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    stem = f"{started:%Y%m%d-%H%M%S}-{args.model.replace(':', '_').replace('/', '_')}"
    (args.out / f"{stem}.json").write_text(
        json.dumps({"meta": meta, "summary": summary, "results": results}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    md = markdown(meta, summary, results)
    (args.out / f"{stem}.md").write_text(md, encoding="utf-8")
    print(md.split("## 사례별")[0])
    print(f"보고서: {args.out / stem}.md")


if __name__ == "__main__":
    main()
