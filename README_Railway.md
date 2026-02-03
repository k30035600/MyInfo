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

## Error: '$PORT' is not a valid port number

Railway **Settings** 에서 지정한 **Start Command** 는 셸을 거치지 않아 `$PORT` 가 확장되지 않고, 그대로 문자열 `$PORT` 로 전달됩니다.

**해결:**

1. **https://railway.app** → 해당 **프로젝트** → **서비스** 클릭
2. **Settings** 탭 → **Deploy** 또는 **Build** 섹션으로 이동
3. **Custom Start Command** / **Start Command** / **Deploy** → **Start Command** 필드 확인
4. 여기에 `gunicorn ... $PORT` 같은 명령이 있으면:
   - **비우기** (권장) → Procfile / nixpacks.toml 의 `python start_web.py` 가 사용됨  
   - 또는 **`python start_web.py`** 로 변경
5. 저장 후 **Redeploy** (또는 다시 push)

Variables 에서 **PORT** 를 수동으로 넣었다면 삭제. Railway 가 자동으로 PORT 를 넣어 줍니다.

## 커스텀 도메인 (myinfo.com)

Railway에서 **Generate Domain**으로 만든 URL 대신 **myinfo.com** 으로 접속하려면:

1. **Railway 대시보드** → 해당 **서비스** 클릭 → **Settings** → **Networking** (또는 **Domains**)
2. **Custom Domain** / **Add custom domain** 에서 `myinfo.com` 입력 후 추가
3. Railway가 안내하는 **CNAME** 값을 확인 (예: `xxx.up.railway.app`)
4. **도메인 등록처(DNS)** 에서:
   - **myinfo.com** 에 대해 **CNAME** 레코드 추가: 이름 `@`(또는 비워두기), 값 `xxx.up.railway.app`
   - 또는 **www.myinfo.com** 만 쓰려면: 이름 `www`, 값 `xxx.up.railway.app`
5. DNS 전파 후(수 분~최대 48시간) Railway가 SSL 인증서를 발급해 **https://myinfo.com** 으로 접속 가능

참고: Railway는 기본 포트(80/443)를 사용하므로 URL에 **:8080** 을 붙일 필요 없음. 로컬 개발용 포트 8080은 `app.py` / `start-server.bat` 에서 사용.

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

## 배포가 중단되었을 때

배포가 멈췄거나 서비스가 안 뜨면 아래 순서로 확인하세요.

### 1. 재배포하기

- **대시보드**: 프로젝트 → 해당 **서비스** 클릭 → **Deployments** 탭 → 최신 배포 오른쪽 **⋮** (또는 **Redeploy**) → **Redeploy** 클릭  
- **Git으로 트리거**: 저장소에서 빈 커밋 push 하면 자동 재배포됨  
  ```bash
  git commit --allow-empty -m "chore: trigger Railway redeploy"
  git push origin main
  ```

### 2. 로그로 원인 확인

- **서비스** 클릭 → **Deployments** → 해당 배포 클릭  
- **Build Logs**: 빌드 실패 시 여기서 에러 메시지 확인 (예: `pip install` 실패, Python 버전)  
- **Deploy Logs**: 실행 후 크래시 시 여기서 확인 (예: 모듈 없음, `PORT` 미설정)

### 3. 자주 나오는 원인

| 상황 | 확인·조치 |
|------|-----------|
| **서비스를 직접 중지함** | 대시보드에서 서비스 **Settings** → 서비스가 **Paused**/중지 상태면 다시 **시작** 또는 **Redeploy** |
| **빌드 실패** | Build Logs에서 에러 확인 → `requirements.txt`, `Procfile`, `nixpacks.toml` 수정 후 push 또는 Redeploy |
| **실행 후 바로 크래시** | Deploy Logs 확인 → `gunicorn`/앱 에러면 코드·환경 변수 수정 후 재배포 |
| **`'$PORT' is not a valid port number`** | **Railway 대시보드** → 해당 **서비스** → **Settings** → **Deploy** (또는 **Build**) 섹션에서 **Custom Start Command** / **Start Command** 가 있으면 **비우거나** `python start_web.py` 로 변경. 이 필드에서는 `$PORT` 가 확장되지 않아 오류 발생. 비우면 Procfile/nixpacks.toml 의 `python start_web.py` 가 사용됨. |
| **크레딧/트라이얼 소진** | Railway 대시보드 **Billing** 확인 → 결제 수단 추가 또는 플랜 변경 |
| **오래 비활성으로 슬립** | 무료/트라이얼은 비활성 시 슬립될 수 있음 → **Redeploy** 또는 저장소 push 로 다시 깨움 |

### 4. 설정만 다시 적용하고 싶을 때

코드는 그대로 두고 Railway만 다시 빌드·실행하려면:  
**Deployments** → 해당 배포 → **Redeploy** 한 번 실행하면 됩니다.

---

## 참고

- Railway는 **250MB 서버리스 제한이 없음** (일반 컨테이너/VM 방식).
- 무료 trial 후 사용량에 따라 과금 (월 약 $5부터).
- 환경 변수: Railway 대시보드 → 프로젝트 → **Variables**에서 설정.
