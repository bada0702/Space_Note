# 천문 기능 4종 (기항지·블랙홀·항로 승격·초신성) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 즐겨찾기(기항지), 보관(블랙홀), 발견 항로의 사용자 승인(항로 승격), 분석 후 대량 신규 연결 이벤트(초신성)를 백엔드-프론트-성도(Three.js)에 걸쳐 구현한다.

**Architecture:** SQLite `notes` 테이블에 `is_favorite`/`is_archived` 플래그 컬럼을 마이그레이션으로 추가하고, 확정 항로는 새 `routes` 테이블에 저장한다. 프론트는 zustand store를 확장하고, 성도는 기존 씬 구성 effect 안에 시각 요소(비콘 링, 블랙홀, 항로 위계, 초신성 버스트)를 추가한다. 초신성 판정은 백엔드 이벤트 없이 프론트에서 분석 전후 routes diff로 계산한다.

**Tech Stack:** FastAPI + SQLite(raw SQL) + pytest / React 18 + TypeScript + zustand + Three.js 0.184

**Spec:** `docs/superpowers/specs/2026-07-07-astro-features-design.md`

## Global Constraints

- 즐겨찾기/보관 상태는 .md frontmatter에 쓰지 않는다 (DB 전용 — vault 파일 형식 불변).
- 플래그만 바꾸는 PATCH는 `modified_at`을 갱신하지 않고 .md 파일도 다시 쓰지 않는다 (목록 정렬이 흔들리면 안 됨).
- routes 테이블 저장 시 항상 `note_a < note_b` (문자열 비교) 정규화 — 기존 `/discoveries/routes` 규칙과 동일.
- 확정 항로는 발견 쌍이 사라져도(엔티티 변화) `/discoveries/routes` 응답에 유지한다. 이때 `shared_entities`는 빈 배열.
- 보관 노트는 `/notes`(기본)·`/search`·`/discoveries`·`/discoveries/routes`·`POST /notes/analyze`에서 모두 제외.
- 성도 신규 시각 요소는 데이터 로드 실패 시 콘솔 기록 후 생략 — 씬의 나머지는 정상 렌더링.
- UI 문구는 한국어, 기존 컴포넌트의 인라인 스타일·CSS 변수(`var(--bg-input)` 등) 관용구를 따른다.
- 백엔드 테스트 실행: `cd /var/www/html/Space_Note_v100/backend && venv/bin/python -m pytest tests -q`
- 프론트 검증: `cd /var/www/html/Space_Note_v100 && npm run build` (tsc && vite build). 프론트에는 테스트 러너가 없으므로 타입체크+빌드+최종 브라우저 QA(Task 12)로 검증한다.

---

### Task 1: DB 마이그레이션 — is_favorite / is_archived 컬럼 + routes 테이블

**Files:**
- Modify: `backend/db.py`
- Test: `backend/tests/test_db_migration.py`

**Interfaces:**
- Produces: `notes.is_favorite`, `notes.is_archived` (INTEGER NOT NULL DEFAULT 0), `routes(id, note_a, note_b, created_at, UNIQUE(note_a, note_b))` 테이블. 이후 모든 태스크가 이 스키마에 의존.

- [ ] **Step 1: 실패하는 테스트 작성** — `backend/tests/test_db_migration.py` 끝에 추가:

```python
def test_init_db_migrates_note_flags_and_routes_table(monkeypatch, tmp_path):
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "legacy2.db"))
    from config import settings
    settings.reload()

    # 플래그 컬럼이 없는 구버전 notes 테이블
    conn = sqlite3.connect(settings.DB_PATH)
    conn.execute(
        "CREATE TABLE notes (id TEXT PRIMARY KEY, path TEXT NOT NULL, "
        "title TEXT NOT NULL, content TEXT NOT NULL DEFAULT '', category_id TEXT, "
        "tags TEXT NOT NULL DEFAULT '[]', word_count INTEGER NOT NULL DEFAULT 0, "
        "analysis_status TEXT NOT NULL DEFAULT 'pending', "
        "created_at TEXT NOT NULL, modified_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO notes (id, path, title, created_at, modified_at) "
        "VALUES ('n1', '/p', 't', 'now', 'now')"
    )
    conn.commit()
    conn.close()

    from db import init_db
    init_db()

    conn = sqlite3.connect(settings.DB_PATH)
    row = conn.execute("SELECT is_favorite, is_archived FROM notes WHERE id='n1'").fetchone()
    assert row == (0, 0)
    # routes 테이블이 생성됐고 UNIQUE 제약이 동작한다
    conn.execute("INSERT INTO routes (id, note_a, note_b, created_at) VALUES ('r1','a','b','now')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO routes (id, note_a, note_b, created_at) VALUES ('r2','a','b','now')")
    conn.close()
```

파일 상단 import에 `import pytest` 추가 (`import sqlite3`는 이미 있음).

- [ ] **Step 2: 실패 확인**

Run: `cd /var/www/html/Space_Note_v100/backend && venv/bin/python -m pytest tests/test_db_migration.py -q`
Expected: FAIL — `sqlite3.OperationalError: no such column: is_favorite`

- [ ] **Step 3: 구현** — `backend/db.py`:

SCHEMA 문자열의 `CREATE TABLE IF NOT EXISTS settings (...);` 앞에 추가:

```sql
CREATE TABLE IF NOT EXISTS routes (
  id TEXT PRIMARY KEY,
  note_a TEXT NOT NULL,
  note_b TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(note_a, note_b)
);
```

`init_db()`의 기존 entities `norm` 마이그레이션 블록 뒤, `conn.commit()` 앞에 추가:

```python
        # 마이그레이션: notes 테이블에 즐겨찾기/보관 플래그 추가
        note_cols = {r[1] for r in conn.execute("PRAGMA table_info(notes)")}
        if "is_favorite" not in note_cols:
            conn.execute(
                "ALTER TABLE notes ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0"
            )
        if "is_archived" not in note_cols:
            conn.execute(
                "ALTER TABLE notes ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0"
            )
```

주의: SCHEMA의 `CREATE TABLE IF NOT EXISTS notes`에도 두 컬럼을 추가한다 (신규 DB용):

```sql
  analysis_status TEXT NOT NULL DEFAULT 'pending',
  is_favorite INTEGER NOT NULL DEFAULT 0,
  is_archived INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  modified_at TEXT NOT NULL
```

- [ ] **Step 4: 통과 확인**

Run: `cd /var/www/html/Space_Note_v100/backend && venv/bin/python -m pytest tests -q`
Expected: 전체 PASS (기존 테스트 포함)

- [ ] **Step 5: Commit**

```bash
git add backend/db.py backend/tests/test_db_migration.py
git commit -m "feat(backend): add is_favorite/is_archived note flags and routes table"
```

---

### Task 2: 기항지·블랙홀 백엔드 — PATCH 플래그 + 보관 노트 제외

**Files:**
- Modify: `backend/models.py` (NotePatch)
- Modify: `backend/routers/notes.py` (`_row_to_note`, `list_notes`, `analyze_all`, `update_note`)
- Modify: `backend/routers/search.py` (`search`, `discoveries`, `discovery_routes`)
- Test: `backend/tests/test_favorites_archive.py` (신규)

**Interfaces:**
- Consumes: Task 1의 `is_favorite`/`is_archived` 컬럼.
- Produces: `PATCH /notes/{nid}`가 `{"is_favorite": bool}`/`{"is_archived": bool}`를 받음. `GET /notes?archived=true`는 보관 노트만, 기본은 활성 노트만. 노트 JSON에 `is_favorite: bool`, `is_archived: bool` 포함. 플래그만 있는 PATCH는 `modified_at` 불변·.md 재작성 없음.

- [ ] **Step 1: 실패하는 테스트 작성** — `backend/tests/test_favorites_archive.py` 신규:

