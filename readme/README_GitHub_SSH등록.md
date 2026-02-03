# GitHub SSH 등록 방법

## 1. SSH 키가 있는지 확인

PowerShell 또는 터미널에서:

```powershell
# 기본 경로에 키가 있는지 확인
Test-Path ~/.ssh/id_ed25519.pub
# 또는
Test-Path ~/.ssh/id_rsa.pub
```

- **True** → 2단계로 이동 (기존 공개키를 GitHub에 등록)
- **False** → 아래 1-2에서 새 키 생성

---

## 2. SSH 키 생성 (없는 경우)

```powershell
# 이메일을 본인 GitHub 이메일로 바꾸기
ssh-keygen -t ed25519 -C "k30035600@gmail.com" -f "$env:USERPROFILE\.ssh\id_ed25519" -N '""'
```

- **-N '""'** : 비밀번호 없이 생성 (입력 없이 엔터만 해도 됨)
- 비밀번호(passphrase)를 넣고 싶으면 `-N '""'` 를 빼고 실행 후 입력

**RSA로 만들고 싶다면:**

```powershell
ssh-keygen -t rsa -b 4096 -C "k30035600@gmail.com" -f "$env:USERPROFILE\.ssh\id_rsa" -N '""'
```

---

## 3. 공개키(Public Key) 복사

**Windows PowerShell:**

```powershell
Get-Content ~/.ssh/id_ed25519.pub | Set-Clipboard
```

- 클립보드에 복사됨 → GitHub 붙여넣기 시 **Ctrl+V** 로 사용

**또는 파일 내용 직접 보기:**

```powershell
Get-Content ~/.ssh/id_ed25519.pub
```

- `ssh-ed25519 AAAAC3...` 로 시작하는 한 줄 전체를 복사

---

## 4. GitHub에 SSH 키 등록

1. **https://github.com/settings/keys** 접속 (로그인된 상태)
2. **New SSH key** 클릭
3. **Title:** 구분용 이름 입력 (예: `내 PC`, `Cursor`)
4. **Key type:** Authentication Key
5. **Key:** 3단계에서 복사한 공개키 전체 붙여넣기 (한 줄)
6. **Add SSH key** 클릭

---

## 5. 연결 확인

```powershell
ssh -T git@github.com
```

- 처음이면 `Are you sure you want to continue connecting?` → **yes** 입력
- 성공 시: `Hi k30035600! You've successfully authenticated...` 와 비슷한 메시지 출력

---

## 6. 저장소 원격을 SSH로 변경

```powershell
cd "d:\OneDrive\Cursor_AI_Project\MyInfo"

# MyBankCard를 SSH로
git remote set-url mybankcard git@github.com:k30035600/MyBankCard.git

# MyInfo를 SSH로
git remote set-url origin git@github.com:k30035600/MyInfo.git

git remote -v
```

이후 `git push mybankcard main`, `git push origin main` 시 비밀번호 없이 푸시 가능합니다.

---

## 요약

| 단계 | 내용 |
|------|------|
| 1 | `~/.ssh/id_ed25519.pub` 또는 `id_rsa.pub` 존재 여부 확인 |
| 2 | 없으면 `ssh-keygen -t ed25519 -C "이메일"` 로 생성 |
| 3 | `Get-Content ~/.ssh/id_ed25519.pub \| Set-Clipboard` 로 공개키 복사 |
| 4 | GitHub → Settings → SSH and GPG keys → **New SSH key** → 붙여넣기 |
| 5 | `ssh -T git@github.com` 로 로그인 확인 |
| 6 | `git remote set-url ... git@github.com:...` 로 원격을 SSH로 변경 |

**GitHub SSH 키 설정:** https://github.com/settings/keys
