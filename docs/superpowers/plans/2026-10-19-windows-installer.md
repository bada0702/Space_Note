# Windows 설치판(setup.exe) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Windows 사용자가 `SpaceNote_<ver>_x64-setup.exe`로 설치하고 `SpaceNote.exe`로 실행할 수 있게 한다.

**Architecture:** Tauri v2 셸이 실행 시 PyInstaller onedir로 묶은 FastAPI 백엔드를 `127.0.0.1:18001`에 sidecar로 띄우고(실행마다 랜덤 토큰), 창 종료 시 kill한다. 프론트는 Tauri 환경에서만 `invoke('backend_info')`로 주소·토큰을 받는다. 리눅스 웹 운영(`/api` 프록시 + `VITE_SPACENOTE_TOKEN`)은 그대로 둔다.

**Tech Stack:** Tauri 2 (Rust), tauri-plugin-dialog, PyInstaller 6, FastAPI/uvicorn, React 18 + Vite, NSIS, PowerShell

**Spec:** `docs/superpowers/specs/2026-10-19-windows-installer-design.md`

## Global Constraints

- 백엔드 바인딩: `127.0.0.1:18001` 고정. `0.0.0.0` 금지.
- sidecar env: `SPACENOTE_TOKEN`, `DB_PATH=%APPDATA%\SpaceNote\spacenote.db`, `VAULT_DIR=%USERPROFILE%\Documents\SpaceNote`, `ALLOWED_ORIGIN=http://tauri.localhost`, `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`
- 로그: `%APPDATA%\SpaceNote\backend.log` (실행할 때마다 덮어씀)
- `backend/main.py`, `backend/config.py`는 수정하지 않는다.
- 번들에 `.env`, `spacenote.db`, `venv`, `tests`, `vault*`를 포함하지 않는다.
- PyInstaller는 onedir 모드, Python 3.12.
- NSIS: `installMode: "currentUser"`, 언어 Korean·English.
- 리눅스 웹 모드 동작 불변 (`npm run dev` + `/api` 프록시).
- 커밋 메시지는 한국어 `<유형>: <요약>` 형식 + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- 별자리(constellations) 관련 미커밋 변경은 건드리지 않는다. 커밋할 때는 항상 경로를 지정한다(`git commit -- <paths>`).

## Review Focus

1. **한글 경로·한글 노트** (`C:\Users\홍길동\...`): Windows 기본 인코딩은 cp949라 깨질 수 있다. sidecar env의 `PYTHONUTF8=1`로 막는다 → Task 4에서 env 목록을 단위 테스트로 고정한다.
2. **백엔드가 늦게 뜨는 경우**(kiwi 모델 로딩, 백신 검사): 프론트가 API를 먼저 호출하면 VaultSetup의 `patchSettings`가 실패한다. 이를 막기 위해 `initBackend()`가 `/health` 200을 받을 때까지 화면을 막는다 → Task 3 수동 검증 항목.
3. **18001 포트 점유 / 앱 이중 실행**: 오류 대화상자를 띄우고 종료해야 한다. 조용히 흰 화면만 뜨면 안 된다 → Task 4에서 `port_available()` 단위 테스트로 고정한다.
4. **창 종료 후 백엔드 잔존**: 다음 실행에서 포트 충돌로 이어진다. onedir 모드는 자식 프로세스를 만들지 않으므로 `Child::kill`로 충분하다 → Windows 체크리스트 항목.
5. **웹 버전에서 만든 vault를 데스크톱에서 열 때 첨부 이미지**: 기존 노트에는 `/api/attachments/...` 상대 URL이 저장돼 있어서 데스크톱에서는 깨진다. **알려진 제약으로 README에 명시하고, 이번 범위에서 고치지 않는다.**

---

## File Structure

