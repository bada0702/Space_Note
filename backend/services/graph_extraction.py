"""지식 그래프 추출 — 노트 본문에서 개념·관계를 뽑아 concepts/relations 테이블에 반영.

설계: docs/superpowers/specs/2026-10-03-knowledge-graph-rag-design.md (2. 추출)
"""
import hashlib
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from db import get_conn
from services import anthropic_client, gemini_client, ollama_client, openai_client
from services.textnorm import norm_name

logger = logging.getLogger(__name__)

# 기본 추출 모델 — 토큰 소모가 적은 경량 모델 (설정 화면에서 Ollama로 바꿀 수 있다)
GRAPH_MODEL = "gemini-3.1-flash-lite"
MAX_INPUT_CHARS = 40_000
MAX_CONCEPTS = 15   # class + instance
MAX_LITERALS = 10
MAX_RELATIONS = 25
MAX_DATA_PROPERTY_CHARS = 20
MAX_EVIDENCE_CHARS = 300

# 온톨로지 노드 종류와 관계
KINDS = ("class", "instance", "literal")
STRUCT_PREDICATES = ("인스턴스이다", "하위클래스이다")  # instance→class, class→class
BASE_PREDICATES = {
    "사용한다": "s가 o를 사용",
    "일부이다": "s는 o의 구성요소",
    "해결한다": "s가 문제 o를 해결",
    "관련있다": "위에 해당하지 않는 관련",
}
DEFAULT_PREDICATE = "관련있다"
BASE_TYPES = ("기술", "도구", "개념", "문제", "사람", "조직", "프로젝트")
DEFAULT_TYPE = "개념"
LITERAL_TYPE = "값"

# 도메인 온톨로지(유형·관계와 그 설명)가 추출 어휘를 넓힌다. 파일이 없으면 기본 어휘만 쓴다
ONTOLOGY_PATH = Path(os.getenv(
    "SPACENOTE_ONTOLOGY", Path(__file__).resolve().parent.parent / "ontology" / "general.json"
))


def _from_owl(onto: dict) -> dict:
    """OWL 온톨로지(JSON-LD, 라벨·정의는 SKOS 주석)를 추출 코드가 쓰는 유형·관계 목록으로 바꾼다.

    owl:Class → 유형 (subClassOf → parent, skos:definition + skos:example → description),
    owl:ObjectProperty → 관계 (rdfs:domain/range, 여러 클래스면 owl:unionOf → domain/range).
    baseProperties(기본·구조 관계)는 코드가 따로 다루므로 IRI 라벨로만 쓴다.
    """
    label = {x["@id"]: x["prefLabel"]
             for x in onto["classes"] + onto["properties"] + onto["baseProperties"]}

    def name(iri: str | None) -> str | None:
        return iri and label[iri]

    def members(expr) -> list[str]:
        if expr is None:
            return []
        return [name(i) for i in ([expr] if isinstance(expr, str) else expr["unionOf"])]

    def description(c: dict) -> str:
        examples = f"예: {', '.join(c['example'])}." if c.get("example") else ""
        return " ".join(s for s in (c.get("definition", ""), examples) if s)

    types = [
        {"key": c["notation"], "name": c["prefLabel"], "description": description(c),
         "parent": name(c.get("subClassOf"))}
        for c in onto["classes"]
    ]
    predicates = [
        {"key": p["notation"], "name": p["prefLabel"], "description": p.get("definition", ""),
         "domain": members(p.get("domain")), "range": members(p.get("range")),
         "transitive": "owl:TransitiveProperty" in p["@type"],
         "symmetric": "owl:SymmetricProperty" in p["@type"],
         "inverse_of": name(p.get("inverseOf"))}
        for p in onto["properties"]
    ]
    return {"name": onto["prefLabel"], "source": onto.get("source"),
            "types": types, "predicates": predicates}


def load_ontology(path: Path = ONTOLOGY_PATH) -> dict:
    try:
        return _from_owl(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError):
        logger.warning("ontology not loaded from %s; using base vocabulary only", path)
        return {"types": [], "predicates": []}


