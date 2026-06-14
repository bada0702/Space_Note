@echo off
chcp 65001 > nul
echo [SpaceNote] Starting...

:: Backend
start "SpaceNote Backend" cmd /k "cd /d "%~dp0backend" && call venv\Scripts\activate && uvicorn main:app --port 8001 --reload"

:: Wait for backend
ping 127.0.0.1 -n 4 > nul

:: Frontend
start "SpaceNote Frontend" cmd /k "cd /d "%~dp0" && npm run dev"

echo.
echo [SpaceNote] Running
echo   Backend  : http://localhost:8001
echo   Frontend : http://localhost:1420
echo.
