# -*- coding: utf-8 -*-
"""before/after 데이터 파일 JSON 읽기·쓰기. (bank_before, bank_after, card_before, card_after, cash_after)"""
import os
import time
import json
from pathlib import Path

import pandas as pd
import numpy as np


def _json_serializable(value):
    """JSON 직렬화 가능한 값으로 변환 (numpy, datetime, NaN)."""
    if hasattr(value, 'item'):  # numpy scalar
        return value.item()
    if hasattr(value, 'isoformat'):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if isinstance(value, (np.integer, np.int64, np.int32)):
        return int(value)
    if isinstance(value, (np.floating, np.float64, np.float32)):
        return None if pd.isna(value) else float(value)
    if pd.isna(value):
        return None
    return value


def safe_read_data_json(path, default_empty=True):
    """JSON 파일을 DataFrame으로 읽기. 없거나 손상 시 빈 DataFrame 또는 None 반환. .bak 생성하지 않음."""
    if not path:
        return pd.DataFrame() if default_empty else None
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame() if default_empty else None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not data or not isinstance(data, list):
            return pd.DataFrame() if default_empty else None
        df = pd.DataFrame(data)
        return df if df is not None else (pd.DataFrame() if default_empty else None)
    except (json.JSONDecodeError, TypeError, IOError, OSError):
        return pd.DataFrame() if default_empty else None


def safe_write_data_json(path, df, max_retries=3):
    """DataFrame을 JSON(orient=records)으로 저장. 권한 오류 시 재시도. .bak 생성하지 않음."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(max_retries):
        try:
            if path.exists():
                try:
                    path.unlink()
                    time.sleep(0.1)
                except PermissionError:
                    if attempt < max_retries - 1:
                        time.sleep(0.5)
                        continue
                    raise
            # NaN/NaT/numpy → JSON 가능 타입
            rec = df.to_dict('records')
            for row in rec:
                for k in list(row.keys()):
                    row[k] = _json_serializable(row[k])
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
            return True
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue
            raise
    return False
