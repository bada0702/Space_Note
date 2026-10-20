import json
import math
import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from db import get_conn
from models import SettingsPatch, ChatRequest
from services import anthropic_client, gemini_client, graph_retrieval, ollama_client, openai_client
from services.extraction import kiwi, is_korean_stopword_or_ending, strip_korean_particles

router = APIRouter()

RAG_LIMIT = 5
RAG_EXCERPT = 1200
RAG_MAX_KEYWORDS = 8
GRAPH_WEIGHT = 0.6
KEYWORD_WEIGHT = 0.4

SUMMARY_SYSTEM = (
    "너는 노트 정리 도우미다. 사용자가 준 노트를 핵심 내용 중심의 마크다운 문서로 다시 정리한다.\n"
    "- 노트가 AI와의 대화 기록이면 질문·답변 형식, 화자 표시(사용자:, AI:, You said 등), "
    "인사말·맞장구·되묻기 같은 대화 군더더기를 모두 없애고 결론과 정보만 남긴다.\n"
    "- 주제별 소제목(##)과 글머리표로 구조화하고, 중복된 설명은 하나로 합친다.\n"
    "- 코드 블록, 명령어, 설정값, 수치, 고유명사는 원문 그대로 보존한다.\n"
    "- 원문에 없는 내용을 지어내지 않는다.\n"
    "- 노트의 주 언어로 작성하고, 정리된 본문만 출력한다 (앞뒤 설명 문구 금지)."
)


def _get_settings() -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    d = dict(row)
    d.pop("id", None)
    return d


@router.get("/ai/settings")
def get_settings():
    return _get_settings()


@router.get("/ai/ollama/models")
def get_ollama_models():
    return ollama_client.list_models()


@router.patch("/ai/settings")
def patch_settings(body: SettingsPatch):
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    with get_conn() as conn:
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE settings SET {sets} WHERE id = 1", (*fields.values(),)
            )
    from config import settings
    settings.reload()
    if "vault_dir" in fields:
        from services.vault import sync_db_with_vault
        sync_db_with_vault()
    return _get_settings()


def _query_keywords(text: str) -> list[str]:
    words: list[str] = []
    if kiwi:
        try:
            words = [
                t.form for t in kiwi.tokenize(text)
                if t.tag in ("NNG", "NNP", "SL", "SH")
            ]
        except Exception:
            words = []
    if not words:
        words = [strip_korean_particles(w) for w in re.findall(r"[0-9A-Za-z가-힣]+", text)]

    seen: set[str] = set()
    keywords = []
    for w in words:
        key = w.casefold()
        if len(w) < 2 or key in seen or is_korean_stopword_or_ending(w):
            continue
        seen.add(key)
        keywords.append(w)
    return keywords[:RAG_MAX_KEYWORDS]


