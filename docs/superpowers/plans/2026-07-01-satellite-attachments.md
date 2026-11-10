# 위성(Satellite/첨부) 기능 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 노트(행성)에 종속되는 첨부 자료(파일/링크/메모)를 "위성"으로 추가하고, 편집기 UI·StarMap 3D 궤도·AI 인덱싱까지 연동한다.

**Architecture:** 백엔드는 FastAPI + SQLite로 `attachments` 테이블과 라우터/서비스를 추가한다. 파일은 `VAULT_DIR/attachments/<note_id>/` 아래에 UUID 파일명으로 저장한다. 텍스트 계열 위성(메모/링크 설명/코드·텍스트 파일)의 내용은 소속 노트의 엔티티 추출·RAG·검색에 합류한다. 프론트는 Zustand 스토어 + 편집기 '위성' 탭 + three.js 자식 메시로 위성을 표현한다.

**Tech Stack:** Python 3 / FastAPI / SQLite / pytest (backend), React 18 / TypeScript / Zustand / three.js / Vite (frontend).

## Global Constraints

- 백엔드 스키마·필드는 **영문 스네이크케이스**, 기존 `categories`/`notes`/`entities` 스타일(TEXT PK, ISO 문자열 타임스탬프)을 따른다.
- 모든 파일 경로는 반드시 `VAULT_DIR` 내부임을 resolve 후 검증한다(경로 이탈 차단). 실패 시 `ValueError`.
- 백엔드 테스트는 `backend/` 디렉터리에서 `pytest`로 실행한다. 테스트는 `conftest.py`의 `client` fixture와 `AUTH` 헤더를 사용한다.
- 프론트엔드는 테스트 러너가 없다. 검증은 `npm run build`(= `tsc && vite build`, 타입체크 포함) + 명시된 수동 확인으로 한다.
- 인증: 모든 신규 라우터는 `main.py`에서 `dependencies=[Depends(require_auth)]`로 등록한다. 프론트 요청은 기존 `client.ts`의 토큰 헤더를 재사용한다.
- 위성 스키마 종류는 3종(`file`/`link`/`memo`). PDF/이미지/코드는 모두 `file`이며 `mime`으로 구분한다. UI 아이콘만 5종으로 노출한다.
- PDF/이미지 **텍스트 추출은 하지 않는다**(비범위). 텍스트 계열 파일만 `text_content`를 채운다.

---

## File Structure

**Backend (신규):**
- `backend/services/attachments.py` — 파일 저장/삭제/경로안전/텍스트추출 + 인덱싱 텍스트 조회
- `backend/routers/attachments.py` — 위성 CRUD·업로드·다운로드·벌크 API

**Backend (수정):**
- `backend/db.py` — `attachments` 테이블 추가
- `backend/models.py` — `LinkCreate`, `MemoCreate`, `AttachmentOut`
- `backend/main.py` — attachments 라우터 등록
- `backend/routers/notes.py` — `_run_extraction`에 위성 텍스트 합류, `delete_note` cascade
- `backend/routers/ai.py` — RAG 컨텍스트에 위성 텍스트 append
- `backend/routers/search.py` — 위성 `text_content` 검색 포함

**Frontend (신규):**
- `src/api/attachmentsApi.ts` — 위성 API 래퍼(멀티파트 업로드 포함)
- `src/store/attachmentsStore.ts` — 위성 상태·CRUD
- `src/components/Editor/SatellitePanel.tsx` — 위성 조회/추가/삭제 UI

**Frontend (수정):**
- `src/types/index.ts` — `Attachment` 인터페이스, `EditorTab`에 `'satellite'` 추가
- `src/api/client.ts` — 인증 전용 헤더(멀티파트용) 추가
- `src/components/Editor/EditorTabs.tsx` — '위성' 탭 버튼
- `src/App.tsx` — `activeTab === 'satellite'` 렌더 분기
- `src/components/StarMap/StarMapCanvas.tsx` — 위성 자식 메시 렌더 + 벌크 로드

---

## Task 1: attachments 테이블 + Pydantic 모델

**Files:**
- Modify: `backend/db.py:5-39` (SCHEMA 문자열)
- Modify: `backend/models.py` (끝에 추가)
- Test: `backend/tests/test_attachments.py` (신규)

**Interfaces:**
- Produces: `attachments` 테이블 (컬럼: `id, note_id, type, name, file_path, mime, size, url, text_content, sort_order, created_at`).
- Produces: `LinkCreate {url: str, name: str, description: Optional[str]}`, `MemoCreate {name: str, text: str}`.
- Produces: `AttachmentOut {id, note_id, type, name, file_path, mime, size, url, text_content, sort_order, created_at}` — 응답 직렬화용.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_attachments.py`:

```python
from conftest import AUTH


def test_attachments_table_exists(client):
    # DB가 초기화되면 attachments 테이블이 존재해야 한다.
    from db import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='attachments'"
        ).fetchall()
    assert len(rows) == 1


def test_link_and_memo_models_importable():
    from models import LinkCreate, MemoCreate, AttachmentOut
    lc = LinkCreate(url="https://x.com", name="X", description="d")
    assert lc.url == "https://x.com"
    mc = MemoCreate(name="m", text="t")
    assert mc.text == "t"
    out = AttachmentOut(
        id="1", note_id="n", type="memo", name="m", file_path=None,
        mime=None, size=0, url=None, text_content="t", sort_order=0,
        created_at="2026-07-01T00:00:00+00:00",
    )
    assert out.type == "memo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_attachments.py -v`
Expected: FAIL — `attachments` 테이블 없음 / `ImportError: cannot import name 'LinkCreate'`.

- [ ] **Step 3: Add the table to SCHEMA**

`backend/db.py` — `SCHEMA` 문자열의 `settings` 테이블 정의 뒤(닫는 `"""` 앞)에 추가:

```sql
CREATE TABLE IF NOT EXISTS attachments (
  id TEXT PRIMARY KEY,
  note_id TEXT NOT NULL,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  file_path TEXT,
  mime TEXT,
  size INTEGER NOT NULL DEFAULT 0,
  url TEXT,
  text_content TEXT NOT NULL DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
```

- [ ] **Step 4: Add the models**

`backend/models.py` 끝에 추가:

```python
class LinkCreate(BaseModel):
    url: str
    name: str
    description: Optional[str] = None


class MemoCreate(BaseModel):
    name: str
    text: str


class AttachmentOut(BaseModel):
    id: str
    note_id: str
    type: str
    name: str
    file_path: Optional[str] = None
    mime: Optional[str] = None
    size: int = 0
    url: Optional[str] = None
    text_content: str = ""
    sort_order: int = 0
    created_at: str
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_attachments.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/db.py backend/models.py backend/tests/test_attachments.py
git commit -m "feat(backend): attachments 테이블 + 위성 pydantic 모델"
```

---

## Task 2: attachments 서비스 (저장/안전/추출/인덱싱 텍스트)

**Files:**
- Create: `backend/services/attachments.py`
- Test: `backend/tests/test_attachments_service.py` (신규)

**Interfaces:**
- Consumes: `config.settings.VAULT_DIR`, `db.get_conn` (호출자가 conn 전달).
- Produces:
  - `save_file(note_id: str, filename: str, data: bytes) -> tuple[str, str, int]` → `(rel_path, mime, size)`. `rel_path`는 `VAULT_DIR` 기준 상대경로.
  - `extract_text(filename: str, data: bytes) -> str` → 텍스트 계열이면 디코드된 내용, 아니면 `""`.
  - `abs_path(rel_path: str) -> Path` → `VAULT_DIR` 내부 검증 후 절대경로(이탈 시 `ValueError`).
  - `delete_file(rel_path: Optional[str]) -> None` → 파일 있으면 제거.
  - `indexable_context(conn, note_id: str) -> str` → 인덱싱 대상 위성 텍스트를 헤더 붙여 결합.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_attachments_service.py`:

```python
import importlib
import pytest


def _svc(monkeypatch, tmp_path):
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    from config import settings
    settings.reload()
    svc = importlib.import_module("services.attachments")
    return importlib.reload(svc)


