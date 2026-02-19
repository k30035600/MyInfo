# MyInfo (금융정보 통합정보)

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
- **.source/** xls/xlsx: 클라이언트용 원본. Git 제외.  
- **category_table.json**: 은행·카드·금융정보 공통. before→after 시 전처리/후처리 적용.  
- **파일 구조·일회성 정리·유틸 스크립트**: [readme(삭제하지 말것)/파일_정리_가이드.md](readme(삭제하지%20말것)/파일_정리_가이드.md) 참고.

---

## Git · GitHub · 배포

| 항목 | 설명 |
|------|------|
| **Git** | 로컬 저장소 관리. 한글 커밋 시: `setup-git-utf8.ps1` 1회 실행 후 `git commit -F UTF8메시지파일.txt` 사용. |
| **GitHub** | 원격 저장소 푸시: `git push origin main`. 저장소 예: `https://github.com/k30035600/MyInfo` |
| **배포** | Railway 등에서 GitHub 저장소 연결 후 자동 빌드·실행. `Procfile`·`Dockerfile`·`nixpacks.toml` 사용. |
| **자동 배포** | Railway에 GitHub 저장소 연결 시 **`main` 푸시마다 자동 재배포**. (Railway 대시보드 → Deployments 확인) |

- **상세 가이드** (문서는 `readme(삭제하지 말것)/` 폴더에 보관)
  - **Git 저장소 만들기 ~ Railway 배포**: [readme(삭제하지 말것)/Git_호스팅_가이드.md](readme(삭제하지%20말것)/Git_호스팅_가이드.md)
  - **Railway 가입·배포·커스텀 도메인**: [readme(삭제하지 말것)/Railway_가입_배포_도메인.md](readme(삭제하지%20말것)/Railway_가입_배포_도메인.md)
- **GitHub Actions**: `main` 푸시 또는 **Actions** → **Run workflow**로 Python 환경·의존성 검증. (` .github/workflows/run-workflow.yml`)

---

## GitHub Actions로 서버에서 실행

프로젝트에 **Actions** 탭이 있다면, 설정된 워크플로우를 선택하여 **Run workflow**를 누르면 GitHub 서버에서 코드 구동을 검증할 수 있습니다.

- **Actions** → **Run workflow** (왼쪽) → **Run workflow** 버튼
- 워크플로우: `run-workflow.yml` (체크아웃 → Python 3.11 → 의존성 설치 → Flask 등 확인)
