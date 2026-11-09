import json
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

import zipfile

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from db import get_conn
from models import ChatGPTImport, MdFilesImport, NoteCreate, NotePatch
from services import chatgpt_share, gemini_share, vault
from services import extraction, note_import
from services import graph_extraction
from services.tagparse import extract_tags
from services.textnorm import norm_name

router = APIRouter()
logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# 가져온 대화 노트는 created_at이 가져온 시각으로 몰려 있어, 본문 머리의 원래 시각을 따로 내려 준다
_ORIGIN_DATE = re.compile(r"\*\*생성 일시\*\*:\s*(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)")
_ORIGIN_HEAD_CHARS = 1000
# 목록은 사이드바가 열릴 때마다 받으므로 본문을 뺀다 — origin_at 계산에 필요한 머리만 읽는다
_LIST_COLUMNS = (
    f"id, path, title, substr(content, 1, {_ORIGIN_HEAD_CHARS}) AS content, category_id, tags, "
    "word_count, analysis_status, created_at, modified_at, is_favorite, is_archived, "
    "graph_status, graph_hash, graph_error"
)


def _origin_at(content: str | None) -> str | None:
    m = _ORIGIN_DATE.search((content or "")[:_ORIGIN_HEAD_CHARS])
    return f"{m[1]}T{m[2]}" if m else None


def _row_to_note(row) -> dict:
    d = dict(row)
    d["origin_at"] = _origin_at(d.get("content"))
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


def _run_extraction(note_id: str, content: str) -> bool:
    """백그라운드: 엔티티 추출 후 저장 + analysis_status 갱신. 성공 여부를 돌려준다."""
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
        return True
    except Exception:
        logger.exception("entity extraction failed for note %s", note_id)
        with get_conn() as conn:
            conn.execute(
                "UPDATE notes SET analysis_status = 'failed' WHERE id = ?", (note_id,)
            )
        return False


def _run_extraction_python(note_id: str, content: str) -> bool:
    """백그라운드: 파이썬 기반 엔티티 추출 후 저장 + analysis_status 갱신. 성공 여부를 돌려준다."""
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
        return True
    except Exception:
        logger.exception("python entity extraction failed for note %s", note_id)
        with get_conn() as conn:
            conn.execute(
                "UPDATE notes SET analysis_status = 'failed' WHERE id = ?", (note_id,)
            )
        return False


# ── 일괄 키워드 분석 진행 상황 ─────────────────────────────
# BackgroundTasks는 서버 메모리에서 돌므로 진행 수도 메모리에 둔다. DB의 analysis_status='pending'은
# 편집·볼트 동기화로도 생기고 재시작하면 처리되지 않은 채 남으므로 진행률 계산에 쓰지 않는다.
_job_lock = threading.Lock()
_job = {"kind": None, "total": 0, "done": 0, "failed": 0, "started_at": None}


def _job_remaining() -> int:
    return _job["total"] - _job["done"] - _job["failed"] if _job["kind"] else 0


def _busy() -> Optional[dict]:
    """일괄 분석이 아직 돌고 있으면 새로 쌓지 않는다 — 두 번 누르면 같은 노트를 중복으로 분석하게 된다."""
    with _job_lock:
        remaining = _job_remaining()
    return {"queued": remaining, "running": True} if remaining > 0 else None


def _start_batch(kind: str, rows, fn, bg: BackgroundTasks) -> dict:
    with _job_lock:
        _job.update(kind=kind, total=len(rows), done=0, failed=0, started_at=_now())
    bg.add_task(_run_batch, [(r["id"], r["content"]) for r in rows], fn)
    return {"queued": len(rows)}


def _run_batch(items: list[tuple[str, str]], fn) -> None:
    for nid, content in items:
        ok = fn(nid, content)
        with _job_lock:
            _job["done" if ok else "failed"] += 1


@router.get("/notes/analyze/progress")
def analyze_progress():
    """마지막 일괄 키워드 분석(kind: ai | python)의 진행 수. 서버가 재시작되면 초기화된다."""
    with _job_lock:
        return {**_job, "running": _job_remaining() > 0}


@router.get("/notes")
def list_notes(category_id: Optional[str] = None, archived: bool = False):
    where = "is_archived = 1" if archived else "is_archived = 0"
    with get_conn() as conn:
        if category_id:
            rows = conn.execute(
                f"SELECT {_LIST_COLUMNS} FROM notes WHERE {where} AND category_id = ? "
                "ORDER BY modified_at DESC",
                (category_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {_LIST_COLUMNS} FROM notes WHERE {where} ORDER BY modified_at DESC"
            ).fetchall()
    notes = [_row_to_note(r) for r in rows]
    for note in notes:
        del note["content"]
    return notes


def _require_api_key() -> None:
    if not extraction.has_api_key():
        raise HTTPException(
            status_code=400,
            detail="AI 설정이 완료되지 않았습니다 (API 키를 저장하거나 로컬 Ollama 모델을 선택하세요)",
        )


@router.post("/notes/analyze")
def analyze_all(bg: BackgroundTasks):
    """내용이 있는 pending/failed/analyzed_py 노트 전체를 백그라운드로 재분석."""
    _require_api_key()
    if busy := _busy():
        return busy
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, content FROM notes "
            "WHERE TRIM(COALESCE(content, '')) != '' "
            "AND analysis_status IN ('pending', 'failed', 'analyzed_py') "
            "AND is_archived = 0"
        ).fetchall()
        for r in rows:
            conn.execute(
                "UPDATE notes SET analysis_status = 'pending' WHERE id = ?",
                (r["id"],),
            )
    return _start_batch("ai", rows, _run_extraction, bg)


@router.post("/notes/analyze-python")
def analyze_all_python(bg: BackgroundTasks):
    """내용이 있는 모든 노트를 파이썬으로 분석 (API 키 불필요)."""
    if busy := _busy():
        return busy
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
    return _start_batch("python", rows, _run_extraction_python, bg)


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
