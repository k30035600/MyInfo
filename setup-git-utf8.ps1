# Git / GitHub / 배포 시 한글 깨짐 방지 - UTF-8 설정 (최초 1회 실행)
# PowerShell에서: .\setup-git-utf8.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Git UTF-8 인코딩 설정 중..." -ForegroundColor Cyan

git config --global i18n.commitEncoding utf-8
git config --global i18n.logOutputEncoding utf-8
git config core.quotepath false

Write-Host "완료. 한글 커밋 메시지는 파일로 저장 후 git commit -F 파일명 사용 권장." -ForegroundColor Green
