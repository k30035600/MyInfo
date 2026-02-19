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
   - **Build**: 루트에 `Dockerfile`이 있으면 Docker로 빌드  
   - **Start Command**: **비워 두세요.** (비어 있으면 Dockerfile의 `CMD`가 사용됩니다.)  
     - ⚠️ **주의**: `LANG=en_US.UTF-8` 같은 환경 변수를 Start Command에 넣으면 "The executable `lang=en_us.utf-8` could not be found" 오류가 납니다. LANG/LC_ALL은 **Variables** 탭에서만 설정하세요.  
     - 꼭 지정해야 하면: `python -X utf8 app.py` 처럼 **실행 명령만** 넣기  
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
   - **한글 여전히 깨질 때**: 아래 "한글 깨짐 계속될 때" 참고.

5. **배포 확인**  
   - **Deployments** 탭에서 빌드/실행 로그 확인  
   - **Generate Domain**으로 `*.railway.app` URL 생성 후 접속 테스트

### 3.5 자동 배포 (GitHub 푸시 시)

Railway에 **GitHub 저장소를 연결**해 두면, **`main` 브랜치에 푸시할 때마다 자동으로 새 배포**가 시작됩니다. 별도 설정 없이 동작합니다.

| 할 일 | 설명 |
|--------|------|
| 로컬에서 수정 후 | `git add .` → `git commit -m "영문 메시지"` → `git push origin main` |
| Railway 동작 | 푸시 감지 → 빌드(Dockerfile 또는 Nixpacks) → 새 배포 실행 |
| 확인 | Railway 대시보드 → **Deployments** 탭에서 최신 배포 상태·로그 확인 |

- **자동 배포가 안 될 때**: Railway 프로젝트 → 해당 서비스 → **Settings** → **Source**에서 연결된 저장소가 **k30035600/MyInfo**, 브랜치가 **main**인지 확인하세요.  
- **수동 재배포**: **Deployments** 탭 → **Redeploy** 버튼.

---

## 3.6 Railway 확인 (체크리스트)

배포 후 아래 순서로 확인하세요.

| 순서 | 확인 항목 | 위치 |
|------|-----------|------|
| 1 | 최근 배포가 **Success**인지 | **Deployments** 탭 → 맨 위 배포 상태 |
| 2 | 빌드·실행 로그에 오류 없는지 | 해당 배포 클릭 → **View Logs** |
| 3 | 도메인 생성 여부 | **Settings** → **Networking** → **Generate Domain** (없으면 클릭) |
| 4 | `/health` 응답 | 브라우저: `https://본인도메인.up.railway.app/health` → `OK` 표시 |
| 5 | 홈 접속 | `https://본인도메인.up.railway.app/` → MyInfo 홈 나오는지 |
| 6 | 환경 변수 | **Variables**: `LANG`, `LC_ALL`, `PYTHONUTF8` (한글용) |

- **대시보드**: https://railway.app/dashboard  
- **문제 시**: 4.5절 "The train has not arrived" 참고.

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

- Railway는 Let's Encrypt로 자동 HTTPS를 제공합니다.  
- 도메인 연결이 끝나면 잠시 후 https://myinfo.com, https://www.myinfo.com 으로 접속 가능합니다.

---

## 4.5 "Not Found - The train has not arrived at the station" 나올 때

이 메시지는 **Railway가 서비스에서 응답을 받지 못할 때** 나옵니다. 아래 순서로 확인하세요.

1. **Railway 대시보드** → 해당 프로젝트 → **서비스 선택** → **Deployments** 탭  
   - 가장 최근 배포가 **Success**(초록)인지 확인.  
   - **Failed**이면 해당 배포 클릭 → **View Logs**에서 빌드/실행 오류 확인.

2. **실행 로그**  
   - 배포 클릭 후 **Deploy Logs** 또는 **View Logs**에서 Python 오류(traceback), `Address already in use`, `ModuleNotFoundError` 등이 있는지 확인.

3. **도메인 방금 만든 경우**  
   - **Generate Domain** 직후 1~2분 정도 기다린 뒤 다시 접속.

4. **환경 변수**  
   - **Variables** 탭에 `PORT`는 Railway가 자동 넣음.  
   - `LANG`=`en_US.UTF-8`, `LC_ALL`=`en_US.UTF-8`, `PYTHONUTF8`=`1` 있으면 좋음.

5. **동작 확인용 URL**  
   - 배포가 성공했다면 `https://본인도메인.up.railway.app/health` 로 접속해 보세요.  
   - `OK`가 보이면 앱은 떠 있는 것이고, 그때도 `/`만 안 보이면 라우팅/템플릿 문제일 수 있음.