def _excerpt(content: str, keywords: list[str]) -> str:
    lower = content.casefold()
    hits = [p for p in (lower.find(k.casefold()) for k in keywords if k) if p >= 0]
    start = max(0, min(hits) - RAG_EXCERPT // 4) if hits else 0
    return content[start:start + RAG_EXCERPT]


def _keyword_scores(conn, keywords: list[str], scope: str, scope_params: list) -> dict:
    """질문 키워드로 노트를 점수화 → {note_id: (점수, 가장 크게 기여한 키워드, row)}."""
    if not keywords:
        return {}
    cond = " OR ".join("title LIKE ? OR content LIKE ?" for _ in keywords)
    like_params = [p for k in keywords for p in (f"%{k}%", f"%{k}%")]
    rows = conn.execute(
        f"SELECT id, title, content, modified_at FROM notes WHERE {scope} AND ({cond})",
        (*scope_params, *like_params),
    ).fetchall()
    total = conn.execute(
        f"SELECT COUNT(*) FROM notes WHERE {scope}", scope_params
    ).fetchone()[0]

    docs = [
        (r, (r["title"] or "").casefold(), (r["content"] or "").casefold())
        for r in rows
    ]
    # 흔한 단어("방법", "정리")가 드문 고유명사를 압도하지 않도록 IDF 가중
    idf = {}
    for k in keywords:
        kl = k.casefold()
        df = sum(1 for _, t, c in docs if kl in t or kl in c)
        idf[k] = math.log(1 + total / df) if df else 0.0

    scored = {}
    for r, title, content in docs:
        score, top_kw, top = 0.0, "", 0.0
        for k in keywords:
            kl = k.casefold()
            part = 3 * idf[k] if kl in title else 0.0
            count = content.count(kl)
            if count:
                part += idf[k] * (1 + math.log(count))
            score += part
            if part > top:
                top_kw, top = k, part
        if score > 0:
            scored[r["id"]] = (score, top_kw, r)
    return scored


def _retrieve_notes(conn, query: str, category_id, exclude_id, fallback_recent: bool = True,
                    context_note_id: Optional[str] = None) -> list[dict]:
    """질문과 관련된 노트를 고른다 → [{id, title, excerpt, reason}].

    지식 그래프 점수(개념 관계를 따라 확장)와 키워드 점수를 0.6 : 0.4로 합친다.
    그래프 출발 개념이 없으면 키워드만, 그것도 없으면 최근 노트로 대체.
    """
    scope = "is_archived = 0"
    scope_params: list = []
    if category_id:
        scope += " AND category_id = ?"
        scope_params.append(category_id)
    if exclude_id:
        scope += " AND id != ?"
        scope_params.append(exclude_id)

    keywords = _query_keywords(query)
    kw = _keyword_scores(conn, keywords, scope, scope_params)
    graph = graph_retrieval.graph_note_scores(
        conn, query, category_id, exclude_id, context_note_id=context_note_id
    )

    if kw or graph:
        kw_max = max((v[0] for v in kw.values()), default=0.0) or 1.0
        g_max = max((v.score for v in graph.values()), default=0.0) or 1.0
        combined = []
        for nid in set(kw) | set(graph):
            k_part = kw[nid][0] / kw_max if nid in kw else 0.0
            g_part = graph[nid].score / g_max if nid in graph else 0.0
            score = (GRAPH_WEIGHT * g_part + KEYWORD_WEIGHT * k_part) if graph else k_part
            combined.append((score, nid))
        combined.sort(reverse=True)
        top = [nid for _, nid in combined[:RAG_LIMIT]]

        # 그래프로만 뽑힌 노트는 본문을 따로 읽는다
        rows = {nid: kw[nid][2] for nid in top if nid in kw}
        missing = [nid for nid in top if nid not in rows]
        if missing:
            ph = ",".join("?" * len(missing))
            for r in conn.execute(
                f"SELECT id, title, content FROM notes WHERE id IN ({ph})", missing
            ):
                rows[r["id"]] = r

        out = []
        for nid in top:
            r = rows[nid]
            if nid in graph:
                hit = graph[nid].concept
                reason = graph_retrieval.format_path(hit)
                terms = [*graph_retrieval.path_terms(hit), *keywords]
            else:
                reason = f"키워드 '{kw[nid][1]}' 일치"
                terms = keywords
            out.append({
                "id": nid,
                "title": r["title"],
                "excerpt": _excerpt(r["content"] or "", terms),
                "reason": reason,
            })
        return out

    if not fallback_recent:
        return []

    rows = conn.execute(
        f"SELECT id, title, content FROM notes WHERE {scope} ORDER BY modified_at DESC LIMIT ?",
        (*scope_params, RAG_LIMIT),
    ).fetchall()
    return [
        {"id": r["id"], "title": r["title"], "excerpt": (r["content"] or "")[:RAG_EXCERPT],
         "reason": "최근 노트"}
        for r in rows
    ]


def _build_system(req: ChatRequest) -> tuple[str, list[dict]]:
    """컨텍스트(현재 노트/RAG/위키)를 system 프롬프트로 구성 → (프롬프트, 근거 노트 목록)."""
    sources: list[dict] = []
    parts = [
        "You are SpaceNote's helpful assistant. "
        "Answer in the same language the user writes in."
    ]
    with get_conn() as conn:
        if req.context_note_id:
            row = conn.execute(
                "SELECT title, content FROM notes WHERE id = ?",
                (req.context_note_id,),
            ).fetchone()
            if row:
                parts.append(f"[현재 노트] {row['title']}\n{row['content']}")

        if req.use_rag:
            # 후속 질문("그건 왜?")도 주제를 잃지 않도록 최근 사용자 발화 2개를 합쳐 검색
            user_turns = [m.content for m in req.messages if m.role == "user"]
            query = "\n".join(user_turns[-2:])
            notes = _retrieve_notes(
                conn, query, req.context_category_id, req.context_note_id,
                context_note_id=req.context_note_id,
            )
            ctx = "\n\n".join(
                f"# {n['title']}\n(선택 근거: {n['reason']})\n{n['excerpt']}" for n in notes
            )
            if ctx:
                parts.append("[참고 노트]\n" + ctx)
            sources = [{"id": n["id"], "title": n["title"], "path": n["reason"]} for n in notes]

        if req.use_wiki:
            rows = conn.execute(
                "SELECT title FROM notes ORDER BY modified_at DESC LIMIT 100"
            ).fetchall()
            titles = ", ".join(r["title"] for r in rows)
            if titles:
                parts.append("[위키 노트 목록]\n" + titles)

    return "\n\n".join(parts), sources


@router.get("/ai/retrieve")
def retrieve(q: str = "", category_id: Optional[str] = None):
    """외부 에이전트(aibot 등)용: 질문과 관련된 노트를 점수순으로 반환."""
    if not q.strip():
        return []
    with get_conn() as conn:
        notes = _retrieve_notes(conn, q, category_id, None, fallback_recent=False)
    return [
        {"id": n["id"], "title": n["title"], "excerpt": n["excerpt"], "reason": n["reason"]}
        for n in notes
    ]


def _client_for(model: str):
    """모델 이름으로 제공자 선택 (ollama:* → Ollama, gemini-* → Google, claude-* → Anthropic, gpt-* → OpenAI)."""
    if ollama_client.is_ollama_model(model):
        return ollama_client, ollama_client.model_name(model)
    if model.startswith("gemini"):
        return gemini_client, model
    if model.startswith("claude"):
        return anthropic_client, model
    return openai_client, model


@router.post("/ai/chat")
def chat(req: ChatRequest):
    system, sources = _build_system(req)
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    client, model = _client_for(req.model)

    def gen():
        try:
            # 답변 텍스트보다 먼저 근거 노트를 한 번 보낸다 (화면에서 답변 아래에 표시)
            if sources:
                yield f"data: {json.dumps({'sources': sources}, ensure_ascii=False)}\n"
            for text in client.stream_chat(model, system, messages):
                yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n"
            yield "data: [DONE]\n"
        except Exception as e:  # noqa: BLE001 - 스트림 중 오류를 클라이언트로 전달
            yield f"data: {json.dumps({'error': str(e)})}\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/ai/summarize/{note_id}")
def summarize(note_id: str):
    """노트 본문을 채팅 모델로 정리·요약해 돌려준다. 저장은 하지 않는다 — 적용 여부는 화면에서 사용자가 정한다."""
    with get_conn() as conn:
        row = conn.execute("SELECT content FROM notes WHERE id = ?", (note_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Note not found")
    content = (row["content"] or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="요약할 내용이 없습니다")

    client, model = _client_for(_get_settings()["default_model"])
    try:
        summary = "".join(
            client.stream_chat(model, SUMMARY_SYSTEM, [{"role": "user", "content": content}])
        ).strip()
    except Exception as e:  # noqa: BLE001 - 제공자 오류 메시지를 화면에 그대로 보여 준다
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"summary": summary}
