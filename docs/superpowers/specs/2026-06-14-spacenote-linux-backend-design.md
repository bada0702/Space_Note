# SpaceNote 리눅스 전환 + 백엔드 신규 구현 — 설계 문서

> 작성일: 2026-06-14
> 상태: 승인됨 (브레인스토밍 완료, 구현 계획 대기)

## 배경

SpaceNote는 Tauri v2 + React 18 데스크톱 노트 앱으로 시작했다. 이제 Windows 개발
환경에서 리눅스 서버 환경으로 옮기면서, **원격 브라우저에서 접속 가능한 웹 앱**으로
운영하려 한다. 현재 체크아웃 상태에서 발견한 문제:

1. **백엔드(:8001) Python 소스가 전부 없음.** `backend/`에는 Windows용 `venv`와 빈
   `routers/`, `services/`, `tests/`만 존재. 프론트엔드는 `http://localhost:8001`로
   `/notes`, `/categories`, `/search`, `/ai/chat` 등을 호출하지만 이를 처리할 코드가
   없다.
2. **venv가 Windows용**(`Scripts/`, `Lib/`)이라 리눅스에서 사용 불가. `requirements.txt`
   도 비어 있음.
3. **프론트엔드가 `http://localhost:8001`을 4곳에 하드코딩** — 원격 브라우저에서 열면
   그 브라우저의 localhost를 가리켜 백엔드 호출이 전부 실패.

`/var/www/html/autology/backend`에 별도 AI 백엔드(:8000)가 있으나, 이는 SpaceNote의
노트/카테고리 백엔드가 아니다.

## 결정 사항 (브레인스토밍 확정)

| 항목 | 결정 |
|------|------|
| 백엔드 | **신규 구현** (FastAPI) |
| 기능 범위 | **MVP + AI 엔티티 추출** (ChromaDB 벡터검색·autology 연동 제외) |
| AI 프로바이더 | **Anthropic만** |
| 인증 | **단일 토큰/비밀번호** (env 기반) |
| 접속 범위 | **인터넷 공개** (리버스 프록시·보안 고려) |
| 프론트 실행 | **Vite dev 서버** (`npm run dev -- --host`) |
| 엔티티 추출 모델 | **claude-haiku-4-5** |

## 비범위 (YAGNI)

- ChromaDB / 벡터 임베딩 검색 (FTS5 키워드 검색으로 대체)
- autology :8000 AI 파이프라인 연동
- OpenAI / Google 프로바이더 실제 연동 (UI에는 남기되 선택 시 안내 메시지)
- `use_wiki` 위키 조회 기능 (향후 확장 표시만)
- 멀티 유저 / 계정 시스템 (단일 토큰 인증만)
- Tauri 데스크톱 빌드 (웹 운영에 집중)

## 전체 아키텍처

```
[원격 브라우저] ──HTTPS──> [nginx 리버스 프록시(권장)]
                                  ├──> Vite dev :1420 (프론트엔드)
                                  └──> FastAPI :8001 (백엔드)
                                          ├── SQLite (메타/카테고리/엔티티/발견/설정)
                                          ├── Vault 디렉토리 (.md 파일, Obsidian 호환)
                                          └── Anthropic SDK (채팅 스트리밍 + 엔티티 추출)
```

- 두 서버 모두 `0.0.0.0` 바인딩.
- 인증: 환경변수 `SPACENOTE_TOKEN`. 프론트 첫 진입 시 토큰 입력 → localStorage 저장 →
  모든 API에 `Authorization: Bearer <token>` 헤더. `/health`만 인증 면제(부팅 체크용).

## 프론트엔드가 기대하는 API 계약 (불변)

소스(`src/api/*.ts`, `src/types/index.ts`)에서 도출한 백엔드가 반드시 노출해야 하는 표면:

