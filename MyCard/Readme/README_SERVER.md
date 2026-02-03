# 서버 실행 가이드

## 실행 방법

### 방법 1: 배치 파일 실행 (권장)
```bash
run_server_utf8.bat
```
또는
```bash
run_server.bat
```

### 방법 2: 직접 실행
```bash
python app.py
```

## 한글 깨짐 문제

Windows PowerShell에서 한글이 깨져 보이는 경우:

1. **배치 파일 사용**: `run_server_utf8.bat` 파일을 사용하면 UTF-8 인코딩으로 설정됩니다.

2. **PowerShell 인코딩 설정**:
   ```powershell
   $OutputEncoding = [System.Text.Encoding]::UTF8
   [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
   ```

3. **참고**: 한글 깨짐은 출력 메시지에만 영향을 미치며, **Flask 서버는 정상 작동**합니다.
   - 브라우저에서 접속하면 한글이 정상적으로 표시됩니다.
   - 웹 페이지의 한글은 정상적으로 표시됩니다.

## 접속 주소

서버 실행 후 브라우저에서 접속:
- http://localhost:5000
- http://127.0.0.1:5000

## 서버 중지

터미널에서 `Ctrl + C`를 누르면 서버가 중지됩니다.
