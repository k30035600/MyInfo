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

## 5-2. Startup failure (시작 실패)

- **"Startup failure"** = 워크플로우가 시작 단계에서 실패해 실행 자체가 안 됨.
- 원인: 권한 부족, 설정 문제, GitHub 측 제한 등.

**해결:**
1. **Settings** → **Actions** → **General** → **Allow all actions** 선택 후 **Save**
2. **Workflow permissions** → **Read and write permissions** 선택
3. 워크플로우에 `permissions: contents: read` 추가 (이미 반영됨)
4. 실패한 run 로그 확인: **Actions** → 해당 run 클릭 → 빨간 X 단계의 로그 확인
5. 계정/저장소가 **Private** 이면 Actions 분당 제한 확인; **Billing** 문제 있으면 결제 정보 확인

---

## 6. Actions 설정 페이지에서 꼭 확인할 것

1. **Actions permissions**  
   - **"Disable actions"** 가 선택돼 있으면 → **Allow all actions** 또는 **Allow [저장소] actions** 로 변경 후 **Save**

2. **Workflow permissions**  
   - **Read and write permissions** 선택 (필요 시)

3. **Fork pull request workflows**  
   - 포크에서 오는 PR에서도 실행하려면 **Run workflows from fork pull requests** 허용

---

## 요약

| 원인 | 확인/해결 |
|------|------------|
| **Actions 비활성** | **Settings** → **Actions** → **General** → **Disable actions** 해제, **Allow all actions** 선택 후 **Save** |
| 한 번도 실행 안 됨 | main 푸시 1회 후 Run workflow 시도 |
| Run workflow 미클릭 | Actions → Run workflow → Run workflow 클릭 |
| 브랜치 | main 선택 후 실행 |
| 권한 | Actions → Workflow permissions → Read and write |