| 메서드 | 경로 | 비고 |
|--------|------|------|
| GET | `/health` | `{ status, default_vault }` — 인증 면제 |
| GET | `/notes?category_id=` | `Note[]` |
| POST | `/notes` | body `{ title, vault_path, category_id?, content? }` → `Note` |
| GET | `/notes/{id}` | `Note` |
| PATCH | `/notes/{id}` | body `{ title?, content?, category_id?, tags? }` → `Note` |
| DELETE | `/notes/{id}` | 204 |
| GET | `/categories` | `Category[]` |
| POST | `/categories` | body `{ name, color? }` → `Category` |
| PATCH | `/categories/{id}` | body `{ name?, color?, sort_order? }` → `Category` |
| DELETE | `/categories/{id}` | 204 |
| GET | `/search?q=` | `SearchResult[]` |
| GET | `/discoveries?note_id=` | `Discovery[]` |
| GET | `/entities/{note_id}` | `Entity[]` |
| GET | `/ai/settings` | `AISettings` (키 마스킹) |
| PATCH | `/ai/settings` | body `Partial<AISettings>` → 204 |
| POST | `/ai/chat` | body `{ model, messages, context_note_id?, context_category_id?, use_rag, use_wiki }` → SSE |

타입 정의(프론트 `types/index.ts`와 1:1):

- `Category { id, name, color, sort_order, created_at }`
- `Note { id, path, title, content, category_id, tags[], word_count, analysis_status, created_at, modified_at }`
  - `analysis_status: 'pending' | 'analyzed' | 'failed'`
- `SearchResult { id, title, content_preview, category_id, modified_at }`
- `Discovery { note_id, title, category_id, shared_count, shared_entities[], modified_at }`
- `Entity { id, note_id, name, type, created_at }`
- `AISettings { anthropic_api_key, openai_api_key, google_api_key, default_model }`

### `/ai/chat` SSE 형식 (프론트 `aiApi.streamChat`이 파싱하는 형식)

```
data: {"text": "부분 텍스트"}
data: {"text": "다음 조각"}
...
data: [DONE]
```

에러 시: `data: {"error": "메시지"}` 후 종료. 각 줄은 `data: ` 접두 + JSON, 줄바꿈 구분.

## 백엔드 구조 (`backend/`)

```
main.py               FastAPI 앱, CORS, 인증 미들웨어, 라우터 등록, /health
config.py             env 로드 (VAULT_DIR, SPACENOTE_TOKEN, ANTHROPIC_API_KEY,
                      ALLOWED_ORIGIN, EXTRACT_MODEL)
db.py                 SQLite 연결 + 스키마 초기화 (앱 시작 시 1회)
models.py             Pydantic 스키마 (프론트 types와 1:1)
auth.py               Bearer 토큰 검증 의존성
routers/
  notes.py            /notes CRUD — .md 파일 + SQLite 동기화
  categories.py       /categories CRUD
  search.py           /search (FTS5), /discoveries, /entities/{id}
  ai.py               /ai/settings (GET/PATCH, 키 마스킹), /ai/chat (SSE)
services/
  vault.py            .md 파일 읽기/쓰기, frontmatter 처리, 파일명 안전화
  extract.py          Anthropic로 엔티티 추출 (노트 저장 시 백그라운드)
  discover.py         엔티티/태그 공유 기반 발견 계산
  anthropic_client.py Anthropic SDK 래퍼 (채팅 스트림 + 추출 호출)
tests/
  conftest.py         테스트 DB/vault 픽스처, Anthropic 목
  test_notes.py
  test_categories.py
  test_search.py
  test_ai.py          인증 401, 키 마스킹, SSE 형식
requirements.txt      fastapi, uvicorn[standard], anthropic, python-dotenv, pydantic
.env.example          환경변수 템플릿
```

## 데이터 저장 방식

### 노트 본문 = .md 파일 (Obsidian 호환)

- 노트 본문은 `VAULT_DIR` 아래 `<title>.md` 파일로 저장. YAML frontmatter에 메타
  일부(id, tags, created/modified)를 기록해 Obsidian과 호환.
- 메타데이터는 SQLite에 인덱싱하여 빠른 목록/검색 제공.

### 보안 — 클라이언트 vault_path 무시

