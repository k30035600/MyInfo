# MyInfo (금융거래 통합정보)

은행·신용카드 거래 전처리·분석을 통합하는 Flask 웹 앱입니다.

---

## 배포용 URL

- **Railway**: 서비스 → **Settings** → **Networking** 또는 **Deployments** 요약에서 확인  
  형식: `https://<서비스명>.up.railway.app`  
  커스텀 도메인 사용 시: `https://myinfo.com` (DNS 설정 후)
- **로컬**: `http://localhost:8080` (개발용)

배포 URL을 한곳에 적어두려면 아래처럼 기입하면 됩니다.

| 환경   | URL |
|--------|-----|
| Railway | *(Generate Domain 후 여기 적기, 예: https://myinfo-production-xxxx.up.railway.app)* |
| 로컬   | http://localhost:8080 |

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
