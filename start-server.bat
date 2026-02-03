@echo off
chcp 65001 >nul
cd /d %~dp0
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo ========================================
echo MyInfo Server
echo ========================================
echo [1/2] Checking packages...
py -m pip install "pandas>=1.5.0" "openpyxl>=3.0.0" "xlrd>=2.0.0" "flask>=2.0.0" "cryptography>=3.4.0" "requests>=2.25.0" "waitress>=2.1.0" "pywin32>=300" -q 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] pip install failed. Retry or run: py -m pip install pandas openpyxl xlrd flask cryptography requests waitress pywin32
    pause
    exit /b 1
)
echo [2/2] Starting server...
echo.
echo Open http://localhost:8080  /bank  /card
echo Stop: Ctrl+C
echo ========================================
py app.py
pause
