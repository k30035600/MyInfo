# GitHub Actions: 모든 워크플로 끄는 방법

## 1. 저장소 전체 Actions 끄기 (모든 워크플로 비활성)

1. GitHub 저장소 페이지 → **Settings**
2. 왼쪽 **Actions** → **General**
3. **Actions permissions** 섹션에서
   - **"Disable actions"** 선택
4. **Save** 클릭

→ 저장소의 **모든** 워크플로가 실행되지 않습니다. (기존 워크플로 파일은 그대로 두고 실행만 막음)

---

## 2. 특정 워크플로만 끄기 (파일 삭제 또는 비활성화)

**방법 A: 워크플로 파일 삭제**

- `.github/workflows/` 폴더 안의 `.yml` 파일을 삭제한 뒤 커밋·푸시
- 예: `run-workflow.yml` 삭제 → 해당 워크플로만 사라짐

**방법 B: 워크플로 파일 이름 변경 (비활성)**

- `.github/workflows/run-workflow.yml` → `run-workflow.yml.disabled` 등으로 변경 후 푸시
- GitHub는 `.github/workflows/` 아래 `.yml` / `.yaml` 만 인식하므로, 확장자를 바꾸면 해당 워크플로만 비활성화됨

---

## 3. 실행 중인 워크플로만 취소하기

- **Actions** 탭 → 실행 목록에서 해당 run 클릭
- 오른쪽 상단 **Cancel workflow** (또는 **Cancel check suite**) 클릭

→ 이미 돌아가고 있는 run 만 취소됩니다. 워크플로 자체는 그대로 있어서 다음에 다시 실행될 수 있습니다.

---

## 요약

| 목적 | 방법 |
|------|------|
| **모든 워크플로 끄기** | **Settings** → **Actions** → **General** → **Disable actions** |
| **특정 워크플로만 끄기** | `.github/workflows/해당파일.yml` 삭제 또는 확장자 변경 후 푸시 |
| **실행 중인 것만 취소** | **Actions** 탭 → 해당 run → **Cancel workflow** |

다시 켜려면: **Settings** → **Actions** → **General** → **Allow all actions** (또는 **Allow [저장소] actions**) 선택 후 저장.
