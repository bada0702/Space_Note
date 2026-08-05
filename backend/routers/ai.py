import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from db import get_conn
from models import SettingsPatch, ChatRequest
from services import anthropic_client, gemini_client, ollama_client

router = APIRouter()


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
            if req.context_category_id:
                rows = conn.execute(
                    "SELECT title, content FROM notes WHERE category_id = ? "
                    "ORDER BY modified_at DESC LIMIT 5",
                    (req.context_category_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT title, content FROM notes ORDER BY modified_at DESC LIMIT 5"
                ).fetchall()
            ctx = "\n\n".join(
                f"# {r['title']}\n{(r['content'] or '')[:1000]}" for r in rows
            )
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
