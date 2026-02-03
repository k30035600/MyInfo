# GitHub 저장소 이름 변경 / 저장소 삭제

> **GitHub 웹에서 여전히 @k30035600-bit 로 보인다면**  
> 저장소 소유자·프로필·커밋 작성자 표시는 **GitHub 계정 사용자명**입니다.  
> **Settings → Account → Change username** 에서 `k30035600` 으로 변경해야 웹 전체가 @k30035600 으로 바뀝니다. (프로젝트 파일만 수정해서는 바뀌지 않습니다.)

## 1. 사용자명 변경 (이전: k30035600-bit → 현재: k30035600)

**저장소 이름만** 바꾸는 경우 (같은 계정 내):

1. https://github.com/k30035600/MyInfo 접속
2. **Settings** (저장소 설정)
3. **General** → **Repository name** 에서 `MyInfo` 대신 원하는 이름 입력  
   (예: 그대로 두거나 `MyInfo` 유지)
4. **Rename** 클릭

**GitHub에서 @k30035600 으로 보이게 하려면** (사용자명 변경):

1. https://github.com 로그인
2. 우측 상단 **프로필 사진** 클릭 → **Settings**
3. 왼쪽 맨 아래 **Account** (계정) 클릭
4. **Change username** (사용자 이름 변경) 섹션에서
   - 새 사용자명 입력: `k30035600`
   - 안내에 따라 확인 후 **Change my username** 실행

변경 후:
- 프로필/저장소 등 모든 곳에서 **@k30035600** 으로 표시됩니다.
- 기존 저장소 URL은 `https://github.com/k30035600/저장소이름` 으로 자동 리다이렉트되는 경우가 많습니다.
- **k30035600** 이 이미 다른 사람이 쓰고 있으면 사용할 수 없습니다. 그때는 비슷한 이름(예: k30035600-kr)을 써야 합니다.

**Organization** 이름 변경:  
**Organization → Settings → General → Organization name** 에서 변경

변경 후 **로컬 원격 주소**를 아래처럼 바꿔야 합니다.

```powershell
cd "d:\OneDrive\Cursor_AI_Project\MyInfo"
git remote set-url origin https://github.com/k30035600/MyInfo.git
git remote -v
```

---

## 2. kcs30035600 저장소 삭제

1. https://github.com/kcs30035600 (또는 kcs30035600/저장소이름) 접속
2. 해당 저장소 선택 → **Settings**
3. 맨 아래 **Danger zone** → **Delete this repository**
4. 삭제 확인란에 저장소 이름(예: `kcs30035600/저장소이름`) 정확히 입력
5. **I understand the consequences, delete this repository** 클릭

> ⚠️ 삭제하면 복구할 수 없습니다. 필요하면 미리 백업(다운로드/다른 저장소로 push)하세요.

---

## 요약

| 작업 | 위치 |
|------|------|
| 저장소 이름 변경 | 저장소 → **Settings** → **General** → **Repository name** → Rename |
| 계정 사용자명 변경 | 프로필 → **Settings** → **Account** → **Change username** |
| 저장소 삭제 | 저장소 → **Settings** → **Danger zone** → **Delete this repository** |

이름 변경 후 로컬에서 `git remote set-url origin https://github.com/k30035600/MyInfo.git` 로 한 번 바꿔 주면 됩니다.
