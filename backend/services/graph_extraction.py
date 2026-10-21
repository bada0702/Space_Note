"""지식 그래프 추출 — 노트 본문에서 개념·관계를 뽑아 concepts/relations 테이블에 반영.

설계: docs/superpowers/specs/2026-10-03-knowledge-graph-rag-design.md (2. 추출)
"""
import hashlib
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone

import httpx

from db import get_conn
from services import gemini_client, ollama_client
from services.textnorm import norm_name

logger = logging.getLogger(__name__)

# 기본 추출 모델 — 토큰 소모가 적은 경량 모델 (설정 화면에서 Ollama로 바꿀 수 있다)
GRAPH_MODEL = "gemini-3.1-flash-lite"
MAX_INPUT_CHARS = 40_000
MAX_CONCEPTS = 15   # class + instance
MAX_LITERALS = 10
MAX_RELATIONS = 25
MAX_DATA_PROPERTY_CHARS = 20

# 온톨로지 노드 종류와 관계
KINDS = ("class", "instance", "literal")
STRUCT_PREDICATES = ("인스턴스이다", "하위클래스이다")  # instance→class, class→class
OBJECT_PREDICATES = ("사용한다", "일부이다", "해결한다", "관련있다")
DEFAULT_PREDICATE = "관련있다"
CONCEPT_TYPES = ("기술", "도구", "개념", "문제", "사람", "조직", "프로젝트")
DEFAULT_TYPE = "개념"
LITERAL_TYPE = "값"

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
 "edges": [{{"s": str, "p": str, "o": str}}]}}

노드 규칙:
- class: 추상적인 분류·범주 (예: 벡터DB, LLM, 컨테이너 기술)
- instance: 구체적인 대상 — 특정 기술·제품·도구·사람·조직·프로젝트 (예: FAISS, Ollama, Docker)
- literal: 값 — 버전, 날짜, 수치, 크기 (예: v0.3, 2026-10, 768차원)
- class와 instance는 합쳐 최대 {MAX_CONCEPTS}개, literal은 최대 {MAX_LITERALS}개.
- type은 다음 중 하나: {", ".join(CONCEPT_TYPES)} (literal은 생략)
- weight: 3 = 노트의 중심 주제, 2 = 중요하게 다룸, 1 = 언급만 됨
- aliases: 같은 대상을 가리키는 다른 표기(한글/영문, 약어, 풀네임). 없으면 빈 배열. literal은 빈 배열.
- 소프트웨어·기술·제품 이름은 널리 쓰이는 공식 영문 표기를 name으로 쓴다(예: 도커 → Docker, 올라마 → Ollama).
- "방법", "코드", "문제", "설명", "예시" 같은 일반어는 노드로 넣지 않는다.

엣지 규칙 (최대 {MAX_RELATIONS}개, s와 o는 반드시 위 nodes의 name):
- 인스턴스이다: instance → class (s는 o의 한 사례)
- 하위클래스이다: class → class (s는 o의 하위 분류)
- {", ".join(OBJECT_PREDICATES)}: class/instance 사이의 관계
  (사용한다: s가 o를 사용 / 일부이다: s는 o의 구성요소 / 해결한다: s가 문제 o를 해결 / 관련있다: 그 밖의 관련)
- 데이터 속성: class/instance → literal. p는 속성 이름(예: 버전, 출시일, 차원 수), {MAX_DATA_PROPERTY_CHARS}자 이내.
- 다른 설명 없이 JSON만 출력.

