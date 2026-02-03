# 은행 거래 내역 처리 시스템

## 실행 방법

### 방법 1: 직접 실행
```bash
python app.py
```

### 방법 2: 별도 스크립트 실행
```bash
python start_server.py
```

서버가 시작되면 브라우저에서 **http://localhost:5000** 으로 접속하세요.

## 문제 해결

서버에 연결할 수 없는 경우:

1. 포트가 사용 중인지 확인:
   ```bash
   netstat -ano | findstr :5000
   ```

2. 프로세스 종료 (필요시):
   ```bash
   taskkill /F /PID [프로세스ID]
   ```

3. 서버 재시작
