# Git: lock 제거 -> readme 복원 -> 스테이징(readme 삭제 제외) -> 커밋 -> 푸시
$ErrorActionPreference = "Stop"
chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Set-Location $PSScriptRoot

# 1) Lock 제거 (다른 Git 프로세스 종료 후)
$lockPath = Join-Path (git rev-parse --git-dir) "index.lock"
if (Test-Path $lockPath) {
    Remove-Item $lockPath -Force
    Write-Host "[OK] index.lock removed."
}

# 2) readme 폴더 복원 (규칙: 삭제하지 않음)
git restore "readme(삭제하지 말것)/"
Write-Host "[OK] readme folder restored."

# 3) 스테이징 (readme 삭제는 제외)
git add .gitignore MyBank/ MyCard/ MyCash/ README.md app.py category_table_io.py data_json_io.py docs/ linkage_table_io.py start-server.bat start-server.ps1 templates/ excel_io.py shared_app_utils.py
Write-Host "[OK] Staged (readme deletions excluded)."

# 4) 커밋 (한글 메시지 UTF-8 파일)
git commit -F commit_msg_utf8.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "[OK] Committed."

# 5) GitHub 푸시 (upstream 없으면 --set-upstream origin main)
$branch = git rev-parse --abbrev-ref HEAD
$upstream = git rev-parse --abbrev-ref @{u} 2>$null
if (-not $upstream) { git push --set-upstream origin $branch } else { git push }
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "[OK] Pushed to GitHub."