프론트가 `POST /notes`에 `vault_path`를 보내지만, **인터넷 공개 환경에서 클라이언트가
지정한 파일시스템 경로를 그대로 쓰면 경로 탐색(path traversal) 공격에 노출**된다.
따라서 백엔드는 클라이언트 `vault_path`를 **무시**하고 서버 env `VAULT_DIR`을 사용한다.
파일명은 안전화(영숫자/공백/하이픈만, `..`·슬래시 제거)하고 항상 `VAULT_DIR` 내부로
정규화한다. `/health`의 `default_vault`는 표시용으로만 `VAULT_DIR`을 반환.

### SQLite 스키마

```sql
CREATE TABLE categories (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, color TEXT,
  sort_order INTEGER DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE notes (
  id TEXT PRIMARY KEY, path TEXT NOT NULL, title TEXT NOT NULL,
  category_id TEXT, tags TEXT,           -- tags: JSON 배열 문자열
  word_count INTEGER DEFAULT 0,
  analysis_status TEXT DEFAULT 'pending',
  created_at TEXT NOT NULL, modified_at TEXT NOT NULL
);
CREATE TABLE entities (
  id TEXT PRIMARY KEY, note_id TEXT NOT NULL,
  name TEXT NOT NULL, type TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE note_fts USING fts5(note_id, title, content);
CREATE TABLE settings (              -- 단일 행 (id=1)
  id INTEGER PRIMARY KEY CHECK (id=1),
  anthropic_api_key TEXT, openai_api_key TEXT,
  google_api_key TEXT, default_model TEXT DEFAULT 'claude-sonnet-4-6'
);
```

- 본문은 `.md` 파일이 원본(source of truth), `note_fts.content`는 검색용 미러.
- 노트 저장 시: ① .md 파일 쓰기 ② notes/메타 갱신 ③ note_fts 갱신 ④ 엔티티 추출
  백그라운드 작업 큐잉.

## AI 연동 (Anthropic만)

### `/ai/chat` — 스트리밍 채팅

- Python `anthropic` SDK `client.messages.stream()` 사용 → 텍스트 델타를 프론트 SSE
  형식으로 변환하여 `StreamingResponse(media_type="text/event-stream")`로 반환.
- 모델: 요청 `model`이 `claude-sonnet-4-6` / `claude-haiku-4-5`면 그대로 호출.
  `gemini-*` / `gpt-*` 선택 시 `data: {"error": "현재 Anthropic 모델만 지원합니다"}`
  스트리밍 후 종료.
- `use_rag=true`: `context_note_id`의 본문 + FTS로 찾은 관련 노트 일부를 system 프롬프트에
  컨텍스트로 주입. `use_wiki`는 MVP 범위 외(무시).
- API 키는 settings(DB) 우선, 없으면 env `ANTHROPIC_API_KEY` 사용. 둘 다 없으면 에러.
- `thinking`은 기본 미사용(채팅 응답 지연 최소화). 필요시 향후 옵션.

### 엔티티 추출 (백그라운드)

- 노트 저장 시 `claude-haiku-4-5`로 본문에서 인물/개념/장소 등 엔티티 추출
  (structured output 또는 JSON 응답 파싱). 추출 결과를 `entities`에 저장하고
  `notes.analysis_status='analyzed'`로 갱신. 실패 시 `'failed'`.
- FastAPI `BackgroundTasks`로 비동기 실행하여 저장 응답을 막지 않음.

### `/ai/settings` — 키 마스킹

- GET: 저장된 키를 마스킹(`sk-ant-...XXXX`, 빈 값은 빈 문자열)하여 반환 — 인터넷 공개 시
  키 평문 유출 방지. PATCH: 새 값이 마스킹 형태가 아니면 갱신, 마스킹 형태면 무시(미변경).

### 발견 (discoveries)

- `services/discover.py`: 대상 노트와 **공유 엔티티 + 공유 태그** 개수가 많은 다른
  노트를 내림차순으로 반환. `shared_count`, `shared_entities[]` 채움. 순수 SQL 집계로 계산.

## 원격 접속 처리

### Vite 설정

`vite.config.ts`의 `server`에 `host: true` 추가 (0.0.0.0 바인딩, strictPort 유지).

