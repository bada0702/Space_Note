import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response

from db import get_conn
from models import NoteCreate, NotePatch
from services import vault
from services import anthropic_client

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_note(row) -> dict:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d


def _run_extraction(note_id: str, content: str) -> None:
    """백그라운드: 엔티티 추출 후 저장 + analysis_status 갱신."""
    try:
        entities = anthropic_client.extract_entities(content)
        now = _now()
        with get_conn() as conn:
            conn.execute("DELETE FROM entities WHERE note_id = ?", (note_id,))
            for e in entities:
                conn.execute(
                    "INSERT INTO entities (id, note_id, name, type, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), note_id, e["name"], e["type"], now),
                )
            conn.execute(
                "UPDATE notes SET analysis_status = 'analyzed' WHERE id = ?", (note_id,)
            )
    except Exception:
        with get_conn() as conn:
            conn.execute(
                "UPDATE notes SET analysis_status = 'failed' WHERE id = ?", (note_id,)
            )


@router.get("/notes")
def list_notes(category_id: Optional[str] = None):
    with get_conn() as conn:
        if category_id:
            rows = conn.execute(
                "SELECT * FROM notes WHERE category_id = ? ORDER BY modified_at DESC",
                (category_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM notes ORDER BY modified_at DESC"
            ).fetchall()
    return [_row_to_note(r) for r in rows]


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

        new_title = body.title if body.title is not None else current["title"]
        new_content = body.content if body.content is not None else current["content"]
        new_category = (
            body.category_id if "category_id" in body.model_dump(exclude_unset=True)
            else current["category_id"]
        )
        new_tags = body.tags if body.tags is not None else current["tags"]
        now = _now()
        word_count = len(new_content.split())

        if new_title != current["title"]:
            vault.delete_md(current["title"])
        path = vault.write_md(new_title, new_content, new_tags)

        conn.execute(
            "UPDATE notes SET title = ?, content = ?, category_id = ?, tags = ?, "
            "word_count = ?, path = ?, modified_at = ?, analysis_status = 'pending' "
            "WHERE id = ?",
            (new_title, new_content, new_category, json.dumps(new_tags),
             word_count, path, now, nid),
        )
        updated = conn.execute("SELECT * FROM notes WHERE id = ?", (nid,)).fetchone()

    if body.content is not None and new_content.strip():
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
    return Response(status_code=204)
