# SpaceNote 리눅스 전환 + 백엔드 신규 구현 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SpaceNote 프론트엔드가 기대하는 FastAPI 백엔드(:8001)를 신규 구현하고, 리눅스에서 원격 브라우저 접속이 가능하도록 프론트 주소·인증을 정비하며, start.sh/stop.sh 실행 스크립트를 추가한다.

**Architecture:** FastAPI + 단일 SQLite(운영 저장소) + Vault `.md` 내보내기(Obsidian 호환) + Anthropic SDK(채팅 스트리밍 + 엔티티 추출). 단일 Bearer 토큰 인증. 프론트는 Vite dev 서버를 `--host`로 띄우고 백엔드 주소를 런타임(`window.location`)으로 해석한다.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, anthropic, python-dotenv, pydantic / React 18 + Vite 5 / bash.

---

## 설계 대비 의도적 단순화 (구현 시 확정)

스펙은 `.md`를 단일 진실원본(source of truth), 검색을 FTS5로 명시했으나, MVP 신뢰성을 위해 아래로 단순화한다 — 기능적으로 동일하며 의존성·드리프트 위험을 줄인다:

1. **운영 진실원본은 SQLite**, `.md`는 노트 저장 시 함께 쓰는 **단방향 내보내기**(Obsidian 호환). frontmatter 역파싱으로 인한 동기화 버그를 피한다.
2. **검색은 SQLite `LIKE`** (title + content). FTS5 확장이 빌드에 없을 수 있어 의존성을 제거한다. (향후 FTS5로 교체 가능.)

## 파일 구조

```
backend/
  requirements.txt        의존성
  .env.example            환경변수 템플릿
  config.py               settings 싱글톤 (env 로드, reload())
  db.py                   sqlite 연결/스키마 초기화
  auth.py                 Bearer 토큰 의존성
  models.py               Pydantic 스키마
  services/
    __init__.py
    vault.py              .md 내보내기 + 파일명 안전화
    anthropic_client.py   채팅 스트림 + 엔티티 추출 (목 가능)
    discover.py           발견 계산
  routers/
    __init__.py
    categories.py
    notes.py
    search.py
    ai.py
  main.py                 앱/CORS/라우터/스타트업 init_db/health
  tests/
    conftest.py
    test_health_auth.py
    test_categories.py
    test_notes.py
    test_search.py
    test_discover.py
    test_ai.py
src/api/config.ts         API_BASE + 토큰 헤더 헬퍼 (신규)
src/api/client.ts         BASE → config 사용, 인증 헤더
src/api/searchApi.ts      동일
src/api/aiApi.ts          동일
src/components/Setup/VaultSetup.tsx   localhost → API_BASE
src/components/Setup/TokenGate.tsx    토큰 입력 게이트 (신규)
src/App.tsx               토큰 게이트 진입 흐름
vite.config.ts            server.host 추가
start.sh / stop.sh        실행 스크립트 (신규)
.gitignore                .run/, vault/, *.db, venv 등 (신규/갱신)
README.md                 운영/nginx 안내 (신규/갱신)
```

기존 `backend/venv`(Windows용)는 사용 불가 — Task 1에서 리눅스 venv를 새로 만든다. 기존
빈 `backend/routers`, `backend/services`, `backend/tests`, `__pycache__`는 그대로 두고
그 안에 파일을 채운다.

---

## Task 1: 백엔드 스캐폴드 (venv, requirements, config, .env.example)

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/config.py`
- Create: `backend/services/__init__.py`
- Create: `backend/routers/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: requirements.txt 작성**

Create `backend/requirements.txt`:

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
anthropic>=0.40.0
python-dotenv==1.0.1
pydantic==2.10.4
pytest==8.3.4
httpx==0.28.1
```

- [ ] **Step 2: .env.example 작성**

Create `backend/.env.example`:

```
SPACENOTE_TOKEN=change-me-to-a-long-random-string
ANTHROPIC_API_KEY=sk-ant-...
VAULT_DIR=/var/www/html/Space_Note_v100/vault
DB_PATH=/var/www/html/Space_Note_v100/backend/spacenote.db
ALLOWED_ORIGIN=http://localhost:1420
EXTRACT_MODEL=claude-haiku-4-5
```

- [ ] **Step 3: config.py 작성**

Create `backend/config.py`:

```python
import os
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent


class Settings:
    """env 기반 설정 싱글톤. 테스트는 os.environ 설정 후 reload() 호출."""

    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        # .env의 값으로 채우되, 이미 설정된 os.environ(테스트/쉘)은 덮어쓰지 않음
        load_dotenv(BACKEND_DIR / ".env", override=False)
        self.SPACENOTE_TOKEN = os.getenv("SPACENOTE_TOKEN", "")
        self.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
        self.VAULT_DIR = Path(os.getenv("VAULT_DIR", str(ROOT_DIR / "vault")))
        self.DB_PATH = os.getenv("DB_PATH", str(BACKEND_DIR / "spacenote.db"))
        self.ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:1420")
        self.EXTRACT_MODEL = os.getenv("EXTRACT_MODEL", "claude-haiku-4-5")
        self.VAULT_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
