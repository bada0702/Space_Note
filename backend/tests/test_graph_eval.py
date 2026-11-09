import json

from graph_eval import run, scoring

CASE = {
    "concepts": [
        {"name": "FAISS", "kind": "instance", "type": "도구", "aliases": ["페이스"]},
        {"name": "벡터DB", "kind": "class", "type": "개념"},
        {"name": "Embedding", "kind": "instance", "type": "기술", "aliases": ["임베딩"]},
        {"name": "Kafka", "kind": "instance", "type": "도구"},
        {"name": "768차원", "kind": "literal", "type": "값"},
    ],
    "relations": [
        {"s": "FAISS", "p": "인스턴스이다", "o": "벡터DB"},
        {"s": "Embedding", "p": "차원 수", "o": "768차원"},
    ],
    "acceptable": [{"s": "FAISS", "p": "사용한다", "o": "Embedding"}],
}


def _pred(nodes, edges):
    from services import graph_extraction as ge
    raw = {"nodes": [{"name": n, "kind": k, "type": t} for n, k, t in nodes],
           "edges": [{"s": s, "p": p, "o": o} for s, p, o in edges]}
    return ge.parse_graph(json.dumps(raw, ensure_ascii=False))


def test_strict_acceptable_and_data_property_matches():
    pred = _pred(
        [("페이스", "instance", "도구"), ("벡터DB", "class", "개념"), ("임베딩", "instance", "기술"),
         ("768차원", "literal", "")],
        [("페이스", "인스턴스이다", "벡터DB"),   # 동의어로 맞힌 필수 관계
         ("페이스", "사용한다", "임베딩"),       # 허용 관계: 정밀도에만 반영
         ("임베딩", "차원 수", "768차원")],      # 데이터 속성
    )
    res = scoring.score_case(CASE, pred)
    assert (res["predicted"], res["correct"], res["required_hit"]) == (3, 3, 2)
    m = scoring.metrics(res)
    assert m["precision"] == 1.0 and m["recall"] == 1.0
    assert m["kind_accuracy"] == 1.0 and m["type_accuracy"] == 1.0


def test_wrong_kind_lowers_kind_accuracy():
    pred = _pred([("FAISS", "class", "도구"), ("벡터DB", "class", "개념")], [])
    m = scoring.metrics(scoring.score_case(CASE, pred))
    assert m["kind_accuracy"] == 0.5


def test_inverse_and_symmetric_relations_match():
    case = {**CASE, "relations": [{"s": "FAISS", "p": "대안이다", "o": "Kafka"},
                                  {"s": "Kafka", "p": "개발 주체", "o": "Apache"}],
            "concepts": [*CASE["concepts"], {"name": "Apache", "kind": "instance", "type": "조직"}],
            "acceptable": []}
    pred = _pred([("FAISS", "instance", "도구"), ("Kafka", "instance", "도구"), ("Apache", "instance", "조직")],
                 [("Kafka", "대안이다", "FAISS"),     # 대칭 관계는 반대 방향도 맞다
                  ("Apache", "개발했다", "Kafka")])   # 역관계(개발했다 ↔ 개발 주체)로 쓴 것도 맞다
    res = scoring.score_case(case, pred)
    assert (res["correct"], res["required_hit"]) == (2, 2)


def test_wrong_direction_counts_only_as_connection():
    case = {**CASE, "relations": [{"s": "FAISS", "p": "사용한다", "o": "Embedding"}], "acceptable": []}
    pred = _pred([("FAISS", "instance", "도구"), ("Embedding", "instance", "기술")], [("Embedding", "사용한다", "FAISS")])
    m = scoring.metrics(scoring.score_case(case, pred))
    assert (m["precision"], m["recall"]) == (0.0, 0.0)
    assert (m["pair_precision"], m["pair_recall"]) == (1.0, 1.0)


def test_subtype_counts_as_correct_type():
    case = {**CASE, "concepts": [{"name": "SQLite", "kind": "instance", "type": "도구"}], "relations": []}
    pred = _pred([("SQLite", "instance", "데이터베이스")], [])
    assert scoring.metrics(scoring.score_case(case, pred))["type_accuracy"] == 1.0
    case["concepts"][0]["type"] = "데이터베이스"
    pred = _pred([("SQLite", "instance", "도구")], [])  # 상위 유형만 맞힌 것은 틀린다
    assert scoring.metrics(scoring.score_case(case, pred))["type_accuracy"] == 0.0


def test_unknown_concepts_are_unmatched():
    pred = _pred([("FAISS", "instance", "도구"), ("Redis", "instance", "도구")], [("FAISS", "관련있다", "Redis")])
    res = scoring.score_case(CASE, pred)
    assert res["correct"] == 0 and not res["unmatched"][0]["known"]


def test_empty_prediction_has_zero_recall_and_no_precision():
    m = scoring.metrics(scoring.score_case(CASE, {"concepts": [], "relations": []}))
    assert m["recall"] == 0.0 and m["precision"] is None and m["f1"] == 0.0


def test_bundled_gold_sets_fit_the_vocabulary():
    cases = run.load_cases(None)
    assert cases
    assert [p for c in cases for p in run.validate(c)] == []


def test_validate_reports_unknown_vocabulary():
    case = {"id": "x", "concepts": [{"name": "A", "kind": "thing", "type": "장비"}, {"name": "B"}],
            "relations": [{"s": "A", "p": "탑재", "o": "B"}, {"s": "A", "p": "x", "o": "없음"}]}
    problems = run.validate(case)
    assert len(problems) == 4


def test_run_and_report_with_fake_model():
    case = run.load_cases(["SAMPLE_DOCKER"])[0]
    answer = json.dumps({
        "nodes": [{"name": "Docker", "kind": "instance", "type": "도구"},
                  {"name": "컨테이너 기술", "kind": "class", "type": "기술"}],
        "edges": [{"s": "Docker", "p": "인스턴스이다", "o": "컨테이너 기술",
                   "q": "Docker는 컨테이너 기술의 대표적인 구현이다."}],
    }, ensure_ascii=False)
    results = run.run([case], lambda text: answer, runs=2)
    summary = run.summarize(results, 2)
    assert summary["overall"]["precision"]["mean"] == 1.0
    assert summary["overall"]["recall"]["mean"] == 1 / len(case["relations"])
    assert summary["overall"]["evidence_rate"]["mean"] == 1.0
    md = run.markdown({"model": "fake", "started": "t", "runs": 2, "cases": ["SAMPLE_DOCKER"],
                       "gold_status": "sample", "errors": 0}, summary, results)
    assert "관계 정밀도 | 100%" in md and "놓친 필수 관계" in md