```python
import services.anthropic_client as ac
from conftest import AUTH


def _mock_extract(monkeypatch, entities):
    monkeypatch.setattr(ac, "extract_entities", lambda content: entities)


def _create(client, title, content=""):
    r = client.post("/notes", json={"title": title, "content": content}, headers=AUTH)
    assert r.status_code == 200
    return r.json()


def test_favorite_toggle_keeps_modified_at(client, monkeypatch):
    _mock_extract(monkeypatch, [])
    note = _create(client, "즐겨찾기 노트", "내용")
    r = client.patch(f"/notes/{note['id']}", json={"is_favorite": True}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["is_favorite"] is True
    assert body["is_archived"] is False
    assert body["modified_at"] == note["modified_at"]  # 플래그만 변경 — 정렬 불변

    r = client.patch(f"/notes/{note['id']}", json={"is_favorite": False}, headers=AUTH)
    assert r.json()["is_favorite"] is False


def test_archive_excludes_from_default_list_and_search(client, monkeypatch):
    _mock_extract(monkeypatch, [])
    note = _create(client, "보관될 노트", "찾을내용")
    _create(client, "남는 노트", "다른내용")

    r = client.patch(f"/notes/{note['id']}", json={"is_archived": True}, headers=AUTH)
    assert r.json()["is_archived"] is True

    titles = [n["title"] for n in client.get("/notes", headers=AUTH).json()]
    assert titles == ["남는 노트"]

    archived = client.get("/notes?archived=true", headers=AUTH).json()
    assert [n["title"] for n in archived] == ["보관될 노트"]

    results = client.get("/search?q=찾을내용", headers=AUTH).json()
    assert results == []


def test_archive_excludes_from_discoveries_and_routes(client, monkeypatch):
    _mock_extract(monkeypatch, [{"name": "Ollama", "type": "tech"}])
    a = _create(client, "노트A", "Ollama 이야기")
    b = _create(client, "노트B", "Ollama 정리")

    routes = client.get("/discoveries/routes", headers=AUTH).json()
    assert len(routes) == 1

    client.patch(f"/notes/{b['id']}", json={"is_archived": True}, headers=AUTH)

    assert client.get("/discoveries/routes", headers=AUTH).json() == []
    assert client.get(f"/discoveries?note_id={a['id']}", headers=AUTH).json() == []


def test_archive_excludes_from_analyze_queue(client, monkeypatch):
    # 추출이 실패하는 노트 → analysis_status 'failed' → 분석 대상 후보가 됨
    def _raise(content):
        raise RuntimeError("extraction failed")
    monkeypatch.setattr(ac, "extract_entities", _raise)
    c = _create(client, "실패 노트", "내용 있음")

    import services.extraction as extraction
    monkeypatch.setattr(extraction, "has_api_key", lambda: True)

    client.patch(f"/notes/{c['id']}", json={"is_archived": True}, headers=AUTH)
    assert client.post("/notes/analyze", headers=AUTH).json()["queued"] == 0

    client.patch(f"/notes/{c['id']}", json={"is_archived": False}, headers=AUTH)
    assert client.post("/notes/analyze", headers=AUTH).json()["queued"] == 1
```

- [ ] **Step 2: 실패 확인**

Run: `cd /var/www/html/Space_Note_v100/backend && venv/bin/python -m pytest tests/test_favorites_archive.py -q`
Expected: FAIL — `is_favorite` 키 없음 / 필터 미적용

- [ ] **Step 3: 구현**

`backend/models.py` — `NotePatch`에 추가:

```python
class NotePatch(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category_id: Optional[str] = None
    tags: Optional[list[str]] = None
    is_favorite: Optional[bool] = None
    is_archived: Optional[bool] = None
```

`backend/routers/notes.py`:

`_row_to_note` 교체:

```python
def _row_to_note(row) -> dict:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["is_favorite"] = bool(d.get("is_favorite"))
    d["is_archived"] = bool(d.get("is_archived"))
    return d
```

`list_notes` 교체:

```python
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
```

`analyze_all`의 SELECT에 보관 제외 조건 추가:

```python
        rows = conn.execute(
            "SELECT id, content FROM notes "
            "WHERE TRIM(COALESCE(content, '')) != '' "
            "AND analysis_status IN ('pending', 'failed') "
            "AND is_archived = 0"
        ).fetchall()
```

`update_note` 교체 (플래그만 바꾸는 PATCH는 .md 재작성·modified_at 갱신 생략):

```python
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
```

`backend/routers/search.py`:

`search()`의 SQL에 보관 제외:

```python
        rows = conn.execute(
            "SELECT id, title, content, category_id, modified_at FROM notes "
            "WHERE (title LIKE ? OR content LIKE ?) AND is_archived = 0 "
            "ORDER BY modified_at DESC LIMIT 50",
            (like, like),
        ).fetchall()
```

`discoveries()` — notes JOIN이 있는 4개 쿼리 모두의 WHERE에 `AND n.is_archived = 0` 추가. 예 (note_id 있는 entities 쿼리):

```python
                rows += conn.execute(
                    f"SELECT e.note_id AS note_id, e.name AS name, "
                    f"'e:' || e.norm AS nkey, n.title AS title, "
                    f"n.category_id AS category_id, n.modified_at AS modified_at "
                    f"FROM entities e JOIN notes n ON n.id = e.note_id "
                    f"WHERE e.norm IN ({placeholders}) AND e.note_id != ? "
                    f"AND n.is_archived = 0",
                    (*norms_e, note_id),
                ).fetchall()
```

같은 방식으로 tags 쿼리와 note_id 없는 분기의 두 쿼리(이쪽은 `WHERE n.is_archived = 0`)에 적용.

`discovery_routes()` — erows/trows를 notes JOIN으로 교체:

```python
        erows = conn.execute(
            "SELECT e.note_id AS note_id, e.norm AS norm, e.name AS name "
            "FROM entities e JOIN notes n ON n.id = e.note_id "
            "WHERE e.norm IS NOT NULL AND e.norm != '' AND n.is_archived = 0"
        ).fetchall()
        trows = conn.execute(
            "SELECT t.note_id AS note_id, t.norm AS norm, t.tag AS name "
            "FROM tags t JOIN notes n ON n.id = t.note_id "
            "WHERE t.norm != '' AND n.is_archived = 0"
        ).fetchall()
```

- [ ] **Step 4: 통과 확인**

Run: `cd /var/www/html/Space_Note_v100/backend && venv/bin/python -m pytest tests -q`
Expected: 전체 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/routers/notes.py backend/routers/search.py backend/tests/test_favorites_archive.py
git commit -m "feat(backend): favorite/archive note flags with archived exclusion"
```

---

### Task 3: 항로 승격 백엔드 — routes CRUD + confirmed 플래그

**Files:**
- Modify: `backend/models.py` (RouteCreate)
- Create: `backend/routers/routes.py`
- Modify: `backend/main.py` (라우터 등록)
- Modify: `backend/routers/search.py` (`discovery_routes`에 confirmed 병합)
- Modify: `backend/routers/notes.py` (`delete_note`에서 routes 정리)
- Test: `backend/tests/test_routes.py` (신규)

**Interfaces:**
- Consumes: Task 1의 `routes` 테이블.
- Produces: `POST /routes {note_a, note_b}` → `{"note_a", "note_b", "confirmed": true}` (순서 정규화, 중복 무시, 없는 노트 404, 동일 노트 400). `DELETE /routes?note_a=..&note_b=..` → 204. `GET /discoveries/routes` 각 항목에 `confirmed: bool` — 확정 쌍은 발견에서 사라져도 유지(`shared_entities: []`).

- [ ] **Step 1: 실패하는 테스트 작성** — `backend/tests/test_routes.py` 신규:

```python
import services.anthropic_client as ac
from conftest import AUTH


def _mock_extract(monkeypatch, entities):
    monkeypatch.setattr(ac, "extract_entities", lambda content: entities)


def _create(client, title, content=""):
    r = client.post("/notes", json={"title": title, "content": content}, headers=AUTH)
    assert r.status_code == 200
    return r.json()


def test_confirm_route_normalizes_and_flags(client, monkeypatch):
    _mock_extract(monkeypatch, [{"name": "Docker", "type": "tech"}])
    a = _create(client, "노트A", "Docker 공부")
    b = _create(client, "노트B", "Docker 배포")
    lo, hi = sorted([a["id"], b["id"]])

    # 역순으로 보내도 정규화되어 저장된다
    r = client.post("/routes", json={"note_a": hi, "note_b": lo}, headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"note_a": lo, "note_b": hi, "confirmed": True}

    # 중복 승인은 무해
    assert client.post("/routes", json={"note_a": lo, "note_b": hi}, headers=AUTH).status_code == 200

    routes = client.get("/discoveries/routes", headers=AUTH).json()
    assert routes == [
        {"note_a": lo, "note_b": hi, "shared_entities": ["Docker"], "confirmed": True}
    ]

    # 해제
    r = client.delete(f"/routes?note_a={hi}&note_b={lo}", headers=AUTH)
    assert r.status_code == 204
    routes = client.get("/discoveries/routes", headers=AUTH).json()
    assert routes[0]["confirmed"] is False


def test_confirmed_route_survives_without_discovery(client, monkeypatch):
    _mock_extract(monkeypatch, [])
    a = _create(client, "무관한 A", "내용")
    b = _create(client, "무관한 B", "내용")
    lo, hi = sorted([a["id"], b["id"]])

    client.post("/routes", json={"note_a": lo, "note_b": hi}, headers=AUTH)
    routes = client.get("/discoveries/routes", headers=AUTH).json()
    assert routes == [
        {"note_a": lo, "note_b": hi, "shared_entities": [], "confirmed": True}
    ]


def test_route_validation_and_cleanup(client, monkeypatch):
    _mock_extract(monkeypatch, [])
    a = _create(client, "홀로 노트", "내용")

    r = client.post("/routes", json={"note_a": a["id"], "note_b": a["id"]}, headers=AUTH)
    assert r.status_code == 400
    r = client.post("/routes", json={"note_a": a["id"], "note_b": "없는id"}, headers=AUTH)
    assert r.status_code == 404

    b = _create(client, "지워질 노트", "내용")
    client.post("/routes", json={"note_a": a["id"], "note_b": b["id"]}, headers=AUTH)
    client.delete(f"/notes/{b['id']}", headers=AUTH)
    assert client.get("/discoveries/routes", headers=AUTH).json() == []