ONTOLOGY = load_ontology()
CONCEPT_TYPES = tuple(dict.fromkeys(
    [*BASE_TYPES, *(t["name"] for t in ONTOLOGY["types"])]
))
# class/instance 사이의 관계 (구조 관계 인스턴스이다·하위클래스이다와 데이터 속성은 따로)
OBJECT_PREDICATES = tuple(dict.fromkeys(
    [*BASE_PREDICATES, *(p["name"] for p in ONTOLOGY["predicates"])]
))


_PARENT = {t["name"]: t.get("parent") for t in ONTOLOGY["types"]}
_SIGNATURE = {
    p["name"]: (set(p["domain"]), set(p["range"]))
    for p in ONTOLOGY["predicates"] if p["domain"] and p["range"]
}


def _is_a(ctype: str, allowed: set[str]) -> bool:
    """ctype이 allowed 중 하나이거나 그 하위 유형인가 (상위 유형을 따라 올라간다)."""
    seen = set()
    while ctype and ctype not in seen:
        if ctype in allowed:
            return True
        seen.add(ctype)
        ctype = _PARENT.get(ctype)
    return False


def fit_signature(pred: str, s: dict, o: dict) -> tuple[str, dict, dict]:
    """관계의 주어·목적어 유형을 온톨로지 시그니처와 대조한다.

    정방향이 맞으면 그대로, 역방향이 맞으면 주어·목적어를 바꾸고, 어느 쪽도 아니면
    기본 관계로 낮춘다. 시그니처가 없는 관계(기본 어휘)는 검사하지 않는다.
    """
    sig = _SIGNATURE.get(pred)
    if sig is None:
        return pred, s, o
    domain, range_ = sig
    if _is_a(s["type"], domain) and _is_a(o["type"], range_):
        return pred, s, o
    if _is_a(o["type"], domain) and _is_a(s["type"], range_):
        return pred, o, s
    return DEFAULT_PREDICATE, s, o


def predicate_strength(pred: str) -> float:
    """관계가 노트 연결을 얼마나 잘 설명하는가 — 온톨로지 관계 > 기본 타입 관계 > 관련있다."""
    if pred == DEFAULT_PREDICATE:
        return 0.4
    if pred in _SIGNATURE:
        return 1.2
    return 1.0


def _type_lines() -> str:
    described = {t["name"]: t.get("description") or "" for t in ONTOLOGY["types"]}
    return "\n".join(
        f"  - {name}: {described[name]}" if described.get(name) else f"  - {name}"
        for name in CONCEPT_TYPES
    )


def _predicate_lines() -> str:
    lines = [f"  - {name}: {desc}" for name, desc in BASE_PREDICATES.items()]
    for p in ONTOLOGY["predicates"]:
        sig = f" ({'|'.join(p['domain'])} → {'|'.join(p['range'])})" if p["domain"] and p["range"] else ""
        desc = p.get("description") or (f"{p['inverse_of']}의 역관계" if p.get("inverse_of") else "")
        lines.append(f"  - {p['name']}{sig}: {desc}" if desc else f"  - {p['name']}{sig}")
    return "\n".join(lines)


# 구조 관계가 저장된 kind와 맞는지 — 별칭 r(relations), cs(주어 concept), co(목적어 concept)를 전제로 한 조건.
# 공유 개념의 kind는 다수결로 바뀔 수 있어, 예전에 저장된 구조 관계가 규칙과 어긋날 수 있다
VALID_STRUCT_SQL = (
    "(r.pred NOT IN ('인스턴스이다', '하위클래스이다') "
    "OR (r.pred = '인스턴스이다' AND cs.kind = 'instance' AND co.kind = 'class') "
    "OR (r.pred = '하위클래스이다' AND cs.kind = 'class' AND co.kind = 'class'))"
)

# 일반어는 개념으로 받지 않는다 (모델이 규칙을 어겨도 걸러냄)
_GENERIC = {norm_name(w) for w in (
    "방법", "코드", "문제", "해결", "설명", "예시", "내용", "정리", "사용", "결과",
    "오류", "에러", "질문", "답변", "user", "assistant", "code", "example", "method",
)}

# 재시도할 HTTP 상태 (요청 한도 초과 / 일시적 서버 오류·혼잡)
_RETRY_STATUS = {429, 500, 502, 503, 504}
_BACKOFF = [0, 8, 16, 32, 64]

