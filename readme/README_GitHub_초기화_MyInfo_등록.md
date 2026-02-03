# GitHub 초기화 후 k30035600 / MyInfo 등록

## 1. GitHub 초기화 (웹에서 진행)

**k30035600** 계정으로 로그인한 뒤:

1. **기존 MyInfo 삭제**  
   https://github.com/k30035600/MyInfo → **Settings** → 맨 아래 **Danger zone** → **Delete this repository**  
   (확인란에 `k30035600/MyInfo` 입력 후 삭제)

2. **새 MyInfo 생성**  
   https://github.com/new → **Repository name:** `MyInfo` → **Create repository**  
   (README, .gitignore 추가 안 함)

---

## 2. 로컬에서 전체 소스 푸시

프로젝트 폴더에서:

```powershell
cd "d:\OneDrive\Cursor_AI_Project\MyInfo"
git remote -v
# origin이 https://github.com/k30035600/MyInfo.git 인지 확인

git push -u origin main
```

- 사용자: **k30035600**
- 비밀번호: **Personal Access Token** 입력

---

## 요약

| 단계 | 내용 |
|------|------|
| 1 | GitHub에서 k30035600/MyInfo **삭제** |
| 2 | **New repository** 로 **MyInfo** 생성 (빈 저장소) |
| 3 | 로컬에서 `git push -u origin main` |

이후 **k30035600/MyInfo** 에 현재까지의 모든 소스가 등록됩니다.
