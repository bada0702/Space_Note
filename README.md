# SpaceNote 🌌

**노트를 쓰면 AI가 온톨로지로 엮어 주는 우주형 지식 노트 — 내 머릿속의 우주, 지식으로 담다.**

SpaceNote는 Markdown 노트 앱입니다. 노트를 저장하면 **키워드·태그·AI 온톨로지** 세 겹으로 노트 사이의 연결을 찾아내고, 그 연결을 은하·행성·항로로 이루어진 3D 우주 성도(星圖)로 보여 줍니다.

- **로컬 우선** — 노트는 일반 `.md` 파일로 저장되어 Obsidian vault와 호환되고, 데이터는 사용자 PC에 남습니다.
- **온톨로지 기반 지식 그래프** — AI가 노트에서 개념(Class / Instance / Literal)과 관계를 추출해 하나의 그래프로 합칩니다.
- **근거 있는 연결** — 성도의 항로(연결선)마다 "어떤 개념·관계·태그 때문에 이어졌는지"가 표시됩니다.
- **그래프 RAG 채팅** — 질문에서 출발 개념을 찾아 관계를 따라가며 관련 노트를 골라 답합니다.
- **AI 제공사 선택** — Claude, OpenAI, Gemini, 로컬 Ollama 중 고를 수 있습니다. 키가 없어도 노트 작성과 키워드·태그 연결은 동작합니다.

> 제품 배경과 컨셉은 [`PRD.MD`](./PRD.MD), 지식 그래프 설계는 [`docs/superpowers/specs/`](./docs/superpowers/specs/)를 참고하세요.

---
윈도우 버전 
exe 버전링크입니다. 다운로드 해서 사용하세요
http://chojungwon.iptime.org/SpaceNote_0.1.0_x64-setup.zip


## 목차