def test_save_file_inside_vault(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    rel, mime, size = svc.save_file("note1", "hello.txt", b"hi there")
    assert rel.startswith("attachments/note1/")
    assert rel.endswith(".txt")
    assert size == 8
    from config import settings
    assert (settings.VAULT_DIR / rel).exists()


def test_extract_text_for_text_files(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    assert svc.extract_text("a.py", b"print(1)") == "print(1)"
    assert svc.extract_text("a.md", b"# title") == "# title"
    # 바이너리(PDF/이미지)는 추출하지 않는다
    assert svc.extract_text("a.pdf", b"%PDF-1.4 binary") == ""
    assert svc.extract_text("a.png", b"\x89PNG\r\n") == ""


def test_abs_path_rejects_escape(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        svc.abs_path("../../etc/passwd")


def test_indexable_context_joins_text_attachments(monkeypatch, tmp_path):
    svc = _svc(monkeypatch, tmp_path)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    from config import settings
    settings.reload()
    from db import init_db, get_conn
    init_db()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO attachments (id, note_id, type, name, text_content, "
            "sort_order, created_at) VALUES "
            "('a1','n1','memo','메모1','토큰 내용',0,'2026-07-01T00:00:00+00:00')"
        )
        conn.execute(
            "INSERT INTO attachments (id, note_id, type, name, text_content, "
            "sort_order, created_at) VALUES "
            "('a2','n1','file','빈파일','',1,'2026-07-01T00:00:00+00:00')"
        )
    with get_conn() as conn:
        ctx = svc.indexable_context(conn, "n1")
    assert "메모1" in ctx
    assert "토큰 내용" in ctx
    assert "빈파일" not in ctx  # text_content 비어있으면 제외
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_attachments_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.attachments'`.

- [ ] **Step 3: Write the service**

`backend/services/attachments.py`:

```python
import uuid
from pathlib import Path
from typing import Optional

from config import settings

# 텍스트로 추출·인덱싱할 확장자
TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".json", ".csv", ".tsv", ".html", ".htm", ".css", ".scss", ".java",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".go", ".rs", ".rb", ".php",
    ".sh", ".bash", ".zsh", ".yml", ".yaml", ".toml", ".ini", ".xml",
    ".sql", ".swift", ".kt", ".dart", ".r", ".lua", ".pl",
}

# 확장자 → MIME (최소 매핑; 없으면 application/octet-stream)
_MIME = {
    ".txt": "text/plain", ".md": "text/markdown", ".json": "application/json",
    ".csv": "text/csv", ".html": "text/html", ".css": "text/css",
    ".py": "text/x-python", ".js": "text/javascript", ".ts": "text/typescript",
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def _attachments_root() -> Path:
    return settings.VAULT_DIR / "attachments"


def guess_mime(filename: str) -> str:
    return _MIME.get(_ext(filename), "application/octet-stream")


def extract_text(filename: str, data: bytes) -> str:
    """텍스트 계열 파일이면 UTF-8로 디코드(에러 무시). 바이너리는 빈 문자열."""
    if _ext(filename) not in TEXT_EXTS:
        return ""
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def save_file(note_id: str, filename: str, data: bytes) -> tuple[str, str, int]:
    """파일을 VAULT_DIR/attachments/<note_id>/<uuid><ext>에 저장.
    (VAULT_DIR 기준 상대경로, mime, 바이트수) 반환."""
    ext = _ext(filename)
    safe_note = uuid.uuid5(uuid.NAMESPACE_URL, note_id).hex if "/" in note_id or "\\" in note_id else note_id
    target_dir = _attachments_root() / safe_note
    target_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{ext}"
    path = (target_dir / fname).resolve()
    root = settings.VAULT_DIR.resolve()
    if root not in path.parents:
        raise ValueError("path escapes vault")
    path.write_bytes(data)
    rel = str(path.relative_to(root))
    return rel, guess_mime(filename), len(data)


def abs_path(rel_path: str) -> Path:
    """상대경로를 VAULT_DIR 내부 절대경로로 변환(이탈 검증)."""
    root = settings.VAULT_DIR.resolve()
    path = (root / rel_path).resolve()
    if root not in path.parents and path != root:
        raise ValueError("path escapes vault")
    return path


def delete_file(rel_path: Optional[str]) -> None:
    if not rel_path:
        return
    try:
        p = abs_path(rel_path)
    except ValueError:
        return
    if p.exists() and p.is_file():
        p.unlink()


def indexable_context(conn, note_id: str) -> str:
    """인덱싱 대상 위성 텍스트를 [위성: name] 헤더와 함께 결합."""
    rows = conn.execute(
        "SELECT name, text_content FROM attachments "
        "WHERE note_id = ? AND text_content != '' "
        "ORDER BY sort_order, created_at",
        (note_id,),
    ).fetchall()
    return "".join(
        f"\n\n[위성: {r['name']}]\n{r['text_content']}" for r in rows
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_attachments_service.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/services/attachments.py backend/tests/test_attachments_service.py
git commit -m "feat(backend): 위성 파일 저장/추출/경로안전 서비스"
```

---

## Task 3: attachments 라우터 (CRUD·업로드·다운로드·벌크) + 노트 cascade

**Files:**
- Create: `backend/routers/attachments.py`
- Modify: `backend/main.py:6` (import), `backend/main.py:33` 이하(라우터 등록)
- Modify: `backend/routers/notes.py:131-139` (`delete_note` cascade)
- Test: `backend/tests/test_attachments.py` (Task 1 파일에 추가)

**Interfaces:**
- Consumes: `services.attachments` (Task 2), `models.LinkCreate/MemoCreate/AttachmentOut` (Task 1).
- Produces (엔드포인트):
  - `GET /notes/{note_id}/attachments` → `list[AttachmentOut]`
  - `POST /notes/{note_id}/attachments/file` (multipart `file`) → `AttachmentOut`
  - `POST /notes/{note_id}/attachments/link` (`LinkCreate`) → `AttachmentOut`
  - `POST /notes/{note_id}/attachments/memo` (`MemoCreate`) → `AttachmentOut`
  - `GET /attachments/{id}/download` → `FileResponse`
  - `DELETE /attachments/{id}` → 204
  - `GET /attachments` → `list[AttachmentOut]` (전체, StarMap 벌크)
- Produces: `routers.attachments.router` (main.py 등록용).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_attachments.py` 끝에 추가:

```python
def _make_note(client, monkeypatch):
    import services.anthropic_client as ac
    monkeypatch.setattr(ac, "extract_entities", lambda content: [])
    return client.post("/notes", json={"title": "행성", "content": "본문"}, headers=AUTH).json()


def test_memo_link_file_crud(client, monkeypatch):
    note = _make_note(client, monkeypatch)
    nid = note["id"]

    # 메모
    r = client.post(f"/notes/{nid}/attachments/memo",
                    json={"name": "토큰메모", "text": "토큰은 조각"}, headers=AUTH)
    assert r.status_code == 200
    memo = r.json()
    assert memo["type"] == "memo"
    assert memo["text_content"] == "토큰은 조각"

    # 링크
    r = client.post(f"/notes/{nid}/attachments/link",
                    json={"url": "https://a.com", "name": "A", "description": "설명"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["url"] == "https://a.com"
    assert "설명" in r.json()["text_content"]

    # 파일
    r = client.post(f"/notes/{nid}/attachments/file",
                    files={"file": ("code.py", b"print(1)", "text/x-python")}, headers=AUTH)
    assert r.status_code == 200
    f = r.json()
    assert f["type"] == "file"
    assert f["size"] == 8
    assert f["text_content"] == "print(1)"

    # 목록
    r = client.get(f"/notes/{nid}/attachments", headers=AUTH)
    assert len(r.json()) == 3

    # 다운로드
    r = client.get(f"/attachments/{f['id']}/download", headers=AUTH)
    assert r.status_code == 200
    assert r.content == b"print(1)"

    # 삭제
    r = client.delete(f"/attachments/{memo['id']}", headers=AUTH)
    assert r.status_code == 204
    assert len(client.get(f"/notes/{nid}/attachments", headers=AUTH).json()) == 2


def test_bulk_attachments(client, monkeypatch):
    note = _make_note(client, monkeypatch)
    client.post(f"/notes/{note['id']}/attachments/memo",
                json={"name": "m", "text": "t"}, headers=AUTH)
    r = client.get("/attachments", headers=AUTH)
    assert r.status_code == 200
    assert any(a["note_id"] == note["id"] for a in r.json())


def test_note_delete_cascades_attachments(client, monkeypatch):
    note = _make_note(client, monkeypatch)
    nid = note["id"]
    client.post(f"/notes/{nid}/attachments/file",
                files={"file": ("a.txt", b"data", "text/plain")}, headers=AUTH)
    from config import settings
    root = settings.VAULT_DIR / "attachments" / nid
    assert root.exists()

    client.delete(f"/notes/{nid}", headers=AUTH)
    from db import get_conn
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM attachments WHERE note_id=?", (nid,)).fetchall()
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_attachments.py -v`
Expected: FAIL — 404 (라우터 미등록).

- [ ] **Step 3: Write the router**

`backend/routers/attachments.py`:

```python
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Response, UploadFile, File
from fastapi.responses import FileResponse

from db import get_conn
from models import LinkCreate, MemoCreate, AttachmentOut
from services import attachments as svc

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(r) -> dict:
    return dict(r)


def _require_note(conn, note_id: str) -> None:
    if conn.execute("SELECT 1 FROM notes WHERE id = ?", (note_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="note not found")


def _next_sort(conn, note_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM attachments WHERE note_id = ?",
        (note_id,),
    ).fetchone()
    return int(row["n"])


def _insert(conn, note_id, type_, name, file_path, mime, size, url, text_content) -> dict:
    aid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO attachments (id, note_id, type, name, file_path, mime, size, "
        "url, text_content, sort_order, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (aid, note_id, type_, name, file_path, mime, size, url, text_content,
         _next_sort(conn, note_id), _now()),
    )
    return _row(conn.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone())


@router.get("/notes/{note_id}/attachments", response_model=list[AttachmentOut])
def list_attachments(note_id: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM attachments WHERE note_id = ? ORDER BY sort_order, created_at",
            (note_id,),
        ).fetchall()
    return [_row(r) for r in rows]


@router.get("/attachments", response_model=list[AttachmentOut])
def list_all_attachments():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM attachments ORDER BY note_id, sort_order, created_at"
        ).fetchall()
    return [_row(r) for r in rows]


@router.post("/notes/{note_id}/attachments/memo", response_model=AttachmentOut)
def add_memo(note_id: str, body: MemoCreate):
    with get_conn() as conn:
        _require_note(conn, note_id)
        out = _insert(conn, note_id, "memo", body.name, None, None, 0, None, body.text)
    return out


@router.post("/notes/{note_id}/attachments/link", response_model=AttachmentOut)
def add_link(note_id: str, body: LinkCreate):
    text = body.name + ("\n" + body.description if body.description else "")
    with get_conn() as conn:
        _require_note(conn, note_id)
        out = _insert(conn, note_id, "link", body.name, None, None, 0, body.url, text)
    return out


@router.post("/notes/{note_id}/attachments/file", response_model=AttachmentOut)
def add_file(note_id: str, file: UploadFile = File(...)):
    data = file.file.read()
    filename = file.filename or "file"
    with get_conn() as conn:
        _require_note(conn, note_id)
        rel, mime, size = svc.save_file(note_id, filename, data)
        text = svc.extract_text(filename, data)
        out = _insert(conn, note_id, "file", filename, rel, mime, size, None, text)
    return out


@router.get("/attachments/{aid}/download")
def download(aid: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
    if row is None or not row["file_path"]:
        raise HTTPException(status_code=404, detail="file not found")
    try:
        path = svc.abs_path(row["file_path"])
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="file missing")
    return FileResponse(str(path), media_type=row["mime"] or "application/octet-stream",
                        filename=row["name"])


@router.delete("/attachments/{aid}", status_code=204)
def delete_attachment(aid: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
        if row is not None:
            svc.delete_file(row["file_path"])
            conn.execute("DELETE FROM attachments WHERE id = ?", (aid,))
    return Response(status_code=204)
```

- [ ] **Step 4: Register the router in main.py**

`backend/main.py` — import 줄(6행) 수정:

```python
from routers import categories, notes, ai, search, attachments
```

라우터 등록부(파일 끝) 마지막에 추가:

```python
app.include_router(attachments.router, dependencies=[Depends(require_auth)])
```

- [ ] **Step 5: Add cascade to note deletion**

`backend/routers/notes.py` — 상단 import에 서비스 추가(기존 `from services import vault` 아래):

```python
from services import attachments as attach_svc
```

`delete_note`(131-139행)를 다음으로 교체:

```python
@router.delete("/notes/{nid}", status_code=204)
def delete_note(nid: str):
    with get_conn() as conn:
        row = conn.execute("SELECT title FROM notes WHERE id = ?", (nid,)).fetchone()
        if row is not None:
            vault.delete_md(row["title"])
        # 위성(첨부) 파일 + 행 정리
        att_rows = conn.execute(
            "SELECT file_path FROM attachments WHERE note_id = ?", (nid,)
        ).fetchall()
        for a in att_rows:
            attach_svc.delete_file(a["file_path"])
        conn.execute("DELETE FROM attachments WHERE note_id = ?", (nid,))
        conn.execute("DELETE FROM notes WHERE id = ?", (nid,))
        conn.execute("DELETE FROM entities WHERE note_id = ?", (nid,))
    return Response(status_code=204)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_attachments.py tests/test_notes.py -v`
Expected: PASS (모든 attachments + notes 테스트 통과).

- [ ] **Step 7: Commit**

```bash
git add backend/routers/attachments.py backend/main.py backend/routers/notes.py backend/tests/test_attachments.py
git commit -m "feat(backend): 위성 CRUD/업로드/다운로드 라우터 + 노트 삭제 cascade"
```

---

## Task 4: AI 인덱싱 연동 (엔티티 추출·재인덱싱·RAG·검색)

**Files:**
- Modify: `backend/routers/notes.py:26-46` (`_run_extraction`)
- Modify: `backend/routers/attachments.py` (create/delete에 재인덱싱 트리거)
- Modify: `backend/routers/ai.py` (RAG 컨텍스트)
- Modify: `backend/routers/search.py:10-31` (검색)
- Test: `backend/tests/test_attachment_indexing.py` (신규)

**Interfaces:**
- Consumes: `services.attachments.indexable_context(conn, note_id)` (Task 2).
- Produces: 위성 텍스트가 소속 노트의 엔티티 추출·RAG·검색에 반영됨. 위성 생성/삭제 시 소속 노트 `analysis_status='pending'` + 백그라운드 재추출.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_attachment_indexing.py`:

```python
import services.anthropic_client as ac
from conftest import AUTH


def _make_note(client):
    return client.post("/notes", json={"title": "행성", "content": "행성 본문"},
                       headers=AUTH).json()


def test_extraction_includes_attachment_text(client, monkeypatch):
    captured = {}

    def fake_extract(content):
        captured["content"] = content
        return [{"name": "토큰", "type": "concept"}]

    monkeypatch.setattr(ac, "extract_entities", fake_extract)

    note = _make_note(client)
    nid = note["id"]
    # 메모 위성 추가 → 재추출 트리거되어 위성 텍스트가 추출 입력에 포함
    client.post(f"/notes/{nid}/attachments/memo",
                json={"name": "메모", "text": "토큰 윈도우 설명"}, headers=AUTH)

    assert "토큰 윈도우 설명" in captured.get("content", "")
    assert "행성 본문" in captured["content"]

    # 노트 analysis_status가 재추출로 갱신됨
    r = client.get(f"/notes/{nid}", headers=AUTH)
    assert r.json()["analysis_status"] in ("analyzed", "pending")


def test_search_matches_attachment_text(client, monkeypatch):
    monkeypatch.setattr(ac, "extract_entities", lambda c: [])
    note = _make_note(client)
    client.post(f"/notes/{note['id']}/attachments/memo",
                json={"name": "메모", "text": "엠베딩 벡터"}, headers=AUTH)

    # 노트 본문/제목에는 없고 위성 텍스트에만 있는 단어로 검색
    r = client.get("/search?q=엠베딩", headers=AUTH)
    ids = [x["id"] for x in r.json()]
    assert note["id"] in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_attachment_indexing.py -v`
Expected: FAIL — 위성 텍스트가 추출 입력/검색에 미포함.

- [ ] **Step 3: Extend `_run_extraction` to include attachment text**

`backend/routers/notes.py` — `_run_extraction`(26-46행)을 교체:

```python
def _run_extraction(note_id: str, content: str) -> None:
    """백그라운드: 노트 본문 + 위성 텍스트로 엔티티 추출 후 저장 + status 갱신."""
    try:
        with get_conn() as conn:
            extra = attach_svc.indexable_context(conn, note_id)
        entities = anthropic_client.extract_entities(content + extra)
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
```

(`attach_svc`는 Task 3에서 이미 import됨. `uuid`, `anthropic_client`, `_now`도 기존에 존재.)

- [ ] **Step 4: Trigger re-indexing on attachment create/delete**

`backend/routers/attachments.py` — 상단 import에 `BackgroundTasks` 및 notes의 재추출 함수 추가:

```python
from fastapi import APIRouter, HTTPException, Response, UploadFile, File, BackgroundTasks
```

파일 상단(라우터 정의 아래)에 헬퍼 추가:

```python
def _reindex(note_id: str, bg: BackgroundTasks) -> None:
    """위성 변경 시 소속 노트를 재추출 대기로 돌리고 백그라운드 추출 예약."""
    from routers.notes import _run_extraction
    with get_conn() as conn:
        row = conn.execute("SELECT content FROM notes WHERE id = ?", (note_id,)).fetchone()
        conn.execute(
            "UPDATE notes SET analysis_status = 'pending' WHERE id = ?", (note_id,)
        )
    if row is not None:
        bg.add_task(_run_extraction, note_id, row["content"])
```

각 생성 엔드포인트 시그니처에 `bg: BackgroundTasks`를 추가하고, `return out` 앞에 `_reindex` 호출을 넣는다. 예: `add_memo`:

```python
@router.post("/notes/{note_id}/attachments/memo", response_model=AttachmentOut)
def add_memo(note_id: str, body: MemoCreate, bg: BackgroundTasks):
    with get_conn() as conn:
        _require_note(conn, note_id)
        out = _insert(conn, note_id, "memo", body.name, None, None, 0, None, body.text)
    _reindex(note_id, bg)
    return out
```

`add_link`, `add_file`도 동일하게 `bg: BackgroundTasks` 파라미터 추가 + `_reindex(note_id, bg)` 호출(각 `return out` 앞).

`delete_attachment`도 `bg: BackgroundTasks` 추가 후, 삭제된 위성의 `note_id`로 재인덱싱:

```python
@router.delete("/attachments/{aid}", status_code=204)
def delete_attachment(aid: str, bg: BackgroundTasks):
    note_id = None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM attachments WHERE id = ?", (aid,)).fetchone()
        if row is not None:
            note_id = row["note_id"]
            svc.delete_file(row["file_path"])
            conn.execute("DELETE FROM attachments WHERE id = ?", (aid,))
    if note_id:
        _reindex(note_id, bg)
    return Response(status_code=204)
```

- [ ] **Step 5: Add attachment text to RAG context**

`backend/routers/ai.py` — 상단 import에 추가:

```python
from services import attachments as attach_svc
```

컨텍스트 구성 함수에서 `context_note_id` 처리 블록(현재 노트 append 부분)을 위성 텍스트까지 포함하도록 수정. 해당 `with get_conn() as conn:` 블록 안, 현재 노트 append 직후:

```python
        if req.context_note_id:
            row = conn.execute(
                "SELECT title, content FROM notes WHERE id = ?",
                (req.context_note_id,),
            ).fetchone()
            if row:
                extra = attach_svc.indexable_context(conn, req.context_note_id)
                parts.append(f"[현재 노트] {row['title']}\n{row['content']}{extra}")
```

`use_rag`로 여러 노트를 모으는 블록에서도 각 행에 대해 위성 텍스트를 덧붙인다. 해당 `rows` 순회 부분을:

```python
            parts.append("\n\n".join(
                f"# {r['title']}\n{(r['content'] or '')[:1000]}"
                f"{attach_svc.indexable_context(conn, r['id'])[:1000]}"
                for r in rows
            ))
```

로 수정한다(RAG SELECT에 `id`를 포함해야 하므로 `SELECT title, content` → `SELECT id, title, content`로 두 쿼리 모두 변경).

- [ ] **Step 6: Add attachment text to search**

`backend/routers/search.py` — `search`(10-31행)를 교체:

```python
@router.get("/search")
def search(q: str = ""):
    term = (q or "").strip()
    if not term:
        return []
    like = f"%{term}%"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT n.id AS id, n.title AS title, n.content AS content, "
            "n.category_id AS category_id, n.modified_at AS modified_at "
            "FROM notes n "
            "LEFT JOIN attachments a ON a.note_id = n.id "
            "WHERE n.title LIKE ? OR n.content LIKE ? OR a.text_content LIKE ? "
            "ORDER BY n.modified_at DESC LIMIT 50",
            (like, like, like),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "content_preview": (r["content"] or "")[:200],
            "category_id": r["category_id"],
            "modified_at": r["modified_at"],
        }
        for r in rows
    ]
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && python -m pytest -v`
Expected: PASS (신규 인덱싱 테스트 + 기존 전체 통과).

- [ ] **Step 8: Commit**

```bash
git add backend/routers/notes.py backend/routers/attachments.py backend/routers/ai.py backend/routers/search.py backend/tests/test_attachment_indexing.py
git commit -m "feat(backend): 위성 텍스트를 엔티티추출/RAG/검색에 인덱싱"
```

---

## Task 5: 프론트 타입 + API 래퍼

**Files:**
- Modify: `src/types/index.ts:22` (`EditorTab`), 끝(인터페이스 추가)
- Modify: `src/api/client.ts` (인증 전용 헤더 추가)
- Create: `src/api/attachmentsApi.ts`

**Interfaces:**
- Produces: `Attachment` 타입, `EditorTab`에 `'satellite'`.
- Produces: `attachmentsApi` = `{ list, uploadFile, addLink, addMemo, downloadUrl, remove, listAll }`.
- Produces: `client.ts`의 `authHeaderOnly(): HeadersInit` (Content-Type 없이 토큰만).

- [ ] **Step 1: Add the Attachment type and EditorTab variant**

`src/types/index.ts` — 22행 수정:

```typescript
export type EditorTab = 'edit' | 'preview' | 'starmap' | 'satellite'
```

파일 끝에 추가:

```typescript
export type AttachmentType = 'file' | 'link' | 'memo'

export interface Attachment {
  id: string
  note_id: string
  type: AttachmentType
  name: string
  file_path: string | null
  mime: string | null
  size: number
  url: string | null
  text_content: string
  sort_order: number
  created_at: string
}
```

- [ ] **Step 2: Add auth-only header to client.ts**

`src/api/client.ts` — `authHeaders` 함수 아래에 추가:

```typescript
/** 멀티파트 업로드용: Content-Type을 브라우저가 정하도록 토큰만 반환. */
export function authHeaderOnly(): HeadersInit {
  return TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}
}
```

- [ ] **Step 3: Write the API wrapper**

`src/api/attachmentsApi.ts`:

```typescript
import { apiFetch, API_BASE, authHeaderOnly } from './client'
import type { Attachment } from '../types'

export const attachmentsApi = {
  list: (noteId: string) =>
    apiFetch<Attachment[]>(`/notes/${noteId}/attachments`),

  listAll: () => apiFetch<Attachment[]>('/attachments'),

  addMemo: (noteId: string, name: string, text: string) =>
    apiFetch<Attachment>(`/notes/${noteId}/attachments/memo`, {
      method: 'POST',
      body: JSON.stringify({ name, text }),
    }),

  addLink: (noteId: string, url: string, name: string, description?: string) =>
    apiFetch<Attachment>(`/notes/${noteId}/attachments/link`, {
      method: 'POST',
      body: JSON.stringify({ url, name, description }),
    }),

  uploadFile: async (noteId: string, file: File): Promise<Attachment> => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${API_BASE}/notes/${noteId}/attachments/file`, {
      method: 'POST',
      headers: authHeaderOnly(),
      body: form,
    })
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`)
    return res.json()
  },

  downloadUrl: (id: string) => `${API_BASE}/attachments/${id}/download`,

  remove: (id: string) =>
    apiFetch<void>(`/attachments/${id}`, { method: 'DELETE' }),
}
```

- [ ] **Step 4: Typecheck**

Run: `npm run build`
Expected: 타입 에러 없이 빌드 성공(위 파일들이 컴파일됨).

- [ ] **Step 5: Commit**

```bash
git add src/types/index.ts src/api/client.ts src/api/attachmentsApi.ts
git commit -m "feat(web): 위성 타입 + API 래퍼(멀티파트 업로드)"
```

---

## Task 6: 위성 Zustand 스토어

**Files:**
- Create: `src/store/attachmentsStore.ts`
- Test: 없음(프론트 러너 없음) — Task 7에서 통합 수동 검증.

**Interfaces:**
- Consumes: `attachmentsApi` (Task 5).
- Produces: `useAttachmentsStore` = 상태 `{ items: Attachment[] }` + 액션 `load(noteId)`, `addMemo(noteId,name,text)`, `addLink(noteId,url,name,description?)`, `uploadFile(noteId,file)`, `remove(id)`, `clear()`.

- [ ] **Step 1: Write the store**

`src/store/attachmentsStore.ts`:

```typescript
import { create } from 'zustand'
import type { Attachment } from '../types'
import { attachmentsApi } from '../api/attachmentsApi'

interface AttachmentsState {
  items: Attachment[]
  load: (noteId: string) => Promise<void>
  addMemo: (noteId: string, name: string, text: string) => Promise<void>
  addLink: (noteId: string, url: string, name: string, description?: string) => Promise<void>
  uploadFile: (noteId: string, file: File) => Promise<void>
  remove: (id: string) => Promise<void>
  clear: () => void
}

export const useAttachmentsStore = create<AttachmentsState>((set) => ({
  items: [],

  load: async (noteId) => {
    const items = await attachmentsApi.list(noteId)
    set({ items })
  },

  addMemo: async (noteId, name, text) => {
    const a = await attachmentsApi.addMemo(noteId, name, text)
    set(s => ({ items: [...s.items, a] }))
  },

  addLink: async (noteId, url, name, description) => {
    const a = await attachmentsApi.addLink(noteId, url, name, description)
    set(s => ({ items: [...s.items, a] }))
  },

  uploadFile: async (noteId, file) => {
    const a = await attachmentsApi.uploadFile(noteId, file)
    set(s => ({ items: [...s.items, a] }))
  },

  remove: async (id) => {
    await attachmentsApi.remove(id)
    set(s => ({ items: s.items.filter(i => i.id !== id) }))
  },

  clear: () => set({ items: [] }),
}))
```

- [ ] **Step 2: Typecheck**

Run: `npm run build`
Expected: 빌드 성공.

- [ ] **Step 3: Commit**

```bash
git add src/store/attachmentsStore.ts
git commit -m "feat(web): 위성 상태 스토어"
```

---

## Task 7: 위성 패널 컴포넌트 + '위성' 탭

**Files:**
- Create: `src/components/Editor/SatellitePanel.tsx`
- Modify: `src/components/Editor/EditorTabs.tsx:5-9` (TABS 배열)
- Modify: `src/App.tsx:6-7`(import), `src/App.tsx:35-37`(렌더 분기)

**Interfaces:**
- Consumes: `useAttachmentsStore` (Task 6), `useNotesStore.activeNote`, `attachmentsApi.downloadUrl`.
- Produces: `SatellitePanel` React 컴포넌트, EditorTab `'satellite'` 렌더.

- [ ] **Step 1: Write the SatellitePanel component**

`src/components/Editor/SatellitePanel.tsx`:

```typescript
import { useEffect, useState } from 'react'
import { useNotesStore } from '../../store/notesStore'
import { useAttachmentsStore } from '../../store/attachmentsStore'
import { attachmentsApi } from '../../api/attachmentsApi'
import type { Attachment } from '../../types'

function iconFor(a: Attachment): string {
  if (a.type === 'link') return '🔗'
  if (a.type === 'memo') return '📝'
  const m = a.mime ?? ''
  if (m === 'application/pdf') return '🌙'
  if (m.startsWith('image/')) return '🖼️'
  return '💻'
}

export function SatellitePanel() {
  const { activeNote } = useNotesStore()
  const { items, load, addMemo, addLink, uploadFile, remove, clear } = useAttachmentsStore()
  const [memoName, setMemoName] = useState('')
  const [memoText, setMemoText] = useState('')
  const [linkUrl, setLinkUrl] = useState('')
  const [linkName, setLinkName] = useState('')

  useEffect(() => {
    if (activeNote) load(activeNote.id)
    else clear()
  }, [activeNote?.id])

  if (!activeNote) return null
  const nid = activeNote.id

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) uploadFile(nid, f)
    e.target.value = ''
  }

  const onAddMemo = () => {
    if (!memoName.trim()) return
    addMemo(nid, memoName.trim(), memoText)
    setMemoName(''); setMemoText('')
  }

  const onAddLink = () => {
    if (!linkUrl.trim()) return
    addLink(nid, linkUrl.trim(), linkName.trim() || linkUrl.trim())
    setLinkUrl(''); setLinkName('')
  }

  return (
    <div className="flex flex-col h-full overflow-auto" style={{ padding: '20px 24px', gap: 16 }}>
      <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
        🌙 위성 <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>({items.length})</span>
      </h2>

      {/* 위성 목록 */}
      <ul style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {items.map(a => (
          <li key={a.id} className="flex items-center gap-2"
              style={{ fontSize: 13, color: 'var(--text-primary)', padding: '6px 8px',
                       border: '1px solid var(--border)', borderRadius: 4 }}>
            <span>{iconFor(a)}</span>
            <span className="truncate" style={{ flex: 1 }}>{a.name}</span>
            {a.type === 'file' && (
              <a href={attachmentsApi.downloadUrl(a.id)} download
                 style={{ fontSize: 11, color: 'var(--text-secondary)' }}>다운로드</a>
            )}
            {a.type === 'link' && a.url && (
              <a href={a.url} target="_blank" rel="noreferrer"
                 style={{ fontSize: 11, color: 'var(--text-secondary)' }}>열기</a>
            )}
            <button onClick={() => remove(a.id)}
                    style={{ fontSize: 11, color: 'var(--text-secondary)' }}>삭제</button>
          </li>
        ))}
        {items.length === 0 && (
          <li style={{ fontSize: 12, color: 'var(--text-secondary)' }}>아직 위성이 없습니다.</li>
        )}
      </ul>

      {/* 파일 업로드 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>파일 위성 (PDF·이미지·코드)</label>
        <input type="file" onChange={onFile} style={{ fontSize: 12 }} />
      </div>

      {/* 링크 위성 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>링크 위성</label>
        <input value={linkUrl} onChange={e => setLinkUrl(e.target.value)} placeholder="https://..."
               style={{ fontSize: 13, padding: '6px 8px', background: 'transparent',
                        border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-primary)' }} />
        <input value={linkName} onChange={e => setLinkName(e.target.value)} placeholder="제목(선택)"
               style={{ fontSize: 13, padding: '6px 8px', background: 'transparent',
                        border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-primary)' }} />
        <button onClick={onAddLink} style={{ fontSize: 12, alignSelf: 'flex-start',
                padding: '4px 12px', border: '1px solid var(--border)', borderRadius: 4,
                color: 'var(--text-primary)' }}>링크 추가</button>
      </div>

      {/* 메모 위성 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>메모 위성</label>
        <input value={memoName} onChange={e => setMemoName(e.target.value)} placeholder="메모 제목"
               style={{ fontSize: 13, padding: '6px 8px', background: 'transparent',
                        border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-primary)' }} />
        <textarea value={memoText} onChange={e => setMemoText(e.target.value)} placeholder="메모 내용" rows={3}
                  style={{ fontSize: 13, padding: '6px 8px', background: 'transparent',
                           border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-primary)' }} />
        <button onClick={onAddMemo} style={{ fontSize: 12, alignSelf: 'flex-start',
                padding: '4px 12px', border: '1px solid var(--border)', borderRadius: 4,
                color: 'var(--text-primary)' }}>메모 추가</button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add the '위성' tab**

`src/components/Editor/EditorTabs.tsx` — `TABS` 배열(5-9행)에 항목 추가:

```typescript
const TABS: { id: EditorTab; label: string }[] = [
  { id: 'edit', label: '편집' },
  { id: 'preview', label: '미리보기' },
  { id: 'satellite', label: '위성' },
  { id: 'starmap', label: '성도' },
]
```

- [ ] **Step 3: Wire the render branch in App.tsx**

`src/App.tsx` — import 추가(NoteEditor import 근처):

```typescript
import { SatellitePanel } from './components/Editor/SatellitePanel'
```

렌더 분기(현재 35-37행)에 추가:

```tsx
        {activeTab === 'edit' && <NoteEditor />}
        {activeTab === 'preview' && <NotePreview />}
        {activeTab === 'satellite' && <SatellitePanel />}
        {activeTab === 'starmap' && <StarMapCanvas />}
```

- [ ] **Step 4: Typecheck**

Run: `npm run build`
Expected: 빌드 성공.

- [ ] **Step 5: Manual verification**

Run: `./start.sh` (또는 `npm run dev`로 프론트, 백엔드 기동). 브라우저에서:
1. 노트를 열고 '위성' 탭 클릭 → 패널 표시.
2. 메모 추가 → 목록에 나타남. 링크 추가 → '열기' 링크 동작. 파일 업로드(예: `.py`) → '다운로드' 동작.
3. 삭제 버튼 → 목록에서 사라짐.
4. 검색창에서 메모에만 있는 단어 검색 → 해당 노트가 결과에 뜸(백엔드 Task 4 연동 확인).

Expected: 위 4개 모두 정상 동작.

- [ ] **Step 6: Commit**

```bash
git add src/components/Editor/SatellitePanel.tsx src/components/Editor/EditorTabs.tsx src/App.tsx
git commit -m "feat(web): 위성 패널 + '위성' 편집기 탭"
```

---

## Task 8: StarMap 위성 궤도 렌더

**Files:**
- Modify: `src/components/StarMap/StarMapCanvas.tsx` (import·데이터 로드·메시 생성·렌더 루프·raycast)
- Test: 없음 — 수동 검증.

**Interfaces:**
- Consumes: `attachmentsApi.listAll()` (Task 5), 기존 `catNotes.forEach` 내 `mesh`(행성), `planetR`, 렌더 루프.
- Produces: 각 행성에 위성 자식 메시(최대 8개) + "+N" 라벨 + 위성 호버 툴팁.

- [ ] **Step 1: Load attachments in the component**

`src/components/StarMap/StarMapCanvas.tsx` — 상단 import에 추가:

```typescript
import { attachmentsApi } from '../../api/attachmentsApi'
import type { Attachment } from '../../types'
```

컴포넌트 함수 본문 상단(기존 `const { notes, ... } = useNotesStore()` 아래)에 위성 상태 로드 추가:

```typescript
  const [moonsByNote, setMoonsByNote] = useState<Record<string, Attachment[]>>({})

  useEffect(() => {
    let cancelled = false
    attachmentsApi.listAll().then(all => {
      if (cancelled) return
      const map: Record<string, Attachment[]> = {}
      for (const a of all) (map[a.note_id] ||= []).push(a)
      setMoonsByNote(map)
    }).catch(() => { /* 위성 없음 무시 */ })
    return () => { cancelled = true }
  }, [notes])
```

그리고 three.js 씬을 만드는 메인 `useEffect`의 의존성 배열(현재 728행 `[categories, notes, starMapFilter]`)에 `moonsByNote`를 추가:

```typescript
  }, [categories, notes, starMapFilter, moonsByNote])
```

- [ ] **Step 2: Add a text-sprite helper for the "+N" label**

`StarMapCanvas.tsx` — 파일 상단 유틸 영역(예: `blobs` 함수 아래)에 추가:

```typescript
// 작은 텍스트 스프라이트(위성 초과 개수 "+N" 표시용)
function makeTextSprite(text: string): THREE.Sprite {
  const c = document.createElement('canvas')
  c.width = 128; c.height = 64
  const ctx = c.getContext('2d')!
  ctx.font = 'bold 40px sans-serif'
  ctx.fillStyle = 'rgba(220,230,255,0.9)'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, 64, 32)
  const tex = new THREE.CanvasTexture(c)
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: tex, transparent: true, depthWrite: false,
  }))
  return sprite
}
```

- [ ] **Step 3: Attach moon meshes to each planet**

`StarMapCanvas.tsx` — 씬 useEffect 안, 궤도 배열 선언부(현재 490-492행)에 위성 추적 배열을 추가:

```typescript
    const orbits: OrbitData[] = []
    const noteIds: string[] = []
    const spinners: THREE.Object3D[] = []
    const moonMeshes: THREE.Mesh[] = []      // 위성 raycast용
    const moonNames: string[] = []           // moonMeshes와 인덱스 대응
