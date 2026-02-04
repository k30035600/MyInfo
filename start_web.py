#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PORT 환경변수가 없거나 '$PORT' 문자열일 때 8080 사용 후 gunicorn 실행 (Heroku 등 호스팅 호환)."""
import os
import sys

# Railway 등 Linux에서 한글 깨짐 방지 (프로세스·gunicorn에 상속)
os.environ.setdefault("LANG", "en_US.UTF-8")
os.environ.setdefault("LC_ALL", "en_US.UTF-8")
os.environ.setdefault("PYTHONUTF8", "1")

port = os.environ.get("PORT", "8080").strip()
if not port or port == "$PORT" or not port.isdigit():
    port = "8080"
os.environ["PORT"] = port

# gunicorn을 현재 프로세스로 대체 (exec)
os.execvp(
    "gunicorn",
    [
        "gunicorn",
        "--bind", f"0.0.0.0:{port}",
        "app:app",
    ],
)