PROMPT = f"""다음 노트를 온톨로지(Class / Instance / Literal 노드와 관계)로 추출해 JSON으로만 답하라.

형식:
{{"nodes": [{{"name": str, "kind": "class"|"instance"|"literal", "type": str, "aliases": [str], "weight": 1|2|3}}],
 "edges": [{{"s": str, "p": str, "o": str, "q": str}}]}}

노드 규칙:
- class: 추상적인 분류·범주 (예: 벡터DB, LLM, 컨테이너 기술)
- instance: 구체적인 대상 — 특정 기술·제품·사람·조직·장소·음식 등 (예: FAISS, Ollama, Docker, 제주도)
- literal: 값 — 버전, 날짜, 수치, 크기 (예: v0.3, 2026-10, 768차원)
- class와 instance는 합쳐 최대 {MAX_CONCEPTS}개, literal은 최대 {MAX_LITERALS}개.
- type은 아래 유형 중 설명에 가장 잘 맞는 하나 (literal은 생략). 더 구체적인 하위 유형이 맞으면 그것을 쓴다(예: 도구보다 데이터베이스):
{_type_lines()}
- weight: 3 = 노트의 중심 주제, 2 = 중요하게 다룸, 1 = 언급만 됨
- aliases: 완전히 같은 대상을 가리키는 다른 표기(한글/영문, 약어, 풀네임)만. 없으면 빈 배열. literal은 빈 배열.
  상위 분류(Piper의 TTS), 하위 사례(LLM의 GPT), 비슷한 다른 대상(PowerHA의 VCS)은 aliases에 넣지 말고
  별도 노드로 만들어 인스턴스이다/하위클래스이다/관련 관계로 잇는다.
- 소프트웨어·기술·제품 이름은 널리 쓰이는 공식 영문 표기를 name으로 쓴다(예: 도커 → Docker, 올라마 → Ollama).
- "방법", "코드", "문제", "설명", "예시" 같은 일반어는 노드로 넣지 않는다.
- name은 그 대상을 가리키는 가장 짧은 표준 이름으로 쓴다. "Docker 설치", "RAG 구축 방법" 같은 활동·작업 명사구는 노드로 만들지 말고, 대상(Docker, RAG)만 노드로 두고 내용은 관계로 나타낸다.
- 세 단어 이상인 name은 제품명·책 제목 같은 고유명사일 때만 쓴다.

엣지 규칙 (최대 {MAX_RELATIONS}개, s와 o는 반드시 위 nodes의 name):
- 인스턴스이다: instance → class (s는 o의 한 사례)
- 하위클래스이다: class → class (s는 o의 하위 분류)
- class/instance 사이의 관계는 아래 중 하나. 괄호는 s 유형 → o 유형이며, 맞는 관계가 없으면 관련있다:
{_predicate_lines()}
- 데이터 속성: class/instance → literal. p는 속성 이름(예: 버전, 출시일, 차원 수), {MAX_DATA_PROPERTY_CHARS}자 이내.
- q: 그 엣지의 근거가 되는 노트 속 문장을 고치지 말고 그대로 옮긴다. 근거 문장이 없으면 빈 문자열.
- 다른 설명 없이 JSON만 출력.

"""
KNOWN_LIMIT = 50
_KNOWN_HEADER = (
    "이미 쓰는 이름 (노트의 대상이 아래 이름과 같은 대상이면 그 이름을 그대로 name으로 쓴다. "
    "같은 대상이 아니면 무시한다):"
)


def build_prompt(content: str, known=()) -> str:
    """추출 규칙 + (있으면) 이미 쓰는 개념 이름 목록 + 노트 본문."""
    block = "".join([_KNOWN_HEADER + "\n", *(f"- {k}\n" for k in known), "\n"]) if known else ""
    return PROMPT + block + "노트:\n" + content[:MAX_INPUT_CHARS]


