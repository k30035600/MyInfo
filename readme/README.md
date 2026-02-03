# 금융거래 통합정보 (FISRINFO)

은행 거래와 신용카드 거래를 통합 관리하는 시스템입니다.

## 서버 실행 방법

### 방법 1: 배치 파일 실행 (권장)

#### 모든 서버 한번에 실행
```bash
start_all_servers.bat
```
이 명령은 다음 세 개의 서버를 모두 시작합니다:
- 홈페이지 서버 (포트 5000)
- 은행거래 통합정보 서버 (포트 5001)
- 신용카드 통합정보 서버 (포트 5002)

#### 홈페이지만 실행
```bash
start_homepage.bat
```

### 방법 2: VS Code에서 실행

1. `F5` 키를 누르거나 디버그 메뉴에서 실행
2. 다음 중 하나를 선택:
   - **Python: FISRINFO 홈페이지** - 홈페이지 서버 실행 (포트 5000)
   - **Python: FISRBANK** - 은행거래 통합정보 서버 실행 (포트 5001)
   - **Python: FISRCARD** - 신용카드 통합정보 서버 실행 (포트 5002)

### 방법 3: 터미널에서 직접 실행

#### 홈페이지 서버
```bash
python app.py
```

#### 은행거래 통합정보 서버
```bash
cd FISRBANK
python app.py
```

#### 신용카드 통합정보 서버
```bash
cd FISRCARD
python app.py
```

## 접속 주소

서버 실행 후 브라우저에서 다음 주소로 접속하세요:

- **홈페이지**: http://localhost:5000
- **은행거래 통합정보**: http://localhost:5001
- **신용카드 통합정보**: http://localhost:5002

## 서버 중지

각 서버 창에서 `Ctrl + C`를 누르면 서버가 중지됩니다.

## 문제 해결

### "사이트에 연결할 수 없음" 오류

1. **서버가 실행 중인지 확인**
   - 터미널에서 서버가 실행 중인지 확인
   - 포트가 사용 중인지 확인:
     ```powershell
     netstat -ano | findstr :5000
     netstat -ano | findstr :5001
     netstat -ano | findstr :5002
     ```

2. **포트 충돌 확인**
   - 다른 프로그램이 같은 포트를 사용하고 있는지 확인
   - 포트를 사용하는 프로세스 종료:
     ```powershell
     taskkill /PID [프로세스ID] /F
     ```

3. **방화벽 확인**
   - Windows 방화벽에서 Python이 허용되어 있는지 확인

4. **브라우저 캐시 삭제**
   - `Ctrl + Shift + Delete`로 캐시 삭제
   - `Ctrl + F5`로 강력 새로고침

## 프로젝트 구조

```
FISRINFO/
├── app.py                    # 홈페이지 서버 (포트 5000)
├── templates/
│   └── index.html           # 홈페이지 템플릿
├── FISRBANK/                # 은행거래 통합정보
│   ├── app.py               # 은행 서버 (포트 5001)
│   └── templates/
├── FISRCARD/                # 신용카드 통합정보
│   ├── app.py               # 카드 서버 (포트 5002)
│   └── templates/
└── start_all_servers.bat     # 모든 서버 실행 배치 파일
```

## 주요 기능

### 전처리
- 원본 데이터를 정제하고 표준화된 형식으로 변환

### 카테고리
- 거래 내역을 카테고리별로 자동 분류 및 관리

### 기본분석
- 거래 통계, 월별 추이 등 기본적인 분석 제공