노트:
"""


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
    if not gemini_client.has_api_key():
        return "Google API 키가 설정되지 않았습니다 (설정의 AI 모델에서 저장하세요)"
    return None


def call_model(content: str) -> str:
    """설정된 추출 모델(Gemini 또는 Ollama)에 요청해 응답 텍스트를 돌려준다."""
    model = graph_model()
    if ollama_client.is_ollama_model(model):
        return ollama_client.chat_json(model, PROMPT + content[:MAX_INPUT_CHARS])
    return _call_gemini(model, content)


def _call_gemini(model: str, content: str) -> str:
    """Gemini 추출 요청. 혼잡/한도 오류는 백오프 재시도."""
    key = gemini_client._api_key()
    if not key:
        raise ValueError("Google API 키가 설정되지 않았습니다")
    payload = {
        "contents": [{"role": "user", "parts": [{"text": PROMPT + content[:MAX_INPUT_CHARS]}]}],
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


def parse_graph(text: str) -> dict:
    """응답 텍스트 → {"concepts": [...], "relations": [...]} (검증·정리된 값).

    새 형식 {"nodes","edges"}와 예전 형식 {"concepts","relations"}를 모두 받는다.
    형식 자체가 깨졌으면 GraphParseError. 개별 항목의 위반(알 수 없는 type, 방향 규칙 위반,
    목록에 없는 노드를 가리키는 관계 등)은 고치거나 버린다.
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
        fixed = _clean_relation(s, str(r.get("p") or "").strip(), o)
        if fixed is None:
            continue
        s, pred, o = fixed
        key = (s["norm"], pred, o["norm"])
        if key in seen:
            continue
        seen.add(key)
        relations.append({"s": s["norm"], "p": pred, "o": o["norm"]})
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
        row = conn.execute(
            "SELECT concept_id AS id FROM concept_aliases WHERE norm = ?", (item["norm"],)
        ).fetchone()
    if row is None:
        for a in item["aliases"]:
            row = conn.execute(
                "SELECT id FROM concepts WHERE norm = ? UNION ALL "
                "SELECT concept_id FROM concept_aliases WHERE norm = ?",
                (norm_name(a), norm_name(a)),
            ).fetchone()
            if row:
                break
    if row is not None:
        cid = row[0]
    else:
        cid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO concepts (id, name, norm, type, kind, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (cid, item["name"], item["norm"], item["type"], kind, _now()),
        )
    # 동의어 등록 — 같은 동의어가 이미 다른 개념에 걸려 있으면 먼저 등록된 쪽을 유지
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


def clear_note_graph(conn, note_id: str) -> None:
    conn.execute("DELETE FROM note_concepts WHERE note_id = ?", (note_id,))
    conn.execute("DELETE FROM relations WHERE note_id = ?", (note_id,))


def gc_orphans(conn) -> None:
    """어떤 노트에서도 쓰이지 않는 개념과 그 동의어를 정리."""
    conn.execute(
        "DELETE FROM concepts WHERE id NOT IN (SELECT concept_id FROM note_concepts) "
        "AND id NOT IN (SELECT subj_id FROM relations) AND id NOT IN (SELECT obj_id FROM relations)"
    )
    conn.execute("DELETE FROM concept_aliases WHERE concept_id NOT IN (SELECT id FROM concepts)")


def store_graph(conn, note_id: str, graph: dict) -> None:
    """노트의 그래프를 통째로 교체."""
    clear_note_graph(conn, note_id)
    ids: dict[str, str] = {}
    for item in graph["concepts"]:
        cid = _resolve_concept(conn, item, note_id)
        ids[item["norm"]] = cid
        # 두 항목이 같은 개념으로 합쳐지면 더 큰 weight를 남긴다
        conn.execute(
            "INSERT INTO note_concepts (note_id, concept_id, weight) VALUES (?, ?, ?) "
            "ON CONFLICT(note_id, concept_id) DO UPDATE SET weight = MAX(weight, excluded.weight)",
            (note_id, cid, item["weight"]),
        )
    for r in graph["relations"]:
        s, o = ids.get(r["s"]), ids.get(r["o"])
        if not s or not o or s == o:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO relations (id, subj_id, pred, obj_id, note_id) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), s, r["p"], o, note_id),
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

    try:
        try:
            graph = parse_graph(call_model(content))
        except GraphParseError:
            logger.info("graph parse failed for %s, retrying once", note_id)
            graph = parse_graph(call_model(content))
    except Exception:
        logger.exception("graph extraction failed for note %s", note_id)
        _set_status(note_id, "failed", None)
        return "failed"

    with get_conn() as conn:
        # 처리하는 동안 본문이 바뀌었으면 결과를 버리고 다음 차례에 다시 처리
        cur = conn.execute("SELECT content FROM notes WHERE id = ?", (note_id,)).fetchone()
        if cur is None:
            return "missing"
        if content_hash(cur["content"] or "") != digest:
            return "pending"
        store_graph(conn, note_id, graph)
        conn.execute(
            "UPDATE notes SET graph_status = 'done', graph_hash = ? WHERE id = ?", (digest, note_id)
        )
    return "done"


def _set_status(note_id: str, status: str, digest) -> None:
    with get_conn() as conn:
        if digest is None:
            conn.execute("UPDATE notes SET graph_status = ? WHERE id = ?", (status, note_id))
        else:
            conn.execute(
                "UPDATE notes SET graph_status = ?, graph_hash = ? WHERE id = ?",
                (status, digest, note_id),
            )