def test_confirmed_route_hidden_when_note_archived(client, monkeypatch):
    _mock_extract(monkeypatch, [])
    a = _create(client, "활성 노트", "내용")
    b = _create(client, "보관될 노트", "내용")
    client.post("/routes", json={"note_a": a["id"], "note_b": b["id"]}, headers=AUTH)
    client.patch(f"/notes/{b['id']}", json={"is_archived": True}, headers=AUTH)
    assert client.get("/discoveries/routes", headers=AUTH).json() == []
```

- [ ] **Step 2: 실패 확인**

Run: `cd /var/www/html/Space_Note_v100/backend && venv/bin/python -m pytest tests/test_routes.py -q`
Expected: FAIL — `POST /routes` 404 Not Found (엔드포인트 없음)

- [ ] **Step 3: 구현**

`backend/models.py` 끝에 추가:

```python
class RouteCreate(BaseModel):
    note_a: str
    note_b: str
```

`backend/routers/routes.py` 신규:

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response

from db import get_conn
from models import RouteCreate

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ordered(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


@router.post("/routes")
def confirm_route(body: RouteCreate):
    """미개척 항로를 확정 항로로 승격. 쌍은 note_a < note_b로 정규화 저장."""
    if body.note_a == body.note_b:
        raise HTTPException(status_code=400, detail="same note")
    a, b = _ordered(body.note_a, body.note_b)
    with get_conn() as conn:
        for nid in (a, b):
            if conn.execute("SELECT 1 FROM notes WHERE id = ?", (nid,)).fetchone() is None:
                raise HTTPException(status_code=404, detail="note not found")
        conn.execute(
            "INSERT OR IGNORE INTO routes (id, note_a, note_b, created_at) "
            "VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), a, b, _now()),
        )
    return {"note_a": a, "note_b": b, "confirmed": True}


@router.delete("/routes", status_code=204)
def unconfirm_route(note_a: str, note_b: str):
    a, b = _ordered(note_a, note_b)
    with get_conn() as conn:
        conn.execute("DELETE FROM routes WHERE note_a = ? AND note_b = ?", (a, b))
    return Response(status_code=204)
```

`backend/main.py` — import와 등록:

```python
from routers import attachments, categories, notes, ai, search, routes
```

```python
app.include_router(routes.router, dependencies=[Depends(require_auth)])
```

`backend/routers/notes.py` `delete_note`에 routes 정리 추가 (tags DELETE 다음 줄):

```python
        conn.execute("DELETE FROM routes WHERE note_a = ? OR note_b = ?", (nid, nid))
```

`backend/routers/search.py` `discovery_routes()` — 확정 쌍 병합. `with get_conn() as conn:` 블록 안에 확정 쌍 조회 추가(보관 노트 포함 쌍은 제외):

```python
        crows = conn.execute(
            "SELECT r.note_a AS note_a, r.note_b AS note_b FROM routes r "
            "JOIN notes na ON na.id = r.note_a AND na.is_archived = 0 "
            "JOIN notes nb ON nb.id = r.note_b AND nb.is_archived = 0"
        ).fetchall()
```

함수 끝의 return을 교체:

```python
    confirmed = {(r["note_a"], r["note_b"]) for r in crows}
    # 확정 항로는 발견 쌍에서 사라져도 유지한다 — 사용자의 명시적 선택이므로
    # AI 재계산에 좌우되지 않는다.
    all_keys = sorted(keep | confirmed)
    return [
        {
            "note_a": a,
            "note_b": b,
            "shared_entities": sorted(pairs.get((a, b), set())),
            "confirmed": (a, b) in confirmed,
        }
        for a, b in all_keys
    ]
```

- [ ] **Step 4: 통과 확인**

Run: `cd /var/www/html/Space_Note_v100/backend && venv/bin/python -m pytest tests -q`
Expected: 전체 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/routers/routes.py backend/main.py backend/routers/search.py backend/routers/notes.py backend/tests/test_routes.py
git commit -m "feat(backend): route confirmation endpoints and confirmed flag on discovery routes"
```

---

### Task 4: 프론트 데이터층 — 타입·API·notesStore 확장

**Files:**
- Modify: `src/types/index.ts`
- Modify: `src/api/notesApi.ts`
- Modify: `src/api/searchApi.ts`
- Modify: `src/store/notesStore.ts`

**Interfaces:**
- Consumes: Task 2·3의 백엔드 API.
- Produces: `Note.is_favorite/is_archived: boolean`, `DiscoveryRoute.confirmed: boolean`. `notesApi.list(categoryId?, archived?)`, `notesApi.update` patch에 플래그. `searchApi.confirmRoute(a, b)`, `searchApi.unconfirmRoute(a, b)`. `useNotesStore`: `archivedNotes: Note[]`, `archivedCount: number`, `toggleFavorite(id)`, `archiveNote(id)`, `restoreNote(id)`, `fetchArchived()`.

- [ ] **Step 1: 타입 확장** — `src/types/index.ts`:

`Note` 인터페이스의 `analysis_status` 줄 아래 추가:

```ts
  is_favorite: boolean
  is_archived: boolean
```

`DiscoveryRoute` 교체:

```ts
export interface DiscoveryRoute {
  note_a: string
  note_b: string
  shared_entities: string[]
  confirmed: boolean
}
```

- [ ] **Step 2: notesApi 확장** — `src/api/notesApi.ts`의 `list`와 `update` 교체:

```ts
  list: (categoryId?: string, archived?: boolean) => {
    const params = new URLSearchParams()
    if (categoryId) params.set('category_id', categoryId)
    if (archived) params.set('archived', 'true')
    const qs = params.toString()
    return apiFetch<Note[]>(`/notes${qs ? `?${qs}` : ''}`)
  },
