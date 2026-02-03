# Railway 배포

MyInfo(Flask) 프로젝트를 Railway에 배포하는 방법입니다.

## 계속 진행 (바로 배포하기)

**방법 A — 대시보드 (권장)**  
1. [railway.com/new](https://railway.com/new) 접속  
2. **Deploy from GitHub repo** → 이 저장소 선택  
3. 배포 완료 후 **도메인 생성** (아래 "Generate Domain 못 찾을 때" 참고)  
4. 이후 `main`에 push할 때마다 자동 재배포  

**방법 B — CLI**  
1. 터미널에서 `npx @railway/cli login` (브라우저에서 로그인)  
2. `npx @railway/cli init` 또는 `railway link` 로 프로젝트 연결  
3. `npx @railway/cli up` 으로 배포  
4. 대시보드에서 **Generate Domain** 으로 URL 생성  

---

## 사전 준비

- [Railway 계정](https://railway.com/login) (GitHub 로그인 가능)
- GitHub에 코드 푸시된 상태

## 배포 방법 (GitHub 연동)

1. **https://railway.com/new** 접속
2. **Deploy from GitHub repo** 선택 후 이 저장소(MyInfo) 선택
3. GitHub 연동이 안 되어 있으면 Railway에서 GitHub 권한 허용
4. 배포가 자동으로 시작됨 (Python 감지 → `requirements.txt` 설치 → Procfile/nixpacks.toml 기준 실행)
5. **공개 URL 생성** — 아래 "Generate Domain 못 찾을 때" 참고

## 자동 배포 (Auto Deploy)

GitHub 저장소를 연결하면 **별도 설정 없이** 자동 배포가 켜집니다.

| 동작 | 설명 |
|------|------|
| **트리거** | 연결한 브랜치(기본값: `main`)에 **push**할 때마다 새 배포가 시작됩니다. |
| **설정** | Railway 대시보드 → 해당 서비스 → **Settings** → **Source** 에서 **Branch** 확인/변경 가능. |
| **동작** | push → Railway가 자동으로 빌드 후 배포 → 배포 완료 시 서비스가 새 버전으로 전환됩니다. |

- PR(Pull Request)마다 **프리뷰 환경**을 만들고 싶다면, **Settings** → **Previews** 에서 활성화할 수 있습니다.
- 자동 배포를 끄려면 **Settings** → **Source** 에서 **Auto Deploy** 를 끄면 됩니다.

## 로컬에 필요한 파일

| 파일 | 역할 |
|------|------|
| **Procfile** | `web: gunicorn --bind 0.0.0.0:$PORT app:app` (Railway가 `$PORT` 주입) |
| **nixpacks.toml** | Railway 권장 설정: 빌드/시작 명령 |
| **requirements.txt** | Python 의존성 (gunicorn 포함) |

## CLI로 배포 (선택)

```bash
npm i -g @railway/cli
railway login
railway init
railway up
```

배포 후 **Settings** → **Networking** → **Generate Domain**으로 URL 생성.

## Generate Domain 못 찾을 때

도메인 생성은 **프로젝트가 아니라, 배포된 서비스(Service)** 단위에서 합니다.

1. **캔버스에서 서비스 클릭**  
   프로젝트 화면에서 GitHub로 만든 **서비스 카드**(웹 앱 하나)를 클릭합니다.
2. **Settings 탭**  
   오른쪽 패널 또는 상단에서 **Settings** 탭을 엽니다.
3. **Networking**  
   **Networking** 섹션을 펼치면 **Public Networking** 이 보입니다.  
   그 안에 **Generate Domain** 버튼이 있습니다.
4. **프롬프트로 나오는 경우**  
   서비스가 정상 리스닝 중이면, **서비스 카드 위**나 **서비스 패널 안**에  
   "Generate domain" / "Add public URL" 같은 **안내 프롬프트**가 나올 수 있습니다. 그걸 클릭해도 됩니다.
5. **Generate Domain이 안 보일 때**  
   - **TCP Proxy**를 이미 켜 두었으면 **Generate Domain**이 숨겨집니다.  
     Settings → Networking에서 **TCP Proxy** 옆 휴지통으로 제거한 뒤 다시 확인하세요.  
   - 메뉴가 바뀐 경우: **Settings** 안에서 **Networking**, **Public**, **Domains** 같은 항목을 둘러보세요.

정리: **서비스 선택 → Settings → Networking (또는 Public Networking) → Generate Domain**

## 도메인 메뉴를 못 찾을 때 — CLI로 생성 (계속 진행)

대시보드에서 **Generate Domain**을 못 찾아도, **배포는 이미 완료된 상태**입니다. 아래처럼 CLI로 공개 URL을 만들 수 있습니다.

1. 터미널에서 프로젝트 폴더로 이동 후 로그인·연결:
   ```powershell
   cd d:\OneDrive\Cursor_AI_Project\MyInfo
   npx @railway/cli login
   npx @railway/cli link
   ```
   (`link` 시 브라우저나 터미널에서 프로젝트/서비스 선택)

2. **도메인 생성** (Railway 제공 URL 자동 생성):
   ```powershell
   npx @railway/cli domain
   ```
   실행 후 터미널에 나온 URL(예: `https://xxx.up.railway.app`)로 접속하면 됩니다.

3. **이미 도메인이 있으면** URL만 확인:
   ```powershell
   npx @railway/cli status
   ```
   또는 대시보드에서 **서비스 카드**를 클릭했을 때, **Deployments** 탭의 최신 배포나 **요약 패널**에 URL이 표시될 수 있습니다.

**요약:** 도메인 메뉴를 못 찾아도 **계속 진행**해도 됩니다. `railway domain` 한 번으로 공개 URL 생성 가능합니다.

## 참고

- Railway는 **250MB 서버리스 제한이 없음** (일반 컨테이너/VM 방식).
- 무료 trial 후 사용량에 따라 과금 (월 약 $5부터).
- 환경 변수: Railway 대시보드 → 프로젝트 → **Variables**에서 설정.
