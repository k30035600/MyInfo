# -*- coding: utf-8 -*-
"""
Vercel 서버리스 진입점: 루트 Flask 앱을 WSGI로 노출합니다.
rewrites로 모든 요청이 /api/index로 오므로 여기서 app을 처리합니다.
"""
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가 (api/ 폴더 기준 상위)
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app import app  # noqa: E402

# Vercel Python 런타임은 "app" 변수(WSGI 앱)를 진입점으로 사용합니다.