### 프론트엔드 백엔드 주소 통합

- 신규 `src/api/config.ts`:
  ```ts
  export const API_BASE =
    import.meta.env.VITE_API_BASE ??
    `${location.protocol}//${location.hostname}:8001`
  ```
- `src/api/client.ts`, `searchApi.ts`, `aiApi.ts`, `components/Setup/VaultSetup.tsx`의
  하드코딩된 `http://localhost:8001`을 `API_BASE`로 교체.
- 결과: 원격 브라우저에서 `http://<서버IP>:1420`로 접속하면 백엔드는
  `http://<서버IP>:8001`을 가리킴.

### 인증 헤더 주입

- `client.ts`의 `apiFetch`와 `aiApi`/`searchApi`의 fetch에 `Authorization: Bearer`
  헤더 자동 추가(localStorage `sn-token`). 토큰 미설정/401 시 토큰 입력 화면 표시.
- 신규 경량 토큰 게이트 컴포넌트(또는 VaultSetup 흐름에 통합).

### CORS & 보안

- 백엔드 CORS `allow_origins`는 env `ALLOWED_ORIGIN`(쉼표 구분 다중 허용).
- TLS·도메인은 nginx 리버스 프록시 권장 — 설계 문서/README에 예시 포함.
- **인증서 없이 평문 HTTP로 공개하면 토큰·노트가 평문 전송**되는 위험을 README에 명시.

## start.sh / stop.sh

### start.sh

1. backend venv 없으면 `python3 -m venv backend/venv` 생성 후
   `backend/venv/bin/pip install -r backend/requirements.txt`.
2. `backend/.env` 없으면 `.env.example` 복사 후 "토큰·키를 입력하세요" 안내 출력하고 중단.
3. uvicorn `main:app --host 0.0.0.0 --port 8001` 백그라운드 기동, PID를 `.run/backend.pid`.
4. 루트 `node_modules` 없으면 `npm install`. `npm run dev -- --host` 백그라운드 기동,
   PID를 `.run/frontend.pid`.
5. 접속 URL 안내 출력 (프론트 :1420, 백엔드 :8001, 서버 IP 힌트).

### stop.sh

- `.run/backend.pid`, `.run/frontend.pid`를 읽어 프로세스 종료, PID 파일 제거.
  프로세스가 이미 죽었으면 경고만 출력.

## 에러 처리

- 모든 라우터: 404(없는 리소스), 401(토큰 불일치), 400(검증 실패)를 적절히 반환.
  `apiFetch`가 `API <status>: <body>` 형태 에러를 던지므로 본문에 사람이 읽을 메시지 포함.
- AI 키 없음 / Anthropic 호출 실패: `/ai/chat`은 SSE `error` 이벤트로, 추출은
  `analysis_status='failed'`로 흡수(앱 흐름 차단 안 함).
- 백엔드 미기동 시 프론트는 이미 try/catch로 무시하도록 작성되어 있음(`loadSettings` 등).

## 테스트 전략

- pytest + FastAPI `TestClient`. Anthropic SDK는 목으로 대체(실제 API 키 불필요).
- 커버: 노트/카테고리 CRUD 라운드트립, .md 파일 생성 확인, FTS 검색, 발견 계산,
  인증 401, `/ai/settings` 키 마스킹, `/ai/chat` SSE 형식(목 스트림).
- 임시 `VAULT_DIR`과 인메모리/임시 SQLite를 픽스처로 사용.

## 환경변수 (`.env.example`)

```
SPACENOTE_TOKEN=change-me-to-a-long-random-string
ANTHROPIC_API_KEY=sk-ant-...
VAULT_DIR=/var/www/html/Space_Note_v100/vault
ALLOWED_ORIGIN=http://localhost:1420
EXTRACT_MODEL=claude-haiku-4-5
```

## 미해결/후속 (문서화만)

- HTTPS/도메인 운영 시 nginx 설정은 README 예시로 제공(이번 구현 범위는 앱 코드 + 스크립트).
- OpenAI/Google 실제 연동, 벡터 검색, autology 연동은 향후 확장.