def known_concepts(conn, content: str, limit: int = KNOWN_LIMIT) -> list[str]:
    """본문에 이름·동의어가 나오는 기존 개념의 표준 이름 (노트 사이 표기 통일용).

    2개 이상 활성 노트에서 쓰이고 이름이 3단어 미만인 개념만 — 재분석 중 남아 있는
    한 노트짜리·명사구 이름이 다시 퍼지지 않게. 노트 수 내림차순, 같으면 이름순.
    """
    from services.graph_retrieval import _query_ngrams, mentions  # graph_retrieval이 이 모듈을 import한다

    qnorm, grams = norm_name(content), _query_ngrams(content)
    rows = conn.execute(
        "SELECT c.id AS id, c.name AS name, COUNT(DISTINCT nc.note_id) AS df FROM concepts c "
        "JOIN note_concepts nc ON nc.concept_id = c.id "
        "JOIN notes n ON n.id = nc.note_id AND n.is_archived = 0 "
        "WHERE c.kind != 'literal' GROUP BY c.id HAVING df >= 2"
    ).fetchall()
    forms: dict[str, set[str]] = {}
    for r in conn.execute("SELECT concept_id, norm FROM concept_aliases"):
        forms.setdefault(r[0], set()).add(r[1])
    hits = [r for r in rows if len(r["name"].split()) < 3
            and any(mentions(f, qnorm, grams) for f in forms.get(r["id"], {norm_name(r["name"])}))]
    hits.sort(key=lambda r: (-r["df"], r["name"]))
    return [r["name"] for r in hits[:limit]]


class GraphParseError(ValueError):
    """모델 응답이 약속한 JSON 형식이 아님."""


def content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 모델 호출 ────────────────────────────────────────────────

def graph_model() -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT graph_model FROM settings WHERE id = 1").fetchone()
    return (row["graph_model"] if row else "") or GRAPH_MODEL


def model_ready() -> str | None:
    """추출 모델을 쓸 수 없으면 사용자에게 보일 이유, 쓸 수 있으면 None."""
    model = graph_model()
    if ollama_client.is_ollama_model(model):
        if not ollama_client.list_models():
            return "Ollama 서버에 연결할 수 없습니다 (설정의 Ollama 주소를 확인하세요)"
        return None
    if model.startswith("claude"):
        return None if anthropic_client.has_api_key() else "Anthropic API 키가 설정되지 않았습니다 (설정의 AI 모델에서 저장하세요)"
    if model.startswith("gpt"):
        return None if openai_client.has_api_key() else "OpenAI API 키가 설정되지 않았습니다 (설정의 AI 모델에서 저장하세요)"
    if not gemini_client.has_api_key():
        return "Google API 키가 설정되지 않았습니다 (설정의 AI 모델에서 저장하세요)"
    return None


def call_model(content: str, known=()) -> str:
    """설정된 추출 모델(Gemini, Claude, GPT, Ollama)에 요청해 응답 텍스트를 돌려준다."""
    model = graph_model()
    prompt = build_prompt(content, known)
    if ollama_client.is_ollama_model(model):
        return ollama_client.chat_json(model, prompt)
    if model.startswith("claude"):
        return anthropic_client.complete_json(model, prompt)
    if model.startswith("gpt"):
        return openai_client.complete_json(model, prompt)
    return _call_gemini(model, prompt)


def _call_gemini(model: str, prompt: str) -> str:
    """Gemini 추출 요청. 혼잡/한도 오류는 백오프 재시도."""
    key = gemini_client._api_key()
    if not key:
        raise ValueError("Google API 키가 설정되지 않았습니다")
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }
    resp = None
    for delay in _BACKOFF:
        if delay:
            time.sleep(delay)
        try:
            resp = httpx.post(
                f"{gemini_client._BASE}/{model}:generateContent",
                headers={"x-goog-api-key": key},
                json=payload,
                timeout=120,
            )
        except httpx.TransportError as e:  # 네트워크 일시 오류도 재시도
            logger.warning("graph extraction transport error: %s", e)
            continue
        if resp.status_code not in _RETRY_STATUS:
            break
        logger.info("graph extraction got %s, retrying", resp.status_code)
    if resp is None:
        raise RuntimeError("Gemini 요청이 네트워크 오류로 계속 실패했습니다")
    resp.raise_for_status()
    data = resp.json()
    return "".join(
        part.get("text", "")
        for cand in data.get("candidates", [])
        for part in cand.get("content", {}).get("parts", [])
    )


# ── 응답 검증 ────────────────────────────────────────────────

def _kind_of(c: dict) -> str:
    kind = str(c.get("kind") or "").strip().lower()
    if kind in KINDS:
        return kind
    # kind가 없는 예전 형식: '개념'은 분류(class), 나머지는 구체 대상(instance)
    return "class" if str(c.get("type") or "").strip() == "개념" else "instance"


