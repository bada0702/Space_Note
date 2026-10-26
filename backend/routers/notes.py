import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import zipfile

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from db import get_conn
from models import ChatGPTImport, MdFilesImport, NoteCreate, NotePatch
from services import chatgpt_share, gemini_share, vault
from services import extraction, note_import
from services import graph_extraction, graph_worker
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
    if d.get("analysis_status") in ("analyzed_ai", "analyzed_py"):
        d["analysis_status"] = "analyzed"
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
                "UPDATE notes SET analysis_status = 'analyzed_ai' WHERE id = ?", (note_id,)
            )
    except Exception:
        logger.exception("entity extraction failed for note %s", note_id)
        with get_conn() as conn:
            conn.execute(
                "UPDATE notes SET analysis_status = 'failed' WHERE id = ?", (note_id,)
            )


def _run_extraction_python(note_id: str, content: str) -> None:
    """백그라운드: 파이썬 기반 엔티티 추출 후 저장 + analysis_status 갱신."""
    try:
        entities = extraction.extract_entities_python(content)
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
                "UPDATE notes SET analysis_status = 'analyzed_py' WHERE id = ?", (note_id,)
            )
    except Exception:
        logger.exception("python entity extraction failed for note %s", note_id)
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


def _require_graph_model() -> None:
    reason = graph_extraction.model_ready()
    if reason:
        raise HTTPException(status_code=400, detail=reason)


@router.post("/notes/analyze")
def analyze_all():
    """AI 항로분석: 온톨로지가 아직 없거나 본문이 바뀐 노트를 지식 그래프 추출 대기열에 넣는다.

    처리는 graph_worker가 분당 RATE_PER_MINUTE개씩 하고, 진행 상황은 GET /graph/status로 본다.
    """
    _require_graph_model()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, content, graph_hash FROM notes "
            "WHERE TRIM(COALESCE(content, '')) != '' AND is_archived = 0"
        ).fetchall()
        targets = [
            r["id"] for r in rows
            if r["graph_hash"] != graph_extraction.content_hash(r["content"])
        ]
        for nid in targets:
            conn.execute("UPDATE notes SET graph_status = 'pending' WHERE id = ?", (nid,))
    graph_worker.start()
    return {"queued": len(targets)}


@router.post("/notes/analyze-python")
def analyze_all_python(bg: BackgroundTasks):
    """내용이 있는 모든 노트를 파이썬으로 분석 (API 키 불필요)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, content FROM notes "
            "WHERE TRIM(COALESCE(content, '')) != '' "
            "AND is_archived = 0"
        ).fetchall()
        for r in rows:
            conn.execute(
                "UPDATE notes SET analysis_status = 'pending' WHERE id = ?",
                (r["id"],),
            )
    for r in rows:
        bg.add_task(_run_extraction_python, r["id"], r["content"])
    return {"queued": len(rows)}


@router.post("/notes/{nid}/analyze")
def analyze_one(nid: str):
    """이 노트만 본문이 그대로여도 다시 추출한다 (해시를 지워 강제)."""
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM notes WHERE id = ?", (nid,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Note not found")
    _require_graph_model()
    with get_conn() as conn:
        conn.execute(
            "UPDATE notes SET graph_status = 'pending', graph_hash = NULL WHERE id = ?", (nid,)
        )
    graph_worker.start()
    return {"queued": 1}


@router.post("/notes/{nid}/analyze-python")
def analyze_one_python(nid: str, bg: BackgroundTasks):
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
    bg.add_task(_run_extraction_python, nid, row["content"] or "")
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
            "word_count, analysis_status, graph_status, created_at, modified_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 'pending', ?, ?)",
            (nid, path, body.title, content, body.category_id,
             json.dumps(tags), word_count, now, now),
        )
        _sync_tags(conn, nid, content)
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (nid,)).fetchone()
    if content.strip():
        bg.add_task(_run_extraction, nid, content)
    return _row_to_note(row)


def _unique_title(title: str) -> str:
    """같은 이름의 노트/파일이 있으면 _2, _3…을 붙인다 (create_note는 같은 파일명을 덮어쓴다)."""
    with get_conn() as conn:
        taken = {r["title"] for r in conn.execute("SELECT title FROM notes")}
    candidate, n = title, 1
    while candidate in taken or vault.md_path(candidate).exists():
        n += 1
        candidate = f"{title}_{n}"
    return candidate


@router.post("/notes/import/chatgpt")
def import_chatgpt(body: ChatGPTImport, bg: BackgroundTasks):
    """ChatGPT·Gemini 공유 링크의 대화를 새 노트로 만든다."""
    try:
        if gemini_share.is_gemini_url(body.url):
            url = gemini_share.normalize_share_url(body.url)
            conv = gemini_share.parse_batchexecute(gemini_share.fetch_share_data(url))
        else:
            url = chatgpt_share.normalize_share_url(body.url)
            conv = chatgpt_share.parse_share_html(chatgpt_share.fetch_share_html(url))
    except chatgpt_share.ShareImportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 볼트 노트 제목 관례: 공백 대신 밑줄
    title = _unique_title(vault.safe_filename(conv.title).replace(" ", "_"))
    content = chatgpt_share.to_markdown(conv, url)
    return create_note(NoteCreate(title=title, category_id=body.category_id, content=content), bg)


_MAX_ZIP_BYTES = 200 * 1024 * 1024


@router.post("/notes/import/files")
def import_md_files(body: MdFilesImport):
    """폴더에서 읽은 .md 파일들(상대 경로 + 본문)을 노트로 등록한다."""
    return note_import.import_md_files([(f.path, f.content) for f in body.files])


@router.post("/notes/import/zip")
async def import_md_zip(request: Request):
    """raw body로 받은 zip 안의 .md 파일들을 노트로 등록한다."""
    data = await request.body()
    if len(data) > _MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail="파일이 너무 큽니다 (최대 200MB)")
    try:
        files = note_import.read_zip(data)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="zip 파일을 읽을 수 없습니다")
    return note_import.import_md_files(files)


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
        graph_status = "pending" if content_changed else row["graph_status"]

        # 플래그만 바꾸는 PATCH는 vault 파일과 modified_at을 건드리지 않는다
        now = _now() if content_touched else current["modified_at"]
        if content_touched:
            if new_title != current["title"]:
                vault.delete_md(current["path"])
            path = vault.write_md(new_title, new_content, new_tags, existing_path=current["path"])
        else:
            path = current["path"]

        conn.execute(
            "UPDATE notes SET title = ?, content = ?, category_id = ?, tags = ?, "
            "word_count = ?, path = ?, modified_at = ?, analysis_status = ?, graph_status = ?, "
            "is_favorite = ?, is_archived = ? WHERE id = ?",
            (new_title, new_content, new_category, json.dumps(new_tags),
             word_count, path, now, analysis_status, graph_status,
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
        row = conn.execute("SELECT path FROM notes WHERE id = ?", (nid,)).fetchone()
        if row is not None:
            vault.delete_md(row["path"])
        conn.execute("DELETE FROM notes WHERE id = ?", (nid,))
        conn.execute("DELETE FROM entities WHERE note_id = ?", (nid,))
        conn.execute("DELETE FROM tags WHERE note_id = ?", (nid,))
        conn.execute("DELETE FROM routes WHERE note_a = ? OR note_b = ?", (nid, nid))
        graph_extraction.clear_note_graph(conn, nid)
        graph_extraction.gc_orphans(conn)
    return Response(status_code=204)
