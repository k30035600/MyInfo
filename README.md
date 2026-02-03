# MyInfo (금융거래 통합정보)

은행·신용카드 거래 전처리·분석을 통합하는 Flask 웹 앱입니다.

---

## 로컬 실행

| 용도 | URL | 비고 |
|------|-----|------|
| **로컬 개발** | `http://localhost:8080` | `python app.py` 또는 `start-server.bat` 실행 시 |

- 8080은 로컬 개발용 포트.

---

- **MyBank**: 은행 거래 전처리·분석
- **MyCard**: 카드 거래 전처리·분석
- 상세 문서: `readme/` 폴더 참고

---

## GitHub Actions로 서버에서 실행

프로젝트에 **Actions** 탭이 있다면, 설정된 워크플로우를 선택하여 **Run workflow**를 누르면 GitHub 서버에서 바로 코드를 구동할 수 있습니다.

- **Actions** → **Run workflow** (왼쪽) → 오른쪽 상단 **Run workflow** 버튼 클릭
- **이 워크플로에는 workflow_dispatch 이벤트 트리거가 있습니다.** → 푸시/PR 없이, "Run workflow" 버튼으로만 실행됩니다.
- 워크플로우: `run-workflow.yml` (체크아웃 → Python 설정 → 의존성 설치 → 실행)
