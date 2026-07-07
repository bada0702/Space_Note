import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response

from db import get_conn
from models import NoteCreate, NotePatch
from services import vault
from services import extraction
from services.tagparse import extract_tags
from services.textnorm import norm_name

router = APIRouter()
logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_note(row) -> dict:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["is_favorite"] = bool(d.get("is_favorite"))
    d["is_archived"] = bool(d.get("is_archived"))
    return d


def _sync_tags(conn, note_id: str, content: str) -> None:
    """본문 인라인 #태그를 파싱해 tags 테이블을 최신 상태로 맞춘다 (AI 호출 없음, 동기 처리)."""
    conn.execute("DELETE FROM tags WHERE note_id = ?", (note_id,))
    now = _now()
    for tag in extract_tags(content):
        conn.execute(
            "INSERT INTO tags (id, note_id, tag, norm, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), note_id, tag, norm_name(tag), now),
        )


def _run_extraction(note_id: str, content: str) -> None:
    """백그라운드: 엔티티 추출 후 저장 + analysis_status 갱신."""
    try:
        entities = extraction.extract_entities(content)
        now = _now()
        with get_conn() as conn:
            conn.execute("DELETE FROM entities WHERE note_id = ?", (note_id,))
            for e in entities:
                conn.execute(
                    "INSERT INTO entities (id, note_id, name, type, norm, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), note_id, e["name"], e["type"],
                     norm_name(e["name"]), now),
                )
            conn.execute(
                "UPDATE notes SET analysis_status = 'analyzed' WHERE id = ?", (note_id,)
            )
    except Exception:
        logger.exception("entity extraction failed for note %s", note_id)
        with get_conn() as conn:
            conn.execute(
                "UPDATE notes SET analysis_status = 'failed' WHERE id = ?", (note_id,)
            )


@router.get("/notes")
def list_notes(category_id: Optional[str] = None, archived: bool = False):
    where = "is_archived = 1" if archived else "is_archived = 0"
    with get_conn() as conn:
        if category_id:
            rows = conn.execute(
                f"SELECT * FROM notes WHERE {where} AND category_id = ? "
                "ORDER BY modified_at DESC",
                (category_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM notes WHERE {where} ORDER BY modified_at DESC"
            ).fetchall()
    return [_row_to_note(r) for r in rows]


def _require_api_key() -> None:
    if not extraction.has_api_key():
        raise HTTPException(
            status_code=400,
            detail="AI API 키가 설정되지 않았습니다 (설정에서 Anthropic 또는 Google 키를 저장하세요)",
        )


@router.post("/notes/analyze")
def analyze_all(bg: BackgroundTasks):
    """내용이 있는 pending/failed 노트 전체를 백그라운드로 재분석."""
    _require_api_key()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, content FROM notes "
            "WHERE TRIM(COALESCE(content, '')) != '' "
            "AND analysis_status IN ('pending', 'failed') "
            "AND is_archived = 0"
        ).fetchall()
        for r in rows:
            conn.execute(
                "UPDATE notes SET analysis_status = 'pending' WHERE id = ?",
                (r["id"],),
            )
    for r in rows:
        bg.add_task(_run_extraction, r["id"], r["content"])
    return {"queued": len(rows)}


@router.post("/notes/{nid}/analyze")
def analyze_one(nid: str, bg: BackgroundTasks):
    _require_api_key()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, content FROM notes WHERE id = ?", (nid,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Note not found")
    with get_conn() as conn:
        conn.execute(
            "UPDATE notes SET analysis_status = 'pending' WHERE id = ?", (nid,)
        )
    bg.add_task(_run_extraction, nid, row["content"] or "")
    return {"queued": 1}


@router.post("/notes")
def create_note(body: NoteCreate, bg: BackgroundTasks):
    nid = str(uuid.uuid4())
    now = _now()
    content = body.content or ""
    tags: list[str] = []
    path = vault.write_md(body.title, content, tags)
    word_count = len(content.split())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO notes (id, path, title, content, category_id, tags, "
            "word_count, analysis_status, created_at, modified_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (nid, path, body.title, content, body.category_id,
             json.dumps(tags), word_count, now, now),
        )
        _sync_tags(conn, nid, content)
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (nid,)).fetchone()
    if content.strip():
        bg.add_task(_run_extraction, nid, content)
    return _row_to_note(row)


@router.get("/notes/{nid}")
def get_note(nid: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (nid,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="note not found")
    return _row_to_note(row)


@router.patch("/notes/{nid}")
def update_note(nid: str, body: NotePatch, bg: BackgroundTasks):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (nid,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="note not found")
        current = _row_to_note(row)

        fields = body.model_dump(exclude_unset=True)
        content_touched = any(
            k in fields for k in ("title", "content", "category_id", "tags")
        )

        new_title = body.title if body.title is not None else current["title"]
        new_content = body.content if body.content is not None else current["content"]
        new_category = (
            body.category_id if "category_id" in fields
            else current["category_id"]
        )
        new_tags = body.tags if body.tags is not None else current["tags"]
        new_favorite = (
            body.is_favorite if body.is_favorite is not None
            else current["is_favorite"]
        )
        new_archived = (
            body.is_archived if body.is_archived is not None
            else current["is_archived"]
        )
        word_count = len(new_content.split())
        content_changed = body.content is not None and new_content != current["content"]
        analysis_status = "pending" if content_changed else current["analysis_status"]

        # 플래그만 바꾸는 PATCH는 vault 파일과 modified_at을 건드리지 않는다
        now = _now() if content_touched else current["modified_at"]
        if content_touched:
            if new_title != current["title"]:
                vault.delete_md(current["title"])
            path = vault.write_md(new_title, new_content, new_tags)
        else:
            path = current["path"]

        conn.execute(
            "UPDATE notes SET title = ?, content = ?, category_id = ?, tags = ?, "
            "word_count = ?, path = ?, modified_at = ?, analysis_status = ?, "
            "is_favorite = ?, is_archived = ? WHERE id = ?",
            (new_title, new_content, new_category, json.dumps(new_tags),
             word_count, path, now, analysis_status,
             int(new_favorite), int(new_archived), nid),
        )
        if content_changed:
            _sync_tags(conn, nid, new_content)
        updated = conn.execute("SELECT * FROM notes WHERE id = ?", (nid,)).fetchone()

    if content_changed and new_content.strip():
        bg.add_task(_run_extraction, nid, new_content)
    return _row_to_note(updated)


@router.delete("/notes/{nid}", status_code=204)
def delete_note(nid: str):
    with get_conn() as conn:
        row = conn.execute("SELECT title FROM notes WHERE id = ?", (nid,)).fetchone()
        if row is not None:
            vault.delete_md(row["title"])
        conn.execute("DELETE FROM notes WHERE id = ?", (nid,))
        conn.execute("DELETE FROM entities WHERE note_id = ?", (nid,))
        conn.execute("DELETE FROM tags WHERE note_id = ?", (nid,))
    return Response(status_code=204)
