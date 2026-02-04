# Railway 가입 · MyInfo 배포 · myinfo.com 도메인 설정

## 1. Railway.com Gmail로 로그인(가입)

1. **브라우저에서 Railway 열기**  
   https://railway.com 접속

2. **로그인/가입**  
   - 오른쪽 상단 **Login** 클릭  
   - **Continue with Google** 선택  
   - Gmail 계정 선택 후 권한 허용  
   - (최초 이용 시) 팀/이름 등 설정 후 대시보드 진입

3. **참고**  
   - Gmail 대신 **GitHub**로 로그인해도 됩니다.  
   - GitHub로 로그인하면 이후 "GitHub 저장소 연결"이 더 수월합니다.

---

## 2. MyInfo를 Git · GitHub에 커밋

로컬에서 이미 진행한 경우 다음만 확인하면 됩니다.

```powershell
cd d:\OneDrive\Cursor_AI_Project\MyInfo
git add .
git status
git commit -m "chore: Railway 배포 준비 및 문서 정리"
git push origin main
```

- 저장소: `https://github.com/k30035600/MyInfo.git`  
- `main` 브랜치에 푸시하면 Railway에서 해당 브랜치를 연결할 수 있습니다.

---

## 3. Railway에 MyInfo 배포

1. **Railway 대시보드**  
   https://railway.app/dashboard

2. **New Project**  
   - **Deploy from GitHub repo** 선택  
   - GitHub 연동(처음이면 권한 허용)  
   - 저장소 **k30035600/MyInfo** 선택  
   - 브랜치 **main** 선택

3. **서비스 설정**  
   - 생성된 서비스 클릭 → **Settings**  
   - **Build**: Nixpacks 또는 Docker 사용  
     - 루트에 `Dockerfile`이 있으면 Docker로 빌드  
     - 없으면 Nixpacks이 `Procfile` 또는 `start_web.sh` 등으로 실행  
   - **Start Command** (필요 시):  
     - `python start_web.py` 또는  
     - `gunicorn --bind 0.0.0.0:$PORT app:app`  
   - **Root Directory**: 비워두면 저장소 루트 사용

4. **환경 변수**  
   - **Variables** 탭에서 `PORT`는 Railway가 자동 주입  
   - **한글 깨짐 방지**: 아래 변수를 **반드시** 추가하세요. (Procfile에서도 설정하지만, Variables에 넣어 두면 빌드·로그에도 적용됩니다.)  
     | 이름 | 값 |
     |------|-----|
     | `LANG` | `en_US.UTF-8` |
     | `LC_ALL` | `en_US.UTF-8` |
     | `PYTHONUTF8` | `1` |
   - 앱 코드: HTML/JSON 응답에 `charset=utf-8`, Procfile·start_web.py에서 위 환경 변수 설정.
   - **한글 여전히 깨질 때**: Railway 대시보드 → 해당 서비스 → **Variables**에 위 세 개가 모두 있는지 확인하고, 값에 공백/오타가 없는지 확인한 뒤 **Redeploy** 하세요.

5. **배포 확인**  
   - **Deployments** 탭에서 빌드/실행 로그 확인  
   - **Generate Domain**으로 `*.railway.app` URL 생성 후 접속 테스트

---

## 4. 도메인 myinfo.com 연결

**전제**: myinfo.com 도메인을 소유하고 있어야 합니다 (등록업체에서 구매·이전 완료).

### 4.1 Railway에서 커스텀 도메인 추가

1. Railway 프로젝트 → 해당 서비스 선택  
2. **Settings** → **Networking** (또는 **Domains**)  
3. **Custom Domain** 추가  
   - **myinfo.com**  
   - **www.myinfo.com** (필요 시 둘 다 추가)

4. Railway가 안내하는 **CNAME** 또는 **A** 레코드 값을 확인합니다.  
   - 예: `xxxx.up.railway.app` (CNAME)  
   - 또는 A 레코드 IP

### 4.2 도메인 등록처(네임서버)에서 DNS 설정

도메인 관리 페이지(가비아, Cloudflare, Namecheap 등)에서:

| 타입  | 호스트     | 값/대상                    |
|-------|------------|----------------------------|
| CNAME | @ 또는 www | Railway에서 안내한 호스트  |
| 또는 A | @         | Railway에서 안내한 IP      |

- **@ (루트)**  
  - 일부 업체는 루트에 CNAME을 허용하지 않습니다.  
  - 그 경우 Railway/Cloudflare 등이 안내하는 **A 레코드** 사용.  
- **www**  
  - 보통 CNAME을 `xxxx.up.railway.app` 형태로 설정.

### 4.3 SSL(HTTPS)

- Railway는 Let’s Encrypt로 자동 HTTPS를 제공합니다.  
- 도메인 연결이 끝나면 잠시 후 https://myinfo.com, https://www.myinfo.com 으로 접속 가능합니다.

---

## 5. 체크리스트 요약

- [ ] Railway Gmail(또는 GitHub) 로그인  
- [ ] MyInfo `git push origin main` 완료  
- [ ] Railway에서 GitHub 저장소 연결 후 배포  
- [ ] `*.railway.app` URL로 동작 확인  
- [ ] myinfo.com 도메인 소유 확인  
- [ ] Railway에 myinfo.com, www.myinfo.com 추가  
- [ ] DNS에 CNAME/A 레코드 설정  
- [ ] https://myinfo.com 접속 및 동작 확인  

문제가 있으면 Railway 대시보드의 **Deployments** 로그와 **Settings → Networking** 메시지를 확인하세요.