```

- [ ] **Step 4: 패키지 __init__ 생성**

Create `backend/services/__init__.py` (빈 파일) 와 `backend/routers/__init__.py` (빈 파일).

- [ ] **Step 5: .gitignore 작성**

Create `.gitignore` (루트):

```
node_modules/
dist/
backend/venv/
backend/__pycache__/
backend/**/__pycache__/
backend/.pytest_cache/
backend/.env
backend/*.db
vault/
.run/
*.log
```

- [ ] **Step 6: 리눅스 venv 생성 + 의존성 설치**

Run:
```bash
cd /var/www/html/Space_Note_v100
rm -rf backend/venv
python3 -m venv backend/venv
backend/venv/bin/pip install -q -r backend/requirements.txt
backend/venv/bin/python -c "import fastapi, anthropic, uvicorn, dotenv, pydantic, pytest, httpx; print('deps ok')"
```
Expected: `deps ok`

- [ ] **Step 7: 테스트용 .env 생성 (로컬 실행 가능하도록)**

Run:
```bash
cp backend/.env.example backend/.env
```
그리고 `backend/.env`의 `SPACENOTE_TOKEN`을 임시값(`dev-token`)으로 바꾼다. (실서비스 토큰/키는 배포 시 교체.)

---

## Task 2: DB 스키마 + 연결 (`db.py`)

**Files:**
- Create: `backend/db.py`
- Test: `backend/tests/conftest.py`, `backend/tests/test_health_auth.py` (Task 3에서 사용)

- [ ] **Step 1: db.py 작성**

Create `backend/db.py`:

```python
import sqlite3
from contextlib import contextmanager
from config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
  id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  category_id TEXT,
  tags TEXT NOT NULL DEFAULT '[]',
  word_count INTEGER NOT NULL DEFAULT 0,
  analysis_status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  modified_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  note_id TEXT NOT NULL,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  anthropic_api_key TEXT NOT NULL DEFAULT '',
  openai_api_key TEXT NOT NULL DEFAULT '',
  google_api_key TEXT NOT NULL DEFAULT '',
  default_model TEXT NOT NULL DEFAULT 'claude-sonnet-4-6'
);
"""


def init_db() -> None:
    conn = sqlite3.connect(settings.DB_PATH)
    try:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_conn():
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 2: conftest.py 작성 (모든 테스트 공용 픽스처)**

Create `backend/tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SPACENOTE_TOKEN", "test-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_ORIGIN", "http://localhost:1420")

    from config import settings
    settings.reload()
    from db import init_db
    init_db()
    from main import app
    return TestClient(app)
```

`get_conn()`/`auth`가 호출 시점에 `settings`를 읽으므로 reload만으로 테스트 격리가 된다.

- [ ] **Step 3: 커밋**

```bash
git add backend/db.py backend/tests/conftest.py
git commit -m "feat(backend): sqlite schema and connection helper"
```

---

## Task 3: 앱 골격 + 인증 + /health (`auth.py`, `main.py`)

**Files:**
- Create: `backend/auth.py`
- Create: `backend/main.py`
- Test: `backend/tests/test_health_auth.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/test_health_auth.py`:

```python
from conftest import AUTH


def test_health_no_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "default_vault" in body


def test_categories_requires_auth(client):
    r = client.get("/categories")
    assert r.status_code == 401


def test_categories_with_auth_ok(client):
    r = client.get("/categories", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_health_auth.py -v`
Expected: FAIL (`main` 모듈 없음 / import 에러)

- [ ] **Step 3: auth.py 작성**

Create `backend/auth.py`:

```python
from fastapi import Header, HTTPException
from config import settings


def require_auth(authorization: str | None = Header(default=None)) -> None:
    expected = settings.SPACENOTE_TOKEN
    if not expected:
        raise HTTPException(status_code=500, detail="SPACENOTE_TOKEN not configured")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid or missing token")
```

- [ ] **Step 4: main.py 작성 (categories 라우터는 다음 태스크에서 채움 — 임시 빈 라우터 포함)**

Create `backend/routers/categories.py` (임시 골격, Task 4에서 확장):

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/categories")
def list_categories():
    from db import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM categories ORDER BY sort_order, created_at"
        ).fetchall()
    return [dict(r) for r in rows]
```

Create `backend/main.py`:

```python
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db import init_db
from auth import require_auth
from routers import categories

app = FastAPI(title="SpaceNote Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGIN.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "default_vault": str(settings.VAULT_DIR)}


app.include_router(categories.router, dependencies=[Depends(require_auth)])
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_health_auth.py -v`
Expected: 3 passed

- [ ] **Step 6: 커밋**

```bash
git add backend/auth.py backend/main.py backend/routers/categories.py backend/tests/test_health_auth.py
git commit -m "feat(backend): app skeleton, bearer auth, health endpoint"
```

---

## Task 4: Pydantic 모델 + 카테고리 CRUD (`models.py`, `routers/categories.py`)

**Files:**
- Create: `backend/models.py`
- Modify: `backend/routers/categories.py`
- Test: `backend/tests/test_categories.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/test_categories.py`:

```python
from conftest import AUTH


def test_create_list_update_delete_category(client):
    # create
    r = client.post("/categories", json={"name": "은하1", "color": "#abcdef"}, headers=AUTH)
    assert r.status_code == 200
    cat = r.json()
    assert cat["name"] == "은하1"
    assert cat["color"] == "#abcdef"
    assert cat["id"]
    assert cat["sort_order"] == 0
    assert cat["created_at"]

    cid = cat["id"]

    # list
    r = client.get("/categories", headers=AUTH)
    assert len(r.json()) == 1

    # update
    r = client.patch(f"/categories/{cid}", json={"name": "은하-수정", "sort_order": 3}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["name"] == "은하-수정"
    assert r.json()["sort_order"] == 3

    # delete
    r = client.delete(f"/categories/{cid}", headers=AUTH)
    assert r.status_code == 204
    r = client.get("/categories", headers=AUTH)
    assert r.json() == []


def test_update_missing_category_404(client):
    r = client.patch("/categories/nope", json={"name": "x"}, headers=AUTH)
    assert r.status_code == 404
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_categories.py -v`
Expected: FAIL (POST/PATCH/DELETE 경로 없음 → 405/404)

- [ ] **Step 3: models.py 작성**

Create `backend/models.py`:

```python
from typing import Optional
from pydantic import BaseModel


class CategoryCreate(BaseModel):
    name: str
    color: Optional[str] = None


class CategoryPatch(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None


class NoteCreate(BaseModel):
    title: str
    vault_path: Optional[str] = None  # 보안상 무시됨 (서버 VAULT_DIR 사용)
    category_id: Optional[str] = None
    content: Optional[str] = None


class NotePatch(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category_id: Optional[str] = None
    tags: Optional[list[str]] = None


class SettingsPatch(BaseModel):
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    default_model: Optional[str] = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    context_note_id: Optional[str] = None
    context_category_id: Optional[str] = None
    use_rag: bool = False
    use_wiki: bool = False
```

- [ ] **Step 4: categories.py 전체 구현**

Replace `backend/routers/categories.py`:

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response

from db import get_conn
from models import CategoryCreate, CategoryPatch

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/categories")
def list_categories():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM categories ORDER BY sort_order, created_at"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/categories")
def create_category(body: CategoryCreate):
    cid = str(uuid.uuid4())
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO categories (id, name, color, sort_order, created_at) "
            "VALUES (?, ?, ?, 0, ?)",
            (cid, body.name, body.color, now),
        )
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone()
    return dict(row)


@router.patch("/categories/{cid}")
def update_category(cid: str, body: CategoryPatch):
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="category not found")
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE categories SET {sets} WHERE id = ?",
                (*fields.values(), cid),
            )
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cid,)).fetchone()
    return dict(row)


@router.delete("/categories/{cid}", status_code=204)
def delete_category(cid: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM categories WHERE id = ?", (cid,))
    return Response(status_code=204)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_categories.py -v`
Expected: 2 passed

- [ ] **Step 6: 커밋**

```bash
git add backend/models.py backend/routers/categories.py backend/tests/test_categories.py
git commit -m "feat(backend): pydantic models and categories CRUD"
```

---

## Task 5: Vault 서비스 (`services/vault.py`)

**Files:**
- Create: `backend/services/vault.py`
- Test: `backend/tests/test_vault.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/test_vault.py`:

```python
import importlib


def _vault(monkeypatch, tmp_path):
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    from config import settings
    settings.reload()
    vault = importlib.import_module("services.vault")
    return vault


def test_safe_filename_strips_traversal(monkeypatch, tmp_path):
    vault = _vault(monkeypatch, tmp_path)
    assert vault.safe_filename("../../etc/passwd") == "etcpasswd"
    assert vault.safe_filename("normal title") == "normal title"
    assert vault.safe_filename("a/b\\c") == "abc"
    assert vault.safe_filename("") == "untitled"


def test_write_md_creates_file_inside_vault(monkeypatch, tmp_path):
    vault = _vault(monkeypatch, tmp_path)
    path = vault.write_md("My Note", "hello world", tags=["x"])
    assert path.endswith("My Note.md")
    from config import settings
    assert str(settings.VAULT_DIR) in path
    with open(path, encoding="utf-8") as f:
        text = f.read()
    assert "hello world" in text
    assert "tags:" in text  # frontmatter 존재
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_vault.py -v`
Expected: FAIL (`services.vault` 없음)

- [ ] **Step 3: vault.py 구현**

Create `backend/services/vault.py`:

```python
import re
from pathlib import Path

from config import settings

_SAFE = re.compile(r"[^\w \-]", re.UNICODE)


def safe_filename(title: str) -> str:
    """파일명 안전화: 영숫자(유니코드)/공백/하이픈만 허용, 경로 구분자 제거."""
    cleaned = _SAFE.sub("", title).strip()
    return cleaned or "untitled"


def md_path(title: str) -> Path:
    return settings.VAULT_DIR / f"{safe_filename(title)}.md"


def write_md(title: str, content: str, tags: list[str]) -> str:
    """노트를 .md로 내보내기 (Obsidian 호환 frontmatter). 절대경로 문자열 반환."""
    settings.VAULT_DIR.mkdir(parents=True, exist_ok=True)
    path = md_path(title)
    # 항상 VAULT_DIR 내부인지 보장
    resolved = path.resolve()
    if settings.VAULT_DIR.resolve() not in resolved.parents and resolved != (
        settings.VAULT_DIR.resolve() / path.name
    ):
        raise ValueError("path escapes vault")
    tag_line = ", ".join(tags)
    frontmatter = f"---\ntags: [{tag_line}]\n---\n\n"
    path.write_text(frontmatter + content, encoding="utf-8")
    return str(path)


def delete_md(title: str) -> None:
    path = md_path(title)
    if path.exists():
        path.unlink()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_vault.py -v`
Expected: 3 passed

- [ ] **Step 5: 커밋**

```bash
git add backend/services/vault.py backend/tests/test_vault.py
git commit -m "feat(backend): vault .md export service with filename safety"
```

---

## Task 6: Anthropic 클라이언트 래퍼 (`services/anthropic_client.py`)

**Files:**
- Create: `backend/services/anthropic_client.py`
- Test: `backend/tests/test_anthropic_parse.py`

이 래퍼는 실제 API 호출을 캡슐화하여 라우터/추출이 목으로 대체할 수 있게 한다.

- [ ] **Step 1: 실패 테스트 작성 (JSON 파싱만 단위 테스트, 네트워크 없음)**

Create `backend/tests/test_anthropic_parse.py`:

```python
from services import anthropic_client as ac


def test_parse_entities_valid_json():
    text = '[{"name": "서울", "type": "place"}, {"name": "칸트", "type": "person"}]'
    out = ac.parse_entities(text)
    assert out == [
        {"name": "서울", "type": "place"},
        {"name": "칸트", "type": "person"},
    ]


def test_parse_entities_with_codefence():
    text = '```json\n[{"name": "A", "type": "concept"}]\n```'
    out = ac.parse_entities(text)
    assert out == [{"name": "A", "type": "concept"}]


def test_parse_entities_garbage_returns_empty():
    assert ac.parse_entities("not json at all") == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_anthropic_parse.py -v`
Expected: FAIL (`services.anthropic_client` 없음)

- [ ] **Step 3: anthropic_client.py 구현**

Create `backend/services/anthropic_client.py`:

```python
import json
import re
from typing import Iterator

from anthropic import Anthropic

from config import settings
from db import get_conn

ALLOWED_CHAT_MODELS = {"claude-sonnet-4-6", "claude-haiku-4-5"}

_EXTRACT_PROMPT = (
    "다음 노트에서 핵심 엔티티(인물/개념/장소/조직 등)를 추출해 "
    'JSON 배열로만 답하라. 각 항목은 {"name": str, "type": str} 형식. '
    "다른 설명 없이 JSON만 출력.\n\n노트:\n"
)


def _api_key() -> str:
    """settings(DB) 우선, 없으면 env."""
    with get_conn() as conn:
        row = conn.execute("SELECT anthropic_api_key FROM settings WHERE id = 1").fetchone()
    db_key = row["anthropic_api_key"] if row else ""
    return db_key or settings.ANTHROPIC_API_KEY


def parse_entities(text: str) -> list[dict]:
    """모델 응답 텍스트에서 엔티티 JSON 배열을 안전 파싱."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, dict) and "name" in item and "type" in item:
            out.append({"name": str(item["name"]), "type": str(item["type"])})
    return out


def extract_entities(content: str) -> list[dict]:
    key = _api_key()
    if not key or not content.strip():
        return []
    client = Anthropic(api_key=key)
    msg = client.messages.create(
        model=settings.EXTRACT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": _EXTRACT_PROMPT + content}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    return parse_entities(text)


def stream_chat(model: str, system: str, messages: list[dict]) -> Iterator[str]:
    """텍스트 델타를 순차 yield. 모델/키 검증 실패 시 예외."""
    if model not in ALLOWED_CHAT_MODELS:
        raise ValueError("현재 Anthropic 모델(claude-sonnet-4-6, claude-haiku-4-5)만 지원합니다")
    key = _api_key()
    if not key:
        raise ValueError("Anthropic API 키가 설정되지 않았습니다")
    client = Anthropic(api_key=key)
    with client.messages.stream(
        model=model,
        max_tokens=4096,
        system=system or "You are SpaceNote's helpful assistant.",
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_anthropic_parse.py -v`
Expected: 3 passed

- [ ] **Step 5: 커밋**

```bash
git add backend/services/anthropic_client.py backend/tests/test_anthropic_parse.py
git commit -m "feat(backend): anthropic wrapper (chat stream, entity extraction, parse)"
```

---

## Task 7: 노트 CRUD (`routers/notes.py`)

**Files:**
- Create: `backend/routers/notes.py`
- Modify: `backend/main.py` (라우터 등록)
- Test: `backend/tests/test_notes.py`

노트는 DB가 운영 진실원본이고, 저장 시 `.md`로 내보내며, 엔티티 추출을 백그라운드로
큐잉한다. 테스트에서는 `anthropic_client.extract_entities`를 목으로 대체한다.

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/test_notes.py`:

```python
import services.anthropic_client as ac
from conftest import AUTH


def _mock_extract(monkeypatch, entities):
    monkeypatch.setattr(ac, "extract_entities", lambda content: entities)


def test_create_get_update_delete_note(client, monkeypatch):
    _mock_extract(monkeypatch, [{"name": "테스트", "type": "concept"}])

    r = client.post(
        "/notes",
        json={"title": "첫 노트", "vault_path": "/ignored/path", "content": "본문 내용"},
        headers=AUTH,
    )
    assert r.status_code == 200
    note = r.json()
    assert note["title"] == "첫 노트"
    assert note["content"] == "본문 내용"
    assert note["tags"] == []
    assert note["word_count"] == 2
    assert note["analysis_status"] in ("analyzed", "pending")
    assert note["path"].endswith("첫 노트.md")
    nid = note["id"]

    # .md 파일이 서버 VAULT_DIR에 생성됐는지
    with open(note["path"], encoding="utf-8") as f:
        assert "본문 내용" in f.read()

    # get
    r = client.get(f"/notes/{nid}", headers=AUTH)
    assert r.json()["content"] == "본문 내용"

    # list
    r = client.get("/notes", headers=AUTH)
    assert len(r.json()) == 1

    # update
    r = client.patch(f"/notes/{nid}", json={"content": "수정 본문", "tags": ["a", "b"]}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["content"] == "수정 본문"
    assert r.json()["tags"] == ["a", "b"]

    # delete
    r = client.delete(f"/notes/{nid}", headers=AUTH)
    assert r.status_code == 204
    assert client.get("/notes", headers=AUTH).json() == []


def test_list_filter_by_category(client, monkeypatch):
    _mock_extract(monkeypatch, [])
    cat = client.post("/categories", json={"name": "C"}, headers=AUTH).json()
    client.post("/notes", json={"title": "n1", "category_id": cat["id"]}, headers=AUTH)
    client.post("/notes", json={"title": "n2"}, headers=AUTH)

    r = client.get(f"/notes?category_id={cat['id']}", headers=AUTH)
    assert len(r.json()) == 1
    assert r.json()[0]["title"] == "n1"


def test_get_missing_note_404(client):
    assert client.get("/notes/nope", headers=AUTH).status_code == 404
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_notes.py -v`
Expected: FAIL (`/notes` 경로 없음)

- [ ] **Step 3: notes.py 구현**

Create `backend/routers/notes.py`:

```python
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

        # 제목이 바뀌면 기존 .md 삭제 후 재작성
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
```

- [ ] **Step 4: main.py에 notes 라우터 등록**

Modify `backend/main.py` — import와 include_router 추가:

```python
from routers import categories, notes
```
그리고 categories include 아래에:
```python
app.include_router(notes.router, dependencies=[Depends(require_auth)])
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_notes.py -v`
Expected: 3 passed

> 주의: `BackgroundTasks`는 TestClient에서 응답 후 동기 실행되며 `extract_entities`는
> 목이므로 네트워크 호출이 없다. `analysis_status`는 추출 성공 시 `analyzed`가 된다.

- [ ] **Step 6: 커밋**

```bash
git add backend/routers/notes.py backend/main.py backend/tests/test_notes.py
git commit -m "feat(backend): notes CRUD with .md export and background entity extraction"
```

---

## Task 8: 검색 + 엔티티 + 발견 (`routers/search.py`, `services/discover.py`)

**Files:**
- Create: `backend/services/discover.py`
- Create: `backend/routers/search.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_search.py`, `backend/tests/test_discover.py`

- [ ] **Step 1: discover 실패 테스트 작성**

Create `backend/tests/test_discover.py`:

```python
import uuid
from datetime import datetime, timezone

from conftest import AUTH


def _seed_note(conn, title, content="", category_id=None):
    nid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO notes (id, path, title, content, category_id, tags, "
        "word_count, analysis_status, created_at, modified_at) "
        "VALUES (?, ?, ?, ?, ?, '[]', 0, 'analyzed', ?, ?)",
        (nid, f"/x/{title}.md", title, content, category_id, now, now),
    )
    return nid


def _seed_entity(conn, note_id, name, type_="concept"):
    conn.execute(
        "INSERT INTO entities (id, note_id, name, type, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), note_id, name, type_,
         datetime.now(timezone.utc).isoformat()),
    )


def test_discoveries_by_shared_entities(client):
    from db import get_conn
    with get_conn() as conn:
        a = _seed_note(conn, "A")
        b = _seed_note(conn, "B")
        c = _seed_note(conn, "C")
        for nid in (a, b):
            _seed_entity(conn, nid, "칸트")
            _seed_entity(conn, nid, "이성")
        _seed_entity(conn, c, "무관")

    r = client.get(f"/discoveries?note_id={a}", headers=AUTH)
    assert r.status_code == 200
    disc = r.json()
    assert len(disc) == 1
    assert disc[0]["note_id"] == b
    assert disc[0]["shared_count"] == 2
    assert set(disc[0]["shared_entities"]) == {"칸트", "이성"}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_discover.py -v`
Expected: FAIL (`/discoveries` 없음)

- [ ] **Step 3: discover.py 구현**

Create `backend/services/discover.py`:

```python
from db import get_conn


def discoveries_for(note_id: str) -> list[dict]:
    """대상 노트와 엔티티 이름을 공유하는 다른 노트를 공유 개수 내림차순으로."""
    with get_conn() as conn:
        own = conn.execute(
            "SELECT DISTINCT name FROM entities WHERE note_id = ?", (note_id,)
        ).fetchall()
        own_names = {r["name"] for r in own}
        if not own_names:
            return []

        placeholders = ",".join("?" for _ in own_names)
        rows = conn.execute(
            f"""
            SELECT e.note_id AS nid, n.title, n.category_id, n.modified_at,
                   GROUP_CONCAT(DISTINCT e.name) AS shared
            FROM entities e
            JOIN notes n ON n.id = e.note_id
            WHERE e.name IN ({placeholders}) AND e.note_id != ?
            GROUP BY e.note_id
            ORDER BY COUNT(DISTINCT e.name) DESC, n.modified_at DESC
            """,
            (*own_names, note_id),
        ).fetchall()

    result = []
    for r in rows:
        shared = [s for s in (r["shared"] or "").split(",") if s in own_names]
        result.append({
            "note_id": r["nid"],
            "title": r["title"],
            "category_id": r["category_id"],
            "shared_count": len(shared),
            "shared_entities": shared,
            "modified_at": r["modified_at"],
        })
    return result


def discoveries_all() -> list[dict]:
    """note_id 미지정 시: 엔티티가 2개 이상 공유되는 모든 노트쌍 대신
    엔티티를 가진 모든 노트를 최근순으로 반환 (단순 목록)."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT n.id AS note_id, n.title, n.category_id, n.modified_at,
                   COUNT(e.id) AS cnt
            FROM notes n JOIN entities e ON e.note_id = n.id
            GROUP BY n.id ORDER BY n.modified_at DESC
            """
        ).fetchall()
    return [{
        "note_id": r["note_id"], "title": r["title"],
        "category_id": r["category_id"], "shared_count": r["cnt"],
        "shared_entities": [], "modified_at": r["modified_at"],
    } for r in rows]
```

- [ ] **Step 4: search 실패 테스트 작성**

Create `backend/tests/test_search.py`:

```python
import services.anthropic_client as ac
from conftest import AUTH


def test_search_and_entities(client, monkeypatch):
    monkeypatch.setattr(ac, "extract_entities", lambda content: [])
    client.post("/notes", json={"title": "우주 노트", "content": "별과 은하 이야기"}, headers=AUTH)
    client.post("/notes", json={"title": "요리 노트", "content": "파스타 레시피"}, headers=AUTH)

    r = client.get("/search?q=은하", headers=AUTH)
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
    assert results[0]["title"] == "우주 노트"
    assert "content_preview" in results[0]

    r = client.get("/search?q=레시피", headers=AUTH)
    assert len(r.json()) == 1
    assert r.json()[0]["title"] == "요리 노트"


def test_entities_endpoint(client, monkeypatch):
    monkeypatch.setattr(ac, "extract_entities", lambda content: [{"name": "별", "type": "concept"}])
    note = client.post("/notes", json={"title": "n", "content": "별 이야기"}, headers=AUTH).json()
    r = client.get(f"/entities/{note['id']}", headers=AUTH)
    assert r.status_code == 200
    ents = r.json()
    assert len(ents) == 1
    assert ents[0]["name"] == "별"
    assert ents[0]["note_id"] == note["id"]
```

- [ ] **Step 5: search.py 구현**

Create `backend/routers/search.py`:

```python
from typing import Optional

from fastapi import APIRouter

from db import get_conn
from services import discover

router = APIRouter()


@router.get("/search")
def search(q: str):
    if not q.strip():
        return []
    like = f"%{q}%"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, content, category_id, modified_at FROM notes "
            "WHERE title LIKE ? OR content LIKE ? ORDER BY modified_at DESC LIMIT 50",
            (like, like),
        ).fetchall()
    return [{
        "id": r["id"],
        "title": r["title"],
        "content_preview": (r["content"] or "")[:160],
        "category_id": r["category_id"],
        "modified_at": r["modified_at"],
    } for r in rows]


@router.get("/discoveries")
def discoveries(note_id: Optional[str] = None):
    if note_id:
        return discover.discoveries_for(note_id)
    return discover.discoveries_all()


@router.get("/entities/{note_id}")
def entities(note_id: str):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM entities WHERE note_id = ? ORDER BY created_at", (note_id,)
        ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 6: main.py에 search 라우터 등록**

Modify `backend/main.py`:
```python
from routers import categories, notes, search
```
그리고:
```python
app.include_router(search.router, dependencies=[Depends(require_auth)])
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_search.py tests/test_discover.py -v`
Expected: 3 passed

- [ ] **Step 8: 커밋**

```bash
git add backend/services/discover.py backend/routers/search.py backend/main.py backend/tests/test_search.py backend/tests/test_discover.py
git commit -m "feat(backend): search, entities, and discoveries endpoints"
```

---

## Task 9: AI 설정 + 채팅 SSE (`routers/ai.py`)

**Files:**
- Create: `backend/routers/ai.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_ai.py`

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/test_ai.py`:

```python
import services.anthropic_client as ac
from conftest import AUTH


def test_settings_masks_keys(client):
    # 키 저장
    r = client.patch("/ai/settings", json={"anthropic_api_key": "sk-ant-secret12345"}, headers=AUTH)
    assert r.status_code == 204

    # 조회 시 마스킹
    r = client.get("/ai/settings", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["anthropic_api_key"] != "sk-ant-secret12345"
    assert body["anthropic_api_key"].endswith("2345")
    assert "..." in body["anthropic_api_key"]
    assert body["default_model"] == "claude-sonnet-4-6"


def test_settings_patch_ignores_masked_value(client):
    client.patch("/ai/settings", json={"anthropic_api_key": "sk-ant-realkey9999"}, headers=AUTH)
    masked = client.get("/ai/settings", headers=AUTH).json()["anthropic_api_key"]
    # 마스킹된 값을 그대로 다시 PATCH → 무시되어 실제 키 유지
    client.patch("/ai/settings", json={"anthropic_api_key": masked}, headers=AUTH)
    # default_model만 바꿔도 키는 유지
    client.patch("/ai/settings", json={"default_model": "claude-haiku-4-5"}, headers=AUTH)
    r = client.get("/ai/settings", headers=AUTH)
    assert r.json()["default_model"] == "claude-haiku-4-5"
    assert r.json()["anthropic_api_key"].endswith("9999")


def test_chat_streams_sse(client, monkeypatch):
    def fake_stream(model, system, messages):
        yield "안녕"
        yield "하세요"
    monkeypatch.setattr(ac, "stream_chat", fake_stream)

    r = client.post(
        "/ai/chat",
        json={"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "hi"}],
              "use_rag": False, "use_wiki": False},
        headers=AUTH,
    )
    assert r.status_code == 200
    text = r.text
    assert 'data: {"text": "안녕"}' in text
    assert 'data: {"text": "하세요"}' in text
    assert "data: [DONE]" in text


def test_chat_unsupported_model_streams_error(client, monkeypatch):
    def fake_stream(model, system, messages):
        raise ValueError("현재 Anthropic 모델만 지원합니다")
        yield  # pragma: no cover
    monkeypatch.setattr(ac, "stream_chat", fake_stream)

    r = client.post(
        "/ai/chat",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}],
              "use_rag": False, "use_wiki": False},
        headers=AUTH,
    )
    assert r.status_code == 200
    assert '"error"' in r.text
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_ai.py -v`
Expected: FAIL (`/ai/*` 없음)

- [ ] **Step 3: ai.py 구현**

Create `backend/routers/ai.py`:

```python
import json

from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse

from db import get_conn
from models import SettingsPatch, ChatRequest
from services import anthropic_client

router = APIRouter()

_KEY_FIELDS = ("anthropic_api_key", "openai_api_key", "google_api_key")


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "..." + key
    return key[:6] + "..." + key[-4:]


@router.get("/ai/settings")
def get_settings():
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    d = dict(row)
    for f in _KEY_FIELDS:
        d[f] = _mask(d[f])
    d.pop("id", None)
    return d


@router.patch("/ai/settings", status_code=204)
def patch_settings(body: SettingsPatch):
    fields = body.model_dump(exclude_unset=True)
    with get_conn() as conn:
        for k, v in fields.items():
            if v is None:
                continue
            # 마스킹된 값(...)을 그대로 받은 경우 키 갱신 무시
            if k in _KEY_FIELDS and "..." in v:
                continue
            conn.execute(f"UPDATE settings SET {k} = ? WHERE id = 1", (v,))
    return Response(status_code=204)


def _build_system(req: ChatRequest) -> str:
    base = "You are SpaceNote's helpful assistant. Answer in the user's language."
    if not req.use_rag:
        return base
    parts = [base]
    with get_conn() as conn:
        if req.context_note_id:
            row = conn.execute(
                "SELECT title, content FROM notes WHERE id = ?", (req.context_note_id,)
            ).fetchone()
            if row:
                parts.append(f"\n\n[현재 노트: {row['title']}]\n{row['content'][:2000]}")
        if req.context_category_id:
            rows = conn.execute(
                "SELECT title, content FROM notes WHERE category_id = ? "
                "ORDER BY modified_at DESC LIMIT 5",
                (req.context_category_id,),
            ).fetchall()
            for r in rows:
                parts.append(f"\n\n[관련 노트: {r['title']}]\n{r['content'][:800]}")
    return "".join(parts)


@router.post("/ai/chat")
def chat(req: ChatRequest):
    system = _build_system(req)
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    def gen():
        try:
            for chunk in anthropic_client.stream_chat(req.model, system, messages):
                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 4: main.py에 ai 라우터 등록**

Modify `backend/main.py`:
```python
from routers import categories, notes, search, ai
```
그리고:
```python
app.include_router(ai.router, dependencies=[Depends(require_auth)])
```

- [ ] **Step 5: 전체 테스트 통과 확인**

Run: `cd backend && venv/bin/python -m pytest -v`
Expected: 모든 테스트 passed

- [ ] **Step 6: 커밋**

```bash
git add backend/routers/ai.py backend/main.py backend/tests/test_ai.py
git commit -m "feat(backend): ai settings (masked keys) and streaming chat SSE"
```

---

## Task 10: 백엔드 수동 기동 검증

**Files:** 없음 (실행 검증)

- [ ] **Step 1: 백엔드 기동**

Run:
```bash
cd /var/www/html/Space_Note_v100/backend
venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001 &
sleep 2
```

- [ ] **Step 2: health + 인증 확인**

Run:
```bash
curl -s http://localhost:8001/health
echo
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/categories
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer dev-token" http://localhost:8001/categories
```
Expected: `{"status":"ok",...}` / `401` / `200` (단, `backend/.env`의 토큰이 `dev-token`일 때)

- [ ] **Step 3: 백엔드 종료**

Run: `kill %1 2>/dev/null; pkill -f "uvicorn main:app" 2>/dev/null; true`

---

## Task 11: 프론트엔드 — API 주소 통합 + 인증 헤더 (`src/api/config.ts`)

**Files:**
- Create: `src/api/config.ts`
- Modify: `src/api/client.ts`, `src/api/searchApi.ts`, `src/api/aiApi.ts`, `src/components/Setup/VaultSetup.tsx`

프론트는 별도 테스트 러너가 없으므로 이 태스크들은 편집 후 빌드(`npx tsc --noEmit`)와
브라우저 수동 확인으로 검증한다.

- [ ] **Step 1: config.ts 작성**

Create `src/api/config.ts`:

```ts
// 백엔드 주소를 런타임에 결정 — 원격 브라우저에서도 같은 호스트의 :8001을 가리킴
export const API_BASE: string =
  (import.meta as any).env?.VITE_API_BASE ??
  `${location.protocol}//${location.hostname}:8001`

const TOKEN_KEY = 'sn-token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function authHeaders(): Record<string, string> {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}
```

- [ ] **Step 2: client.ts 수정**

Replace `src/api/client.ts`:

```ts
import { API_BASE, authHeaders } from './config'

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`API ${res.status}: ${err}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}
```

- [ ] **Step 3: searchApi.ts 수정**

Replace `src/api/searchApi.ts`:

```ts
import type { SearchResult, Discovery, Entity } from '../types'
import { API_BASE, authHeaders } from './config'

export const searchApi = {
  search: (q: string): Promise<SearchResult[]> =>
    fetch(`${API_BASE}/search?q=${encodeURIComponent(q)}`, { headers: authHeaders() }).then(r => r.json()),

  discoveries: (noteId?: string): Promise<Discovery[]> =>
    fetch(`${API_BASE}/discoveries${noteId ? `?note_id=${noteId}` : ''}`, { headers: authHeaders() }).then(r => r.json()),

  entities: (noteId: string): Promise<Entity[]> =>
    fetch(`${API_BASE}/entities/${noteId}`, { headers: authHeaders() }).then(r => r.json()),
}
```

- [ ] **Step 4: aiApi.ts 수정**

Modify `src/api/aiApi.ts` — 상단 `const BASE = 'http://localhost:8001'`를 제거하고 import 추가, 모든 `${BASE}` → `${API_BASE}`, fetch에 `authHeaders()` 병합:

```ts
import type { AIModel, AIChatMessage, AISettings } from '../types'
import { API_BASE, authHeaders } from './config'

export const aiApi = {
  getSettings: (): Promise<AISettings> =>
    fetch(`${API_BASE}/ai/settings`, { headers: authHeaders() }).then(r => r.json()),

  patchSettings: (data: Partial<AISettings>): Promise<void> =>
    fetch(`${API_BASE}/ai/settings`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(data),
    }).then(() => {}),

  async *streamChat(params: {
    model: AIModel
    messages: Pick<AIChatMessage, 'role' | 'content'>[]
    contextNoteId?: string
    contextCategoryId?: string
    useRag: boolean
    useWiki: boolean
  }): AsyncGenerator<{ text?: string; error?: string }> {
    const resp = await fetch(`${API_BASE}/ai/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({
        model: params.model,
        messages: params.messages,
        context_note_id: params.contextNoteId ?? null,
        context_category_id: params.contextCategoryId ?? null,
        use_rag: params.useRag,
        use_wiki: params.useWiki,
      }),
    })
    if (!resp.ok) {
      const msg = await resp.text()
      yield { error: msg }
      return
    }
    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6)
        if (raw === '[DONE]') return
        try { yield JSON.parse(raw) } catch { /* skip */ }
      }
    }
  },
}
```

- [ ] **Step 5: VaultSetup.tsx 수정**

Modify `src/components/Setup/VaultSetup.tsx` — `fetchDefaultVault` 내 하드코딩 주소 교체:

```ts
import { API_BASE, authHeaders } from '../../api/config'
```
그리고 함수 본문의 `fetch('http://localhost:8001/health')` →
`fetch(`${API_BASE}/health`, { headers: authHeaders() })`.

- [ ] **Step 6: 타입 체크**

Run: `cd /var/www/html/Space_Note_v100 && npx tsc --noEmit`
Expected: 에러 없음 (이 태스크에서 만진 파일 관련)

- [ ] **Step 7: 커밋**

```bash
git add src/api/config.ts src/api/client.ts src/api/searchApi.ts src/api/aiApi.ts src/components/Setup/VaultSetup.tsx
git commit -m "feat(frontend): runtime API base + auth headers for remote access"
```

---

## Task 12: 프론트엔드 — 토큰 게이트 + Vite host

**Files:**
- Create: `src/components/Setup/TokenGate.tsx`
- Modify: `src/App.tsx`, `vite.config.ts`

- [ ] **Step 1: TokenGate.tsx 작성**

Create `src/components/Setup/TokenGate.tsx`:

```tsx
import { useState } from 'react'
import { setToken, getToken } from '../../api/config'