| 파일 | 역할 |
|---|---|
| `backend/desktop_entry.py` (신규) | PyInstaller 진입점. `main()` → `uvicorn.run(app, "127.0.0.1", 18001)` |
| `backend/tests/test_desktop_entry.py` (신규) | 진입점 인자 고정 테스트 |
| `backend/spacenote-backend.spec` (신규) | PyInstaller onedir 빌드 정의 |
| `src/api/client.ts` (수정) | `initBackend()`, 동적 `API_BASE`/토큰 |
| `src/api/aiApi.ts`, `src/api/attachmentsApi.ts` (수정) | `API_BASE` 상수 → `apiBase()` 호출 |
| `src/App.tsx` (수정) | `initBackend()` 완료 전 로딩/오류 화면 |
| `src-tauri/src/sidecar.rs` (신규) | 경로·env 계산, 포트 확인, 토큰 생성, 실행 (순수 함수는 단위 테스트) |
| `src-tauri/src/lib.rs` (수정) | setup / `backend_info` 커맨드 / Exit 시 kill |
| `src-tauri/Cargo.toml`, `tauri.conf.json`, `icons/` (수정·생성) | 의존성, NSIS·resources·아이콘 |
| `scripts/build-windows.ps1` (신규) | Windows 원클릭 빌드 |
| `README.md` (수정) | Windows 빌드·설치·검증 체크리스트 섹션 |
| `.gitignore` (수정) | `src-tauri/target/`, `build/`, `backend/.venv-build/` |

---

### Task 1: 백엔드 데스크톱 진입점

**Files:**
- Create: `backend/desktop_entry.py`
- Test: `backend/tests/test_desktop_entry.py`