def _clean_relation(s: dict, p: str, o: dict) -> tuple[dict, str, dict] | None:
    """온톨로지 방향 규칙에 맞춘 (s, p, o) 또는 버릴 관계면 None."""
    if s["kind"] == "literal":
        return None
    if o["kind"] == "literal":
        # 데이터 속성: 이름이 구조·객체 관계와 겹치거나 너무 길면 버림
        if not p or p in STRUCT_PREDICATES or p in OBJECT_PREDICATES or len(p) > MAX_DATA_PROPERTY_CHARS:
            return None
        return s, p, o
    if p == "인스턴스이다":
        if s["kind"] == "class" and o["kind"] == "instance":
            s, o = o, s  # 방향만 거꾸로 온 경우 살린다
        return (s, p, o) if (s["kind"], o["kind"]) == ("instance", "class") else None
    if p == "하위클래스이다":
        return (s, p, o) if (s["kind"], o["kind"]) == ("class", "class") else None
    return s, (p if p in OBJECT_PREDICATES else DEFAULT_PREDICATE), o


def _fit_relation(s: dict, p: str, o: dict) -> tuple[dict, str, dict] | None:
    """kind 방향 규칙을 맞춘 뒤, class/instance 사이 관계는 온톨로지 시그니처로 다시 맞춘다."""
    fixed = _clean_relation(s, p, o)
    if fixed is None:
        return None
    s, p, o = fixed
    if p in OBJECT_PREDICATES and o["kind"] != "literal":
        p, s, o = fit_signature(p, s, o)
    return s, p, o


def _squash(text: str) -> str:
    return " ".join((text or "").split())


def _evidence(quote, source: str | None) -> str | None:
    """근거 문장은 노트 본문에 (공백 차이 외에는) 그대로 있을 때만 인정한다."""
    quote = _squash(str(quote or ""))[:MAX_EVIDENCE_CHARS]
    if not quote or source is None or quote not in _squash(source):
        return None
    return quote


def parse_graph(text: str, source: str | None = None) -> dict:
    """응답 텍스트 → {"concepts": [...], "relations": [...]} (검증·정리된 값).

    새 형식 {"nodes","edges"}와 예전 형식 {"concepts","relations"}를 모두 받는다.
    형식 자체가 깨졌으면 GraphParseError. 개별 항목의 위반(알 수 없는 type, 방향 규칙 위반,
    목록에 없는 노드를 가리키는 관계 등)은 고치거나 버린다.
    source(노트 본문)를 주면 엣지의 근거 문장 q를 본문과 대조해 evidence로 남긴다.
    """
    cleaned = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise GraphParseError(f"JSON 파싱 실패: {e}") from e
    if not isinstance(obj, dict):
        raise GraphParseError("JSON 객체가 아닙니다")
    raw_nodes = obj.get("nodes", obj.get("concepts"))
    if not isinstance(raw_nodes, list):
        raise GraphParseError("nodes 배열이 없습니다")
    raw_edges = obj.get("edges", obj.get("relations")) or []

    concepts: list[dict] = []
    by_norm: dict[str, dict] = {}
    n_terms = n_literals = 0
    for c in raw_nodes:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        norm = norm_name(name)
        kind = _kind_of(c)
        if not norm or norm in by_norm:
            continue
        if kind == "literal":
            if n_literals >= MAX_LITERALS:
                continue
            item = {"name": name, "norm": norm, "kind": kind, "type": LITERAL_TYPE,
                    "weight": 1, "aliases": []}
            n_literals += 1
        else:
            if n_terms >= MAX_CONCEPTS:
                continue
            if len(norm) < 2 and not re.fullmatch(r"[a-z0-9+#]+", norm):
                continue
            if norm in _GENERIC:
                continue
            ctype = str(c.get("type") or "").strip()
            if ctype not in CONCEPT_TYPES:
                ctype = DEFAULT_TYPE
            try:
                weight = int(c.get("weight", 1))
            except (TypeError, ValueError):
                weight = 1
            aliases = []
            for a in c.get("aliases") or []:
                a = str(a).strip()
                an = norm_name(a)
                if an and an != norm and an not in _GENERIC and a not in aliases:
                    aliases.append(a)
            item = {"name": name, "norm": norm, "kind": kind, "type": ctype,
                    "weight": min(3, max(1, weight)), "aliases": aliases[:8]}
            n_terms += 1
        concepts.append(item)
        by_norm[norm] = item

    # 관계의 s/o는 이름 또는 동의어로 노드를 가리킬 수 있다
    lookup = dict(by_norm)
    for c in concepts:
        for a in c["aliases"]:
            lookup.setdefault(norm_name(a), c)

    relations: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for r in raw_edges:
        if not isinstance(r, dict):
            continue
        s = lookup.get(norm_name(str(r.get("s") or "")))
        o = lookup.get(norm_name(str(r.get("o") or "")))
        if not s or not o or s is o:
            continue
        fixed = _fit_relation(s, str(r.get("p") or "").strip(), o)
        if fixed is None:
            continue
        s, pred, o = fixed
        key = (s["norm"], pred, o["norm"])
        if key in seen:
            continue
        seen.add(key)
        relations.append({"s": s["norm"], "p": pred, "o": o["norm"],
                          "evidence": _evidence(r.get("q"), source)})
        if len(relations) >= MAX_RELATIONS:
            break

    return {"concepts": concepts, "relations": relations}


