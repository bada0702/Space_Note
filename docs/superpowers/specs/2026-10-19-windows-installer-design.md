# SpaceNote Windows 설치판(setup.exe) 배포 — 설계 문서

> 작성일: 2026-10-19
> 상태: 승인됨 (브레인스토밍 완료, 구현 계획 대기)

## 배경

SpaceNote는 현재 리눅스 서버에서 **웹 앱**(Vite dev :1420 + FastAPI :8001, `/api` 프록시,
단일 토큰 인증)으로 운영 중이다. 이를 **불특정 사용자에게 배포할 Windows 설치판**으로도
제공하려 한다. 사용자는 `setup.exe`로 설치하고 `SpaceNote.exe`로 실행한다.

현재 상태에서 확인한 사실:

1. `src-tauri/`에 Tauri v2 스캐폴드가 있으나 백엔드 연동이 없고, `bundle.icon`이 비어 있다.
2. 프론트는 이미 Tauri 폴더 선택 다이얼로그(`VaultSetup.tsx`, `ApiSettings.tsx`)를
   `__TAURI_INTERNALS__` 감지 시 사용한다.
3. API 키 입력 UI(`ApiSettings`)가 이미 있고, 키는 DB `settings` 테이블에 저장된다.
   → 첫 실행 키 입력 흐름은 신규 구현 불필요.
4. 인증 토큰이 빌드 시점 환경변수(`VITE_SPACENOTE_TOKEN`)로 번들에 박힌다.
   → 그대로 배포하면 모든 설치본이 같은 토큰을 공유한다.
5. `API_BASE = '/api'`는 Vite 프록시에 의존한다. Tauri 창(`http://tauri.localhost`)에는
   프록시가 없다.
6. `config.py`는 이미 `DB_PATH`, `VAULT_DIR`, `SPACENOTE_TOKEN`, `ALLOWED_ORIGIN`을
   환경변수로 받는다. → 백엔드 설정 코드 수정 불필요.
7. `kiwipiepy_model`이 105MB이며, 미설치 시 `kiwi = None` 폴백이 있다.

## 결정 사항 (브레인스토밍 확정)

| 항목 | 결정 |
|------|------|
| 사용 대상 | **불특정 사용자 배포** (각자 API 키 입력, 로컬 데이터) |
| 빌드 환경 | **본인 Windows PC에서 직접** (CI 없음) |
| 패키징 방식 | **Tauri 셸 + PyInstaller 백엔드 sidecar** |
| 설치 파일 | Tauri NSIS (`*_x64-setup.exe`) |
| 백엔드 포트 | 고정 **127.0.0.1:18001** |
| 인증 토큰 | **실행할 때마다 Rust가 랜덤 생성** |
| PyInstaller 모드 | **onedir** (Tauri `bundle.resources`로 포함) |
| kiwipiepy 모델 | **포함** |

## 비범위 (YAGNI)

- 자동 업데이트, 코드 서명 (SmartScreen 경고는 README로 안내)
- macOS / Linux 패키징
- CI(GitHub Actions) 빌드
- 멀티유저
- WebView2 오프라인 설치 (기본 부트스트래퍼 사용 — 폐쇄망 배포 시 별도 전환 필요)

## 1. 런타임 구조

```
SpaceNote.exe (Tauri, WebView2)
 ├─ setup 단계
 │   1) %APPDATA%\SpaceNote 생성
 │   2) 127.0.0.1:18001 점유 확인 → 점유 중이면 오류 대화상자 후 종료
 │   3) 랜덤 토큰 생성 (32바이트 hex)
 │   4) <resources>\spacenote-backend\spacenote-backend.exe 실행 (CREATE_NO_WINDOW)
 │        env: SPACENOTE_TOKEN=<토큰>
 │             DB_PATH=%APPDATA%\SpaceNote\spacenote.db
 │             VAULT_DIR=%USERPROFILE%\Documents\SpaceNote
 │             ALLOWED_ORIGIN=http://tauri.localhost
 │        stdout/stderr → %APPDATA%\SpaceNote\backend.log
 │   5) Child 핸들·토큰을 tauri State에 저장
 ├─ 커맨드 backend_info → { baseUrl: "http://127.0.0.1:18001", token }
 └─ RunEvent::Exit → sidecar kill
```

- **고정 포트를 쓰는 이유:** MCP 설정에 등록된 aibot 엔드포인트 URL이 실행할 때마다
  바뀌면 안 된다.
- **실행마다 토큰을 새로 만드는 이유:** 같은 PC의 다른 프로세스가 API를 호출하지 못하게
  하고, 빌드에 비밀값을 넣지 않기 위해서다. MCP는 기존 `mcp_token`을 그대로 쓴다.
- **백엔드 준비 대기:** 프론트가 `/health`를 폴링한다(최대 약 20초). 시간을 넘기면
  "백엔드를 시작하지 못했습니다 — backend.log 확인" 메시지를 띄운다.

## 2. 컴포넌트별 변경

### 프론트엔드 — `src/api/client.ts`
- Tauri 환경(`__TAURI_INTERNALS__`)이면 `invoke('backend_info')`로 받은 `baseUrl`과
  `token`을 사용하고, 아니면 기존 `/api` + `VITE_SPACENOTE_TOKEN`을 사용한다.
