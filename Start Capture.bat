@echo off
title Claude Screen + Audio Capture
cd /d "%~dp0claude_capture"

rem ---------------------------------------------------------------------------
rem  Self-bootstrapping launcher.
rem  First run: creates a virtual environment and installs dependencies.
rem  Every run after that: launches straight away.
rem ---------------------------------------------------------------------------

rem --- Find a Python interpreter (prefer the 'py' launcher, fall back to python) ---
set "PYEXE="
where py >nul 2>&1 && set "PYEXE=py"
if not defined PYEXE (
    where python >nul 2>&1 && set "PYEXE=python"
)
if not defined PYEXE (
    echo.
    echo   Python was not found on this PC.
    echo   Install Python 3.11 or newer from https://www.python.org/downloads/
    echo   ^(tick "Add python.exe to PATH" during install^), then run this again.
    echo.
    pause
    exit /b 1
)

rem --- First-time setup: create venv + install dependencies ---
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   First-time setup: creating the environment and installing dependencies.
    echo   This downloads a few hundred MB and can take several minutes.
    echo   You only have to wait through this once.
    echo.
    %PYEXE% -m venv .venv
    if errorlevel 1 (
        echo   Failed to create the virtual environment.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo   Dependency installation failed. Scroll up to see the error.
        pause
        exit /b 1
    )
    echo.
    echo   Setup complete. Starting...
    echo.
)

rem --- Optional: uncomment and set your key ONLY for the Alt+F12 (paid API) path ---
rem set ANTHROPIC_API_KEY=sk-ant-...

".venv\Scripts\python.exe" main.py

echo.
echo Capture tool exited. Press any key to close this window.
pause >nul
