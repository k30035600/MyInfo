# Git 저장소 만들고 Railway에 배포하기

로컬 프로젝트를 Git으로 관리하고, GitHub에 올린 뒤 Railway에서 호스팅하는 전체 흐름입니다.

---

## 1. Git 저장소 만들기

### 1.1 로컬에서 Git 초기화 (이미 되어 있으면 생략)

프로젝트 폴더에서:

```powershell
cd d:\OneDrive\Cursor_AI_Project\MyInfo
git init
```

- 이미 `git status`가 동작한다면 이 단계는 건너뛰면 됩니다.

### 1.2 GitHub에서 새 저장소 생성

1. **GitHub** (https://github.com) 로그인
2. 오른쪽 상단 **+** → **New repository**
3. 설정:
   - **Repository name**: `MyInfo` (원하는 이름)
   - **Public** 선택
   - **Add a README** 등은 체크하지 않음 (로컬에 이미 코드가 있으므로)
4. **Create repository** 클릭
5. 생성된 페이지에서 **저장소 URL** 복사  
   - 예: `https://github.com/k30035600/MyInfo.git`

### 1.3 로컬과 GitHub 저장소 연결

처음 한 번만:

```powershell
git remote add origin https://github.com/k30035600/MyInfo.git
```

- 이미 `origin`이 있으면:  
  `git remote set-url origin https://github.com/사용자명/저장소명.git`  
  으로 URL만 바꿀 수 있습니다.
- 브랜치 이름이 `main`이 아니면:  
  `git branch -M main`

---

## 2. 코드 커밋하고 GitHub에 푸시

```powershell
cd d:\OneDrive\Cursor_AI_Project\MyInfo
git add .
git status
git commit -m "chore: Railway 배포 준비"
git push -u origin main
```

- `git status`로 커밋될 파일 확인
- 첫 푸시 시 `-u origin main`으로 upstream 설정
- 이후에는 `git push`만 해도 됩니다.

---

## 3. Railway에 배포

### 3.1 Railway 가입·로그인

1. https://railway.com 접속
2. **Login** → **Continue with Google** 또는 **GitHub**
   - GitHub로 로그인하면 저장소 연결이 더 쉽습니다.

### 3.2 GitHub 저장소로 프로젝트 생성

1. Railway 대시보드: https://railway.app/dashboard
2. **New Project** 클릭
3. **Deploy from GitHub repo** 선택
4. GitHub 권한 허용 후 **MyInfo** 저장소 선택
5. 배포할 **브랜치**: `main` 선택

### 3.3 서비스 설정

- **Build**:  
  - 루트에 `Dockerfile`이 있으면 Docker로 빌드  
  - 없으면 Nixpacks이 `Procfile`의 `web: python start_web.py`를 사용
- **Start Command** (필요 시):  
  - `python start_web.py` 또는  
  - `gunicorn --bind 0.0.0.0:$PORT app:app`
- **Variables**: `PORT`는 Railway가 자동 설정. 필요 시 다른 변수 추가.

### 3.4 도메인 확인

1. **Deployments** 탭에서 빌드·실행 로그 확인
2. **Settings** → **Networking** → **Generate Domain**
3. 생성된 `*.railway.app` 주소로 접속해 동작 확인

---

## 4. 이후 작업 흐름

| 할 일           | 명령어 / 위치                    |
|----------------|----------------------------------|
| 코드 수정 후 배포 | `git add .` → `git commit -m "메시지"` → `git push` |
| Railway 재배포   | 푸시하면 자동으로 새 배포 시작        |
| 로그·설정 확인   | Railway 대시보드 → 해당 서비스 → Deployments / Settings |

---

## 5. 참고 문서

- **Railway 상세**(가입, 배포, 커스텀 도메인): `Railway_가입_배포_도메인.md`
- **로컬 실행**: `README.md`

---

## 6. 한 번에 확인하는 명령어

```powershell
cd d:\OneDrive\Cursor_AI_Project\MyInfo
git status
git remote -v
git branch
```

- `git status`: 커밋되지 않은 변경 사항
- `git remote -v`: 연결된 원격 저장소(origin) URL
- `git branch`: 현재 브랜치(보통 `main`)
