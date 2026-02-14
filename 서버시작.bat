@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo MyInfo Server
echo ========================================
echo Open http://localhost:8080  /bank  /card  /cash
echo Stop: Ctrl+C
echo ========================================
py app.py
pause
