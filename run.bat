@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo Error: virtual environment not found
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
echo ========================================
echo   Luoke Kingdom AI Knowledge Base
echo   Engine: Ollama + Qwen2.5
echo   Starting...
echo ========================================
echo.
python run.py
if %errorlevel% NEQ 0 (
    echo.
    echo Program exited with code: %errorlevel%
    pause
)
call venv\Scripts\deactivate.bat
