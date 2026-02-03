# GitHub 모두 삭제 후 k30035600 / MyInfo 로 다시 작성하기

## 요약

1. GitHub에서 **현재 저장소 삭제** (또는 사용 중인 저장소들 정리)
2. **사용자명을 k30035600 으로** (계정 이름 변경 또는 새 계정)
3. **새 저장소 MyInfo** 생성 (빈 저장소, README 추가 안 함)
4. **로컬에서 다시 푸시**

---

## 1단계: 현재 저장소 삭제

1. https://github.com/k30035600/MyInfo 접속
2. **Settings** → 맨 아래 **Danger zone**
3. **Delete this repository** 클릭
4. 확인란에 `k30035600/MyInfo` (또는 표시된 저장소 이름) 입력
5. **I understand the consequences, delete this repository** 실행

> 다른 저장소도 삭제하려면 각 저장소마다 위 과정 반복.

---

## 2단계: 사용자명을 k30035600 으로

**방법 A – 기존 계정 이름만 변경**

1. https://github.com/settings/admin 로그인
2. **Change username** → 새 사용자명에 `k30035600` 입력
3. **Change my username** 실행  
   → 이후 모든 곳에서 **@k30035600** 으로 표시됨

**방법 B – 새 계정으로 k30035600 사용**

- `k30035600`이 이미 사용 중이면 기존 계정에서는 이 이름을 쓸 수 없음.
- 새 GitHub 계정을 만들고 사용자명을 `k30035600`으로 설정하면 됨.
- 이전 사용자명을 쓰던 계정은 그대로 두거나, 계정 삭제는 GitHub 지원(계정 삭제) 절차를 따름.

---

## 3단계: 새 저장소 MyInfo 만들기

1. https://github.com/new 접속 (k30035600 계정으로 로그인된 상태)
2. **Repository name:** `MyInfo`
3. **Public** / **Private** 선택
4. **Add a README file** 등 체크하지 말고 **Create repository** 클릭  
   (로컬에 이미 코드가 있으므로 빈 저장소로 생성)

---

## 4단계: 로컬에서 다시 푸시

프로젝트 폴더에서 PowerShell 실행:

```powershell
cd "d:\OneDrive\Cursor_AI_Project\MyInfo"

# 원격이 이미 k30035600/MyInfo 라면 그대로, 아니면 설정
git remote set-url origin https://github.com/k30035600/MyInfo.git
git remote -v

# 전체 푸시 (새 저장소라서 히스토리 그대로 올라감)
git push -u origin main
```

- **HTTPS:** 사용자명 `k30035600`, 비밀번호 대신 **Personal Access Token** 입력
- **SSH:** SSH 키가 k30035600 계정에 등록되어 있으면 `git@github.com:k30035600/MyInfo.git` 로 설정 후 푸시 가능

---

## 정리

| 단계 | 내용 |
|------|------|
| 1 | GitHub에서 기존 MyInfo(및 필요 시 다른 저장소) 삭제 |
| 2 | 사용자명을 k30035600 으로 변경 또는 새 계정 k30035600 생성 |
| 3 | k30035600 계정으로 빈 저장소 **MyInfo** 생성 |
| 4 | 로컬에서 `origin`을 `https://github.com/k30035600/MyInfo.git` 로 두고 `git push -u origin main` |

이후에는 **@k30035600** 의 **MyInfo** 프로젝트로 깨끗하게 다시 사용할 수 있습니다.
