# -*- coding: utf-8 -*-
# Cursor 한글 깨짐 원인 제거: 한글 없는 경로 사용
#
# 1) C:\CursorWorkspace 폴더 생성
# 2) 실제 프로젝트를 C:\CursorWorkspace\MyInfo 로 연결 (정션)
# 3) C:\Temp 폴더 생성 (TEMP 환경변수용 - 한글 없음)
#
# 사용법:
#   - PowerShell에서 이 스크립트 실행 (관리자 권한 불필요)
#   - Cursor: 파일 > 폴더 열기 > C:\CursorWorkspace 선택
#   - Cursor 실행 시 TEMP 깨짐 방지: start-cursor-no-hangul.ps1 사용

$CursorWorkspace = "C:\CursorWorkspace"
$CursorTemp = "C:\Temp"

# 현재 스크립트 경로 = 실제 프로젝트 (OneDrive\Cursor\MyInfo 등)
$ActualProject = Split-Path -Parent $MyInvocation.MyCommand.Path
$JunctionTarget = Join-Path $CursorWorkspace "MyInfo"

# 1) C:\CursorWorkspace 생성
if (-not (Test-Path $CursorWorkspace)) {
    New-Item -ItemType Directory -Path $CursorWorkspace -Force | Out-Null
    Write-Host "생성: $CursorWorkspace" -ForegroundColor Green
} else {
    Write-Host "존재: $CursorWorkspace" -ForegroundColor Gray
}

# 2) C:\Temp 생성 (TEMP 한글 없음 경로)
if (-not (Test-Path $CursorTemp)) {
    New-Item -ItemType Directory -Path $CursorTemp -Force | Out-Null
    Write-Host "생성: $CursorTemp (TEMP용)" -ForegroundColor Green
} else {
    Write-Host "존재: $CursorTemp" -ForegroundColor Gray
}

# 3) 정션 연결 (C:\CursorWorkspace\MyInfo -> 실제 프로젝트)
if (Test-Path $JunctionTarget) {
    Write-Host "정션 존재: $JunctionTarget" -ForegroundColor Gray
} else {
    cmd /c mklink /J "$JunctionTarget" "$ActualProject"
    Write-Host "정션 생성: $JunctionTarget -> $ActualProject" -ForegroundColor Green
}

Write-Host ""
Write-Host "다음 단계:" -ForegroundColor Cyan
Write-Host "  1. Cursor: 파일 > 폴더 열기 > $CursorWorkspace"
Write-Host "  2. 한글 깨짐/Add-Content 오류 시: start-cursor-no-hangul.ps1 로 Cursor 실행"
Write-Host ""
