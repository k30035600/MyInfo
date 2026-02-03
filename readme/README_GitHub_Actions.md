# GitHub Actions: Run workflow

프로젝트에 **Actions** 탭이 있다면, 설정된 워크플로우를 선택하여 **Run workflow**를 눌러 GitHub 서버에서 바로 코드를 구동할 수 있습니다.

## 사용 방법

1. GitHub 저장소 페이지에서 **Actions** 탭 클릭
2. 왼쪽에서 **Run workflow** (또는 해당 워크플로우 이름) 선택
3. **Run workflow** 버튼 클릭 (브랜치 선택 후)
4. 실행 목록에서 해당 run 클릭 → 로그 확인

## 현재 설정된 워크플로우

- **파일:** `.github/workflows/run-workflow.yml`
- **트리거:**
  - **수동:** `workflow_dispatch` — Actions 탭에서 **Run workflow** 버튼으로 실행  
    (GitHub: *"This workflow has a workflow_dispatch event trigger."* / 한글: **이 워크플로에는 workflow_dispatch 이벤트 트리거가 있습니다.**)
  - **자동:** `push` (main 브랜치) — main에 푸시할 때마다 1회 실행
- **동작:** 체크아웃 → Python 3.11 설정 → `requirements.txt` 설치 → Python 버전·Flask 확인

## 워크플로우 추가/수정

`.github/workflows/` 폴더에 YAML 파일을 추가하거나 수정한 뒤 커밋·푸시하면 Actions 탭에 반영됩니다.
