# 서버 실행 가이드

## 🚀 빠른 시작

### 모든 서버 한번에 실행 (권장)
```bash
start_all_servers.bat
```
이 파일을 더블클릭하면 세 개의 서버가 모두 시작됩니다.

### 개별 서버 실행

#### 홈페이지 서버 (포트 5000)
```bash
start_server_simple.bat
```
또는
```bash
python app.py
```

#### 은행거래 통합정보 서버 (포트 5001)
```bash
FISRBANK\start_server.bat
```
또는
```bash
cd FISRBANK
python app.py
```

#### 신용카드 통합정보 서버 (포트 5002)
```bash
FISRCARD\start_server.bat
```
또는
```bash
cd FISRCARD
python app.py
```

## 📍 접속 주소

서버 실행 후 브라우저에서 접속:

- **홈페이지**: http://localhost:5000
- **은행거래 통합정보**: http://localhost:5001
- **신용카드 통합정보**: http://localhost:5002

## ⚠️ 문제 해결

### "사이트에 연결할 수 없음" 오류

#### 1. 서버가 실행 중인지 확인
각 서버 창에서 다음 메시지가 보여야 합니다:
```
Running on http://127.0.0.1:5000 (또는 5001, 5002)
```

#### 2. 포트 사용 확인
PowerShell에서 다음 명령 실행:
```powershell
netstat -ano | findstr :5000
netstat -ano | findstr :5001
netstat -ano | findstr :5002
```
LISTENING 상태가 보이면 서버가 실행 중입니다.

#### 3. 서버 재시작
1. 모든 서버 창을 닫습니다 (Ctrl+C)
2. `start_all_servers.bat`를 다시 실행합니다

#### 4. 포트 충돌 해결
다른 프로그램이 포트를 사용 중일 수 있습니다:
```powershell
# 포트를 사용하는 프로세스 확인
netstat -ano | findstr :5001

# 프로세스 종료 (PID는 위 명령 결과에서 확인)
taskkill /PID [프로세스ID] /F
```

#### 5. 브라우저 캐시 삭제
- `Ctrl + Shift + Delete` → 캐시 삭제
- `Ctrl + F5`로 강력 새로고침

#### 6. 방화벽 확인
Windows 방화벽에서 Python이 허용되어 있는지 확인

## 🔍 서버 상태 확인

### 방법 1: 배치 파일 사용
```bash
check_servers.bat
```

### 방법 2: 수동 확인
PowerShell에서:
```powershell
netstat -ano | findstr ":5000 :5001 :5002"
```

## 📝 서버 중지

각 서버 창에서 `Ctrl + C`를 누르면 서버가 중지됩니다.

## 💡 팁

1. **VS Code에서 실행**: `F5` 키를 누르고 "Python: FISRBANK" 또는 "Python: FISRCARD" 선택
2. **개별 실행**: 각 서버를 개별적으로 실행할 수 있습니다
3. **모든 서버 실행**: 홈페이지에서 다른 서비스로 이동하려면 모든 서버가 실행되어 있어야 합니다
