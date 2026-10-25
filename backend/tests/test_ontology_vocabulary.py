"""일반 온톨로지 규칙 사전(SKOS) — 추출 어휘, 관계 시그니처, 사전 무결성."""
import json


# ── 일반 온톨로지 어휘와 관계 시그니처 ─────────────────────

def _parse(nodes, edges):
    from services import graph_extraction as ge
    raw = {"nodes": [{"name": n, "kind": k, "type": t} for n, k, t in nodes],
           "edges": [{"s": s, "p": p, "o": o} for s, p, o in edges]}
    return {(r["s"], r["p"], r["o"]) for r in ge.parse_graph(json.dumps(raw, ensure_ascii=False))["relations"]}


def test_general_ontology_vocabulary_is_loaded():
    from services import graph_extraction as ge
    for t in ("프로그래밍 언어", "데이터베이스", "장소", "음식", "운동"):
        assert t in ge.CONCEPT_TYPES and t in ge.PROMPT
    for p in ("작성 언어", "실행 환경", "발생 장소", "재료"):
        assert p in ge.OBJECT_PREDICATES and p in ge.PROMPT
    assert ge._is_a("데이터베이스", {"도구"}) and not ge._is_a("데이터베이스", {"기술"})


def test_signature_keeps_swaps_or_downgrades_relation():
    rels = _parse(
        [("FastAPI", "instance", "프레임워크·라이브러리"), ("Python", "instance", "프로그래밍 언어"),
         ("러닝", "instance", "운동"), ("한강공원", "instance", "장소"), ("두통", "instance", "질병·증상")],
        [("FastAPI", "작성 언어", "Python"),   # 하위 유형(프레임워크 ⊂ 도구)도 시그니처에 맞는다
         ("한강공원", "발생 장소", "러닝"),     # 방향이 거꾸로 → 주어·목적어를 바꾼다
         ("두통", "작성 언어", "러닝")],        # 어느 방향도 안 맞음 → 관련있다로 낮춘다
    )
    assert ("fastapi", "작성 언어", "python") in rels
    assert ("러닝", "발생 장소", "한강공원") in rels
    assert ("두통", "관련있다", "러닝") in rels


def test_signature_does_not_touch_structure_or_data_properties():
    rels = _parse(
        [("SQLite", "instance", "데이터베이스"), ("데이터베이스", "class", "개념"), ("3.45", "literal", "")],
        [("SQLite", "인스턴스이다", "데이터베이스"), ("SQLite", "버전", "3.45")],
    )
    from services.textnorm import norm_name
    assert rels == {("sqlite", "인스턴스이다", "데이터베이스"), ("sqlite", "버전", norm_name("3.45"))}


def test_predicate_strength_ranks_ontology_relations():
    from services import graph_extraction as ge
    assert ge.predicate_strength("작성 언어") > ge.predicate_strength("사용한다") > ge.predicate_strength("관련있다")


# ── SKOS 규칙 사전 ─────────────────────────────────────────

def _scheme():
    from services import graph_extraction as ge
    return json.loads(ge.ONTOLOGY_PATH.read_text(encoding="utf-8"))


def test_ontology_file_is_skos_concept_scheme():
    scheme = _scheme()
    assert scheme["@context"]["skos"] == "http://www.w3.org/2004/02/skos/core#"
    assert scheme["@type"] == "skos:ConceptScheme"
    concepts = scheme["concepts"]
    ids = {c["@id"] for c in concepts}
    assert all(c["@type"] == "skos:Concept" for c in concepts)
    # prefLabel은 사전 안에서 하나뿐이어야 한다 (SKOS 무결성 조건 S14)
    labels = [c["prefLabel"] for c in concepts]
    assert len(labels) == len(set(labels))
    # broader는 사전 안의 개념을 가리키고, 최상위 개념은 broader가 없는 개념과 같다
    assert all(c["broader"] in ids for c in concepts if "broader" in c)
    assert set(scheme["hasTopConcept"]) == {c["@id"] for c in concepts if "broader" not in c}
    for p in scheme["properties"]:
        assert "owl:ObjectProperty" in p["@type"]
        assert set(p["domainIncludes"]) <= ids and set(p["rangeIncludes"]) <= ids


def test_skos_scheme_loads_into_internal_vocabulary():
    from services import graph_extraction as ge
    types = {t["name"]: t for t in ge.ONTOLOGY["types"]}
    assert types["오류"]["parent"] == "문제" and types["문제"]["parent"] is None
    # skos:definition + skos:example이 프롬프트용 설명으로 합쳐진다
    assert types["오류"]["description"] == "버그·에러 메시지·시스템 장애. 예: OOM, 404 오류."
    assert types["프로그래밍 언어"]["description"] == "예: Python, TypeScript."
    preds = {p["name"]: p for p in ge.ONTOLOGY["predicates"]}
    assert preds["구현체"]["inverse_of"] == "구현한다"
    assert preds["포함한다"]["inverse_of"] == "일부이다"   # 코드에 정의된 기본 어휘를 가리킨다
    assert preds["연동한다"]["symmetric"] and preds["위치한다"]["transitive"]
    assert preds["작성 언어"]["range"] == ["프로그래밍 언어"]
