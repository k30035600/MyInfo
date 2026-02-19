# -*- coding: utf-8 -*-
"""
MyInfo 서브앱 공통 유틸 (Bank/Card/Cash 중복 제거)

- ensure_working_directory: API 호출 시 cwd를 해당 앱 폴더로 고정 (통합 서버 경로 충돌 방지)
- json_safe 계열: DataFrame/NaN/numpy/datetime → JSON 직렬화 가능한 Python 타입 변환 (API 응답용)
- is_bad_zip_error: openpyxl/손상된 xlsx 읽기 시 발생하는 zip 관련 예외 여부 판별 (은행/카드 데이터 파일용)
- format_bytes: 바이트 수 → 사람이 읽기 쉬운 문자열 (B/KB/MB, 캐시 정보 표시용)

사용: 각 앱에서 make_ensure_working_directory(SCRIPT_DIR)로 데코레이터 생성 후 사용.
"""


def format_bytes(b):
    """바이트 수를 사람이 읽기 쉬운 문자열로 (B, KB, MB). 캐시 정보 등 표시용."""
    if b is None or (isinstance(b, (int, float)) and (b < 0 or (isinstance(b, float) and (b != b)))):
        return '0 B'
    b = int(b)
    if b < 1024:
        return f'{b} B'
    if b < 1024 * 1024:
        return f'{b / 1024:.1f} KB'
    return f'{b / (1024 * 1024):.2f} MB'
from functools import wraps
import os
import zipfile
import numpy as np
import pandas as pd


def is_bad_zip_error(e):
    """openpyxl이 손상된/비xlsx 파일을 읽을 때 발생하는 오류인지 확인 (zip/decompress 손상 포함)."""
    msg = str(e).lower()
    return (
        isinstance(e, zipfile.BadZipFile)
        or 'not a zip file' in msg
        or 'bad zip' in msg
        or 'zip file' in msg
        or (('zip' in msg or 'badzip' in msg) and ('file' in msg or 'open' in msg))
        or 'decompress' in msg
        or 'invalid block' in msg
        or 'error -3' in msg
    )


def make_ensure_working_directory(script_dir):
    """script_dir로 chdir한 뒤 뷰를 실행하고, 종료 후 원래 cwd로 복원하는 데코레이터를 반환."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            original_cwd = os.getcwd()
            try:
                os.chdir(script_dir)
                return func(*args, **kwargs)
            finally:
                os.chdir(original_cwd)
        return wrapper
    return decorator


def json_safe_val(v):
    """단일 값을 JSON 가능 타입으로 변환 (재귀 없음). NaN/numpy/datetime 처리."""
    if hasattr(v, 'item'):
        return v.item()
    if hasattr(v, 'isoformat'):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    if isinstance(v, (np.integer, np.int64, np.int32)):
        return int(v)
    if isinstance(v, (np.floating, np.float64, np.float32)):
        return None if pd.isna(v) else float(v)
    if isinstance(v, float) and pd.isna(v):
        return None
    if pd.isna(v):
        return None
    return v


def json_safe_records(data):
    """list of dict 한 번 순회로 치환 (대용량 응답 시 CPU 절감)."""
    if not data or not isinstance(data, list):
        return data
    return [{k: json_safe_val(v) for k, v in row.items()} for row in data]


def json_safe(obj):
    """JSON 직렬화: NaN/NaT, numpy, datetime → Python 타입. list of dict는 json_safe_records 경로."""
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return json_safe_records(obj)
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(x) for x in obj]
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64, np.float32)):
        return None if pd.isna(obj) else float(obj)
    if isinstance(obj, float) and pd.isna(obj):
        return None
    if pd.isna(obj):
        return None
    if hasattr(obj, 'isoformat'):
        try:
            return obj.isoformat()
        except Exception:
            return str(obj)
    return obj
