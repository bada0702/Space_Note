@echo off
taskkill /f /im uvicorn.exe 2>nul
taskkill /f /fi "WINDOWTITLE eq SpaceNote*" 2>nul
echo SpaceNote 종료 완료
