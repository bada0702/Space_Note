# SpaceNote 🌌

**AI 기반 우주형 지식 노트 시스템 — 내 머릿속의 우주, 지식으로 담다.**

SpaceNote는 Markdown 기반 노트 작성을 핵심으로 하되, AI가 노트 사이의 관계를 자동으로 발견하고 이를 우주 공간(성도, 星圖)으로 시각화해주는 로컬 우선(local-first) 지식 관리 앱입니다. 노트는 일반 `.md` 파일로 저장되어 Obsidian vault와 호환되며, 데이터 소유권은 항상 사용자에게 있습니다.

- 노트를 작성하면 AI(Claude / OpenAI / Gemini / 로컬 Ollama)가 엔티티와 관계를 추출해 지식 그래프를 만듭니다.
- 그래프는 은하 · 별 · 항로로 은유된 3D 우주 성도(StarMap)로 탐험할 수 있습니다.
- 노트는 카테고리(은하), 즐겨찾기(기항지), 보관(블랙홀) 등으로 정리할 수 있습니다.

> 자세한 제품 배경과 컨셉은 [`PRD.MD`](./PRD.MD) 문서를 참고하세요.

---

## 목차

- [기술 스택](#기술-스택)
- [사전 요구사항](#사전-요구사항)
- [설치 방법](#설치-방법)
- [환경 변수 설정](#환경-변수-설정)
- [실행 방법](#실행-방법)
- [앱 내 AI 설정](#앱-내-ai-설정)
- [프로젝트 구조](#프로젝트-구조)
- [백엔드 API 개요](#백엔드-api-개요)
- [테스트](#테스트)
- [데스크톱 앱 빌드 (Tauri)](#데스크톱-앱-빌드-tauri)
- [문제 해결](#문제-해결)

---

## 기술 스택

| 영역 | 스택 |
|---|---|
| 프론트엔드 | React 18, TypeScript, Vite, Zustand, Tailwind CSS |
| 에디터 | Monaco Editor (Markdown) |
| 3D 시각화 | Three.js, PixiJS, d3-force |
| 데스크톱 셸 | Tauri 2 (선택 사항) |
| 백엔드 | FastAPI (Python), Uvicorn |
| 데이터베이스 | SQLite |
| AI 연동 | Anthropic Claude, OpenAI, Google Gemini, Ollama(로컬 모델) |

---

## 사전 요구사항

- **Node.js** 18 이상 (npm 포함)
- **Python** 3.10 이상
- **Git**
- (선택) 데스크톱 앱으로 실행하려면 **Rust** + Tauri 빌드 도구 체인 ([Tauri 사전 준비 가이드](https://tauri.app/start/prerequisites/))
- (선택) 로컬 LLM을 쓰려면 [Ollama](https://ollama.com/)가 설치되어 있고 실행 중이어야 함

---

## 설치 방법

### 1. 저장소 클론

```bash
git clone https://github.com/bada0702/Space_Note.git
cd Space_Note
```

### 2. 프론트엔드 의존성 설치

```bash
npm install
```

### 3. 백엔드 가상환경 및 의존성 설치

```bash
cd backend
python3 -m venv venv

# Linux / macOS
source venv/bin/activate
# Windows
venv\Scripts\activate

pip install -r requirements.txt
cd ..
```

> `start.sh` / `start.bat` 스크립트를 사용하면 가상환경 생성과 의존성 설치를 자동으로 처리해주므로 위 3번 단계를 직접 하지 않아도 됩니다.

### 4. 환경 변수 파일 생성

```bash
cp backend/.env.example backend/.env
```

생성된 `backend/.env` 파일을 열어 아래 [환경 변수 설정](#환경-변수-설정) 섹션을 참고해 값을 채워주세요. 특히 `SPACENOTE_TOKEN`은 반드시 임의의 긴 문자열로 바꿔야 합니다.

프론트엔드가 백엔드에 인증 요청을 보내려면, 프로젝트 루트에 `.env.local` 파일도 만들고 백엔드와 동일한 토큰을 넣어줍니다.

```bash
# 프로젝트 루트/.env.local
VITE_SPACENOTE_TOKEN=<backend/.env에 설정한 SPACENOTE_TOKEN과 동일한 값>
```

---

## 환경 변수 설정

`backend/.env.example`을 복사해 `backend/.env`로 사용합니다.

| 변수 | 설명 | 기본값 |
|---|---|---|
| `SPACENOTE_TOKEN` | 프론트엔드 ↔ 백엔드 API 인증에 사용되는 Bearer 토큰. 반드시 임의의 긴 문자열로 변경 | `change-me-to-a-long-random-string` |
| `ANTHROPIC_API_KEY` | Claude 모델을 사용할 경우의 Anthropic API 키. 앱 설정 화면에서도 입력/변경 가능 | (없음) |
| `VAULT_DIR` | 노트(`.md`)와 첨부파일이 저장될 로컬 디렉터리 경로 | `<프로젝트 루트>/vault` |
| `DB_PATH` | SQLite 데이터베이스 파일 경로 (노트 메타데이터, 설정 등 저장) | `backend/spacenote.db` |
| `ALLOWED_ORIGIN` | CORS 허용 origin (콤마로 여러 개 지정 가능) | `http://localhost:1420` |
| `EXTRACT_MODEL` | 노트에서 엔티티/관계를 추출할 때 사용하는 기본 AI 모델 | `claude-haiku-4-5` |

`VAULT_DIR`, Ollama 서버 주소, 기본 모델, 각 AI 제공사의 API 키 등은 `.env` 대신 **앱 실행 후 설정(⚙️) 화면**에서 변경할 수도 있습니다. 이 경우 값은 SQLite `settings` 테이블에 저장되어 `.env`보다 우선 적용됩니다.

---

## 실행 방법

### 방법 A. 원클릭 스크립트 (권장)

**Linux / macOS**

```bash
chmod +x start.sh stop.sh
./start.sh
```

- 백엔드 가상환경 생성/의존성 설치를 자동 처리하고, 백엔드(8001)를 백그라운드로 먼저 띄웁니다.
- 이어서 실행 모드를 선택합니다 (인자로 바로 지정 가능: `./start.sh web` 또는 `./start.sh desktop`).
  - `1) Web Mode` — Vite 개발 서버로 브라우저에서 사용 (`http://localhost:1420`)
  - `2) Desktop Mode` — Tauri 데스크톱 앱 실행
- 로그는 `backend.log`, `frontend.log`에 기록되며, `tail -f backend.log frontend.log`로 확인할 수 있습니다.
- 종료: `./stop.sh` (PID 파일과 포트 8001/1420을 기준으로 프로세스를 정리합니다)

**Windows**

```bat
start.bat
```

- 백엔드(`uvicorn`, 포트 8001)와 프론트엔드(`npm run dev`, 포트 1420)를 각각 별도의 콘솔 창으로 띄웁니다.
- 종료: `stop.bat` 또는 각 콘솔 창을 직접 닫기

### 방법 B. 수동 실행

두 개의 터미널이 필요합니다.

```bash
# 터미널 1 — 백엔드
cd backend
source venv/bin/activate   # Windows: venv\Scripts\activate
uvicorn main:app --port 8001 --reload

# 터미널 2 — 프론트엔드
npm run dev
```

정상 실행되면:

- 백엔드: `http://localhost:8001` (헬스체크: `GET /health`)
- 프론트엔드(웹): `http://localhost:1420`

브라우저에서 `http://localhost:1420`에 접속하면 첫 실행 시 Vault(노트 저장 폴더) 설정 화면이 나타납니다.

---

## 앱 내 AI 설정

앱을 처음 실행하면 초기 설정(Vault 경로) 화면을 거치고, 좌측 하단 설정(⚙️) 메뉴에서 다음을 구성할 수 있습니다.

- **노트 저장 경로 (Vault Dir)** — 노트/첨부파일이 실제로 저장될 폴더
- **API 키** — Anthropic(Claude) / OpenAI(GPT) / Google(Gemini) 키 중 사용할 항목 입력
- **기본 모델** — 노트 분석/채팅에 사용할 기본 AI 모델 선택. Ollama가 로컬에서 실행 중이면 설치된 모델 목록이 자동으로 드롭다운에 추가됩니다.

API 키를 하나도 입력하지 않아도 노트 작성 자체는 가능하지만, AI 관계 추출·채팅 기능을 쓰려면 최소 하나의 제공사 키(또는 로컬 Ollama)가 필요합니다.

---

## 프로젝트 구조

```
Space_Note/
├── src/                      # 프론트엔드 (React + TypeScript)
│   ├── components/
│   │   ├── AI/                # AI 채팅 패널
│   │   ├── Editor/             # Markdown 에디터, 탭, 포맷 툴바
│   │   ├── Navigation/          # 발견(Discoveries) 패널
│   │   ├── Setup/               # 초기 Vault 설정, API 설정
│   │   ├── Sidebar/              # 카테고리, 항해일지(즐겨찾기/보관)
│   │   └── StarMap/               # 3D 우주 성도(그래프) 캔버스
│   ├── api/                   # 백엔드 API 클라이언트
│   ├── store/                 # Zustand 상태 스토어
│   └── types/                 # 공용 타입 정의
├── backend/                   # 백엔드 (FastAPI)
│   ├── routers/                 # API 라우터 (notes, ai, search, categories, routes, attachments)
│   ├── services/                 # AI 클라이언트, 추출(extraction), vault 동기화 등
│   ├── tests/                     # pytest 테스트
│   ├── config.py                  # 환경설정 로딩
│   ├── db.py                       # SQLite 스키마/마이그레이션
│   └── main.py                      # FastAPI 앱 엔트리포인트
├── src-tauri/                 # Tauri 데스크톱 셸 설정
├── vault/                     # 기본 노트 저장 폴더 (VAULT_DIR)
├── start.sh / start.bat       # 실행 스크립트
├── stop.sh / stop.bat         # 종료 스크립트
└── PRD.MD                     # 제품 요구사항 문서
```

---

## 백엔드 API 개요

모든 API는 `Authorization: Bearer <SPACENOTE_TOKEN>` 헤더가 필요합니다 (첨부파일 정적 제공 라우트 제외).

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/health` | 헬스체크, 현재 Vault 경로 반환 |
| GET | `/notes` | 노트 목록 조회 |
| POST | `/notes` | 노트 생성 |
| GET | `/notes/{id}` | 노트 상세 조회 |
| PATCH | `/notes/{id}` | 노트 수정 |
| DELETE | `/notes/{id}` | 노트 삭제 |
| POST | `/notes/analyze`, `/notes/{id}/analyze` | AI로 노트 관계/엔티티 분석 |
| GET | `/categories` | 카테고리 목록 |
| POST / PATCH / DELETE | `/categories` | 카테고리 생성/수정/삭제 |
| GET | `/search` | 노트 검색 |
| GET | `/discoveries`, `/discoveries/routes` | AI가 발견한 노트 간 관계/항로 |
| GET | `/tags`, `/tags/{tag}/notes` | 태그 목록 및 태그별 노트 |
| GET | `/entities/{note_id}` | 노트에서 추출된 엔티티 조회 |
| POST / DELETE | `/routes` | 노트 간 항로(연결) 생성/삭제 |
| GET | `/ai/settings`, `PATCH /ai/settings` | AI 설정 조회/변경 |
| GET | `/ai/models/ollama` | 로컬 Ollama 설치 모델 목록 |
| POST | `/ai/chat` | AI 채팅 |
| POST | `/attachments` | 첨부파일 업로드 |
| GET | `/attachments/file/{stored}` | 첨부파일 정적 제공 (인증 불필요) |

---

## 테스트

백엔드 테스트는 `pytest`로 실행합니다.

```bash
cd backend
source venv/bin/activate
pytest
```

---

## 데스크톱 앱 빌드 (Tauri)

Rust 및 Tauri 사전 요구사항이 설치되어 있어야 합니다.

```bash
# 개발 모드로 실행
npm run tauri dev

# 배포용 바이너리 빌드
npm run tauri build
```

빌드 산출물은 `src-tauri/target/release` 하위에 생성됩니다.

---

## 문제 해결

- **`SPACENOTE_TOKEN not configured` 오류** — `backend/.env`에 `SPACENOTE_TOKEN`이 비어 있습니다. 값을 채우고 백엔드를 재시작하세요.
- **401 Unauthorized** — 프론트엔드의 `.env.local`(`VITE_SPACENOTE_TOKEN`)과 백엔드의 `backend/.env`(`SPACENOTE_TOKEN`) 값이 일치하는지 확인하세요.
- **CORS 오류** — 프론트엔드를 기본 포트(1420)가 아닌 다른 포트로 띄웠다면 `backend/.env`의 `ALLOWED_ORIGIN`에 해당 origin을 추가하세요.
- **포트 충돌 / 재시작 후에도 안 뜸** — `./stop.sh`(Linux) 실행 후 `lsof -i:8001`, `lsof -i:1420`으로 잔여 프로세스가 없는지 확인 후 다시 `./start.sh`를 실행하세요.
- **AI 기능이 동작하지 않음** — 설정 화면에서 최소 하나의 API 키(Anthropic/OpenAI/Google)를 입력했는지, 또는 Ollama를 로컬 기본 포트(`http://127.0.0.1:11434`)에서 실행 중인지 확인하세요.
