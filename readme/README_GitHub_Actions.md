# GitHub Actions: Run workflow

프로젝트에 **Actions** 탭이 있다면, 설정된 워크플로우를 선택하여 **Run workflow**를 눌러 GitHub 서버에서 바로 코드를 구동할 수 있습니다.

## 사용 방법

1. GitHub 저장소 페이지에서 **Actions** 탭 클릭
2. 왼쪽에서 **Run workflow** (또는 해당 워크플로우 이름) 선택
3. **Run workflow** 버튼 클릭 (브랜치 선택 후)
4. 실행 목록에서 해당 run 클릭 → 로그 확인

## 현재 설정된 워크플로우

- **파일:** `.github/workflows/run-workflow.yml`
- **트리거:** 수동 실행 (`workflow_dispatch`)
- **동작:** 체크아웃 → Python 3.11 설정 → `requirements.txt` 설치 → Python 버전·Flask 확인

## 워크플로우 추가/수정

`.github/workflows/` 폴더에 YAML 파일을 추가하거나 수정한 뒤 커밋·푸시하면 Actions 탭에 반영됩니다.
