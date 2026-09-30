@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m assistant.app
    exit /b 0
)
echo [Xuexitong] .venv not found. Setup:
echo   python -m venv .venv
echo   .venv\Scripts\pip install -r requirements.txt
pause
