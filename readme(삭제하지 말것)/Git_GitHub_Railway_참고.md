# Git · GitHub · Railway 참고

프로젝트에서 Git, GitHub, Railway를 어떻게 쓰는지 한 페이지로 정리한 참고용 문서입니다.

---

## 1. Git (로컬)

| 항목 | 내용 |
|------|------|
| **역할** | 로컬 저장소 관리, 커밋, 브랜치 |
| **한글 커밋** | `git commit -m "한글"` 은 깨질 수 있음 → **UTF-8 파일 + `-F`** 사용. 예: `git commit -F commit_msg_utf8.txt` |
| **인코딩 설정** | 최초 1회: `setup-git-utf8.ps1` 실행 또는 `git config --global i18n.commitEncoding utf-8` 등 (`.cursor/rules/git-commit-encoding.mdc` 참고) |
| **제외 경로** | `.gitignore`에 `.source/`, `venv/`, `.env`, `*.log` 등 포함. `.source/`는 클라이언트용 원본 데이터라 GitHub에 올리지 않음. |

**자주 쓰는 명령**
```powershell
git status
git add .
git commit -F 메시지파일.txt    # 한글 메시지 시
git commit -m "feat: 영문 메시지"  # 영문 시
git push origin main
```

---

## 2. GitHub (원격)

| 항목 | 내용 |
|------|------|
| **역할** | 원격 저장소, 푸시/풀, Railway와 연결 |
| **저장소 예** | `https://github.com/k30035600/MyInfo` |
| **기본 브랜치** | `main` (Railway는 이 브랜치 푸시 시 자동 배포) |
| **연결** | `git remote add origin https://github.com/사용자명/MyInfo.git` (최초 1회) |
| **푸시** | `git push origin main` 또는 `git push` (upstream 설정 후) |

**GitHub Actions**  
- `.github/workflows/run-workflow.yml`: 푸시 또는 수동 Run workflow로 Python·의존성 검증.

---

## 3. Railway (배포)

| 항목 | 내용 |
|------|------|
| **역할** | GitHub 저장소 연결 후 웹 앱 빌드·실행·호스팅 |
| **가입** | https://railway.com → Login (Google 또는 GitHub) |
| **배포 방식** | **Deploy from GitHub repo** → 저장소·브랜치(main) 선택 |
| **자동 배포** | `main`에 푸시할 때마다 Railway가 자동으로 새 빌드·배포 |
| **빌드** | `Dockerfile` 있으면 Docker, 없으면 Nixpacks (`nixpacks.toml` 참고) |
| **실행** | `Procfile`: `web: python start_web.py` |
| **환경 변수** | Railway 대시보드 **Variables** 탭에서 설정. 한글 깨짐 방지용: `LANG=en_US.UTF-8`, `LC_ALL=en_US.UTF-8`, `PYTHONUTF8=1` |
| **도메인** | **Generate Domain**으로 `*.railway.app` URL 발급. 커스텀 도메인은 Railway 문서 참고. |

**주의**  
- **Start Command**에 `LANG=en_US.UTF-8` 같은 환경 변수를 넣지 말 것. "The executable could not be found" 오류 발생. LANG/LC_ALL은 **Variables** 탭에서만 설정.
- Root Directory는 비워 두면 저장소 루트가 기준.

---

## 4. 프로젝트 내 관련 파일

| 파일 | 용도 |
|------|------|
| `.gitignore` | Git 제외 목록 (.source/, venv/, .env, 로그 등) |
| `.gitattributes` | 줄바꿈·인코딩 등 (있는 경우) |
| `Procfile` | Railway 등에서 웹 프로세스: `web: python start_web.py` |
| `nixpacks.toml` | Nixpacks 빌드 시 apt 패키지(gcc, libffi-dev, libssl-dev) |
| `setup-git-utf8.ps1` | Git 한글 커밋용 UTF-8 설정 (최초 1회) |
| `.cursor/rules/git-commit-encoding.mdc` | 커밋 인코딩 규칙 (에이전트·수동 공통) |

---

## 5. 상세 가이드 위치

| 주제 | 문서 |
|------|------|
| Git 저장소 만들기 ~ Railway 배포 흐름 | [Git_호스팅_가이드.md](../Git_호스팅_가이드.md) |
| Railway 가입·배포·커스텀 도메인·한글 깨짐 | [Railway_가입_배포_도메인.md](../Railway_가입_배포_도메인.md) |
| README 요약 | [README.md](../README.md) (Git · GitHub · 배포 섹션) |

---

## 6. 한 줄 요약

- **Git**: 로컬 커밋. 한글 메시지는 `-F UTF8파일` 사용.
- **GitHub**: 원격 저장소. `git push origin main`으로 푸시.
- **Railway**: GitHub `main` 푸시 시 자동 빌드·배포. LANG/LC_ALL/PYTHONUTF8은 Variables에 설정.
