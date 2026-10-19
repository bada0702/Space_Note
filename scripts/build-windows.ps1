# SpaceNote Windows 설치 파일(setup.exe) 빌드 스크립트
#
# 목적  : 백엔드를 PyInstaller로 묶고 Tauri NSIS 설치 파일을 만든다.
# 사용법: 저장소 루트에서
#         powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1
# 필요  : (1회 설치) Python 3.12, Node 20, Rust(rustup), Visual Studio 2022 Build Tools(C++ 워크로드)
#         관리자 권한 불필요
# 결과  : src-tauri\target\release\bundle\nsis\SpaceNote_<버전>_x64-setup.exe

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Invoke-Step([string]$Name, [scriptblock]$Block) {
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Block
    if ($LASTEXITCODE -ne 0) { throw "$Name 실패 (exit $LASTEXITCODE)" }
}

# 1. 사전 점검
foreach ($cmd in @(
    @{ Exe = 'py'; Args = @('-3.12', '--version'); Hint = 'Python 3.12: https://www.python.org/downloads/' },
    @{ Exe = 'node'; Args = @('--version'); Hint = 'Node 20: https://nodejs.org/' },
    @{ Exe = 'cargo'; Args = @('--version'); Hint = 'Rust: https://rustup.rs/ (+ VS 2022 Build Tools C++)' }
)) {
    if (-not (Get-Command $cmd.Exe -ErrorAction SilentlyContinue)) { throw "$($cmd.Exe) 없음 → $($cmd.Hint)" }
    & $cmd.Exe @($cmd.Args)
    if ($LASTEXITCODE -ne 0) { throw "$($cmd.Exe) 확인 실패 → $($cmd.Hint)" }
}

# 2. 백엔드 빌드용 venv
$Venv = Join-Path $Root 'backend\.venv-build'
$Py = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path $Py)) { Invoke-Step 'venv 생성' { py -3.12 -m venv $Venv } }
Invoke-Step '백엔드 의존성 설치' { & $Py -m pip install -q -r backend\requirements.txt pyinstaller }

# 3. PyInstaller (onedir)
Push-Location backend
try {
    Invoke-Step 'PyInstaller 빌드' {
        & $Py -m PyInstaller spacenote-backend.spec --noconfirm --distpath ..\build\backend --workpath ..\build\pyi-work
    }
} finally { Pop-Location }

# 4. 산출물 검사: 비밀값·개인 데이터가 번들에 들어가면 중단
$Bundle = Join-Path $Root 'build\backend\spacenote-backend'
if (-not (Test-Path (Join-Path $Bundle 'spacenote-backend.exe'))) { throw "백엔드 exe 없음: $Bundle" }
$Leak = Get-ChildItem $Bundle -Recurse -Force -Include '.env', 'spacenote.db'
if ($Leak) { throw "번들에 포함되면 안 되는 파일: $($Leak.FullName -join ', ')" }

# 5. 프론트 + Tauri 설치 파일
#    beforeBuildCommand가 `vite build --mode desktop`으로 빌드 → .env.desktop이 .env.local의 서버 토큰을 비운다
Invoke-Step 'npm ci' { npm ci }
Invoke-Step 'tauri build' { npx tauri build }

# 서버 토큰이 번들(dist)에 남았는지 재확인 — 남았으면 설치 파일을 배포하면 안 된다
$EnvLocal = Join-Path $Root '.env.local'
if (Test-Path $EnvLocal) {
    $Line = Select-String -Path $EnvLocal -Pattern '^VITE_SPACENOTE_TOKEN=(.+)$' | Select-Object -First 1
    if ($Line) {
        $Token = $Line.Matches[0].Groups[1].Value.Trim()
        if (Select-String -Path (Join-Path $Root 'dist\assets\*') -SimpleMatch $Token -Quiet) {
            throw '.env.local의 VITE_SPACENOTE_TOKEN이 dist 번들에 포함됨 — 이 설치 파일은 배포 금지'
        }
    }
}

# 6. 결과
$Setup = Get-ChildItem (Join-Path $Root 'src-tauri\target\release\bundle\nsis') -Filter '*-setup.exe' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host ''
Write-Host "완료: $($Setup.FullName) ($([math]::Round($Setup.Length / 1MB, 1)) MB)" -ForegroundColor Green
