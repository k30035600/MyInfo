# GitHub "내 정보"에 MyInfo 프로젝트가 안 보일 때

## 원인

- **k30035600/MyInfo** 저장소는 **계정 k30035600** 소유입니다.
- 지금 **k30035600-bit** (또는 다른 계정)으로 로그인해 있으면, "내 정보"(프로필)에는 **내 계정이 만든 저장소**만 나옵니다.
- 그래서 k30035600/MyInfo는 **다른 사람(k30035600) 계정**이라 "내 프로젝트" 목록에 안 보일 수 있습니다.

## 해결 방법

### 방법 1: 사용자명을 k30035600 으로 변경 (권장)

- GitHub **Settings** → **Account** → **Change username** → `k30035600` 입력 후 변경
- 그러면 **k30035600/MyInfo**가 **내 계정** 소유가 되어, "내 정보" → Repositories에 **MyInfo**가 표시됩니다.

### 방법 2: 내 계정(k30035600-bit)에도 MyInfo 저장소 만들기

1. **k30035600-bit** 로그인 상태에서  
   https://github.com/new → **Repository name:** `MyInfo` → **Create repository** (README 추가 안 함)
2. 로컬에서 아래 실행 (한 번만):

```powershell
cd "d:\OneDrive\Cursor_AI_Project\MyInfo"
git remote add myinfo-bit https://github.com/k30035600-bit/MyInfo.git
git push myinfo-bit main
```

- 그러면 **k30035600-bit/MyInfo** 가 생기고, "내 정보" → Repositories에 **MyInfo**가 보입니다.
- **k30035600/MyInfo** 와 **k30035600-bit/MyInfo** 두 곳에 같은 코드가 있게 됩니다.

### 방법 3: 그냥 k30035600/MyInfo 로 쓰기

- "내 정보" 목록에 안 나와도, **https://github.com/k30035600/MyInfo** 주소로 들어가면 전체 소스(app.py, MyBank, MyCard, readme 등)가 다 있습니다.
- k30035600 이 본인 계정이면, 사용자명만 k30035600 으로 바꾸면(방법 1) 프로필에 표시됩니다.

---

## 요약

| 상황 | 할 일 |
|------|--------|
| k30035600 이 내 계정이다 | **Settings → Account → Change username** 으로 k30035600 으로 변경 → "내 정보"에 MyInfo 표시됨 |
| k30035600-bit 가 내 계정이다 | **New repository** 로 k30035600-bit/MyInfo 생성 후, 위처럼 `git remote add myinfo-bit` + `git push myinfo-bit main` |
| 목록은 상관없고 주소만 알면 된다 | https://github.com/k30035600/MyInfo 로 접속해 사용 |