- `API_BASE`, `authHeaders`를 쓰는 곳(`aiApi.ts`, `attachmentsApi.ts`)이 비동기 초기화
  이후의 값을 쓰도록 맞춘다. 앱 시작 시 한 번 `initBackend()`를 호출해 값을 확정하고,
  `/health` 대기도 여기서 한다.
- **리눅스 웹 운영 방식에는 영향이 없어야 한다.**

### 백엔드 — `backend/desktop_entry.py` (신규, 약 15줄)
- `uvicorn.run(app, host="127.0.0.1", port=18001)`로 실행한다. PyInstaller에서는
  `"main:app"` 문자열 import가 동작하지 않으므로 app 객체를 직접 넘긴다.
- 기존 `main.py`, `config.py`는 수정하지 않는다.

### 백엔드 번들 — `backend/spacenote-backend.spec` (신규)
- onedir 모드로 빌드하고, `kiwipiepy`·`kiwipiepy_model` 데이터 파일과 uvicorn의 동적
  import(hiddenimports)를 포함한다.
- **제외:** `.env`, `spacenote.db`, `venv`, `tests`, `vault*`.

### Tauri — `src-tauri/`
- `lib.rs`: 위 런타임 구조를 구현한다(약 60~80줄). `backend_info` 커맨드를 추가하고,
  종료 시 sidecar를 kill한다.
- `tauri.conf.json`:
  - `bundle.targets: ["nsis"]`
  - `bundle.resources`: `../build/backend/spacenote-backend/` → `spacenote-backend/`
  - NSIS: `installMode: "currentUser"`, 언어 Korean/English, 시작 메뉴·바탕화면 바로가기
  - `bundle.icon`: `npx tauri icon`으로 생성한 아이콘 세트 (원본은 `src-tauri/icons/source.png`)
- 아이콘: 원본이 없으므로 임시 아이콘(별 모양 단색 1024×1024 PNG)을 만든다. 나중에
  `source.png`만 교체하고 `npx tauri icon`을 다시 실행하면 된다.

### 빌드 스크립트 — `scripts/build-windows.ps1` (신규)
```
1. 사전 점검: python 3.12, node, cargo 존재 확인 → 없으면 설치 안내 후 중단
2. backend\.venv-build 생성 → requirements.txt + pyinstaller 설치
3. pyinstaller backend\spacenote-backend.spec → build\backend\spacenote-backend\
4. 산출물 검사: .env / spacenote.db가 포함돼 있으면 실패 처리
5. npm ci → npx tauri build
6. 결과 경로 출력: src-tauri\target\release\bundle\nsis\SpaceNote_<ver>_x64-setup.exe
```
- 빌드 PC 사전 설치(1회): Python 3.12, Node 20, Rust(rustup), VS 2022 Build Tools(C++).

### 기타
- `.gitignore`: `src-tauri/target/`, `build/`, `backend/.venv-build/`
- README: Windows 빌드 방법, SmartScreen 안내, 데이터 위치, 수동 검증 체크리스트

## 3. 데이터 위치

| 항목 | 위치 | 비고 |
|---|---|---|
| DB | `%APPDATA%\SpaceNote\spacenote.db` | 앱을 제거해도 유지 |
| 기본 vault | `%USERPROFILE%\Documents\SpaceNote` | VaultSetup에서 변경하면 DB 값이 우선 (기존 로직) |
| 백엔드 로그 | `%APPDATA%\SpaceNote\backend.log` | 실행할 때마다 덮어씀 |

## 4. 오류 처리

| 상황 | 동작 |
|---|---|
| 18001 포트 점유 | 네이티브 오류 대화상자 → 앱 종료 |
| sidecar 실행 파일 없음 / 실행 실패 | 오류 대화상자(경로 포함) → 앱 종료 |
| `/health` 20초 내 무응답 | 화면에 오류와 backend.log 경로 표시 |
| API 키 미입력 | 기존 동작 유지 (AI 기능 사용 시 설정 안내) |

## 5. 검증

1. **리눅스(자동):**
   - `pytest`로 기존 백엔드 테스트 회귀 없음
   - `npm run build`(tsc 포함) 통과
   - `cargo check` 통과 (Windows 전용 코드는 `cfg(windows)`로 분리)
2. **리눅스(수동):** `desktop_entry.py` 직접 실행 → `/health` 200, 토큰 없으면 401, 토큰 있으면 200
3. **Windows 실기기 (사용자 수행, README 체크리스트):**
   - [ ] setup.exe 설치 (관리자 권한 없이)
   - [ ] 실행 → 화면 표시, 노트 생성·저장
   - [ ] API 키 입력 → AI 채팅 응답
   - [ ] vault 폴더 변경 (네이티브 다이얼로그)
   - [ ] 창 종료 후 작업 관리자에 `spacenote-backend.exe`가 남지 않음
   - [ ] 제거 후 `%APPDATA%\SpaceNote`, vault 데이터 유지
   - [ ] 설치 파일 크기 기록 (예상 90~120MB, 미검증)
