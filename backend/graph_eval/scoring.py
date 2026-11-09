"""정답 세트 대비 지식 그래프 추출 결과 채점.

정답 파일(cases/<이름>.json) 형식:
  concepts:   [{name, kind?, type?, aliases?}] — kind는 class|instance|literal,
                                                  type은 문자열 또는 허용 유형 목록 (하위 유형도 정답)
  relations:  [{s, p, o}]                     — 반드시 뽑아야 하는 관계 (재현율의 분모)
  acceptable: [{s, p, o}]                     — 뽑지 않아도 되지만 뽑으면 맞은 것으로 치는 관계
p는 문자열 또는 허용 관계 목록이고, s·o는 정답 개념 이름이다.
o가 literal이면 p는 데이터 속성 이름(예: 버전)이다.
"""
from services import graph_extraction as ge
from services.textnorm import norm_name


def _as_list(v) -> list[str]:
    return [v] if isinstance(v, str) else list(v or [])


_INVERSE: dict[str, str] = {}
for _p in ge.ONTOLOGY["predicates"]:
    if _p.get("inverse_of"):
        _INVERSE[_p["name"]] = _p["inverse_of"]
        _INVERSE[_p["inverse_of"]] = _p["name"]
_SYMMETRIC = {p["name"] for p in ge.ONTOLOGY["predicates"] if p.get("symmetric")}


def alias_index(case: dict) -> dict[str, str]:
    """정규화한 이름·동의어 → 정답 개념 이름."""
    idx: dict[str, str] = {}
    for c in case["concepts"]:
        for n in [c["name"], *c.get("aliases", [])]:
            idx.setdefault(norm_name(n), c["name"])
    return idx


def map_concepts(pred: dict, idx: dict[str, str]) -> dict[str, str]:
    """추출된 개념(norm) → 정답 개념 이름. 추출 쪽 동의어로도 맞춰 본다."""
    out: dict[str, str] = {}
    for c in pred["concepts"]:
        for n in [c["norm"], *(norm_name(a) for a in c.get("aliases", []))]:
            if n in idx:
                out[c["norm"]] = idx[n]
                break
    return out


def relation_matches(gold: dict, s: str, p: str, o: str) -> bool:
    """방향·관계까지 맞는가. 역관계를 뒤집어 쓴 것과 대칭 관계의 반대 방향도 인정한다."""
    preds = _as_list(gold["p"])
    if (s, o) == (gold["s"], gold["o"]) and p in preds:
        return True
    if (s, o) == (gold["o"], gold["s"]):
        return (p in preds and p in _SYMMETRIC) or _INVERSE.get(p) in preds
    return False


def pair_matches(gold: dict, s: str, o: str) -> bool:
    return {s, o} == {gold["s"], gold["o"]}


def score_case(case: dict, pred: dict) -> dict:
    idx = alias_index(case)
    cmap = map_concepts(pred, idx)
    gold_types = {c["name"]: _as_list(c.get("type")) for c in case["concepts"]}
    gold_kinds = {c["name"]: c.get("kind") for c in case["concepts"]}
    required, acceptable = case["relations"], case.get("acceptable", [])

    found_concepts = set(cmap.values())
    typed = [(cmap[c["norm"]], c["type"]) for c in pred["concepts"]
             if c["norm"] in cmap and gold_types[cmap[c["norm"]]]]
    type_ok = sum(any(ge._is_a(t, {g}) for g in gold_types[name]) for name, t in typed)
    kinded = [(cmap[c["norm"]], c["kind"]) for c in pred["concepts"]
              if c["norm"] in cmap and gold_kinds[cmap[c["norm"]]]]
    kind_ok = sum(k == gold_kinds[name] for name, k in kinded)

    hit_required: set[int] = set()
    pair_required: set[int] = set()
    correct = pair_correct = 0
    wrong: list[dict] = []
    for r in pred["relations"]:
        s, o = cmap.get(r["s"]), cmap.get(r["o"])
        row = {"s": s or r["s"], "p": r["p"], "o": o or r["o"],
               "known": bool(s and o), "evidence": r.get("evidence")}
        if not (s and o):
            wrong.append(row)
            continue
        strict = [i for i, g in enumerate(required) if relation_matches(g, s, r["p"], o)]
        hit_required.update(strict)
        pair_required.update(i for i, g in enumerate(required) if pair_matches(g, s, o))
        if strict or any(relation_matches(g, s, r["p"], o) for g in acceptable):
            correct += 1
        else:
            wrong.append(row)
        if any(pair_matches(g, s, o) for g in [*required, *acceptable]):
            pair_correct += 1

    n_pred = len(pred["relations"])
    return {
        "predicted": n_pred,
        "required": len(required),
        "correct": correct,
        "pair_correct": pair_correct,
        "required_hit": len(hit_required),
        "required_pair_hit": len(pair_required),
        "generic": sum(r["p"] == ge.DEFAULT_PREDICATE for r in pred["relations"]),
        "with_evidence": sum(bool(r.get("evidence")) for r in pred["relations"]),
        "gold_concepts": len(case["concepts"]),
        "concepts_found": len(found_concepts),
        "typed": len(typed),
        "type_ok": type_ok,
        "kinded": len(kinded),
        "kind_ok": kind_ok,
        "missed": [required[i] for i in range(len(required)) if i not in hit_required],
        "unmatched": wrong,
    }


def _ratio(a: int, b: int) -> float | None:
    return a / b if b else None


def metrics(counts: dict) -> dict:
    """여러 사례의 합계로 비율 지표를 낸다 (사례 평균이 아니라 관계 단위 micro 평균)."""
    p = _ratio(counts["correct"], counts["predicted"])
    r = _ratio(counts["required_hit"], counts["required"])
    return {
        "precision": p,
        "recall": r,
        "f1": 2 * p * r / (p + r) if p and r else 0.0,
        "pair_precision": _ratio(counts["pair_correct"], counts["predicted"]),
        "pair_recall": _ratio(counts["required_pair_hit"], counts["required"]),
        "concept_recall": _ratio(counts["concepts_found"], counts["gold_concepts"]),
        "kind_accuracy": _ratio(counts["kind_ok"], counts["kinded"]),
        "type_accuracy": _ratio(counts["type_ok"], counts["typed"]),
        "generic_rate": _ratio(counts["generic"], counts["predicted"]),
        "evidence_rate": _ratio(counts["with_evidence"], counts["predicted"]),
    }


SUM_KEYS = ("predicted", "required", "correct", "pair_correct", "required_hit", "required_pair_hit",
            "generic", "with_evidence", "gold_concepts", "concepts_found", "typed", "type_ok",
            "kinded", "kind_ok")


def total(results: list[dict]) -> dict:
    return {k: sum(r[k] for r in results) for k in SUM_KEYS}
