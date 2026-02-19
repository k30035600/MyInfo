# Cursor를 TEMP/TMP 한글 없음 경로로 실행 (한글 깨짐, Add-Content -Encoding 오류 방지)
#
# 사용자 프로필에 한글이 있으면 (예: C:\Users\삼아개발\) %TEMP% 경로가
# Cursor 임시 스크립트에서 깨져 오류가 납니다. TEMP를 C:\Temp로 설정 후 Cursor를 실행합니다.
#
# 실행: .\readme(삭제하지 말것)\start-cursor-no-hangul.ps1

$CursorTemp = "C:\Temp"
$CursorWorkspace = "C:\CursorWorkspace"

# C:\Temp 생성
if (-not (Test-Path $CursorTemp)) {
    New-Item -ItemType Directory -Path $CursorTemp -Force | Out-Null
}

# Cursor 실행 파일 찾기
$cursorPaths = @(
    "$env:LOCALAPPDATA\Programs\cursor\Cursor.exe",
    "$env:ProgramFiles\Cursor\Cursor.exe",
    "$env:ProgramFiles(x86)\Cursor\Cursor.exe"
)
$cursorExe = $null
foreach ($p in $cursorPaths) {
    if (Test-Path $p) {
        $cursorExe = $p
        break
    }
}
if (-not $cursorExe) {
    Write-Host "Cursor.exe 를 찾을 수 없습니다. 경로를 확인하세요." -ForegroundColor Red
    exit 1
}

# TEMP/TMP 를 한글 없는 경로로 설정 후 Cursor 실행
$env:TEMP = $CursorTemp
$env:TMP = $CursorTemp
Start-Process -FilePath $cursorExe -ArgumentList $CursorWorkspace
