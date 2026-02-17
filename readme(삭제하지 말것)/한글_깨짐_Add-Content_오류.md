# 한글 깨짐 / Add-Content -Encoding 오류

## 지금 바로 (3단계)

**New-Item / Add-Content 오류가 나오면** Cursor가 `%TEMP%`(한글 사용자명 경로)에 임시 스크립트를 만들다가 경로가 깨져서 발생합니다. 아래만 하면 대부분 해결됩니다.

| 순서 | 할 일 |
|------|--------|
| **1** | **Cursor를 모두 종료**합니다. |
| **2** | **Windows 탐색기**에서 프로젝트 폴더(MyInfo)로 이동한 뒤, **주소창에 `powershell` 입력 후 Enter** 해서 PowerShell을 엽니다. |
| **3** | 아래 명령 **한 줄**을 붙여넣고 Enter 합니다. (Cursor가 TEMP=C:\Temp 로 설정된 채로 **C:\CursorWorkspace** 를 엽니다.) |
| | `.\readme(삭제하지 말것)\start-cursor-no-hangul.ps1` |
| **4** | Cursor가 **C:\CursorWorkspace** 로 열리면, **파일 → 폴더 열기 → C:\CursorWorkspace** 가 맞는지 확인합니다. (처음에 **C:\CursorWorkspace\MyInfo** 가 없다면, 같은 PowerShell에서 `.\readme(삭제하지 말것)\create-workspace-junction.ps1` 를 먼저 실행한 뒤 다시 3번 실행.) |

이후에는 **항상** `start-cursor-no-hangul.ps1` 로 Cursor를 켜고, **C:\CursorWorkspace** 만 열어서 작업하면 한글 깨짐·New-Item·Add-Content 오류가 거의 나지 않습니다.

---

## 증상

- 터미널이나 명령 출력에서 한글이 `Ű`, ``, `ŷ` 처럼 깨져 보임.
- **JSON/파일 내용**이 에디터나 터미널에서 `"": ""` 처럼 깨져 보임 (실제 파일은 UTF-8인데 CP949로 해석되는 경우).
- 에러 메시지: `Add-Content : Ű  ̸ 'Encoding'() ġϴ ...`  
  (의미: `Add-Content`에서 `-Encoding` 매개변수를 찾을 수 없음)
- `New-Item :ο ߸ ڰ ֽϴ` (경로에 잘못된 문자가 포함됨 — 한글 경로가 깨진 경우)

## 원인

- **Add-Content 오류**: Cursor가 명령 출력을 저장할 때 사용하는 내부 스크립트에서  
  `Add-Content -Encoding UTF8`을 쓰는데, 사용 중인 PowerShell 버전/환경에서  
  `-Encoding` 매개변수가 지원되지 않거나 인식되지 않을 때 발생합니다.  
  **명령 자체는 정상 실행된 경우가 많습니다** (exit code 0).
- **한글 깨짐**: 터미널 또는 스크립트의 코드페이지/인코딩이 UTF-8이 아닐 때 발생합니다.

## 계속 한글 깨짐일 때 — 우선 순서

1. **Cursor를 한글 경로 없이 실행**  
   - **지금 Cursor를 모두 닫은 뒤**, 아래 스크립트로 다시 실행합니다.  
   - **실행**: `.\readme(삭제하지 말것)\start-cursor-no-hangul.ps1`  
   - 이 스크립트는 TEMP/TMP를 `C:\Temp`로 바꾼 뒤 Cursor를 **C:\CursorWorkspace** 로 엽니다.  
   - 프로젝트가 OneDrive 등 다른 경로에 있으면, 먼저 **C:\CursorWorkspace** 에 연결(정션/바로가기)해 두고, Cursor에서는 **파일 → 폴더 열기 → C:\CursorWorkspace** 만 사용합니다.

2. **기본 터미널을 PowerShell 7로**  
   - Cursor **설정 → Terminal → Default Profile: Windows** 에서 **PowerShell 7** 선택.  
   - PowerShell 7이 없으면 [PowerShell 7 설치](https://learn.microsoft.com/ko-kr/powershell/scripting/install/installing-powershell-on-windows) 후 선택.

3. **JSON/텍스트 파일이 깨져 보일 때**  
   - Cursor 하단 상태 표시줄 **인코딩**(예: UTF-8) 클릭 → **Reopen with Encoding** → **UTF-8** 선택.  
   - 파일이 UTF-8이면 한글이 정상 표시됩니다.

---

## 대응 방법 (상세)

### 1. 터미널을 UTF-8로 사용 (권장)

- Cursor **터미널 기본 프로필**을 **PowerShell 7 (UTF-8)** 로 두고 사용합니다.  
  (이미 `.vscode/settings.json`에 설정되어 있으면 그대로 사용)
- 새 터미널에서 한 번 실행해 두면 도움이 됩니다:
  ```powershell
  chcp 65001
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
  ```

### 2. 사용자 경로에 한글이 있을 때 (예: `C:\Users\삼아개발\`)

- Cursor 내부 스크립트가 `%TEMP%` 등 한글 경로에서 깨질 수 있습니다.
- **해결**: `start-cursor-no-hangul.ps1` 로 Cursor를 실행해, TEMP/TMP를 `C:\Temp` 같은 한글이 없는 경로로 바꾼 뒤 사용합니다.  
  - 실행:  
    `.\readme(삭제하지 말것)\start-cursor-no-hangul.ps1`

### 3. Git 한글 (커밋 메시지, 파일명)

- **최초 1회** 실행:  
  `.\readme(삭제하지 말것)\setup-git-utf8.ps1`  
  - `i18n.commitEncoding`, `i18n.logOutputEncoding` UTF-8 설정  
  - `core.quotepath false` 로 한글 파일명이 깨지지 않게 표시
- 한글 커밋 메시지는 `git commit -F 파일명` 으로 UTF-8 파일에서 읽어서 커밋하는 것을 권장합니다.

### 4. 본인 스크립트에서 Add-Content 사용 시

- **PowerShell 7**: `Add-Content -Path $path -Value $content` (기본이 UTF-8)
- **Windows PowerShell 5.1** 등에서 `-Encoding` 오류가 나면:
  - `$content | Out-File -FilePath $path -Append -Encoding utf8`
  - 또는 `Set-Content -Path $path -Value $content -Encoding UTF8`  
  (사용 중인 버전에서 지원하는 매개변수에 맞게 조정)

## 요약

| 현상 | 대응 |
|------|------|
| **계속** 터미널/출력 한글 깨짐, New-Item·Add-Content 오류 | **start-cursor-no-hangul.ps1** 로 Cursor 실행 + **C:\CursorWorkspace** 만 열기 |
| Cursor 명령 후 Add-Content 오류만 보임 | 명령은 성공한 경우 많음. 2번(한글 경로 회피) 적용 권장 |
| JSON/파일 내용이 깨져 보임 | Cursor에서 해당 파일 **Reopen with Encoding → UTF-8** |
| 터미널에서 한글 깨짐 | 1번(UTF-8 터미널), 가능하면 PowerShell 7 사용 |
| Git 커밋/로그 한글 깨짐 | 3번(setup-git-utf8.ps1, commit -F) 적용 |
