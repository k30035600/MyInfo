# GitHub 프로젝트 2개 삭제 후 다시 푸시하기

## 1. GitHub에서 저장소 2개 삭제

**각 저장소마다** 아래 순서로 진행:

1. 해당 저장소 페이지 접속  
   예: https://github.com/k30035600-bit/저장소이름
2. **Settings** (저장소 설정)
3. 맨 아래 **Danger zone** → **Delete this repository**
4. 확인란에 **저장소 전체 이름** 입력  
   예: `k30035600-bit/MyInfo`
5. **I understand the consequences, delete this repository** 클릭

→ 두 번째 저장소도 같은 방법으로 삭제.

---

## 2. 푸시할 대상 정하기

**A) k30035600/MyInfo 가 이미 있는 경우**  
- 그대로 `origin`을 `https://github.com/k30035600/MyInfo.git` 로 두고 푸시하면 됨.

**B) k30035600/MyInfo 도 새로 만들 경우**  
- https://github.com/new → Repository name: `MyInfo` → **Create repository** (README 추가 안 함)  
- 로컬 원격이 `https://github.com/k30035600/MyInfo.git` 인지 확인 후 푸시.

---

## 3. 로컬에서 푸시

```powershell
cd "d:\OneDrive\Cursor_AI_Project\MyInfo"
git remote -v
# origin이 https://github.com/k30035600/MyInfo.git 인지 확인

git push -u origin main
```

- **A)** k30035600/MyInfo 가 이미 있으면 → 기존 원격에 그대로 푸시됨.
- **B)** 방금 빈 MyInfo 를 만들었으면 → 로컬 히스토리가 그대로 올라감.

---

## 요약

| 단계 | 할 일 |
|------|--------|
| 1 | GitHub에서 @k30035600-bit 의 저장소 2개 각각 **Settings → Danger zone → Delete** |
| 2 | 푸시할 곳: **k30035600/MyInfo** (이미 있으면 그대로, 없으면 New repository 로 생성) |
| 3 | 로컬에서 `git push -u origin main` |

저장소 삭제는 **GitHub 웹에서만** 가능합니다. 삭제 후 푸시는 위 3단계대로 하시면 됩니다.
