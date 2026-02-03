# 터미널 한글 인코딩 설정 (Windows)

Git 로그·파일명에서 한글이 깨질 때 아래 설정을 적용하세요.

## 1. Git 전역 설정 (한 번만)

이미 적용되어 있습니다. 다른 PC에서도 사용하려면:

```powershell
git config --global i18n.commitEncoding utf-8
git config --global i18n.logOutputEncoding utf-8
git config --global core.quotepath false
```

- **i18n.commitEncoding** : 커밋 메시지를 UTF-8로 저장
- **i18n.logOutputEncoding** : `git log` 출력을 UTF-8로 해석
- **core.quotepath false** : 한글 파일명을 `\xxx` 형태가 아닌 원문으로 표시

## 2. PowerShell 세션마다 (터미널 열 때)

PowerShell을 연 뒤 **한 번** 실행:

```powershell
chcp 65001
$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

- **chcp 65001** : 콘솔 코드페이지를 UTF-8로 변경
- **$OutputEncoding / OutputEncoding** : 파이프·외부 프로그램에 넘기는 문자열을 UTF-8로

## 3. PowerShell 자동 적용 (선택)

매번 치지 않으려면 프로필에 넣기:

```powershell
# 프로필 경로 확인
$PROFILE

# 프로필이 없으면 생성 후 아래 한 줄 추가
Set-Content -Path $PROFILE -Value 'chcp 65001 | Out-Null; $OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8' -Encoding UTF8
```

이후 새 PowerShell을 열면 자동으로 UTF-8이 적용됩니다.

## 4. 한글 커밋 메시지가 깨졌을 때

이미 만든 커밋 메시지를 수정하려면:

1. **UTF-8 터미널에서** (위 2번 적용 후) 수정:
   ```powershell
   chcp 65001
   git commit --amend -m "Initial commit: MyInfo (금융거래 통합정보) 프로젝트"
   ```

2. **또는 메시지를 파일로** (항상 UTF-8로 저장):
   ```powershell
   # msg.txt 내용: Initial commit: MyInfo (금융거래 통합정보) 프로젝트
   git commit --amend -F msg.txt
   ```

## 5. Windows Terminal / Cursor 터미널

- **Windows Terminal**: 설정 → 기본값 → "코드 페이지" 없음이면 UTF-8 사용.
- **Cursor 통합 터미널**: 위 2번을 매번 실행하거나, 3번처럼 `$PROFILE`에 넣어 두면 됩니다.

이 설정 후 `git log`, `git status` 등에서 한글이 정상적으로 보입니다.
