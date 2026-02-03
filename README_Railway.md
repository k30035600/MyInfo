# Railway 배포

MyInfo(Flask) 프로젝트를 Railway에 배포하는 방법입니다.

## 사전 준비

- [Railway 계정](https://railway.com/login) (GitHub 로그인 가능)
- GitHub에 코드 푸시된 상태

## 배포 방법 (GitHub 연동)

1. **https://railway.com/new** 접속
2. **Deploy from GitHub repo** 선택 후 이 저장소(MyInfo) 선택
3. GitHub 연동이 안 되어 있으면 Railway에서 GitHub 권한 허용
4. 배포가 자동으로 시작됨 (Python 감지 → `requirements.txt` 설치 → Procfile/nixpacks.toml 기준 실행)
5. **Settings** → **Networking** → **Generate Domain** 클릭하여 공개 URL 생성

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

## 참고

- Railway는 **250MB 서버리스 제한이 없음** (일반 컨테이너/VM 방식).
- 무료 trial 후 사용량에 따라 과금 (월 약 $5부터).
- 환경 변수: Railway 대시보드 → 프로젝트 → **Variables**에서 설정.