```

```ts
  update: (id: string, patch: {
    title?: string; content?: string; category_id?: string | null
    tags?: string[]; is_favorite?: boolean; is_archived?: boolean
  }) =>
    apiFetch<Note>(`/notes/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
```

- [ ] **Step 3: searchApi 확장** — `src/api/searchApi.ts`의 `discoveryRoutes` 아래 추가:

```ts
  confirmRoute: (noteA: string, noteB: string) =>
    apiFetch<{ note_a: string; note_b: string; confirmed: boolean }>('/routes', {
      method: 'POST',
      body: JSON.stringify({ note_a: noteA, note_b: noteB }),
    }),

  unconfirmRoute: (noteA: string, noteB: string) =>
    apiFetch<void>(
      `/routes?note_a=${encodeURIComponent(noteA)}&note_b=${encodeURIComponent(noteB)}`,
      { method: 'DELETE' },
    ),
```

- [ ] **Step 4: notesStore 확장** — `src/store/notesStore.ts`:

`NotesState` 인터페이스에 추가:

```ts
  archivedNotes: Note[]
  archivedCount: number
  toggleFavorite: (id: string) => Promise<void>
  archiveNote: (id: string) => Promise<void>
  restoreNote: (id: string) => Promise<void>
  fetchArchived: () => Promise<void>
```

초기값에 `archivedNotes: [], archivedCount: 0,` 추가. 액션 구현 (`deleteNote` 아래):

```ts
  toggleFavorite: async (id) => {
    const note = get().notes.find(n => n.id === id) ?? get().activeNote
    if (!note) return
    const updated = await notesApi.update(id, { is_favorite: !note.is_favorite })
    set(s => ({
      notes: s.notes.map(n => n.id === id ? updated : n),
      activeNote: s.activeNote?.id === id ? updated : s.activeNote,
    }))
  },

  archiveNote: async (id) => {
    const updated = await notesApi.update(id, { is_archived: true })
    set(s => ({
      notes: s.notes.filter(n => n.id !== id),
      archivedNotes: [updated, ...s.archivedNotes],
      archivedCount: s.archivedCount + 1,
      activeNote: s.activeNote?.id === id ? null : s.activeNote,
    }))
  },

  restoreNote: async (id) => {
    const updated = await notesApi.update(id, { is_archived: false })
    set(s => ({
      notes: [updated, ...s.notes],
      archivedNotes: s.archivedNotes.filter(n => n.id !== id),
      archivedCount: Math.max(0, s.archivedCount - 1),
    }))
  },

  fetchArchived: async () => {
    const archivedNotes = await notesApi.list(undefined, true)
    set({ archivedNotes, archivedCount: archivedNotes.length })
  },
```

- [ ] **Step 5: 타입체크**

Run: `cd /var/www/html/Space_Note_v100 && npm run build`
Expected: 성공 (기존 코드는 새 필드를 아직 안 쓰므로 에러 없음)

- [ ] **Step 6: Commit**

```bash
git add src/types/index.ts src/api/notesApi.ts src/api/searchApi.ts src/store/notesStore.ts
git commit -m "feat(web): note flag types, routes API, archive/favorite store actions"
```

---

### Task 5: 기항지 UI — 별 토글 + 기항지 섹션 + 에디터 토글

**Files:**
- Modify: `src/components/Sidebar/CategoryItem.tsx` (NoteItem에 별 버튼)
- Modify: `src/components/Sidebar/VoyageLog.tsx` (기항지 섹션)
- Modify: `src/components/Editor/NoteEditor.tsx` (제목 옆 별 토글)

**Interfaces:**
- Consumes: Task 4의 `toggleFavorite`, `Note.is_favorite`.

- [ ] **Step 1: NoteItem에 별 토글** — `src/components/Sidebar/CategoryItem.tsx`의 `NoteItem` 교체 부분:

`useNotesStore()`에서 `toggleFavorite`도 꺼낸다:

```ts
  const { deleteNote, toggleFavorite } = useNotesStore()
```

hover 시 삭제 버튼 왼쪽에 별 버튼 추가. 즐겨찾기 별은 hover가 아닐 때도 항상 보이므로 제목과 겹치지 않게 `paddingRight: hovered ? '46px' : note.is_favorite ? '24px' : '12px'`로 조정하고, 기존 `{hovered && (...삭제 버튼...)}` 블록을 다음으로 교체:

```tsx
      {(hovered || note.is_favorite) && (
        <button
          title={note.is_favorite ? '기항지 해제' : '기항지로 지정'}
          onClick={e => { e.stopPropagation(); toggleFavorite(note.id) }}
          style={{
            position: 'absolute',
            right: hovered ? '22px' : '6px',
            top: '50%',
            transform: 'translateY(-50%)',
            fontSize: '10px',
            color: note.is_favorite ? '#E8B23A' : 'var(--text-secondary)',
            padding: '0 3px',
            lineHeight: 1,
            opacity: note.is_favorite ? 1 : 0.7,
          }}
        >
          {note.is_favorite ? '★' : '☆'}
        </button>
      )}
      {hovered && (
        <button
          onClick={handleDelete}
          style={{
            position: 'absolute',
            right: '6px',
            top: '50%',
            transform: 'translateY(-50%)',
            fontSize: '10px',
            color: 'var(--text-primary)',
            padding: '0 3px',
            lineHeight: 1,
            opacity: 0.8,
          }}
          onMouseEnter={e => ((e.currentTarget as HTMLButtonElement).style.opacity = '1')}
          onMouseLeave={e => ((e.currentTarget as HTMLButtonElement).style.opacity = '0.8')}
        >
          ✕
        </button>
      )}
```

- [ ] **Step 2: VoyageLog에 기항지 섹션** — `src/components/Sidebar/VoyageLog.tsx`:

`const uncategorized = ...` 아래에 추가:

```ts
  const favorites = notes.filter(n => n.is_favorite)
```

렌더링에서 "항해일지" 헤더 블록(`<div className="px-3 py-1 flex ...">...</div>`)과 `{showNewCat && ...}` 사이에 삽입:

```tsx
      {favorites.length > 0 && (
        <div className="mb-1 pb-1" style={{ borderBottom: '1px solid var(--glass-border)' }}>
          <div className="px-3 py-1" style={{
            fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase',
            color: '#E8B23A', opacity: 0.85,
          }}>
            ⚓ 기항지
          </div>
          {favorites.map(note => (
            <button
              key={note.id}
              className="w-full text-left truncate"
              style={{
                fontSize: '13px',
                color: activeNote?.id === note.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                borderLeft: activeNote?.id === note.id ? '2px solid #E8B23A' : '2px solid transparent',
                paddingLeft: activeNote?.id === note.id ? '14px' : '16px',
                paddingRight: '12px', paddingTop: '3px', paddingBottom: '3px',
                display: 'block', cursor: 'pointer',
              }}
              onClick={() => handleSelectNote(note.id)}
            >
              {note.title}
            </button>
          ))}
        </div>
      )}
```

- [ ] **Step 3: 에디터 제목 옆 별 토글** — `src/components/Editor/NoteEditor.tsx`:

`useNotesStore()`에서 `toggleFavorite` 추가:

```ts
  const { activeNote, saveNote, renameNote, toggleFavorite } = useNotesStore()
```

제목 `<input ...>`을 flex 행으로 감싼다 (기존 input의 `borderBottom`은 감싼 div로 이동):

```tsx
      {/* 제목 입력 + 기항지 토글 */}
      <div style={{
        display: 'flex', alignItems: 'center', flexShrink: 0,
        borderBottom: '1px solid var(--border)',
      }}>
        <input
          ref={titleRef}
          value={titleValue}
          onChange={e => setTitleValue(e.target.value)}
          onBlur={handleTitleBlur}
          onKeyDown={handleTitleKeyDown}
          placeholder="제목 없음"
          style={{
            flex: 1,
            minWidth: 0,
            padding: '14px 8px 10px 48px',
            fontSize: '16px',
            fontWeight: 600,
            color: 'var(--text-primary)',
            background: 'transparent',
            border: 'none',
            outline: 'none',
          }}
        />
        <button
          title={activeNote.is_favorite ? '기항지 해제' : '기항지로 지정'}
          onClick={() => toggleFavorite(activeNote.id)}
          style={{
            fontSize: '15px', padding: '10px 16px 6px', lineHeight: 1,
            color: activeNote.is_favorite ? '#E8B23A' : 'var(--text-secondary)',
            background: 'transparent', border: 'none', cursor: 'pointer',
            opacity: activeNote.is_favorite ? 1 : 0.55,
          }}
        >
          {activeNote.is_favorite ? '★' : '☆'}
        </button>
      </div>
```

- [ ] **Step 3.5: 에디터에 생성일·수정일 표시 (추가 요청 2026-07-07)** — 제목 행 바로 아래에 노트 메타데이터 줄을 추가한다. `src/components/Editor/NoteEditor.tsx`:

import에 추가:

```ts
import { formatDateTime } from '../../utils/dateFormat'
```

Step 3에서 만든 제목 flex 행(div)의 닫는 태그 바로 다음(= `<FormatToolbar ...>` 앞)에 삽입:

```tsx
      {/* 노트 메타데이터: 생성일·수정일 */}
      <div style={{
        display: 'flex', gap: 16, flexShrink: 0,
        padding: '4px 16px 6px 48px',
        fontSize: '10.5px', color: 'var(--text-secondary)', opacity: 0.75,
        borderBottom: '1px solid var(--border)',
        whiteSpace: 'nowrap', overflow: 'hidden',
      }}>
        <span>최초 생성일: {formatDateTime(activeNote.created_at)}</span>
        <span>최근 수정일: {formatDateTime(activeNote.modified_at)}</span>
      </div>
```

주의: Step 3의 제목 행 div에 있던 `borderBottom`은 이 메타데이터 줄로 이동한다 (제목 행 div의 `borderBottom: '1px solid var(--border)'` 스타일을 제거하고 위 메타데이터 div가 대신 가진다 — 헤더 하단 경계선이 중복되지 않게).

- [ ] **Step 4: 빌드 확인**

Run: `cd /var/www/html/Space_Note_v100 && npm run build`
Expected: 성공

- [ ] **Step 5: Commit**

```bash
git add src/components/Sidebar/CategoryItem.tsx src/components/Sidebar/VoyageLog.tsx src/components/Editor/NoteEditor.tsx
git commit -m "feat(web): favorite (기항지) toggle in note list, sidebar section, editor header"
```

---

### Task 6: 블랙홀 UI — 보관 액션 + 접이식 블랙홀 섹션

**Files:**
- Modify: `src/components/Sidebar/CategoryItem.tsx` (NoteItem에 보관 버튼)
- Modify: `src/components/Sidebar/VoyageLog.tsx` (블랙홀 섹션)

**Interfaces:**
- Consumes: Task 4의 `archiveNote`, `restoreNote`, `fetchArchived`, `archivedNotes`, `archivedCount`, `deleteNote`.

- [ ] **Step 1: NoteItem에 보관 버튼** — `src/components/Sidebar/CategoryItem.tsx`:

`useNotesStore()`에 `archiveNote` 추가:

```ts
  const { deleteNote, toggleFavorite, archiveNote } = useNotesStore()
```

hover 버튼이 3개가 되므로 paddingRight를 `hovered ? '62px' : note.is_favorite ? '24px' : '12px'`로 조정. 별 버튼의 `right`를 `hovered ? '38px' : '6px'`로 바꾸고, 별 버튼과 삭제 버튼 사이에 보관 버튼 추가:

```tsx
      {hovered && (
        <button
          title="블랙홀로 보내기 (보관)"
          onClick={e => { e.stopPropagation(); archiveNote(note.id) }}
          style={{
            position: 'absolute',
            right: '22px',
            top: '50%',
            transform: 'translateY(-50%)',
            fontSize: '10px',
            color: 'var(--text-secondary)',
            padding: '0 3px',
            lineHeight: 1,
            opacity: 0.7,
          }}
          onMouseEnter={e => ((e.currentTarget as HTMLButtonElement).style.opacity = '1')}
          onMouseLeave={e => ((e.currentTarget as HTMLButtonElement).style.opacity = '0.7')}
        >
          ◐
        </button>
      )}
```

- [ ] **Step 2: VoyageLog 하단 블랙홀 섹션** — `src/components/Sidebar/VoyageLog.tsx`:

store에서 추가로 꺼낸다:

```ts
  const { notes, fetchNotes, openNote, createNote, activeNote, setTab, moveNote,
    archivedNotes, archivedCount, fetchArchived, restoreNote, deleteNote } = useNotesStore()
```

상태 추가:

```ts
  const [blackholeOpen, setBlackholeOpen] = useState(false)
```

마운트 시 보관 개수 로드 — 기존 useEffect에 한 줄 추가:

```ts
  useEffect(() => {
    fetchCategories().catch(console.error)
    fetchNotes().catch(console.error)
    fetchArchived().catch(console.error)
  }, [])
```

렌더링 마지막(미분류 블록 뒤)에 추가:

```tsx
      {archivedCount > 0 && (
        <div className="mt-2 pt-2" style={{ borderTop: '1px solid var(--glass-border)' }}>
          <button
            className="w-full text-left px-3 py-1 flex items-center gap-1.5"
            style={{
              fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase',
              color: 'var(--text-secondary)', opacity: 0.7,
            }}
            onClick={() => {
              setBlackholeOpen(o => !o)
              if (!blackholeOpen) fetchArchived().catch(console.error)
            }}
          >
            <span>🕳 블랙홀 ({archivedCount})</span>
            <span className="ml-auto" style={{ fontSize: '9px' }}>{blackholeOpen ? '▾' : '▸'}</span>
          </button>
          {blackholeOpen && archivedNotes.map(note => (
            <div key={note.id} className="flex items-center" style={{ paddingRight: '8px' }}>
              <span
                className="flex-1 truncate"
                style={{
                  fontSize: '12px', color: 'var(--text-secondary)', opacity: 0.6,
                  paddingLeft: '16px', paddingTop: '3px', paddingBottom: '3px',
                }}
              >
                {note.title}
              </span>
              <button
                title="복원"
                onClick={() => restoreNote(note.id)}
                style={{ fontSize: '10px', color: 'var(--text-secondary)', padding: '0 4px' }}
              >
                ↺
              </button>
              <button
                title="영구 삭제"
                onClick={() => {
                  if (confirm(`"${note.title}" 노트를 영구 삭제할까요? (.md 파일도 삭제됩니다)`)) {
                    deleteNote(note.id).then(() => fetchArchived()).catch(console.error)
                  }
                }}
                style={{ fontSize: '10px', color: '#C92A2A', padding: '0 4px' }}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
```

주의: `deleteNote`는 활성 목록(`notes`) 기준이므로 보관 노트 삭제 후 `fetchArchived()`로 보관 목록·개수를 다시 맞춘다 (위 코드에 포함).

- [ ] **Step 3: 빌드 확인**

Run: `cd /var/www/html/Space_Note_v100 && npm run build`
Expected: 성공

- [ ] **Step 4: Commit**

```bash
git add src/components/Sidebar/CategoryItem.tsx src/components/Sidebar/VoyageLog.tsx
git commit -m "feat(web): archive (블랙홀) action and collapsible archived section"
```

---

### Task 7: 성도 — 기항지 비콘 링 + 블랙홀 오브젝트 + 위성(첨부파일)

**Files:**
- Modify: `src/components/StarMap/StarMapCanvas.tsx`

**Interfaces:**
- Consumes: `Note.is_favorite`, `Note.content`, `useNotesStore.getState().archivedCount`.

- [ ] **Step 1: 비콘 텍스처 헬퍼 추가** — `makeGlowTexture()` 함수 아래에 추가:

```ts
function makeBeaconTexture(): THREE.Texture {
  const s = 128
  const canvas = document.createElement('canvas')
  canvas.width = s
  canvas.height = s
  const ctx = canvas.getContext('2d')!
  ctx.strokeStyle = 'rgba(255, 214, 122, 0.95)'
  ctx.lineWidth = 5
  ctx.beginPath()
  ctx.arc(s / 2, s / 2, s / 2 - 8, 0, Math.PI * 2)
  ctx.stroke()
  return new THREE.CanvasTexture(canvas)
}
```

- [ ] **Step 2: 행성 생성 루프에서 비콘 부착** — 씬 구성 effect 안:

행성 루프 앞(`const starMeshes: THREE.Mesh[] = []` 옆)에 준비:

```ts
    const beaconTex = makeBeaconTexture()
    disposables.push(beaconTex)
    const beacons: { spr: THREE.Sprite; base: number; phase: number }[] = []
```

`catNotes.forEach((note, j) => { ... })` 안, `mesh.userData.categoryColor = catColor.clone()` 다음에 추가:

```ts
        // 기항지 비콘: 즐겨찾기 행성에 맥동하는 금색 링 (스프라이트 = 항상 카메라 정면)
        if (note.is_favorite) {
          const spr = new THREE.Sprite(new THREE.SpriteMaterial({
            map: beaconTex, color: 0xffd67a,
            transparent: true, opacity: 0.7,
            depthWrite: false, blending: THREE.AdditiveBlending,
          }))
          const base = planetR * 2.4
          spr.scale.setScalar(base)
          mesh.add(spr)
          beacons.push({ spr, base, phase: Math.random() * Math.PI * 2 })
        }
```

- [ ] **Step 3: 블랙홀 오브젝트 추가** — 항로 로드 블록(`searchApi.discoveryRoutes()...`) 앞에 추가:

```ts
    // ── 블랙홀 (보관 노트의 거처) — 전체 성도에서만 표시 ─────
    let blackholeMesh: THREE.Mesh | null = null
    let accretionDisk: THREE.Mesh | null = null
    if (!starMapFilter) {
      const bhPos = lookTarget.clone().add(
        new THREE.Vector3(-initCamR * 0.5, -initCamR * 0.16, initCamR * 0.28),
      )
      blackholeMesh = new THREE.Mesh(
        new THREE.SphereGeometry(10, 32, 24),
        new THREE.MeshBasicMaterial({ color: 0x000000 }),
      )
      blackholeMesh.position.copy(bhPos)
      blackholeMesh.userData.blackhole = true
      scene.add(blackholeMesh)

      accretionDisk = new THREE.Mesh(
        makeRingGeometry(13, 26),
        new THREE.MeshBasicMaterial({
          map: ringTex, color: 0xff9440, transparent: true, opacity: 0.75,
          side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
        }),
      )
      accretionDisk.rotation.x = Math.PI / 2 - 0.35
      blackholeMesh.add(accretionDisk)

      const bhGlow = new THREE.Sprite(new THREE.SpriteMaterial({
        map: glowTex, color: 0x8a5aff,
        transparent: true, opacity: 0.22,
        depthWrite: false, blending: THREE.AdditiveBlending,
      }))
      bhGlow.scale.setScalar(70)
      blackholeMesh.add(bhGlow)
    }
```

- [ ] **Step 4: 레이캐스트·툴팁·애니메이션 연결**

`getHit()`의 intersectObjects 대상에 블랙홀 포함:

```ts
      const targets: THREE.Object3D[] = [...starMeshes, ...shipMeshes]
      if (blackholeMesh) targets.push(blackholeMesh)
      const hits = raycaster.intersectObjects(targets, false)
```

pointermove 핸들러의 `if (hit)` 블록 안, `shared` 처리 앞에 추가:

```ts
        if (hit.userData.blackhole) {
          canvas.style.cursor = 'default'
          const n = useNotesStore.getState().archivedCount
          setTooltip({ title: `블랙홀 — 보관된 노트 ${n}개`, x: e.clientX - rect.left, y: e.clientY - rect.top })
          return
        }
```

행성 툴팁에는 기항지·첨부 수 표시를 붙인다 — 기존 `setTooltip({ title: note.title, ... })` 줄 교체:

```ts
          const att = attachmentCount(note.content)
          setTooltip({
            title: `${note.is_favorite ? '⚓ ' : ''}${note.title}${att > 0 ? ` · 📎${att}` : ''}`,
            x: e.clientX - rect.left, y: e.clientY - rect.top,
          })
```

- [ ] **Step 4.4: 행성 궤도 안정화 (버그 수정, 사용자 보고 2026-07-07)** — 현재 행성은 노트 목록 순서(`modified_at` DESC)대로 안쪽 궤도부터 배치되어, 노트를 수정할 때마다 그 행성이 태양 쪽으로 점프하고 궤도가 전부 밀린다. 배치를 생성 시각 오름차순으로 고정한다 — 먼저 만든 노트가 안쪽, 나중에 만든 노트가 바깥쪽(수정해도 불변).

행성 루프의 `const catNotes = visibleNotes.filter(n => n.category_id === cat.id)` 줄을 다음으로 교체 (항성 크기 계산부의 filter는 개수만 세므로 그대로 둔다):

```ts
      const catNotes = visibleNotes
        .filter(n => n.category_id === cat.id)
        .sort((a, b) => a.created_at.localeCompare(b.created_at))
```

- [ ] **Step 4.5: 위성(첨부파일) 렌더링** — 첨부가 있는 노트의 행성에 작은 위성을 공전시킨다.

파일 상단(컴포넌트 밖, `makeBeaconTexture` 근처)에 첨부 수 헬퍼 추가:

```ts
function attachmentCount(content: string): number {
  return (content.match(/\/attachments\/file\//g) ?? []).length
}
```

행성 루프 준비부(`const beacons: ...` 옆)에 위성 목록 추가:

```ts
    const moons: { pivot: THREE.Object3D; speed: number }[] = []
```

행성 루프 안, 기항지 비콘 블록 다음에 추가:

```ts
        // 위성: 첨부파일이 있는 노트 (첨부 수만큼, 최대 3개)
        const attCount = Math.min(3, attachmentCount(note.content))
        for (let m = 0; m < attCount; m++) {
          const pivot = new THREE.Object3D()
          pivot.rotation.z = 0.4 + m * 0.9   // 위성마다 다른 궤도 기울기
          pivot.rotation.y = m * 2.1          // 시작각 분산
          const moon = new THREE.Mesh(
            new THREE.SphereGeometry(planetR * 0.22, 12, 10),
            new THREE.MeshStandardMaterial({ color: 0xb8bcc8, roughness: 0.95 }),
          )
          moon.position.x = planetR * (1.8 + m * 0.4)
          pivot.add(moon)
          mesh.add(pivot)
          moons.push({ pivot, speed: 0.02 - m * 0.004 })
        }
```

`animate()` 안(비콘 맥동 처리 옆)에 공전 추가:

```ts
      moons.forEach(mo => { mo.pivot.rotation.y += mo.speed })
```

`animate()` 안(`sunMaterials.forEach` 다음)에 추가:

```ts
      // 기항지 비콘 맥동
      beacons.forEach(bc => {
        const pulse = 1 + Math.sin(t * 2 + bc.phase) * 0.18
        bc.spr.scale.setScalar(bc.base * pulse)
        ;(bc.spr.material as THREE.SpriteMaterial).opacity =
          0.5 + Math.sin(t * 2 + bc.phase) * 0.25
      })
      // 블랙홀 강착원반 회전
      if (accretionDisk) accretionDisk.rotation.z += 0.012
```

주의: `useNotesStore`는 이미 이 파일에서 import되어 있다. `archivedCount`는 훅이 아니라 이벤트 시점에 `getState()`로 읽으므로 effect deps 추가가 필요 없다.

- [ ] **Step 5: 빌드 확인**

Run: `cd /var/www/html/Space_Note_v100 && npm run build`
Expected: 성공

- [ ] **Step 6: Commit**

```bash
git add src/components/StarMap/StarMapCanvas.tsx
git commit -m "feat(web): favorite beacon rings and black hole object in StarMap"
```

---

### Task 8: 성도 — 확정/미개척 항로 시각 위계

**Files:**
- Modify: `src/components/StarMap/StarMapCanvas.tsx`

**Interfaces:**
- Consumes: Task 3·4의 `DiscoveryRoute.confirmed`.
- Produces: 확정 항로 = 금색(0xffd27a)·opacity 0.85·우주선 있음. 미개척 = 기존 카테고리 혼합색·opacity 0.18·우주선 없음. `RouteVisual.ship`은 optional.

- [ ] **Step 1: RouteVisual 타입 변경** — 파일 상단:

```ts
interface RouteVisual {
  aIdx: number
  bIdx: number
  line: THREE.Line
  ship?: THREE.Mesh
  t: number
  dir: number
}
```

- [ ] **Step 2: 항로 생성 분기** — `searchApi.discoveryRoutes().then(...)` 안의 `routes.forEach` 본문에서 line/ship 생성부 교체:

```ts
        const colorA = starMeshes[aIdx].userData.categoryColor as THREE.Color
        const colorB = starMeshes[bIdx].userData.categoryColor as THREE.Color
        // 확정 항로는 금색 실선으로 강조, 미개척 항로는 흐린 배경 선으로
        const lineColor = route.confirmed
          ? new THREE.Color(0xffd27a)
          : colorA.clone().lerp(colorB, 0.5)

        const points = buildRouteCurvePoints(starMeshes[aIdx].position, starMeshes[bIdx].position)
        const lineGeo = new THREE.BufferGeometry().setFromPoints(points)
        const line = new THREE.Line(
          lineGeo,
          new THREE.LineBasicMaterial({
            color: lineColor, transparent: true,
            opacity: route.confirmed ? 0.85 : 0.18,
            depthWrite: false, blending: THREE.AdditiveBlending,
          }),
        )
        scene.add(line)

        let ship: THREE.Mesh | undefined
        if (route.confirmed) {
          ship = new THREE.Mesh(shipGeometry, shipMaterial)
          ship.userData.shared = route.shared_entities
          ship.userData.confirmed = true
          scene.add(ship)
          shipMeshes.push(ship)
        }

        routeVisuals.push({ aIdx, bIdx, line, ship, t: Math.random(), dir: 1 })
```

- [ ] **Step 3: 애니메이션 가드** — `animate()`의 `routeVisuals.forEach` 안에서 우주선 이동부를 조건 처리:

```ts
      routeVisuals.forEach(rv => {
        const a = starMeshes[rv.aIdx].position
        const b = starMeshes[rv.bIdx].position
        const points = buildRouteCurvePoints(a, b)
        rv.line.geometry.setFromPoints(points)

        if (!rv.ship) return
        rv.t += rv.dir * 0.006
        if (rv.t >= 1) { rv.t = 1; rv.dir = -1 }
        if (rv.t <= 0) { rv.t = 0; rv.dir = 1 }
        const eased = rv.t * rv.t * (3 - 2 * rv.t) // smoothstep — 양 끝에서 감속

        const curve = new THREE.CatmullRomCurve3(points)
        const pos = curve.getPointAt(Math.min(0.999, Math.max(0.001, eased)))
        const tangent = curve.getTangentAt(Math.min(0.999, Math.max(0.001, eased)))
        rv.ship.position.copy(pos)
        rv.ship.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), tangent.normalize())
      })
```

- [ ] **Step 4: 우주선 툴팁에 확정 표시** — pointermove의 `shared` 처리 교체:

```ts
        const shared = hit.userData.shared as string[] | undefined
        if (shared) {
          canvas.style.cursor = 'default'
          const label = shared.length > 0 ? `확정 항로 — 공유: ${shared.join(', ')}` : '확정 항로'
          setTooltip({ title: label, x: e.clientX - rect.left, y: e.clientY - rect.top })
          return
        }
```

- [ ] **Step 5: 빌드 확인**

Run: `cd /var/www/html/Space_Note_v100 && npm run build`
Expected: 성공

- [ ] **Step 6: Commit**

```bash
git add src/components/StarMap/StarMapCanvas.tsx
git commit -m "feat(web): visual hierarchy for confirmed vs uncharted routes in StarMap"
```

---

### Task 9: 미개척 항로 패널 — 항로 확정 버튼

**Files:**
- Modify: `src/components/Navigation/DiscoveriesPanel.tsx`

**Interfaces:**
- Consumes: Task 4의 `searchApi.discoveryRoutes/confirmRoute/unconfirmRoute`, `DiscoveryRoute.confirmed`.

- [ ] **Step 1: 확정 상태 로드** — 컴포넌트에 상태·로더 추가:

```ts
import { searchApi } from '../../api/searchApi'
import type { DiscoveryRoute } from '../../types'
```

```ts
  const [routes, setRoutes] = useState<DiscoveryRoute[]>([])

  const loadRoutes = async () => {
    try { setRoutes(await searchApi.discoveryRoutes()) } catch { setRoutes([]) }
  }

  useEffect(() => {
    loadRoutes()
  }, [activeNote?.id]) // eslint-disable-line react-hooks/exhaustive-deps
```

확정 판정 헬퍼 (컴포넌트 안):

```ts
  const pairKey = (a: string, b: string) => (a < b ? `${a}|${b}` : `${b}|${a}`)
  const confirmedSet = new Set(routes.filter(r => r.confirmed).map(r => pairKey(r.note_a, r.note_b)))

  const toggleConfirm = async (otherId: string) => {
    if (!activeNote) return
    const isConfirmed = confirmedSet.has(pairKey(activeNote.id, otherId))
    try {
      if (isConfirmed) await searchApi.unconfirmRoute(activeNote.id, otherId)
      else await searchApi.confirmRoute(activeNote.id, otherId)
      await loadRoutes()
    } catch (e) {
      console.error('항로 확정 실패:', e)
    }
  }
```

`runAnalyze`의 `await loadDiscoveries(activeNote?.id)` 뒤에도 `await loadRoutes()` 한 줄 추가.

- [ ] **Step 2: 목록 항목에 확정 버튼** — 발견 항목의 outer `<button>`을 `<div role="button">`으로 바꾸고(버튼 중첩 금지) 확정 버튼 추가. `discoveries.map(d => (...))` 블록 교체:

```tsx
        {discoveries.map(d => {
          const isConfirmed = activeNote ? confirmedSet.has(pairKey(activeNote.id, d.note_id)) : false
          return (
            <div
              key={d.note_id}
              role="button"
              tabIndex={0}
              onClick={() => { openNote(d.note_id); setTab('edit'); setPanel(null) }}
              onKeyDown={e => { if (e.key === 'Enter') { openNote(d.note_id); setTab('edit'); setPanel(null) } }}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                padding: '10px 16px', background: 'none', cursor: 'pointer',
                border: 'none', borderBottom: '1px solid var(--border)',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-input)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'none')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                  background: catColor(d.category_id),
                }} />
                <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                  {d.title}
                </span>
                <span style={{
                  marginLeft: 'auto', fontSize: 10,
                  color: 'var(--accent-line)', fontWeight: 600,
                }}>
                  {d.shared_count}개 공통
                </span>
              </div>
              {d.shared_entities.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, paddingLeft: 12 }}>
                  {d.shared_entities.map(ent => (
                    <span
                      key={ent}
                      style={{
                        fontSize: 10, padding: '1px 6px',
                        background: 'var(--bg-input)', borderRadius: 10,
                        color: 'var(--text-secondary)', border: '1px solid var(--border)',
                      }}
                    >
                      {ent}
                    </span>
                  ))}
                </div>
              )}
              {activeNote && (
                <div style={{ paddingLeft: 12, marginTop: 6 }}>
                  <button
                    onClick={e => { e.stopPropagation(); toggleConfirm(d.note_id) }}
                    style={{
                      fontSize: 10, padding: '2px 8px', borderRadius: 4, cursor: 'pointer',
                      color: isConfirmed ? '#E8B23A' : 'var(--text-secondary)',
                      background: 'var(--bg-input)',
                      border: isConfirmed ? '1px solid #E8B23A' : '1px solid var(--border)',
                    }}
                  >
                    {isConfirmed ? '✦ 확정됨 — 클릭해 해제' : '⟡ 항로 확정'}
                  </button>
                </div>
              )}
            </div>
          )
        })}
```

주의: 확정 버튼은 `activeNote`가 있을 때만 표시한다 (쌍의 한쪽이 현재 노트라는 전제가 성립해야 하므로).

- [ ] **Step 3: 빌드 확인**

Run: `cd /var/www/html/Space_Note_v100 && npm run build`
Expected: 성공

- [ ] **Step 4: Commit**

```bash
git add src/components/Navigation/DiscoveriesPanel.tsx
git commit -m "feat(web): route confirmation toggle in discoveries panel"
```

---

### Task 10: 토스트 시스템 — uiStore + ToastStack (+dev 훅)

**Files:**
- Create: `src/store/uiStore.ts`
- Create: `src/components/Layout/ToastStack.tsx`
- Modify: `src/App.tsx` (마운트 + dev 훅)

**Interfaces:**
- Produces: `useUIStore` — `toasts: Toast[]`, `pushToast(message, onClick?)`, `dismissToast(id)`, `supernovaIds: string[]`, `setSupernovae(ids)`, `consumeSupernovae(): string[]`. dev 모드에서 `window.__sn = { useUIStore, useNotesStore }` (QA용).

- [ ] **Step 1: uiStore 작성** — `src/store/uiStore.ts` 신규:

```ts
import { create } from 'zustand'

export interface Toast {
  id: number
  message: string
  onClick?: () => void
}

interface UIState {
  toasts: Toast[]
  supernovaIds: string[]
  pushToast: (message: string, onClick?: () => void) => void
  dismissToast: (id: number) => void
  setSupernovae: (ids: string[]) => void
  consumeSupernovae: () => string[]
}

let toastSeq = 0

export const useUIStore = create<UIState>((set, get) => ({
  toasts: [],
  supernovaIds: [],

  pushToast: (message, onClick) => {
    const id = ++toastSeq
    set(s => ({ toasts: [...s.toasts, { id, message, onClick }] }))
    setTimeout(() => get().dismissToast(id), 8000)
  },

  dismissToast: (id) => set(s => ({ toasts: s.toasts.filter(t => t.id !== id) })),

  setSupernovae: (ids) => set({ supernovaIds: ids }),

  consumeSupernovae: () => {
    const ids = get().supernovaIds
    if (ids.length) set({ supernovaIds: [] })
    return ids
  },
}))
```

- [ ] **Step 2: ToastStack 작성** — `src/components/Layout/ToastStack.tsx` 신규:

```tsx
import { useUIStore } from '../../store/uiStore'

export function ToastStack() {
  const { toasts, dismissToast } = useUIStore()
  if (toasts.length === 0) return null

  return (
    <div style={{
      position: 'fixed', bottom: 20, right: 20, zIndex: 100,
      display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 340,
    }}>
      {toasts.map(t => (
        <div
          key={t.id}
          role={t.onClick ? 'button' : undefined}
          onClick={() => { t.onClick?.(); dismissToast(t.id) }}
          style={{
            background: 'rgba(2,4,10,0.94)',
            border: '1px solid rgba(232,178,58,0.45)',
            borderRadius: 8,
            padding: '10px 14px',
            fontSize: 12.5,
            color: '#eee6d0',
            cursor: t.onClick ? 'pointer' : 'default',
            boxShadow: '0 4px 18px rgba(0,0,0,0.55)',
            letterSpacing: '0.02em',
            lineHeight: 1.5,
          }}
        >
          {t.message}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: App에 마운트 + dev 훅** — `src/App.tsx`:

import 추가:

```ts
import { ToastStack } from './components/Layout/ToastStack'
import { useUIStore } from './store/uiStore'
```

`SettingsAwareLayout`의 return에 추가:

```tsx
    <>
      <AppLayout sidebar={<Sidebar />} main={<MainPanel />} />
      {showSettings && <ApiSettings onClose={() => setShowSettings(false)} />}
      <ToastStack />
    </>
```

파일 하단 `export default App` 앞에 (브라우저 QA에서 스토어를 조작하기 위한 dev 전용 훅):

```ts
// dev 전용: 브라우저 QA에서 스토어 접근용 (프로덕션 빌드 제외)
if (import.meta.env.DEV) {
  ;(window as unknown as Record<string, unknown>).__sn = { useUIStore, useNotesStore }
}
```

- [ ] **Step 4: 빌드 확인**

Run: `cd /var/www/html/Space_Note_v100 && npm run build`
Expected: 성공

- [ ] **Step 5: Commit**

```bash
git add src/store/uiStore.ts src/components/Layout/ToastStack.tsx src/App.tsx
git commit -m "feat(web): toast stack and ui store with dev hook"
```

---

### Task 11: 초신성 — 분석 diff 판정 + 성도 버스트 연출

**Files:**
- Modify: `src/components/Navigation/DiscoveriesPanel.tsx` (판정)
- Modify: `src/components/StarMap/StarMapCanvas.tsx` (버스트)

**Interfaces:**
- Consumes: Task 10의 `useUIStore`, Task 8의 항로 데이터.
- Produces: 분석 후 새 연결 3개 이상 생긴 노트 → 토스트 + `supernovaIds`. 성도가 열리면(또는 열려 있으면) 해당 행성에서 버스트 1회 재생.

- [ ] **Step 1: 판정 로직** — `src/components/Navigation/DiscoveriesPanel.tsx`:

import 추가:

```ts
import { useUIStore } from '../../store/uiStore'
```

`runAnalyze` 교체(스냅샷·diff 추가 — 기존 폴링·오류 처리는 그대로 유지):

```ts
  const runAnalyze = async (call: () => Promise<{ queued: number }>) => {
    setNotice('')
    setAnalyzing(true)
    // 초신성 판정용: 분석 전 항로 스냅샷
    let before: DiscoveryRoute[] = []
    try { before = await searchApi.discoveryRoutes() } catch { /* 스냅샷 실패 시 판정 생략 */ }
    try {
      const { queued } = await call()
      if (queued === 0) {
        setNotice('분석할 노트가 없습니다')
        return
      }
      setNotice(`${queued}개 노트 분석 중...`)
      const done = await pollUntilDone()
      if (!alive.current) return
      await fetchNotes()
      await loadDiscoveries(activeNote?.id)
      await loadRoutes()
      detectSupernovae(before)
      if (!done) {
        setNotice('아직 분석이 진행 중입니다 — 잠시 후 새로고침을 눌러주세요')
        return
      }
      const failed = useNotesStore.getState().notes
        .filter(n => n.analysis_status === 'failed' && n.word_count > 0).length
      setNotice(
        failed > 0
          ? `${failed}개 분석 실패 — API 요청 한도(429)일 수 있습니다. 1분 후 다시 시도하세요`
          : '',
      )
    } catch (e: any) {
      setNotice(
        String(e?.message).includes('API 400')
          ? '설정에서 API 키를 먼저 저장하세요 (Anthropic 또는 Gemini)'
          : '분석 요청에 실패했습니다',
      )
    } finally {
      if (alive.current) setAnalyzing(false)
    }
  }
```

판정 함수 (컴포넌트 안, `runAnalyze` 위):

```ts
  // 새 연결이 3개 이상 생긴 노트를 초신성으로 판정 (일회성 — 저장하지 않음)
  const detectSupernovae = async (before: DiscoveryRoute[]) => {
    let after: DiscoveryRoute[] = []
    try { after = await searchApi.discoveryRoutes() } catch { return }
    const beforeKeys = new Set(before.map(r => `${r.note_a}|${r.note_b}`))
    const newCounts = new Map<string, number>()
    after.forEach(r => {
      if (beforeKeys.has(`${r.note_a}|${r.note_b}`)) return
      newCounts.set(r.note_a, (newCounts.get(r.note_a) ?? 0) + 1)
      newCounts.set(r.note_b, (newCounts.get(r.note_b) ?? 0) + 1)
    })
    const supernovae = [...newCounts.entries()].filter(([, c]) => c >= 3)
    if (supernovae.length === 0) return
    const { setSupernovae, pushToast } = useUIStore.getState()
    setSupernovae(supernovae.map(([id]) => id))
    const allNotes = useNotesStore.getState().notes
    supernovae.forEach(([id, c]) => {
      const title = allNotes.find(n => n.id === id)?.title ?? '알 수 없는 노트'
      pushToast(`💥 초신성 발견: ${title} — 새 항로 ${c}개`, () => {
        useNotesStore.getState().setTab('starmap')
        useSearchStore.getState().setPanel(null)
      })
    })
  }
```

주의: `useSearchStore`는 이미 import되어 있다.

- [ ] **Step 2: 성도 버스트 연출** — `src/components/StarMap/StarMapCanvas.tsx`:

import 추가:

```ts
import { useUIStore } from '../../store/uiStore'
```

씬 구성 effect 안, 항로 로드 블록 뒤에 추가:

```ts
    // ── 초신성 버스트 (분석에서 발견된 대량 신규 연결 — 1회 재생) ──
    interface Burst { flash: THREE.Sprite; ring: THREE.Sprite; idx: number; age: number }
    const bursts: Burst[] = []

    function spawnBursts(ids: string[]) {
      ids.forEach(id => {
        const idx = noteIds.indexOf(id)
        if (idx < 0) return
        const flash = new THREE.Sprite(new THREE.SpriteMaterial({
          map: glowTex, color: 0xfff2cc,
          transparent: true, opacity: 1,
          depthWrite: false, blending: THREE.AdditiveBlending,
        }))
        const ring = new THREE.Sprite(new THREE.SpriteMaterial({
          map: beaconTex, color: 0xffe9a0,
          transparent: true, opacity: 0.9,
          depthWrite: false, blending: THREE.AdditiveBlending,
        }))
        scene.add(flash)
        scene.add(ring)
        bursts.push({ flash, ring, idx, age: 0 })
      })
    }
    spawnBursts(useUIStore.getState().consumeSupernovae())
    // 성도가 이미 열려 있는 동안 초신성이 판정된 경우에도 재생
    const unsubSupernova = useUIStore.subscribe(state => {
      if (state.supernovaIds.length > 0) {
        spawnBursts(useUIStore.getState().consumeSupernovae())
      }
    })
```

`animate()` 안(비콘 맥동 처리 뒤)에 추가:

```ts
      // 초신성 버스트: 행성 위치에서 플래시 축소·링 확장 후 소멸 (~2.5초)
      for (let i = bursts.length - 1; i >= 0; i--) {
        const bu = bursts[i]
        bu.age += 0.008
        const p = starMeshes[bu.idx].position
        bu.flash.position.copy(p)
        bu.ring.position.copy(p)
        const fade = Math.max(0, 1 - bu.age)
        bu.flash.scale.setScalar(14 + bu.age * 10)
        ;(bu.flash.material as THREE.SpriteMaterial).opacity = fade
        bu.ring.scale.setScalar(6 + bu.age * 70)
        ;(bu.ring.material as THREE.SpriteMaterial).opacity = fade * 0.9
        if (bu.age >= 1) {
          scene.remove(bu.flash, bu.ring)
          bu.flash.material.dispose()
          bu.ring.material.dispose()
          bursts.splice(i, 1)
        }
      }
```

effect의 cleanup(return 함수) 첫 줄에 추가:

```ts
      unsubSupernova()
```

- [ ] **Step 3: 빌드 확인**

Run: `cd /var/www/html/Space_Note_v100 && npm run build`
Expected: 성공

- [ ] **Step 4: Commit**

```bash
git add src/components/Navigation/DiscoveriesPanel.tsx src/components/StarMap/StarMapCanvas.tsx
git commit -m "feat(web): supernova detection after analysis with StarMap burst effect"
```

---

### Task 12: 최종 검증 — 백엔드 전체 테스트 + 브라우저 QA

**Files:**
- Create: 스크래치패드에 QA 스크립트 (레포에 커밋하지 않음, 기존 `qa_starmap.mjs` 패턴 참고)

**Interfaces:**
- Consumes: 전체 기능.

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `cd /var/www/html/Space_Note_v100/backend && venv/bin/python -m pytest tests -q`
Expected: 전체 PASS

- [ ] **Step 2: 프론트 빌드**

Run: `cd /var/www/html/Space_Note_v100 && npm run build`
Expected: 성공

- [ ] **Step 3: 앱 기동**

Run: `cd /var/www/html/Space_Note_v100 && ./start.sh web` 후 `curl -s http://localhost:8001/health`
Expected: `{"status": "ok", ...}` (이미 떠 있으면 `./stop.sh` 후 재기동 — 백엔드 코드가 바뀌었으므로 반드시 재기동)

- [ ] **Step 4: 브라우저 QA 스크립트 작성·실행** — `qa_starmap.mjs`의 chromium 실행 패턴(playwright-core, `/snap/bin/chromium`, `--no-sandbox`)을 그대로 따라 스크래치패드에 `qa_astro.mjs`를 작성한다. 검증 시나리오:

1. 접속·온보딩 통과 (`기본 경로 사용` 버튼) 후 스크린샷.
2. **기항지**: 노트 생성 → 에디터 제목 옆 ☆ 클릭 → ★로 바뀌고 사이드바에 "⚓ 기항지" 섹션 등장 확인 (`page.waitForSelector('text=기항지')`). 스크린샷.
3. **블랙홀**: 다른 노트 hover → ◐ 클릭 → 노트가 목록에서 사라지고 "🕳 블랙홀 (1)" 섹션 등장 확인. 펼쳐서 복원(↺) 클릭 → 목록 복귀 확인. 다시 보관. 스크린샷.
4. **성도**: 성도 탭 진입 → canvas 렌더 대기 2.5초 → 스크린샷 (비콘 링·블랙홀 오브젝트 육안 확인용). 콘솔 에러 0건 확인.
5. **항로 확정**: 같은 단어(예: "Docker")를 포함한 노트 2개는 AI 분석 없이는 엔티티가 없으므로, 인라인 태그(`#docker`)를 두 노트에 넣어 태그 기반 발견을 만든다 → 미개척 항로 패널에서 "⟡ 항로 확정" 클릭 → "✦ 확정됨" 배지 확인 → 성도에서 금색 항로 스크린샷.
6. **초신성(연출만)**: dev 훅으로 주입 —
   ```js
   await page.evaluate(() => {
     const sn = window.__sn
     const note = sn.useNotesStore.getState().notes[0]
     sn.useUIStore.getState().pushToast(`💥 초신성 발견: ${note.title} — 새 항로 3개`, () => {})
     sn.useUIStore.getState().setSupernovae([note.id])
   })
   ```
   토스트 표시 확인 → 성도 탭 진입 → 1초 후 스크린샷(버스트 링 확인).
7. 전체 과정에서 `console.error`/`pageerror` 수집해 0건 확인 (외부 폰트 로드 등 기존 무관 오류는 제외하고 판단).

Expected: 모든 단계 통과, 스크린샷으로 시각 요소 확인.

- [ ] **Step 5: 발견된 문제 수정 후 재실행** — QA에서 발견된 버그는 수정하고 QA를 다시 실행해 통과를 확인한다.

- [ ] **Step 6: 최종 Commit**

```bash
git add -A
git commit -m "fix(web): QA fixes for astro features"  # 수정이 있었던 경우에만 (QA 스크립트는 스크래치패드에 있어 레포에 안 잡힘)
```