- [노트가 연결되는 방식: 키워드 → 태그 → 온톨로지](#노트가-연결되는-방식-키워드--태그--온톨로지)
- [주요 기능](#주요-기능)
- [기술 스택](#기술-스택)
- [설치](#설치)
- [실행](#실행)
- [환경 변수](#환경-변수)
- [앱 내 설정](#앱-내-설정)
- [MCP 서버 (외부 에이전트 연동)](#mcp-서버-외부-에이전트-연동)
- [지식 그래프 평가 도구](#지식-그래프-평가-도구)
- [프로젝트 구조](#프로젝트-구조)
- [백엔드 API](#백엔드-api)
- [테스트](#테스트)
- [Windows 설치판 (setup.exe)](#windows-설치판-setupexe)
- [문제 해결](#문제-해결)

---

## 노트가 연결되는 방식: 키워드 → 태그 → 온톨로지

노트 두 개를 잇는 근거는 세 층으로 쌓입니다. 아래층일수록 가볍고 항상 동작하며, 위층일수록 정확합니다.

```
 ┌───────────────────────────────────────────────────────────────┐
 │ 3. AI 온톨로지   개념(Class/Instance/Literal) + 관계(술어)     │  ← 가장 정확, AI 필요
 │    "FastAPI" ─인스턴스이다→ "웹 프레임워크"                     │
 │    "FastAPI" ─작성 언어→ "Python"                               │
 ├───────────────────────────────────────────────────────────────┤
 │ 2. 태그          본문의 #태그 (사용자가 직접 단 연결)           │  ← 항상 유지
 ├───────────────────────────────────────────────────────────────┤
 │ 1. 키워드        Kiwi 형태소 분석 / AI 엔티티 추출              │  ← AI 없이도 동작
 └───────────────────────────────────────────────────────────────┘
                 ↓ 근거를 점수로 합산 (희소한 개념일수록 높게)
          성도의 항로 · 발견(Discoveries) 패널 · 경로 탐색 · 채팅 RAG
```

### 1. 키워드 연결

- 노트에서 핵심 명사를 뽑아 `entities` 테이블에 저장합니다.
- AI 키가 있으면 AI가 엔티티를 추출하고, 없으면 [Kiwi](https://github.com/bab2min/kiwipiepy) 형태소 분석기로 추출합니다. 한국어 조사·어미를 떼고 불용어를 거르며, `프론트엔드`·`마이크로서비스` 같은 복합어는 사용자 사전에 등록해 잘못 쪼개지지 않게 합니다.
- 같은 키워드를 가진 노트끼리 연결 후보가 됩니다. **두 노트 모두 지식 그래프가 있으면** 키워드 대신 그래프를 근거로 씁니다. 그래프가 같은 내용을 더 정확하게 담고 있기 때문입니다.

### 2. 태그 연결

- 본문에 쓴 `#태그`를 인라인으로 인식합니다. `# 제목`(# 뒤 공백)과는 구분됩니다.
- 코드 블록, `#1` 같은 숫자, `#fff` 같은 색상 코드, `#include`·`#password =` 같은 주석 처리된 설정은 태그로 잡지 않습니다.
- 태그는 **사용자의 명시적인 의도**이므로 지식 그래프가 있어도 연결 근거로 남깁니다.

### 3. AI 온톨로지 (지식 그래프)

노트를 저장하면 백그라운드 워커가 AI에게 노트를 온톨로지로 추출하게 하고, 결과를 `concepts` / `relations` / `note_concepts` 테이블에 합칩니다.

| 노드 종류 | 의미 | 예 |
|---|---|---|
| `class` | 분류·범주 | 웹 프레임워크, 데이터베이스 |
| `instance` | 구체적인 대상 | FastAPI, SQLite |
| `literal` | 값 (노트마다 따로 관리, 연결 근거로 쓰지 않음) | 8001, 2026-10 |

- **규칙 사전** — 추출 어휘는 [`backend/ontology/general.json`](./backend/ontology/general.json)에 OWL/SKOS(JSON-LD) 형식으로 정의돼 있습니다.
  - 유형(클래스) 34개: 개념, 문제, 사람, 조직, 프로젝트, 기술, 프로그래밍 언어, 프레임워크·라이브러리, 데이터베이스, AI 모델, 장소, 음식, 금융 등
  - 관계(술어) 27개: 기본 술어 `사용한다`·`일부이다`·`해결한다`·`관련있다`·`인스턴스이다`·`하위클래스이다`와 도메인 술어 `의존한다`·`구현한다`·`작성 언어`·`실행 환경`·`대안이다`·`원인이다`·`선행한다` 등
  - 각 술어에는 `rdfs:domain`/`range`(어떤 유형끼리 이을 수 있는지)가 있어, 맞지 않는 관계는 보정되거나 걸러집니다.
  - `SPACENOTE_ONTOLOGY` 환경변수로 다른 도메인의 규칙 사전 파일로 바꿀 수 있습니다.
- **개념 병합** — 이름을 정규화해 같은 개념을 하나로 합칩니다. 추출할 때 기존 개념 목록을 프롬프트에 함께 넣어 표기 흔들림을 줄입니다. 공유 개념의 kind(class/instance)는 노트별 다수결로 정합니다.
- **근거 문장** — 관계마다 근거가 된 원문 문장을 저장하고, 그 관계를 추출한 노트에만 묶습니다.
- **추출 모델** — 기본값은 토큰 소모가 적은 `gemini-3.1-flash-lite`입니다. 설정에서 Claude, GPT, Ollama 로컬 모델로 바꿀 수 있습니다. 진행률 확인, 실패 재시도, 전체 재구축, 취소를 지원합니다.

### 연결 점수와 활용

`_PairEvidence`(`backend/routers/search.py`)가 노트 쌍마다 **공유 개념(희소성 IDF 가중) + 개념 사이 관계 + 공유 키워드·태그**를 합산합니다. 여러 노트에 흔하게 나오는 허브 개념은 지름길이 되지 않도록 제외합니다.

- **항로** — 성도의 연결선. 사용자가 확정(confirmed)한 항로는 AI가 다시 계산해도 유지되고, 거절(rejected)한 쌍은 다시 나오지 않습니다.
- **경로 탐색** — 두 노트를 잇는 가장 짧은 `노트 — 개념 — 관계 — 개념 — 노트` 경로를 보여 줍니다.
- **별자리** — 노트 3개 이상이 공유하는 개념을 묶어 보여 주고, 개념 관계도를 그립니다.
- **그래프 RAG 채팅** — 질문에서 출발 개념을 찾아 최대 2홉까지 관계를 따라 노트 점수를 매기고, 노트 앞부분이 아니라 질문과 관련된 구간을 여러 곳에서 발췌해 답변 근거로 씁니다.

---

## 주요 기능

| 기능 | 설명 |
|---|---|
| Markdown 에디터 | Monaco 기반 에디터, 탭, 서식 툴바, 이미지·파일 첨부 |
| 3D 성도 | Three.js 우주 화면. 카테고리 = 은하, 노트 = 행성, 연결 = 항로. 행성 검색, 범례 |
| 정리 | 카테고리(은하), 즐겨찾기(기항지), 보관(블랙홀, 빨려 들어가는 연출 포함) |
| 발견 패널 | 노트별 연결 후보와 근거(공유 개념·관계·태그) 표시, 항로 확정·거절 |
| AI 채팅 | 그래프 RAG, 마크다운 답변 렌더링, 대화 기록 저장 |
| 노트 요약 | AI로 노트 한 개 요약 |
| 가져오기 | `.md` 폴더, zip, ChatGPT·Gemini 공유 링크의 대화 → 노트 |
| MCP 서버 | 외부 AI 에이전트가 노트 검색·조회·그래프 탐색(·작성) |
| 개인화 | 앱 이름·로고 변경, 다크/라이트 모드 |
| 모바일 | 모바일 화면 레이아웃 (성도, 채팅) |
| 초기화 | 미리보기 후 데이터 초기화 |

---

## 기술 스택

| 영역 | 스택 |
|---|---|
| 프론트엔드 | React 18, TypeScript, Vite, Zustand, Tailwind CSS |
| 에디터 | Monaco Editor, marked |
| 시각화 | Three.js, PixiJS, d3-force |
| 데스크톱 | Tauri 2 (선택) |
| 백엔드 | FastAPI, Uvicorn, SQLite |
| 한국어 처리 | kiwipiepy (형태소 분석) |
| 온톨로지 | OWL / SKOS 규칙 사전 (JSON-LD) |
| AI | Anthropic Claude, OpenAI, Google Gemini, Ollama |

---

## 설치

### 사전 요구사항

- **Node.js** 18 이상, **Python** 3.10 이상, **Git**
- (선택) 데스크톱 앱: **Rust** + [Tauri 사전 준비](https://tauri.app/start/prerequisites/)
- (선택) 로컬 LLM: [Ollama](https://ollama.com/) 실행 중

### 1. 클론과 의존성 설치

```bash
git clone https://github.com/bada0702/Space_Note.git
cd Space_Note
npm install

cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cd ..
```

> `start.sh` / `start.bat`을 쓰면 가상환경 생성과 `pip install`을 자동으로 해 줍니다.

### 2. 환경 변수 파일

```bash
cp backend/.env.example backend/.env
```

`backend/.env`의 `SPACENOTE_TOKEN`을 임의의 긴 문자열로 바꾸고, 같은 값을 프로젝트 루트의 `.env.local`에도 넣습니다.

```bash
# 프로젝트 루트/.env.local
VITE_SPACENOTE_TOKEN=<backend/.env의 SPACENOTE_TOKEN과 같은 값>
```

> `.env`, `.env.local`은 커밋하지 마세요.

---

## 실행

### 원클릭 스크립트 (권장)

**Linux / macOS**

```bash
chmod +x start.sh stop.sh
./start.sh            # 실행 모드 선택 메뉴
./start.sh web        # 브라우저 모드 (http://localhost:1420)
./start.sh desktop    # Tauri 데스크톱 앱
./stop.sh             # 종료
```

로그는 `backend.log`, `frontend.log`에 남습니다.

**Windows**: `start.bat`으로 실행하고 `stop.bat`으로 종료합니다.

### 수동 실행

```bash
# 터미널 1 — 백엔드 (포트 8001)
cd backend && source venv/bin/activate
uvicorn main:app --port 8001 --reload

# 터미널 2 — 프론트엔드 (포트 1420)
npm run dev
```

- 프론트엔드는 Vite 프록시로 `/api/*` 요청을 `http://127.0.0.1:8001`에 넘깁니다.
- 백엔드 헬스체크: `GET http://localhost:8001/health`
- 처음 접속하면 Vault(노트 저장 폴더) 설정 화면이 나옵니다.

---

## 환경 변수

`backend/.env`에 둡니다.

| 변수 | 설명 | 기본값 |
|---|---|---|
| `SPACENOTE_TOKEN` | 프론트엔드 ↔ 백엔드 Bearer 토큰 (**필수**) | — |
| `ALLOWED_ORIGIN` | CORS 허용 origin, 콤마로 여러 개 | `http://localhost:1420` |
| `VAULT_DIR` | 노트·첨부파일 폴더 (절대 경로) | `<프로젝트 루트>/vault` |
| `DB_PATH` | SQLite DB 파일 (절대 경로) | `backend/spacenote.db` |
| `ANTHROPIC_API_KEY` | Claude API 키 | — |
| `OPENAI_API_KEY` | OpenAI API 키 | — |
| `GOOGLE_API_KEY` | Gemini API 키 | — |
| `OLLAMA_BASE_URL` | Ollama 서버 주소 | `http://127.0.0.1:11434` |
| `EXTRACT_MODEL` | Claude로 키워드(엔티티)를 추출할 때 쓰는 모델 | `claude-haiku-4-5` |
| `SPACENOTE_ONTOLOGY` | 온톨로지 규칙 사전 경로 | `backend/ontology/general.json` |
| `SPACENOTE_GRAPH_WORKER` | `0`이면 지식 그래프 백그라운드 워커 끔 | `1` |

API 키, Vault 경로, 기본 모델 등은 앱의 **설정(⚙️) 화면**에서도 바꿀 수 있습니다. 설정 화면에서 입력한 값은 SQLite `settings` 테이블에 저장되어 `.env`보다 우선합니다.

> **외부 전송 주의**: 클라우드 AI를 쓰면 노트 본문이 해당 제공사로 전송됩니다. 민감한 노트는 Ollama 로컬 모델을 쓰세요.

---

## 앱 내 설정

좌측 하단 설정(⚙️)에서 다음을 구성합니다.

- **Vault 경로** — 노트가 저장될 폴더
- **API 키** — Anthropic / OpenAI / Google. 저장된 키는 삭제 버튼으로 지울 수 있습니다.
- **기본 모델 (채팅)** — Ollama가 실행 중이면 설치된 모델이 목록에 자동으로 추가됩니다.
- **지식 그래프** — 추출 모델 선택, 분석 진행률, 실패 재시도, 전체 재구축, 취소
- **가져오기** — `.md` 폴더 / zip / ChatGPT·Gemini 공유 링크
- **MCP** — 켜기·끄기, 쓰기 허용, 토큰 재발급
- **앱 이름·로고**, **데이터 초기화**

---

## MCP 서버 (외부 에이전트 연동)

SpaceNote 백엔드는 [MCP](https://modelcontextprotocol.io/) 서버를 내장하고 있어, Claude Code 같은 외부 AI 에이전트가 노트와 지식 그래프를 도구로 쓸 수 있습니다.

- 엔드포인트: `POST /mcp` (Streamable HTTP, 무상태 JSON 응답)
- 인증: 앱 토큰과 별개인 **MCP 전용 Bearer 토큰** (설정 화면에서 발급·재발급)
- 설정 화면에 클라이언트 설정 JSON(`mcpServers`)이 표시되므로 복사해서 쓰면 됩니다.

| 도구 | 설명 |
|---|---|
| `search_notes` | 노트 검색 |
| `get_note` | 노트 본문 조회 |
| `list_notes` | 노트 목록 |
| `list_categories` | 카테고리 목록 |
| `graph_neighbors` | 개념의 이웃 개념·관계 조회 |
| `graph_path` | 두 개념·노트 사이 그래프 경로 |
| `create_note` | 노트 작성 (**쓰기 허용**을 켰을 때만 노출) |

---

## 지식 그래프 평가 도구

온톨로지 추출과 연결 품질을 수치로 확인하는 도구입니다. 모두 **DB에 쓰지 않으며**, 보고서는 `backend/graph_eval/reports/`에 JSON과 Markdown으로 남습니다. 실제 노트에서 만든 표본·질문은 `graph_eval/local/`(git 제외)에만 둡니다.

```bash
cd backend

# 추출 정확도 — 정답 세트(graph_eval/cases)로 관계 정밀도·재현율·F1, kind·유형 정확도 채점
venv/bin/python -m graph_eval.run --model gemini-3.1-flash-lite --runs 2
venv/bin/python -m graph_eval.run --model ollama:<모델명>

# 연결선 정밀도@5 — 표본 노트의 상위 항로를 사람이 판정
venv/bin/python -m graph_eval.links export
venv/bin/python -m graph_eval.links score --min-score 5

# 채팅 검색 적중률@5, MRR — local/questions.json 기준
venv/bin/python -m graph_eval.retrieval

# 운영 DB 구조 진단 — 개념·관계·항로 분포
venv/bin/python -m graph_eval.audit
```

---

## 프로젝트 구조

```
Space_Note/
├── src/                        # 프론트엔드 (React + TypeScript)
│   ├── components/
│   │   ├── AI/                 # AI 채팅 패널
│   │   ├── Editor/             # Markdown 에디터, 탭, 서식 툴바
│   │   ├── Layout/             # 화면 레이아웃
│   │   ├── Navigation/         # 발견(Discoveries) 패널
│   │   ├── Setup/              # 초기 Vault 설정, API·시스템 설정
│   │   ├── Sidebar/            # 카테고리, 항해일지(즐겨찾기/보관)
│   │   ├── StarMap/            # 3D 성도, 별자리, 경로 탐색
│   │   └── common/
│   ├── api/                    # 백엔드 API 클라이언트
│   ├── store/                  # Zustand 스토어
│   └── types/
├── backend/                    # 백엔드 (FastAPI)
│   ├── main.py                 # 앱 엔트리포인트
│   ├── config.py / db.py       # 설정, SQLite 스키마·마이그레이션
│   ├── routers/                # notes, ai, search, graph, routes, categories,
│   │                           # conversations, attachments, mcp, reset
│   ├── services/
│   │   ├── extraction.py       # 키워드(엔티티) 추출: AI / Kiwi
│   │   ├── tagparse.py         # 인라인 #태그 파싱
│   │   ├── graph_extraction.py # 온톨로지 추출·개념 병합
│   │   ├── graph_worker.py     # 백그라운드 추출 워커
│   │   ├── graph_retrieval.py  # 그래프 RAG 검색
│   │   ├── note_import.py      # .md 폴더·zip 가져오기
│   │   ├── chatgpt_share.py / gemini_share.py  # 공유 링크 가져오기
│   │   └── *_client.py         # Anthropic, OpenAI, Gemini, Ollama
│   ├── ontology/general.json   # OWL/SKOS 규칙 사전
│   ├── graph_eval/             # 지식 그래프 평가 도구
│   └── tests/                  # pytest
├── src-tauri/                  # Tauri 데스크톱 셸
├── scripts/build-windows.ps1   # Windows 설치판 빌드
├── docs/superpowers/           # 설계·구현 계획 문서
├── start.sh / start.bat
├── stop.sh / stop.bat
└── PRD.MD
```

---

## 백엔드 API

`/health`, `/attachments/file/*`, `/mcp`를 제외한 모든 API는 `Authorization: Bearer <SPACENOTE_TOKEN>` 헤더가 필요합니다.

| 영역 | 경로 |
|---|---|
| 노트 | `GET/POST /notes`, `GET/PATCH/DELETE /notes/{id}` |
| 키워드 분석 | `POST /notes/analyze`, `POST /notes/{id}/analyze`, `…/analyze-python`, `GET /notes/analyze/progress` |
| 가져오기 | `POST /notes/import/files`, `/notes/import/zip`, `/notes/import/chatgpt` (ChatGPT·Gemini 링크) |
| 지식 그래프 | `GET /graph/status`, `POST /graph/rebuild`, `/graph/retry-failed`, `/graph/cancel`, `/graph/analyze`, `/graph/notes/{id}` |
| 별자리 | `GET /constellations`, `/constellations/{cid}/notes`, `/constellations/{cid}/graph` |
| 연결 | `GET /discoveries`, `/discoveries/routes`, `/routes/path`, `POST/DELETE /routes` |
| 검색·태그 | `GET /search`, `/tags`, `/tags/{tag}/notes`, `/entities/{note_id}` |
| 카테고리 | `GET/POST /categories`, `PATCH/DELETE /categories/{cid}` |
| AI | `GET/PATCH /ai/settings`, `GET /ai/ollama/models`, `GET /ai/retrieve`, `POST /ai/chat`, `POST /ai/summarize/{note_id}` |
| 대화 기록 | `GET /conversations`, `GET/PUT/DELETE /conversations/{cid}` |
| 첨부파일 | `POST /attachments`, `GET /attachments/file/{stored}` |
| MCP | `GET/PATCH /mcp/config`, `POST /mcp/token/rotate`, `POST /mcp` |
| 초기화 | `GET /reset/preview`, `POST /reset` |

전체 스키마는 백엔드 실행 후 `http://localhost:8001/docs`(Swagger UI)에서 볼 수 있습니다.

---

## 테스트

```bash
cd backend
source venv/bin/activate
pytest
```

---

## Windows 설치판 (setup.exe)

Tauri 셸이 PyInstaller로 묶은 백엔드를 `127.0.0.1:18001`에 띄우는 데스크톱 앱입니다.
인증 토큰은 실행할 때마다 새로 만들어지며, API 키는 앱의 설정 화면에서 입력합니다.

### 빌드 (Windows PC)

사전 설치(1회): Python 3.12, Node 20, Rust([rustup](https://rustup.rs/)), Visual Studio 2022 Build Tools(C++ 워크로드)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1
```

산출물: `src-tauri\target\release\bundle\nsis\SpaceNote_<버전>_x64-setup.exe`

- 빌드 PC의 `.env.local` 토큰은 번들에 들어가지 않습니다(`vite build --mode desktop` + `.env.desktop`, 빌드 후 스크립트가 재확인).
- `build-windows.ps1`은 UTF-8 BOM으로 저장돼 있어야 Windows PowerShell 5.1에서 한글이 깨지지 않습니다.
- 아이콘을 바꾸려면 `src-tauri/icons/source.svg`(또는 1024×1024 PNG)를 교체하고 `npx tauri icon <파일> -o src-tauri/icons`를 실행하세요.

### 설치·데이터 위치

| 항목 | 위치 |
|---|---|
| 프로그램 | 사용자별 설치 (관리자 권한 불필요) |
| DB | `%APPDATA%\SpaceNote\spacenote.db` |
| 기본 vault | `%USERPROFILE%\Documents\SpaceNote` (첫 실행 화면에서 변경 가능) |
| 백엔드 로그 | `%APPDATA%\SpaceNote\backend.log` |

앱을 제거해도 DB와 vault는 남습니다.

### 알려진 제약

- **SmartScreen 경고**: 코드 서명을 하지 않아 첫 실행 시 "Windows의 PC 보호" 창이 뜹니다. **추가 정보 → 실행**을 누르세요.
- **WebView2**: Windows 10/11에는 기본 포함입니다. 없으면 설치 중 인터넷으로 내려받으므로 폐쇄망 PC에서는 별도 설치가 필요합니다.
- **포트 18001**을 다른 프로그램이 쓰고 있으면 실행되지 않습니다(오류 창 표시).
- 웹 버전에서 만든 vault를 열면 첨부 이미지(`/api/attachments/...` 링크)가 표시되지 않습니다.

### 설치판 검증 체크리스트

- [ ] setup.exe 설치 (관리자 권한 없이)
- [ ] 실행 → 화면 표시, 노트 생성·저장
- [ ] API 키 입력 → AI 채팅 응답
- [ ] vault 폴더 변경 (네이티브 다이얼로그)
- [ ] 창 종료 후 작업 관리자에 `spacenote-backend.exe`가 남지 않음
- [ ] 제거 후 `%APPDATA%\SpaceNote`, vault 데이터 유지
- [ ] 한글 사용자명 계정(`C:\Users\홍길동`)에서 실행 → 태그·키워드 추출 동작
- [ ] 작업 관리자에서 SpaceNote.exe 강제 종료 → `spacenote-backend.exe`도 몇 초 내 종료, 재실행 정상
- [ ] 설치 파일 크기 기록

---

## 문제 해결

- **`SPACENOTE_TOKEN not configured` 오류** — `backend/.env`에 `SPACENOTE_TOKEN`이 비어 있습니다. 값을 채우고 백엔드를 재시작하세요.
- **401 Unauthorized** — 프론트엔드의 `.env.local`(`VITE_SPACENOTE_TOKEN`)과 백엔드의 `backend/.env`(`SPACENOTE_TOKEN`) 값이 일치하는지 확인하세요.
- **CORS 오류** — 프론트엔드를 기본 포트(1420)가 아닌 다른 포트로 띄웠다면 `backend/.env`의 `ALLOWED_ORIGIN`에 해당 origin을 추가하세요.
- **포트 충돌 / 재시작 후에도 안 뜸** — `./stop.sh`(Linux) 실행 후 `lsof -i:8001`, `lsof -i:1420`으로 잔여 프로세스가 없는지 확인 후 다시 `./start.sh`를 실행하세요.
- **AI 기능이 동작하지 않음** — 설정 화면에서 최소 하나의 API 키(Anthropic/OpenAI/Google)를 입력했는지, 또는 Ollama를 로컬 기본 포트(`http://127.0.0.1:11434`)에서 실행 중인지 확인하세요.