# ── DB 반영 ─────────────────────────────────────────────────

def _resolve_concept(conn, item: dict, note_id: str) -> str:
    """이름/동의어로 기존 개념을 찾고, 없으면 만든다. 개념 id를 돌려준다.

    literal은 노트마다 따로 둔다 — 같은 값이 나왔다는 이유로 노트가 이어지지 않게.
    """
    kind = item.get("kind", "instance")
    if kind == "literal":
        norm = f"lit:{note_id}:{item['norm']}"
        row = conn.execute("SELECT id FROM concepts WHERE norm = ?", (norm,)).fetchone()
        if row is not None:
            return row[0]
        cid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO concepts (id, name, norm, type, kind, created_at) VALUES (?, ?, ?, ?, 'literal', ?)",
            (cid, item["name"], norm, LITERAL_TYPE, _now()),
        )
        return cid
    row = conn.execute("SELECT id FROM concepts WHERE norm = ?", (item["norm"],)).fetchone()
    if row is None:
        # 동의어로 찾은 개념은 kind가 같을 때만 합친다 — 분류(class)와 구체 대상(instance)은
        # 같은 대상일 수 없다. 모델이 상위·하위 개념을 동의어로 넣으면(Piper의 TTS) 다른 노트의
        # 'TTS'가 Piper로 빨려 들어가고, 그 동의어가 또 다음 병합을 부르며 개념이 불어난다
        row = conn.execute(
            "SELECT c.id FROM concept_aliases a JOIN concepts c ON c.id = a.concept_id "
            "WHERE a.norm = ? AND c.kind = ?",
            (item["norm"], kind),
        ).fetchone()
    if row is None:
        for a in item["aliases"]:
            an = norm_name(a)
            row = conn.execute(
                "SELECT id FROM concepts WHERE norm = ? AND kind = ? UNION ALL "
                "SELECT c.id FROM concept_aliases a JOIN concepts c ON c.id = a.concept_id "
                "WHERE a.norm = ? AND c.kind = ?",
                (an, kind, an, kind),
            ).fetchone()
            if row:
                break
    if row is not None:
        cid = row[0]  # 공유 개념의 kind는 덮어쓰지 않는다 — store_graph가 노트별 다수결로 정한다
    else:
        cid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO concepts (id, name, norm, type, kind, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (cid, item["name"], item["norm"], item["type"], kind, _now()),
        )
    # 동의어 등록 — 같은 동의어가 이미 다른 개념에 걸려 있으면 먼저 등록된 쪽을 유지.
    # 단 개념 자신의 이름은 남의 동의어보다 우선한다 ('TTS' 질문이 Piper가 아니라 TTS로 가게)
    own = conn.execute("SELECT norm, name FROM concepts WHERE id = ?", (cid,)).fetchone()
    conn.execute(
        "INSERT INTO concept_aliases (norm, alias, concept_id) VALUES (?, ?, ?) "
        "ON CONFLICT(norm) DO UPDATE SET alias = excluded.alias, concept_id = excluded.concept_id",
        (own[0], own[1], cid),
    )
    for a in [item["name"], *item["aliases"]]:
        an = norm_name(a)
        if not an:
            continue
        taken = conn.execute("SELECT 1 FROM concepts WHERE norm = ? AND id != ?", (an, cid)).fetchone()
        if taken:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO concept_aliases (norm, alias, concept_id) VALUES (?, ?, ?)",
            (an, a, cid),
        )
    return cid