**Interfaces:**
- Produces: `desktop_entry.main() -> None`, 모듈 상수 `HOST = "127.0.0.1"`, `PORT = 18001`. Task 2의 spec 파일이 이 파일을 진입 스크립트로 사용한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_main_runs_uvicorn_on_loopback_fixed_port(client, monkeypatch):
    import desktop_entry, uvicorn
    from main import app
    calls = {}
    monkeypatch.setattr(uvicorn, "run", lambda a, **kw: calls.update(app=a, **kw))
    desktop_entry.main()
    assert calls["app"] is app
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 18001
```
(`client` fixture는 env·DB를 tmp로 격리하기 위해 사용한다.)

- [ ] **Step 2: 실패 확인** — `cd backend && venv/bin/pytest tests/test_desktop_entry.py -v` → FAIL (`ModuleNotFoundError: desktop_entry`)

- [ ] **Step 3: 구현** — `main()`이 `from main import app` 후 `uvicorn.run(app, host=HOST, port=PORT)`를 호출한다. 문자열 `"main:app"`을 쓰지 않는 이유(PyInstaller)를 한국어 주석 한 줄로 남기고, `if __name__ == "__main__": main()`을 둔다. `import uvicorn`은 모듈 상단에 둔다(monkeypatch 대상).

- [ ] **Step 4: 통과 확인** — 같은 명령 → PASS. 이어서 `venv/bin/pytest -q` 전체 실행 → 기존 실패 수가 늘지 않았는지 확인한다(작업 전에 기준선을 먼저 기록).

- [ ] **Step 5: 커밋**
```bash
git add backend/desktop_entry.py backend/tests/test_desktop_entry.py
git commit -m "기능: Windows 설치판용 백엔드 진입점 추가" -- backend/desktop_entry.py backend/tests/test_desktop_entry.py
```

### Task 2: PyInstaller spec + 리눅스 스모크 빌드

**Files:**
- Create: `backend/spacenote-backend.spec`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `backend/desktop_entry.py` (Task 1)
- Produces: `build/backend/spacenote-backend/spacenote-backend(.exe)` — onedir 폴더 이름과 실행 파일 이름이 모두 `spacenote-backend`이다. Task 4의 `resources`와 Task 5 스크립트가 이 경로를 쓴다.

- [ ] **Step 1: spec 작성**
  - `Analysis(['desktop_entry.py'], pathex=['.'])`
  - `datas`: `collect_data_files('kiwipiepy_model')` + `collect_data_files('kiwipiepy')`
  - `hiddenimports`: `collect_submodules('uvicorn')` + `collect_submodules('routers')` + `collect_submodules('services')`
  - `excludes=['pytest', 'tests']`
  - `EXE(..., name='spacenote-backend', console=True)`, `COLLECT(..., name='spacenote-backend')`
  - console=True를 쓰는 이유: 창은 Rust의 `CREATE_NO_WINDOW`로 숨기고, stdout을 로그 파일로 받기 위해서다.
  - 빌드 명령은 `--distpath ../build/backend --workpath ../build/pyi-work`로 지정한다.

- [ ] **Step 2: 스크래치 venv에서 리눅스 빌드**
```bash
python3.12 -m venv $SCRATCH/venv-pyi && $SCRATCH/venv-pyi/bin/pip install -q -r backend/requirements.txt pyinstaller
cd backend && $SCRATCH/venv-pyi/bin/pyinstaller spacenote-backend.spec --noconfirm --distpath ../build/backend --workpath ../build/pyi-work
```
Expected: `build/backend/spacenote-backend/spacenote-backend` 생성

- [ ] **Step 3: 산출물 검사**
  - `find build/backend -name ".env" -o -name "spacenote.db" -o -name "venv"` → 출력이 없어야 한다.
  - `find build/backend -type d -name kiwipiepy_model` → 1건이어야 한다.

- [ ] **Step 4: 실행 스모크**
```bash
SPACENOTE_TOKEN=t DB_PATH=$SCRATCH/s.db VAULT_DIR=$SCRATCH/v ALLOWED_ORIGIN=http://tauri.localhost build/backend/spacenote-backend/spacenote-backend &
# 준비될 때까지 /health 폴링 후:
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18001/health        # 200
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18001/categories    # 401
curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer t" http://127.0.0.1:18001/categories  # 200
curl -s -D - -o /dev/null -H "Origin: http://tauri.localhost" http://127.0.0.1:18001/health | grep -i access-control-allow-origin  # http://tauri.localhost
```
로그에 `kiwipiepy` import 실패 경고가 없는지 확인한 뒤 프로세스를 종료한다. 18001은 기존 개발 서버(:8001)와 겹치지 않는다.

- [ ] **Step 5: `.gitignore`에 `src-tauri/target/`, `build/`, `backend/.venv-build/` 추가 후 커밋**
```bash
git add backend/spacenote-backend.spec .gitignore
git commit -m "설정: PyInstaller onedir 백엔드 번들 spec 추가" -- backend/spacenote-backend.spec .gitignore
```

### Task 3: 프론트엔드 백엔드 주소·토큰 동적화

**Files:**
- Modify: `src/api/client.ts`, `src/api/aiApi.ts`, `src/api/attachmentsApi.ts`, `src/App.tsx`

**Interfaces:**
- Consumes: Tauri 커맨드 `backend_info` → `{ baseUrl: string; token: string }` (Task 4가 제공)
- Produces (`client.ts`):
  - `initBackend(): Promise<void>` — 웹 모드에서는 즉시 resolve한다. Tauri 모드에서는 `invoke('backend_info')` 결과를 저장하고, `${baseUrl}/health`가 200이 될 때까지 500ms 간격으로 폴링한다(최대 20초). 시간을 넘기면 `Error('백엔드를 시작하지 못했습니다. %APPDATA%\\SpaceNote\\backend.log를 확인하세요.')`를 throw한다.
  - `apiBase(): string` — 웹 모드는 `'/api'`, Tauri 모드는 `baseUrl`
  - `authHeaders()`, `apiFetch()` — 시그니처는 그대로 두고 내부에서 현재 토큰과 `apiBase()`를 사용한다.
  - `API_BASE` export는 제거한다(호출처 7곳을 `apiBase()`로 교체).
- Tauri 감지는 `ApiSettings.tsx`와 같은 방식(`'__TAURI_INTERNALS__' in window`)을 쓰고, `invoke`는 `@tauri-apps/api/core`에서 동적 import한다.

- [ ] **Step 1: `client.ts` 구현** — 위 인터페이스대로 구현한다. 웹 모드 토큰은 기존 `import.meta.env.VITE_SPACENOTE_TOKEN`을 쓴다.
- [ ] **Step 2: 호출처 교체** — `grep -rn "API_BASE" src`가 0건이 될 때까지 `aiApi.ts`, `attachmentsApi.ts`의 `${API_BASE}`를 `${apiBase()}`로 바꾼다.
- [ ] **Step 3: `App.tsx` 게이트** — `App`에서 `initBackend()`를 한 번 호출한다. 결과에 따라 `'loading' | 'ready' | Error` 상태를 두고, 로딩 중에는 "백엔드 시작 중…", 실패하면 오류 메시지를 표시한다. `ready`가 된 뒤에만 기존 `<AppContent />`를 렌더한다. 스타일은 VaultSetup의 기존 클래스를 재사용한다.
- [ ] **Step 4: 빌드 검증** — `npm run build` → tsc 오류 0, vite 빌드 성공
- [ ] **Step 5: 웹 모드 회귀 확인** — 기존 개발 서버(:1420/:8001)가 떠 있으면 브라우저나 curl로 앱 로드 → 노트 목록 API가 호출되는지 확인한다. 서버를 재기동해야 하면 사용자에게 먼저 묻는다.
- [ ] **Step 6: 커밋**
```bash
git commit -m "기능: Tauri 실행 시 백엔드 주소·토큰을 런타임에 받도록 변경" -- src/api/client.ts src/api/aiApi.ts src/api/attachmentsApi.ts src/App.tsx
```
주의: `src/App.tsx`에 별자리 관련 미커밋 변경이 섞여 있다. **이 파일은 `git add -p`로 내 hunk만 골라 담을 수 없으므로(대화형 금지), 커밋 직전에 사용자에게 처리 방법을 확인한다.**

### Task 4: Tauri sidecar 수명주기 + 설치 파일 설정

**Files:**
- Create: `src-tauri/src/sidecar.rs`, `src-tauri/icons/source.svg`, `src-tauri/icons/*` (생성물)
- Modify: `src-tauri/src/lib.rs`, `src-tauri/Cargo.toml`, `src-tauri/tauri.conf.json`

**Interfaces:**
- Consumes: Task 2 산출물 경로 `build/backend/spacenote-backend/`
- Produces: 커맨드 `backend_info() -> BackendInfo { base_url, token }` (serde `rename_all = "camelCase"` → JS에서는 `{ baseUrl, token }`)
- `sidecar.rs` 공개 함수:
  - `pub const PORT: u16 = 18001;`
  - `pub fn port_available(port: u16) -> bool` — `TcpListener::bind(("127.0.0.1", port)).is_ok()`
  - `pub fn new_token() -> String` — `getrandom` 32바이트를 hex로 바꿔 64자를 만든다.
  - `pub fn backend_env(token: &str, data_dir: &Path, vault_dir: &Path) -> Vec<(String, String)>` — Global Constraints의 env 6개를 반환한다.
  - `pub fn spawn(exe: &Path, env: &[(String, String)], log: &Path) -> std::io::Result<Child>` — stdout/stderr를 로그 파일로 보낸다. `#[cfg(windows)]`에서 `CommandExt::creation_flags(0x08000000)`(CREATE_NO_WINDOW)를 설정한다.

- [ ] **Step 1: 실패하는 Rust 단위 테스트 작성 (`sidecar.rs` 하단 `#[cfg(test)]`)**
```rust
#[test] fn token_is_64_hex_and_unique() {
    let (a, b) = (new_token(), new_token());
    assert_eq!(a.len(), 64); assert!(a.chars().all(|c| c.is_ascii_hexdigit())); assert_ne!(a, b);
}
#[test] fn env_contains_required_keys() {
    let env = backend_env("tok", Path::new("D"), Path::new("V"));
    let get = |k: &str| env.iter().find(|(x, _)| x == k).map(|(_, v)| v.clone());
    assert_eq!(get("SPACENOTE_TOKEN").as_deref(), Some("tok"));
    assert_eq!(get("DB_PATH"), Some(Path::new("D").join("spacenote.db").to_string_lossy().into()));
    assert_eq!(get("VAULT_DIR").as_deref(), Some("V"));
    assert_eq!(get("ALLOWED_ORIGIN").as_deref(), Some("http://tauri.localhost"));
    assert_eq!(get("PYTHONUTF8").as_deref(), Some("1"));
    assert_eq!(get("PYTHONIOENCODING").as_deref(), Some("utf-8"));
}
#[test] fn port_in_use_is_reported() {
    let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    assert!(!port_available(l.local_addr().unwrap().port()));
}
```

- [ ] **Step 2: `Cargo.toml`에 `getrandom = "0.2"` 추가, `sidecar.rs` 구현**

- [ ] **Step 3: `lib.rs` 연결**
  - `State`: `struct Backend { info: BackendInfo, child: Mutex<Option<Child>> }`
  - `setup`에서 순서대로:
    1. `data_dir = app.path().data_dir()?.join("SpaceNote")` 생성
    2. `vault = app.path().document_dir()?.join("SpaceNote")`
    3. `port_available(PORT)`가 false면 `app.dialog().message("포트 18001이 이미 사용 중입니다. SpaceNote가 이미 실행 중인지 확인하세요.").kind(MessageDialogKind::Error).blocking_show()` 후 `app.handle().exit(1)`
    4. `exe = app.path().resource_dir()?.join("spacenote-backend").join(if cfg!(windows) {"spacenote-backend.exe"} else {"spacenote-backend"})`
    5. `spawn`이 실패하면 경로를 포함한 오류 대화상자를 띄우고 종료한다.
    6. `app.manage(Backend { .. })`
  - `invoke_handler(generate_handler![backend_info])`
  - `.build(generate_context!())?.run(|app, e| if let RunEvent::Exit = e { take child → kill() })`

- [ ] **Step 4: `tauri.conf.json`**
  - `bundle.targets: ["nsis"]`
  - `bundle.resources: { "../build/backend/spacenote-backend/": "spacenote-backend/" }`
  - `bundle.windows.nsis: { "installMode": "currentUser", "languages": ["Korean", "English"], "displayLanguageSelector": false }`
  - `bundle.icon`: 생성된 `icons/32x32.png`, `icons/128x128.png`, `icons/128x128@2x.png`, `icons/icon.ico`
  - `security.csp`는 `null`로 유지한다(변경하지 않음).

- [ ] **Step 5: 아이콘 생성** — `src-tauri/icons/source.svg`(1024×1024 짙은 남색 배경 + 흰 별 단색)를 작성하고 `npx tauri icon src-tauri/icons/source.svg`를 실행한다. `icons/icon.ico`가 생성됐는지 확인한다. (spec의 `source.png` 대신 SVG를 원본으로 쓴다. 나중에 교체할 때도 같은 명령을 실행하면 된다.)

- [ ] **Step 6: 검증**
  - 이 서버에는 `cargo`가 없다. **rustup 설치(약 1GB) 여부를 사용자에게 확인한다.** 승인하면 다음을 실행한다.
    - `cargo test --manifest-path src-tauri/Cargo.toml --lib sidecar` → 3 PASS (리눅스 빌드에 webkit2gtk-dev가 없으면 실패할 수 있다. 그 경우 `sidecar.rs`만 임시 크레이트로 복사해 테스트한다.)
    - `rustup target add x86_64-pc-windows-msvc && cargo check --manifest-path src-tauri/Cargo.toml --target x86_64-pc-windows-msvc` → 성공
  - 거절하면 Rust 검증은 Windows 빌드(Task 5)로 넘기고, 보고할 때 "Rust 코드 미검증"으로 명시한다.

- [ ] **Step 7: 커밋**
```bash
git commit -m "기능: Tauri에서 백엔드 sidecar 실행·종료 및 NSIS 설치 설정" -- src-tauri/
```

### Task 5: Windows 빌드 스크립트 + README

**Files:**
- Create: `scripts/build-windows.ps1`
- Modify: `README.md`

**Interfaces:**
- Consumes: `backend/spacenote-backend.spec`(Task 2), `src-tauri` 설정(Task 4)
- Produces: `src-tauri\target\release\bundle\nsis\SpaceNote_<ver>_x64-setup.exe`

- [ ] **Step 1: 스크립트 작성** — 상단에 한국어 주석(목적, 사용법 `powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1`, 필요한 사전 설치)을 단다. `$ErrorActionPreference = 'Stop'`을 설정하고, 각 외부 명령 뒤에 `$LASTEXITCODE`를 검사한다. 단계는 spec의 1~6을 그대로 따른다.
  - 사전 점검: `py -3.12 --version`, `node --version`, `cargo --version`
  - venv 위치: `backend\.venv-build`
  - PyInstaller 인자: Task 2와 동일 (`--distpath ..\build\backend --workpath ..\build\pyi-work --noconfirm`)
  - 산출물 검사: `.env`나 `spacenote.db`가 있으면 `throw`
  - 마지막에 setup.exe 경로와 크기(MB)를 출력한다.
- [ ] **Step 2: README 섹션 "Windows 설치판"** — 빌드 PC 사전 설치(Python 3.12, Node 20, Rust, VS 2022 Build Tools C++), 빌드 명령, 산출물 위치, 데이터 위치 표, SmartScreen 안내("추가 정보 → 실행"), 알려진 제약(Review Focus 5번, WebView2 부트스트래퍼는 인터넷 필요), spec 5-3의 Windows 체크리스트를 복사해 넣는다.
- [ ] **Step 3: 검증** — 이 서버에 `pwsh`가 없으므로 실행 검증은 불가하다. 스크립트를 눈으로 검토하고 "미검증"으로 보고한다.
- [ ] **Step 4: 커밋**
```bash
git add scripts/build-windows.ps1
git commit -m "문서: Windows 설치판 빌드 스크립트와 안내 추가" -- scripts/build-windows.ps1 README.md
```

### 최종: Windows 실기기 검증 (사용자 수행)

README 체크리스트대로 Windows PC에서 `build-windows.ps1` 실행 → 설치 → 체크리스트 7개 항목을 확인한다. 실패한 항목과 `backend.log`를 공유받으면 수정한다.