```

`catNotes.forEach` 안, `scene.add(mesh)`(588행) 직후에 위성 부착 블록을 추가:

```typescript
        // 위성(첨부): 행성 자식으로 붙여 소궤도 공전 (최대 8개)
        const moons = moonsByNote[note.id] ?? []
        const MOON_CAP = 8
        moons.slice(0, MOON_CAP).forEach((att, mi) => {
          const color =
            att.type === 'memo' ? 0x7fd4c8 :
            att.type === 'link' ? 0xc89ad4 : 0x9aa4b2
          const moonR = Math.max(0.5, planetR * 0.18)
          const moon = new THREE.Mesh(
            new THREE.SphereGeometry(moonR, 12, 8),
            new THREE.MeshStandardMaterial({ color, roughness: 0.9, metalness: 0.0 }),
          )
          const ringR = planetR * (1.7 + mi * 0.35)
          const a0 = (mi * 2.399963) % (Math.PI * 2)
          moon.position.set(ringR * Math.cos(a0), (mi % 2 ? 0.6 : -0.6), ringR * Math.sin(a0))
          mesh.add(moon)          // 행성 자전(mesh.rotation.y)에 실려 공전
          moonMeshes.push(moon)
          moonNames.push(att.name)
        })
        if (moons.length > MOON_CAP) {
          const label = makeTextSprite(`+${moons.length - MOON_CAP}`)
          label.scale.setScalar(planetR * 1.2)
          label.position.set(planetR * 2.4, planetR * 1.2, 0)
          mesh.add(label)
          disposables.push(label.material as THREE.Material)
        }
