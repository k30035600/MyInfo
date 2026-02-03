# Railway 대시보드 — Deploy from GitHub repo

브라우저에서 GitHub 저장소를 연결해 배포하는 방법입니다.

---

## 1. 새 프로젝트 시작

1. **https://railway.com/new** 접속 (또는 [railway.com](https://railway.com) → **New Project**)
2. **Deploy from GitHub repo** 선택

---

## 2. 저장소 선택

1. GitHub 계정이 연결되어 있지 않으면 **Configure GitHub App** / **Authorize** 로 권한 허용
2. 저장소 목록에서 **MyInfo** (또는 사용 중인 저장소 이름) 선택
3. 필요하면 **Branch**: `main` 인지 확인

---

## 3. 배포 대기

- Railway가 자동으로 **빌드** 시작 (Python 감지 → `requirements.txt` 설치 → Procfile/nixpacks.toml 기준 실행)
- **Deployments** 탭에서 로그로 진행 상황 확인
- **Succeeded** 상태가 되면 배포 완료

---

## 4. 공개 URL(도메인) 생성

배포가 끝나면 **웹 주소**를 만들어야 외부에서 접속할 수 있습니다.

1. 프로젝트 화면에서 **서비스 카드**(방금 만든 웹 서비스) 클릭
2. **Settings** 탭 → **Networking** (또는 **Public Networking**) 펼치기
3. **Generate Domain** 클릭
4. 생성된 URL(예: `https://myinfo-production-xxxx.up.railway.app`) 복사 후 브라우저에서 접속해 확인

**Generate Domain이 안 보일 때**

- **TCP Proxy**가 켜져 있으면 **Generate Domain**이 숨겨질 수 있음 → TCP Proxy 제거 후 다시 확인
- 서비스 카드 위에 "Generate domain" / "Add public URL" 안내가 있으면 그걸 클릭해도 됨

---

## 5. 이후

- **자동 배포**: `main` 브랜치에 push할 때마다 자동으로 재배포됨
- **환경 변수**: 프로젝트 또는 서비스 → **Variables** 에서 설정
- **도메인/URL 확인**: 서비스 → **Settings** → **Networking** 또는 **Deployments** 요약에서 확인

---

요약: **railway.com/new** → **Deploy from GitHub repo** → 저장소 선택 → 배포 완료 후 **Generate Domain** 으로 URL 생성.
