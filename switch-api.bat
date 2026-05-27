@echo off
cd /d "%~dp0"
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python 3 not found in PATH.
    echo Install from https://python.org or run: winget install Python.Python.3
    echo.
    pause
    exit /b 1
)
python "%~dp0switch-api.py"
pause