```

- [ ] **Step 4: Show tooltip on moon hover**

`StarMapCanvas.tsx` — `getHit`(620-627행)는 planet만 검사한다. 위성 호버를 위해 `pointermove` 핸들러의 hover 분기(649-660행)를 다음으로 교체:

```typescript
      const rect2 = canvas.getBoundingClientRect()
      const nx = ((e.clientX - rect2.left) / rect2.width) * 2 - 1
      const ny = -((e.clientY - rect2.top) / rect2.height) * 2 + 1
      raycaster.setFromCamera(new THREE.Vector2(nx, ny), camera)

      const planetHit = raycaster.intersectObjects(starMeshes, false)[0]?.object as THREE.Mesh | undefined
      if (planetHit) {
        const idx = starMeshes.indexOf(planetHit)
        const note = idx >= 0 ? visibleNotes.find(n => n.id === noteIds[idx]) : null
        if (note) {
          canvas.style.cursor = 'pointer'
          setTooltip({ title: note.title, x: e.clientX - rect2.left, y: e.clientY - rect2.top })
          return
        }
      }
      const moonHit = raycaster.intersectObjects(moonMeshes, false)[0]?.object as THREE.Mesh | undefined
      if (moonHit) {
        const mIdx = moonMeshes.indexOf(moonHit)
        if (mIdx >= 0) {
          canvas.style.cursor = 'pointer'
          setTooltip({ title: `🌙 ${moonNames[mIdx]}`, x: e.clientX - rect2.left, y: e.clientY - rect2.top })
          return
        }
      }
      canvas.style.cursor = 'grab'
      setTooltip(null)