export function TokenGate({ onDone }: { onDone: () => void }) {
  const [value, setValue] = useState(getToken())

  const apply = () => {
    if (!value.trim()) return
    setToken(value.trim())
    onDone()
  }

  return (
    <div className="flex flex-col items-center justify-center h-screen gap-4"
         style={{ background: 'var(--bg-app)' }}>
      <h1 style={{ fontSize: '22px', fontWeight: 600, color: 'var(--text-primary)' }}>
        SpaceNote 접속
      </h1>
      <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
        접속 토큰을 입력하세요
      </p>
      <div style={{ display: 'flex', gap: '8px', width: '360px' }}>
        <input
          autoFocus
          type="password"
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && apply()}
          placeholder="SPACENOTE_TOKEN"
          style={{
            flex: 1, padding: '8px 10px', fontSize: '13px',
            background: 'var(--bg-input)', color: 'var(--text-primary)',
            border: '1px solid var(--border)', borderRadius: '3px', outline: 'none',
          }}
        />
        <button onClick={apply}
          style={{
            padding: '8px 18px', fontSize: '13px', fontWeight: 500,
            background: 'var(--text-primary)', color: 'var(--bg-app)',
            border: 'none', borderRadius: '3px', cursor: 'pointer',
          }}>
          확인
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: App.tsx 진입 흐름 수정**

Modify `src/App.tsx` — `AppContent`를 토큰 게이트 → vault 게이트 순으로:

import 추가:
```tsx
import { TokenGate } from './components/Setup/TokenGate'
import { getToken } from './api/config'
```

`AppContent` 함수 교체:
```tsx
function AppContent() {
  const { setVaultPath } = useNotesStore()
  const [hasToken, setHasToken] = useState(!!getToken())
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const saved = localStorage.getItem('sn-vault-path')
    if (saved) {
      setVaultPath(saved)
      setReady(true)
    }
  }, [])

  if (!hasToken) return <TokenGate onDone={() => setHasToken(true)} />
  if (!ready) return <VaultSetup onDone={() => setReady(true)} />
  return <SettingsAwareLayout />
}
```

- [ ] **Step 3: vite.config.ts에 host 추가**

Modify `vite.config.ts` — `server` 블록에 `host: true` 추가:

```ts
  server: {
    host: true,
    port: 1420,
    strictPort: true,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },
```

- [ ] **Step 4: 타입 체크**

Run: `cd /var/www/html/Space_Note_v100 && npx tsc --noEmit`
Expected: 에러 없음

- [ ] **Step 5: 커밋**

```bash
git add src/components/Setup/TokenGate.tsx src/App.tsx vite.config.ts
git commit -m "feat(frontend): token gate and vite host binding for remote access"
```

---

## Task 13: start.sh / stop.sh

**Files:**
- Create: `start.sh`, `stop.sh`

- [ ] **Step 1: start.sh 작성**

Create `start.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

ROOT="$(pwd)"
RUN_DIR="$ROOT/.run"
mkdir -p "$RUN_DIR"

echo "[SpaceNote] 시작 중..."

# --- 백엔드 venv ---
if [ ! -x "backend/venv/bin/python" ]; then
  echo "[SpaceNote] 백엔드 venv 생성..."
  python3 -m venv backend/venv
  backend/venv/bin/pip install -q -r backend/requirements.txt
fi

# --- .env 확인 ---
if [ ! -f "backend/.env" ]; then
  cp backend/.env.example backend/.env
  echo "[SpaceNote] backend/.env 를 생성했습니다. SPACENOTE_TOKEN 과 ANTHROPIC_API_KEY 를"
  echo "            입력한 뒤 다시 ./start.sh 를 실행하세요."
  exit 1
fi

# --- 백엔드 기동 ---
echo "[SpaceNote] 백엔드 :8001 기동..."
( cd backend && exec venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001 ) \
  > "$RUN_DIR/backend.log" 2>&1 &
echo $! > "$RUN_DIR/backend.pid"

sleep 2

# --- 프론트 의존성 ---
if [ ! -d "node_modules" ]; then
  echo "[SpaceNote] npm install..."
  npm install
fi

# --- 프론트 기동 ---
echo "[SpaceNote] 프론트엔드 :1420 기동..."
npm run dev -- --host > "$RUN_DIR/frontend.log" 2>&1 &
echo $! > "$RUN_DIR/frontend.pid"

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "[SpaceNote] 실행 완료"
echo "  프론트엔드 : http://${IP:-localhost}:1420"
echo "  백엔드     : http://${IP:-localhost}:8001"
echo "  로그       : $RUN_DIR/*.log"
echo "  종료       : ./stop.sh"
```

- [ ] **Step 2: stop.sh 작성**

Create `stop.sh`:

```bash
#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
RUN_DIR="$(pwd)/.run"

stop_one() {
  local name="$1" pidfile="$RUN_DIR/$2"
  if [ -f "$pidfile" ]; then
    local pid; pid="$(cat "$pidfile")"
    if kill "$pid" 2>/dev/null; then
      echo "[SpaceNote] $name 종료 (pid $pid)"
    else
      echo "[SpaceNote] $name 프로세스가 이미 없음 (pid $pid)"
    fi
    rm -f "$pidfile"
  else
    echo "[SpaceNote] $name PID 파일 없음 — 건너뜀"
  fi
}

stop_one "프론트엔드" frontend.pid
stop_one "백엔드" backend.pid

# 잔여 프로세스 정리
pkill -f "uvicorn main:app --host 0.0.0.0 --port 8001" 2>/dev/null || true
echo "[SpaceNote] 종료 완료"
```

- [ ] **Step 3: 실행 권한 부여**

Run: `chmod +x start.sh stop.sh`

- [ ] **Step 4: 스크립트 동작 검증**

Run:
```bash
cd /var/www/html/Space_Note_v100
./start.sh
sleep 6
curl -s http://localhost:8001/health && echo
curl -s -o /dev/null -w "frontend:%{http_code}\n" http://localhost:1420
./stop.sh
```
Expected: health JSON 출력, `frontend:200`, 종료 메시지. (`backend/.env`의 토큰/키가 설정돼 있어야 함.)

- [ ] **Step 5: 커밋**

```bash
git add start.sh stop.sh
git commit -m "feat: linux start.sh/stop.sh scripts with 0.0.0.0 binding"
```

---

## Task 14: README 운영 안내 (보안/nginx)

**Files:**
- Create or Modify: `README.md`

- [ ] **Step 1: README에 운영 섹션 추가**

`README.md`에 아래 내용을 추가(없으면 생성):

```markdown
## 실행 (리눅스)

```bash
cp backend/.env.example backend/.env   # SPACENOTE_TOKEN, ANTHROPIC_API_KEY 입력
./start.sh                              # 백엔드 :8001 + 프론트 :1420 기동
./stop.sh                               # 종료
```

원격 브라우저에서 `http://<서버IP>:1420` 접속 → 토큰 입력 → 사용.

## 보안 (인터넷 공개 시 필독)

- `SPACENOTE_TOKEN`을 길고 무작위한 값으로 설정하세요. 이 토큰이 유일한 접근 제어입니다.
- **TLS 없이 평문 HTTP로 공개하면 토큰·노트가 평문 전송됩니다.** 운영 시 nginx 등
  리버스 프록시로 HTTPS를 종단하세요. 예:

```nginx
server {
  listen 443 ssl;
  server_name your.domain;
  ssl_certificate     /etc/letsencrypt/live/your.domain/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/your.domain/privkey.pem;

  location /          { proxy_pass http://127.0.0.1:1420; proxy_set_header Host $host; }
  location /api/      { proxy_pass http://127.0.0.1:8001/; }   # 선택: 경로 분리 시
}
```

- `ALLOWED_ORIGIN`을 실제 프론트 도메인으로 좁히세요(기본 `http://localhost:1420`).
- 방화벽에서 8001/1420 직접 노출 대신 프록시(443)만 여는 것을 권장합니다.
```

- [ ] **Step 2: 커밋**

```bash
git add README.md
git commit -m "docs: linux run instructions and internet-exposure security notes"
```

---

## Task 15: 전체 회귀 검증

**Files:** 없음 (검증)

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `cd /var/www/html/Space_Note_v100/backend && venv/bin/python -m pytest -v`
Expected: 모든 테스트 passed

- [ ] **Step 2: 프론트 타입 체크 + 빌드**

Run:
```bash
cd /var/www/html/Space_Note_v100
npx tsc --noEmit
npm run build
```
Expected: 타입 에러 없음, 빌드 성공

- [ ] **Step 3: 엔드투엔드 스모크 (스크립트 기동 → curl)**

Run:
```bash
./start.sh && sleep 6
TOKEN=$(grep '^SPACENOTE_TOKEN=' backend/.env | cut -d= -f2-)
curl -s http://localhost:8001/health; echo
curl -s -H "Authorization: Bearer $TOKEN" -X POST http://localhost:8001/categories \
  -H 'Content-Type: application/json' -d '{"name":"스모크"}'; echo
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8001/categories; echo
./stop.sh
```
Expected: health ok, 카테고리 생성/목록에 "스모크" 표시.

- [ ] **Step 4: 최종 커밋 (잔여 변경 있으면)**

```bash
git add -A
git commit -m "chore: final regression pass for linux backend + remote access" || true
```

---

## 자체 검토 (Self-Review) 결과

- **스펙 커버리지:** 인증(Task 3), 노트/카테고리 CRUD(4,7), 검색/발견/엔티티(8),
  AI 설정 마스킹·채팅 SSE(9), .md 내보내기(5), 엔티티 추출(6,7), 원격 주소·인증
  헤더(11,12), Vite host(12), start/stop(13), 보안 안내(14) — 스펙 전 항목 매핑됨.
- **의도적 단순화 2건**(DB-진실원본 + .md 내보내기, FTS5→LIKE)은 문서 상단에 명시.
- **플레이스홀더 없음:** 모든 코드 단계에 실제 코드 포함.
- **타입/시그니처 일관성:** `get_conn`, `settings.reload`, `_row_to_note`,
  `anthropic_client.stream_chat/extract_entities/parse_entities`, `API_BASE/authHeaders`
  가 정의-사용 간 일치.
- **git 주의:** 현재 저장소의 `.git`이 손상돼 있어(HEAD/refs 없음) 커밋 단계가 실패할 수
  있다. 실행 전 git 재초기화(`.gitignore` 적용 후 `git init` + 초기 커밋)가 필요하며,
  이는 실행 단계 시작 시 사용자와 함께 처리한다.
