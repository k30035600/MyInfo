#!/bin/sh
# PORT가 없으면 8080 사용 (로컬 테스트 시).
PORT=${PORT:-8080}
exec gunicorn --bind "0.0.0.0:$PORT" app:app