```

(위성 클릭 동작은 v1 범위 밖 — 툴팁만. `pointerup`의 planet 클릭 로직은 그대로 둔다.)

- [ ] **Step 5: Typecheck**

Run: `npm run build`
Expected: 빌드 성공.

- [ ] **Step 6: Manual verification**

Run: `./start.sh`. 브라우저에서:
1. 위성이 여러 개 붙은 노트가 있는 상태로 '성도' 탭 열기.
2. 해당 행성 주위에 작은 구체(위성)들이 행성 자전에 따라 도는지 확인.
3. 위성에 마우스 올리면 `🌙 이름` 툴팁 표시.
4. 위성 9개 이상인 행성은 "+N" 라벨이 보이는지 확인.

Expected: 위 4개 정상. 위성 없는 행성은 기존과 동일.

- [ ] **Step 7: Commit**

```bash
git add src/components/StarMap/StarMapCanvas.tsx
git commit -m "feat(starmap): 행성 주위를 도는 위성 궤도 렌더 + 툴팁"
```

---

## Self-Review 결과

**Spec coverage:**
- §1 데이터 모델 → Task 1. §2 파일 저장 → Task 2. §3 API → Task 3. §4 AI 인덱싱(추출/RAG/검색) → Task 4. §5 편집기 패널 → Task 5·6·7. §6 StarMap 시각화 → Task 8. §7 테스트 → Task 1~4 pytest + Task 5·7·8 수동 검증. 전 항목 커버됨.
- 스키마 3종/UI 5종 아이콘 → Task 1(스키마) + Task 7 `iconFor`(5종). PDF 텍스트 추출 제외 → Task 2 `TEXT_EXTS`에 `.pdf` 없음, 테스트로 명시. StarMap 8개 캡 + "+N" → Task 8 `MOON_CAP`.

**Placeholder scan:** "TBD/TODO/적절히 처리" 등 없음. 모든 코드 스텝에 실제 코드 포함.

**Type consistency:** `Attachment`(Task 5) 필드 = 백엔드 `AttachmentOut`(Task 1) = 테이블(Task 1) 일치. `indexable_context(conn, note_id)`(Task 2) 시그니처가 Task 4의 3개 호출부와 일치. `attachmentsApi` 메서드명(`list/listAll/addMemo/addLink/uploadFile/downloadUrl/remove`)이 Task 6 스토어·Task 7 패널 호출과 일치. `EditorTab`에 `'satellite'` 추가(Task 5)와 Task 7 탭/렌더 분기 일치.