6. **재배포**  
   - **Deployments** → **Redeploy** 또는 GitHub에 커밋 후 푸시하여 다시 배포.

---

## 5. 한글 깨짐 계속될 때

- **Docker 사용 시**: Railway가 루트의 `Dockerfile`로 빌드하면 Procfile은 사용되지 않습니다. Dockerfile에 이미 `LANG`, `LC_ALL`, `PYTHONUTF8`와 `python -X utf8`이 들어 있으므로, **Redeploy** 한 번 더 해 보세요.
- **Variables**: Railway 대시보드 → 해당 서비스 → **Variables**에 `LANG`=`en_US.UTF-8`, `LC_ALL`=`en_US.UTF-8`, `PYTHONUTF8`=`1` 세 개가 모두 있는지 확인하고, 값에 공백/따옴표 없이 넣은 뒤 **Redeploy** 하세요.
- **Procfile 사용으로 바꾸기**: 한글이 계속 깨지면 Docker 대신 Nixpacks를 쓰고 싶다면, 프로젝트에서 Dockerfile을 임시로 이름 변경(예: `Dockerfile.bak`)한 뒤 커밋·푸시하면 Railway가 Procfile로 빌드합니다. (Procfile에도 UTF-8 환경 변수 설정이 들어 있습니다.)
- **커밋 메시지**: 한글 커밋 메시지는 터미널/CI에서 깨져 보일 수 있습니다. 가능하면 영문 메시지 사용을 권장합니다.

---

## 5.5 Railway 서비스 제거/삭제

배포를 중단하고 서비스나 프로젝트를 없애고 싶을 때 아래 순서로 진행하세요.

### 서비스만 삭제 (프로젝트는 유지)

1. **https://railway.app/dashboard** 접속 후 로그인.
2. 해당 **프로젝트** 클릭 → 삭제할 **서비스** 선택.
3. **Settings** 탭으로 이동.
4. 아래로 내려 **Danger** 또는 **Danger Zone** 영역 찾기.
5. **Remove Service** / **Delete Service** 클릭 → 확인 시 서비스만 삭제됨. (다른 서비스·프로젝트는 그대로 둠.)

### 프로젝트 전체 삭제

1. 대시보드에서 **프로젝트** 선택.
2. **Project Settings** (톱니바퀴 또는 프로젝트 이름 옆 설정).
3. **Danger** / **Danger Zone** → **Delete Project** (또는 **Remove Project**).
4. 확인 시 해당 프로젝트와 그 안의 **모든 서비스**가 삭제됩니다.

- 삭제 후에는 `*.railway.app` 주소로 접속할 수 없습니다.
- GitHub 저장소 코드는 삭제되지 않습니다. 다시 배포하려면 Railway에서 새 프로젝트를 만들고 같은 저장소를 연결하면 됩니다.

---

## 6. 체크리스트 요약

- [ ] Railway Gmail(또는 GitHub) 로그인  
- [ ] MyInfo `git push origin main` 완료  
- [ ] Railway에서 GitHub 저장소 연결 후 배포  
- [ ] `*.railway.app` URL로 동작 확인  
- [ ] myinfo.com 도메인 소유 확인  
- [ ] Railway에 myinfo.com, www.myinfo.com 추가  
- [ ] DNS에 CNAME/A 레코드 설정  
- [ ] https://myinfo.com 접속 및 동작 확인  

문제가 있으면 Railway 대시보드의 **Deployments** 로그와 **Settings → Networking** 메시지를 확인하세요. 한글 깨짐은 **5. 한글 깨짐 계속될 때**를 참고하세요.

---

## 7. .gitignore / .md / PDF 한글이 깨져 보일 때

- **.gitignore, .md**: 에디터에서 **UTF-8**로 저장하세요. (VS Code: 하단 인코딩 클릭 → "Save with Encoding" → UTF-8.) 프로젝트에 `.gitattributes`를 두어 텍스트 파일을 일관되게 처리합니다.
- **PDF**: 파일 내용이 깨지면 PDF 제작 시 폰트/인코딩을 UTF-8로 설정해야 합니다. **파일명**에 한글이 있으면(예: `Railway_가입_배포_도메인.pdf`) 터미널·일부 CI에서 깨져 보일 수 있으므로, 필요 시 영문 파일명(예: `Railway_deploy_domain.pdf`) 사용을 권장합니다.
- **터미널(PowerShell)**: 한글이 깨지면 `chcp 65001` 실행 후 다시 시도하거나, 터미널 설정에서 UTF-8 사용으로 변경하세요.
