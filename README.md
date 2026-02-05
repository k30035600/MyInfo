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
- **MyCash**: 금융정보 종합분석
- 데이터 보관: `MyInfo/.source/` (은행·카드 원본 및 *_before·*_after·*_category.xlsx). `.source/`는 `.gitignore`에 포함되어 GitHub에 올라가지 않습니다.

---

## Git · GitHub · 배포

| 항목 | 설명 |
|------|------|
| **Git** | 로컬 저장소 관리. 커밋 메시지는 **영문** 권장 (한글 깨짐 방지). |
| **GitHub** | 원격 저장소 푸시: `git push origin main`. 저장소 예: `https://github.com/k30035600/MyInfo` |
| **배포** | Railway 등에서 GitHub 저장소 연결 후 자동 빌드·실행. `Procfile`·`Dockerfile`·`nixpacks.toml` 사용. |

- **상세 가이드**
  - **Git 저장소 만들기 ~ Railway 배포**: [Git_호스팅_가이드.md](Git_호스팅_가이드.md)
  - **Railway 가입·배포·커스텀 도메인**: [Railway_가입_배포_도메인.md](Railway_가입_배포_도메인.md)
- **GitHub Actions**: `main` 푸시 또는 **Actions** → **Run workflow**로 Python 환경·의존성 검증. (` .github/workflows/run-workflow.yml`)

---

## GitHub Actions로 서버에서 실행

프로젝트에 **Actions** 탭이 있다면, 설정된 워크플로우를 선택하여 **Run workflow**를 누르면 GitHub 서버에서 코드 구동을 검증할 수 있습니다.

- **Actions** → **Run workflow** (왼쪽) → **Run workflow** 버튼
- 워크플로우: `run-workflow.yml` (체크아웃 → Python 3.11 → 의존성 설치 → Flask 등 확인)
