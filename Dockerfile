# MyInfo (금융거래 통합정보) - Flask 앱
FROM python:3.11-slim

WORKDIR /app

# Windows 호스트에서 한글/경로 이슈 방지
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 포트 5000 (app.py 기본)
EXPOSE 5000

# 개발: Flask 직접 실행 (waitress 미사용 시)
CMD ["python", "app.py"]