def recompute_kinds(conn, concept_ids) -> None:
    """개념마다 note_concepts.kind 다수결을 concepts.kind에 쓴다. 동률이면 현재 값을 유지한다."""
    for cid in set(concept_ids):
        votes = dict(conn.execute(
            "SELECT kind, COUNT(*) FROM note_concepts WHERE concept_id = ? GROUP BY kind", (cid,)
        ).fetchall())
        if not votes:
            continue
        row = conn.execute("SELECT kind FROM concepts WHERE id = ?", (cid,)).fetchone()
        if row is None:
            continue
        best = max(votes.values())
        tops = [k for k, n in votes.items() if n == best]
        kind = row[0] if row[0] in tops else ("class" if "class" in tops else sorted(tops)[0])
        if kind != row[0]:
            conn.execute("UPDATE concepts SET kind = ? WHERE id = ?", (kind, cid))


def clear_note_graph(conn, note_id: str) -> None:
    ids = [r[0] for r in conn.execute("SELECT concept_id FROM note_concepts WHERE note_id = ?", (note_id,))]
    conn.execute("DELETE FROM note_concepts WHERE note_id = ?", (note_id,))
    conn.execute("DELETE FROM relations WHERE note_id = ?", (note_id,))
    recompute_kinds(conn, ids)


def gc_orphans(conn) -> None:
    """어떤 노트에서도 쓰이지 않는 개념과 그 동의어를 정리."""
    conn.execute(
        "DELETE FROM concepts WHERE id NOT IN (SELECT concept_id FROM note_concepts) "
        "AND id NOT IN (SELECT subj_id FROM relations) AND id NOT IN (SELECT obj_id FROM relations)"
    )
    conn.execute("DELETE FROM concept_aliases WHERE concept_id NOT IN (SELECT id FROM concepts)")


def purge_dangling_rows(conn) -> dict[str, int]:
    """없는 노트를 가리키는 분석 결과(그래프·엔티티·태그·항로)를 지우고 고아 개념을 정리한다.

    앱 밖에서 노트 행만 지워진 경우(볼트 동기화 이전 버전, 직접 DB 수정 등)를 복구한다.
    """
    live = "SELECT id FROM notes"
    removed = {
        "note_concepts": conn.execute(f"DELETE FROM note_concepts WHERE note_id NOT IN ({live})").rowcount,
        "relations": conn.execute(f"DELETE FROM relations WHERE note_id NOT IN ({live})").rowcount,
        "entities": conn.execute(f"DELETE FROM entities WHERE note_id NOT IN ({live})").rowcount,
        "tags": conn.execute(f"DELETE FROM tags WHERE note_id NOT IN ({live})").rowcount,
        "routes": conn.execute(
            f"DELETE FROM routes WHERE note_a NOT IN ({live}) OR note_b NOT IN ({live})"
        ).rowcount,
    }
    before = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
    gc_orphans(conn)
    removed["concepts"] = before - conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
    return removed


