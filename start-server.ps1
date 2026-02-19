# MyInfo Server - PowerShell (한글 깨짐 방지: UTF-8)
$ErrorActionPreference = "Stop"
chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"

Set-Location $PSScriptRoot

Write-Host "========================================"
Write-Host "MyInfo Server  (PowerShell $($PSVersionTable.PSVersion.ToString()))"
Write-Host "========================================"
Write-Host "[1/2] Checking packages..."
$ErrorActionPreference = "Continue"
$null = & py -m pip install "pandas>=1.5.0" "openpyxl>=3.0.0" "xlrd>=2.0.0" "flask>=2.0.0" "cryptography>=3.4.0" "requests>=2.25.0" "waitress>=2.1.0" "pywin32>=300" -q 2>&1
$ErrorActionPreference = "Stop"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] pip install failed. Retry or run: py -m pip install pandas openpyxl xlrd flask cryptography requests waitress pywin32" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "[2/2] Starting server..."
Write-Host ""
Write-Host "Open http://localhost:8080  /bank  /card"
Write-Host "Stop: Ctrl+C"
Write-Host "========================================"
& py app.py
Read-Host "Press Enter to exit"
