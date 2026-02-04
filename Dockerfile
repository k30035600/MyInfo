# MyInfo (금융거래 통합정보) - Flask 앱
FROM python:3.11-slim

WORKDIR /app

# Railway 등 Linux에서 한글 깨짐 방지
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUTF8=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 포트 5000 (app.py 기본)
EXPOSE 5000

# Flask 직접 실행 (UTF-8 모드 강제)
CMD ["python", "-X", "utf8", "app.py"]
