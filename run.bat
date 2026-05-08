@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] 虚拟环境不存在！
    echo 请先运行: python -m venv venv
    pause
    exit /b 1
)

echo ========================================
echo   Luoke Kingdom AI Knowledge Base
echo   Engine: Ollama + Qwen2.5
echo   Starting...
echo ========================================
echo.

:: 直接用 venv 的 Python（避免 Windows App Alias 干扰）
"%~dp0venv\Scripts\python.exe" run.py

if %errorlevel% NEQ 0 (
    echo.
    echo Program exited with code: %errorlevel%
    pause
)
