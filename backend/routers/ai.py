import json
import math
import re

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from db import get_conn
from models import SettingsPatch, ChatRequest
from services import anthropic_client, gemini_client, ollama_client
from services.extraction import kiwi, is_korean_stopword_or_ending, strip_korean_particles

router = APIRouter()

RAG_LIMIT = 5
RAG_EXCERPT = 1200
RAG_MAX_KEYWORDS = 8


def _get_settings() -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    d = dict(row)
    d.pop("id", None)
    return d


@router.get("/ai/settings")
def get_settings():
    return _get_settings()


@router.get("/ai/models/ollama")
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
    hits = [p for p in (lower.find(k.casefold()) for k in keywords) if p >= 0]
    start = max(0, min(hits) - RAG_EXCERPT // 4) if hits else 0
    return content[start:start + RAG_EXCERPT]


def _retrieve_notes(conn, query: str, category_id, exclude_id) -> list:
    """질문 키워드로 관련 노트를 점수화해 고른다. 매칭이 없으면 최근 노트로 대체."""
    scope = "is_archived = 0"
    scope_params: list = []
    if category_id:
        scope += " AND category_id = ?"
        scope_params.append(category_id)
    if exclude_id:
        scope += " AND id != ?"
        scope_params.append(exclude_id)

    keywords = _query_keywords(query)
    if keywords:
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

        scored = []
        for r, title, content in docs:
            score = 0.0
            for k in keywords:
                kl = k.casefold()
                if kl in title:
                    score += 3 * idf[k]
                count = content.count(kl)
                if count:
                    score += idf[k] * (1 + math.log(count))
            if score > 0:
                scored.append((score, r["modified_at"] or "", r))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        if scored:
            return [
                (r["title"], _excerpt(r["content"] or "", keywords))
                for _, _, r in scored[:RAG_LIMIT]
            ]

    rows = conn.execute(
        f"SELECT title, content FROM notes WHERE {scope} ORDER BY modified_at DESC LIMIT ?",
        (*scope_params, RAG_LIMIT),
    ).fetchall()
    return [(r["title"], (r["content"] or "")[:RAG_EXCERPT]) for r in rows]


def _build_system(req: ChatRequest) -> str:
    """컨텍스트(현재 노트/RAG/위키)를 system 프롬프트로 구성."""
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
                conn, query, req.context_category_id, req.context_note_id
            )
            ctx = "\n\n".join(f"# {title}\n{body}" for title, body in notes)
            if ctx:
                parts.append("[참고 노트]\n" + ctx)

        if req.use_wiki:
            rows = conn.execute(
                "SELECT title FROM notes ORDER BY modified_at DESC LIMIT 100"
            ).fetchall()
            titles = ", ".join(r["title"] for r in rows)
            if titles:
                parts.append("[위키 노트 목록]\n" + titles)

    return "\n\n".join(parts)


@router.post("/ai/chat")
def chat(req: ChatRequest):
    system = _build_system(req)
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    # 모델 이름으로 제공자 선택 (gemini-* → Google, claude-* → Anthropic, 그 외 → Ollama)
    if req.model.startswith("gemini"):
        client = gemini_client
    elif req.model.startswith("claude"):
        client = anthropic_client
    else:
        client = ollama_client

    def gen():
        try:
            for text in client.stream_chat(req.model, system, messages):
                yield f"data: {json.dumps({'text': text})}\n"
            yield "data: [DONE]\n"
        except Exception as e:  # noqa: BLE001 - 스트림 중 오류를 클라이언트로 전달
            yield f"data: {json.dumps({'error': str(e)})}\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
