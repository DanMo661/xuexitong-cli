@echo off
rem Launch the Chaoxing schedule floating widget (no console window)
cd /d "%~dp0"
where pythonw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw.exe -m chaoxing_mcp.widget
    exit /b
)
if exist "D:\Python\pythonw.exe" (
    start "" "D:\Python\pythonw.exe" -m chaoxing_mcp.widget
    exit /b
)
echo pythonw not found. Please install Python or edit this script.
pause
