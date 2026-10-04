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
from services import gemini_client
from services.textnorm import norm_name

logger = logging.getLogger(__name__)

# 토큰 소모가 적은 경량 모델로 추출
GRAPH_MODEL = "gemini-3.1-flash-lite"
MAX_INPUT_CHARS = 40_000
MAX_CONCEPTS = 15
MAX_RELATIONS = 20

PREDICATES = ("사용한다", "일종이다", "일부이다", "해결한다", "관련있다")
DEFAULT_PREDICATE = "관련있다"
CONCEPT_TYPES = ("기술", "도구", "개념", "문제", "사람", "조직", "프로젝트")
DEFAULT_TYPE = "개념"

# 일반어는 개념으로 받지 않는다 (모델이 규칙을 어겨도 걸러냄)
_GENERIC = {norm_name(w) for w in (
    "방법", "코드", "문제", "해결", "설명", "예시", "내용", "정리", "사용", "결과",
    "오류", "에러", "질문", "답변", "user", "assistant", "code", "example", "method",
)}

# 재시도할 HTTP 상태 (요청 한도 초과 / 일시적 서버 오류·혼잡)
_RETRY_STATUS = {429, 500, 502, 503, 504}
_BACKOFF = [0, 8, 16, 32, 64]

PROMPT = f"""다음 노트에서 핵심 개념과 개념 사이의 관계를 추출해 JSON으로만 답하라.

형식:
{{"concepts": [{{"name": str, "type": str, "aliases": [str], "weight": 1|2|3}}],
 "relations": [{{"s": str, "p": str, "o": str}}]}}

규칙:
- concepts는 최대 {MAX_CONCEPTS}개. 노트의 주제를 이루는 구체적인 기술·도구·개념·문제·사람·조직·프로젝트만.
- type은 다음 중 하나: {", ".join(CONCEPT_TYPES)}
- weight: 3 = 노트의 중심 주제, 2 = 중요하게 다룸, 1 = 언급만 됨
- aliases: 같은 대상을 가리키는 다른 표기(한글/영문, 약어, 풀네임). 없으면 빈 배열.
- 소프트웨어·기술·제품 이름은 널리 쓰이는 공식 영문 표기를 name으로 쓴다(예: 도커 → Docker, 올라마 → Ollama).
- "방법", "코드", "문제", "설명", "예시" 같은 일반어는 개념으로 넣지 않는다.
- relations는 최대 {MAX_RELATIONS}개. s와 o는 반드시 위 concepts의 name 중 하나.
- p는 다음 중 하나: {", ".join(PREDICATES)}
  (사용한다: s가 o를 사용 / 일종이다: s는 o의 한 종류 / 일부이다: s는 o의 구성요소 /
   해결한다: s가 문제 o를 해결 / 관련있다: 위에 해당하지 않는 관련)
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

def call_model(content: str) -> str:
    """Gemini에 추출 요청을 보내 응답 텍스트를 돌려준다. 혼잡/한도 오류는 백오프 재시도."""
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
                f"{gemini_client._BASE}/{GRAPH_MODEL}:generateContent",
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

def parse_graph(text: str) -> dict:
    """응답 텍스트 → {"concepts": [...], "relations": [...]} (검증·정리된 값).

    형식 자체가 깨졌으면 GraphParseError. 개별 항목의 사소한 위반(알 수 없는 type,
    목록에 없는 개념을 가리키는 관계 등)은 고치거나 버린다.
    """
    cleaned = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise GraphParseError(f"JSON 파싱 실패: {e}") from e
    if not isinstance(obj, dict) or not isinstance(obj.get("concepts"), list):
        raise GraphParseError("concepts 배열이 없습니다")

    concepts: list[dict] = []
    by_norm: dict[str, dict] = {}
    for c in obj["concepts"]:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        norm = norm_name(name)
        if len(norm) < 2 and not re.fullmatch(r"[a-z0-9+#]+", norm or "-"):
            continue
        if not norm or norm in _GENERIC or norm in by_norm:
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
        item = {"name": name, "norm": norm, "type": ctype,
                "weight": min(3, max(1, weight)), "aliases": aliases[:8]}
        concepts.append(item)
        by_norm[norm] = item
        if len(concepts) >= MAX_CONCEPTS:
            break

    # 관계의 s/o는 이름 또는 동의어로 개념을 가리킬 수 있다
    lookup = dict(by_norm)
    for c in concepts:
        for a in c["aliases"]:
            lookup.setdefault(norm_name(a), c)

    relations: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for r in obj.get("relations") or []:
        if not isinstance(r, dict):
            continue
        s = lookup.get(norm_name(str(r.get("s") or "")))
        o = lookup.get(norm_name(str(r.get("o") or "")))
        if not s or not o or s is o:
            continue
        pred = str(r.get("p") or "").strip()
        if pred not in PREDICATES:
            pred = DEFAULT_PREDICATE
        key = (s["norm"], pred, o["norm"])
        if key in seen:
            continue
        seen.add(key)
        relations.append({"s": s["norm"], "p": pred, "o": o["norm"]})
        if len(relations) >= MAX_RELATIONS:
            break

    return {"concepts": concepts, "relations": relations}


# ── DB 반영 ─────────────────────────────────────────────────

def _resolve_concept(conn, item: dict) -> str:
    """이름/동의어로 기존 개념을 찾고, 없으면 만든다. 개념 id를 돌려준다."""
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
            "INSERT INTO concepts (id, name, norm, type, created_at) VALUES (?, ?, ?, ?, ?)",
            (cid, item["name"], item["norm"], item["type"], _now()),
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
        cid = _resolve_concept(conn, item)
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