def store_graph(conn, note_id: str, graph: dict) -> None:
    """노트의 그래프를 통째로 교체."""
    clear_note_graph(conn, note_id)
    ids: dict[str, str] = {}
    for item in graph["concepts"]:
        cid = _resolve_concept(conn, item, note_id)
        ids[item["norm"]] = cid
        # 두 항목이 같은 개념으로 합쳐지면 더 큰 weight를 남기고, kind가 엇갈리면 class를 남긴다
        conn.execute(
            "INSERT INTO note_concepts (note_id, concept_id, weight, kind) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(note_id, concept_id) DO UPDATE SET weight = MAX(weight, excluded.weight), "
            "kind = CASE WHEN excluded.kind = 'class' THEN 'class' ELSE kind END",
            (note_id, cid, item["weight"], item["kind"]),
        )
    # 공유 개념의 kind는 이 노트를 포함한 노트별 판단의 다수결 — 관계는 그 결과로 검사한다
    recompute_kinds(conn, ids.values())
    kinds = {cid: conn.execute("SELECT kind FROM concepts WHERE id = ?", (cid,)).fetchone()[0]
             for cid in set(ids.values())}
    for r in graph["relations"]:
        s, o = ids.get(r["s"]), ids.get(r["o"])
        if not s or not o or s == o:
            continue
        # parse_graph는 항목별 kind로 검사했으므로, 저장된 kind 기준으로 방향을 다시 맞춘다
        fixed = _clean_relation({"id": s, "kind": kinds[s]}, r["p"], {"id": o, "kind": kinds[o]})
        if fixed is None:
            continue
        sd, pred, od = fixed
        conn.execute(
            "INSERT OR IGNORE INTO relations (id, subj_id, pred, obj_id, note_id, evidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), sd["id"], pred, od["id"], note_id, r.get("evidence")),
        )
    gc_orphans(conn)


# ── 노트 하나 처리 ───────────────────────────────────────────

def process_note(note_id: str) -> str:
    """노트 하나의 그래프를 추출·저장하고 최종 graph_status를 돌려준다."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT content, graph_hash FROM notes WHERE id = ?", (note_id,)
        ).fetchone()
    if row is None:
        return "missing"
    content = row["content"] or ""
    digest = content_hash(content)
    if row["graph_hash"] == digest:
        _set_status(note_id, "done", digest)
        return "done"
    if not content.strip():
        with get_conn() as conn:
            clear_note_graph(conn, note_id)
            gc_orphans(conn)
        _set_status(note_id, "done", digest)
        return "done"

    with get_conn() as conn:
        known = known_concepts(conn, content)
    try:
        try:
            graph = parse_graph(call_model(content, known), content)
        except GraphParseError:
            logger.info("graph parse failed for %s, retrying once", note_id)
            graph = parse_graph(call_model(content, known), content)
    except Exception as e:
        logger.exception("graph extraction failed for note %s", note_id)
        _set_status(note_id, "failed", None, describe_failure(e))
        return "failed"

    with get_conn() as conn:
        # 처리하는 동안 본문이 바뀌었으면 결과를 버리고 다음 차례에 다시 처리
        cur = conn.execute("SELECT content, graph_status FROM notes WHERE id = ?", (note_id,)).fetchone()
        if cur is None:
            return "missing"
        if cur["graph_status"] == "idle":  # 기다리는 동안 분석이 취소됨
            return "idle"
        if content_hash(cur["content"] or "") != digest:
            return "pending"
        store_graph(conn, note_id, graph)
        conn.execute(
            "UPDATE notes SET graph_status = 'done', graph_hash = ?, graph_error = NULL WHERE id = ?",
            (digest, note_id),
        )
    return "done"


def describe_failure(e: Exception) -> str:
    """추출 실패를 사용자에게 보여줄 짧은 이유로 바꾼다 (상세는 로그에 남는다)."""
    if isinstance(e, GraphParseError):
        return "모델 응답 형식이 올바르지 않습니다"
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if ollama_client.is_ollama_model(graph_model()):
            return f"Ollama 요청이 실패했습니다 (HTTP {code}) — 모델 이름을 확인하세요"
        if code in (401, 403):
            return "Google API 키가 유효하지 않거나 권한이 없습니다"
        if code == 429:
            return "Google API 사용 한도를 초과했습니다"
        if code >= 500:
            return f"Gemini 서버 오류 (HTTP {code})"
        return f"Gemini 요청이 거부되었습니다 (HTTP {code})"
    if isinstance(e, httpx.TransportError):
        return "추출 모델 서버에 연결할 수 없습니다"
    if isinstance(e, (ValueError, RuntimeError)):
        return str(e)
    return f"알 수 없는 오류 ({type(e).__name__})"


def _set_status(note_id: str, status: str, digest, error: str | None = None) -> None:
    with get_conn() as conn:
        if digest is None:
            conn.execute(
                "UPDATE notes SET graph_status = ?, graph_error = ? WHERE id = ?",
                (status, error, note_id),
            )
        else:
            conn.execute(
                "UPDATE notes SET graph_status = ?, graph_hash = ?, graph_error = ? WHERE id = ?",
                (status, digest, error, note_id),
            )
