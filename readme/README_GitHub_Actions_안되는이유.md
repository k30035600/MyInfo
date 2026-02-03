# GitHub Actions가 안 되는 이유

## 1. workflow_dispatch는 "한 번도 실행된 적 없으면" 비활성

- **workflow_dispatch** 트리거는 **워크플로우가 최소 1번 실행된 뒤** 수동 실행이 활성화됩니다.
- "This workflow has no runs yet" 상태면 **Run workflow** 버튼이 동작하지 않거나 목록에 안 나올 수 있습니다.

**해결:**  
- **main** 브랜치에 푸시하면 워크플로우가 1회 실행되도록 `push: branches: [main]` 를 추가해 두었습니다.  
- 한 번 푸시 후 **Actions** 탭에서 **Run workflow** 로 수동 실행이 가능해집니다.

---

## 2. 저장소에서 Actions가 꺼져 있음

- **Settings** → **Actions** → **General**  
- **"Disable actions"** 로 되어 있으면 모든 워크플로우가 실행되지 않습니다.

**해결:**  
- **Allow all actions** 또는 **Allow [해당 저장소] actions** 로 변경

---

## 3. Run workflow를 누르지 않음

- `workflow_dispatch` 는 **자동 실행되지 않고**, **Actions** 탭에서 **Run workflow** 버튼을 눌러야만 실행됩니다.

**해결:**  
1. **Actions** 탭 → 왼쪽 **Run workflow** 선택  
2. 오른쪽 상단 **Run workflow** 클릭 → **Run workflow** 한 번 더 클릭  

---

## 4. 브랜치 선택

- **Run workflow** 시 **Branch** 가 **main** 이어야 `.github/workflows/run-workflow.yml` 이 있는 브랜치에서 실행됩니다.

**해결:**  
- Branch에서 **main** 선택 후 **Run workflow** 실행

---

## 5. 권한

- 저장소 **쓰기** 권한이 없으면 워크플로우 실행이 제한될 수 있습니다.
- **Settings** → **Actions** → **General** → Workflow permissions 에서 **Read and write** 인지 확인

---

## 요약

| 원인 | 확인/해결 |
|------|------------|
| 한 번도 실행 안 됨 | main 푸시 1회 후 Run workflow 시도 |
| Actions 비활성 | Settings → Actions → General → Disable 해제 |
| Run workflow 미클릭 | Actions → Run workflow → Run workflow 클릭 |
| 브랜치 | main 선택 후 실행 |
| 권한 | Actions → Workflow permissions 확인 |
