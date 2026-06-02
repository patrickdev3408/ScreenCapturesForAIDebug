@echo off
title Claude Screen + Audio Capture
cd /d "%~dp0claude_capture"

rem Optional: uncomment and set your key only if you want the Alt+F12 (paid API) path.
rem set ANTHROPIC_API_KEY=sk-ant-...

if not exist ".venv\Scripts\python.exe" (
    echo Could not find the virtual environment at claude_capture\.venv
    echo Run setup first:  py -m venv .venv  ^&^&  .venv\Scripts\python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py

echo.
echo Capture tool exited. Press any key to close this window.
pause >nul
