# Railway 설정 초기화 — 처음부터 다시 시작

로컬·대시보드 Railway 연결을 끊고, 처음부터 새로 배포하는 방법입니다.

---

## 1. 로컬 초기화 (이 PC에서 연결 해제)

프로젝트 폴더에서 아래를 실행하거나, 수동으로 삭제합니다.

| 대상 | 설명 |
|------|------|
| **`.railway`** | Railway CLI 연결 정보. 삭제하면 `railway link` 상태가 사라짐. |
| **`DEPLOYMENT_URL.txt`** | (선택) 저장해 둔 배포 URL. 삭제해도 됨. |

**PowerShell에서 한 번에 삭제:**

```powershell
cd d:\OneDrive\Cursor_AI_Project\MyInfo
if (Test-Path .railway) { Remove-Item -Recurse -Force .railway; "Removed .railway" }
if (Test-Path DEPLOYMENT_URL.txt) { Remove-Item -Force DEPLOYMENT_URL.txt; "Removed DEPLOYMENT_URL.txt" }
```

---

## 2. Railway 대시보드에서 초기화 (선택)

Railway 쪽 프로젝트/서비스까지 지우고 완전히 새로 시작하려면:

1. **https://railway.app** 접속 → 로그인
2. 해당 **프로젝트** 선택
3. **Settings** → **Danger** (또는 프로젝트 설정 하단) → **Delete Project**  
   또는 서비스만 지우려면: **서비스 카드** → **Settings** → **Remove Service**
4. 삭제 확인 후 완료

삭제하지 않으면 기존 프로젝트에 **다시 Deploy from GitHub** 하거나 **Redeploy** 만 해도 됩니다.

---

## 3. 처음부터 다시 배포하기

로컬·대시보드 초기화 후, 아래 순서로 진행하면 됩니다.

1. **https://railway.com/new** 접속
2. **Deploy from GitHub repo** 선택
3. **MyInfo** (또는 사용 중인 저장소) 선택
4. 배포 완료 후 **서비스** → **Settings** → **Networking** → **Generate Domain** 으로 URL 생성

자세한 단계는 **`Railway_대시보드_배포.md`** 를 참고하세요.

---

## 4. 유지하는 파일 (삭제하지 말 것)

배포를 다시 할 때 그대로 사용하는 파일입니다.

| 파일 | 역할 |
|------|------|
| **Procfile** | `web: gunicorn --bind 0.0.0.0:$PORT app:app` |
| **nixpacks.toml** | Railway 빌드/시작 설정 |
| **requirements.txt** | Python 의존성 (gunicorn 포함) |

이 파일들은 초기화해도 **삭제하지 않고** 그대로 두면 됩니다.

---

**요약:** 로컬에서는 `.railway`(및 선택적으로 `DEPLOYMENT_URL.txt`)만 지우고, Railway 대시보드에서 필요하면 프로젝트/서비스를 삭제한 뒤, **railway.com/new** → **Deploy from GitHub repo** 로 처음부터 다시 배포하면 됩니다.
