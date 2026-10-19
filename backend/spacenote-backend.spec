# -*- mode: python ; coding: utf-8 -*-
# SpaceNote 백엔드 PyInstaller 빌드 정의 (onedir).
# 실행: cd backend && pyinstaller spacenote-backend.spec --noconfirm --distpath ../build/backend --workpath ../build/pyi-work
# .env, spacenote.db, venv, tests, vault*는 포함하지 않는다 (datas에 넣지 않음).
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

a = Analysis(
    ['desktop_entry.py'],
    pathex=['.'],
    datas=collect_data_files('kiwipiepy_model') + collect_data_files('kiwipiepy'),
    # routers/services는 main.py에서 정적 import되지만, uvicorn은 문자열로 동적 import하는 모듈이 많다
    # kiwipiepy_model은 kiwipiepy 내부에서 동적 import되어 명시하지 않으면 .py가 빠진다
    hiddenimports=['kiwipiepy_model'] + collect_submodules('uvicorn') + collect_submodules('routers') + collect_submodules('services'),
    excludes=['pytest', 'tests'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    # frozen 앱은 PYTHONUTF8 등 환경변수를 무시하므로 UTF-8 모드를 부트로더 옵션으로 켠다
    # (Windows 기본 cp949 대신 UTF-8 — 한글·이모지 로그/파일 I/O 깨짐 방지)
    [('X utf8', None, 'OPTION')],
    exclude_binaries=True,
    name='spacenote-backend',
    # 콘솔 창은 Tauri가 CREATE_NO_WINDOW로 숨기고, stdout은 backend.log로 받는다
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, name='spacenote-backend')
