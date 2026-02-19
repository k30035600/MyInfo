# -*- coding: utf-8 -*-
"""before/after 데이터 파일 JSON 읽기·쓰기. (bank_before, bank_after, card_before, card_after, cash_after)"""
import os
import sys
import tempfile
import time
import json
from pathlib import Path

import pandas as pd
import numpy as np

try:
    import orjson
except ImportError:
    orjson = None

try:
    from shared_app_utils import json_safe_val as _json_serializable
except ImportError:
    def _json_serializable(value):
        if hasattr(value, 'item'):
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
    """JSON 파일을 DataFrame으로 읽기. 없거나 손상 시 빈 DataFrame 또는 None 반환. orjson 있으면 사용(파싱 가속)."""
    if not path:
        return pd.DataFrame() if default_empty else None
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame() if default_empty else None
    try:
        with open(path, 'rb') as f:
            raw = f.read()
        if orjson is not None:
            data = orjson.loads(raw)
        else:
            data = json.loads(raw.decode('utf-8'))
        if not data or not isinstance(data, list):
            return pd.DataFrame() if default_empty else None
        df = pd.DataFrame(data)
        return df if df is not None else (pd.DataFrame() if default_empty else None)
    except (json.JSONDecodeError, TypeError, IOError, OSError, ValueError):
        return pd.DataFrame() if default_empty else None


def safe_write_data_json(path, df, max_retries=5):
    """DataFrame을 JSON(orient=records)으로 저장. 임시 파일에 쓴 뒤 os.replace로 교체해
    잠긴 파일(unlink 불가) 상황을 피함. 권한/잠금 오류 시 재시도."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    dirpath = path.parent
    rec = df.to_dict('records')
    for row in rec:
        for k in list(row.keys()):
            row[k] = _json_serializable(row[k])
    tmp = None
    for attempt in range(max_retries):
        try:
            fd, tmp = tempfile.mkstemp(suffix='.json', prefix='.data_', dir=str(dirpath))
            try:
                if orjson is not None:
                    opt = orjson.OPT_INDENT_2 if len(rec) <= 5000 else 0
                    with os.fdopen(fd, 'wb') as f:
                        f.write(orjson.dumps(rec, option=opt))
                else:
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        json.dump(rec, f, ensure_ascii=False, indent=2)
            except Exception:
                if tmp and os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                raise
            # Windows/OneDrive 등이 대상 파일을 잠그는 경우 대비: 첫 replace 전 짧은 대기, replace 재시도·대기 강화
            replace_retries = 10
            if sys.platform == 'win32':
                time.sleep(0.5)
            for replace_attempt in range(replace_retries):
                try:
                    os.replace(tmp, str(path))
                    tmp = None
                    return True
                except (OSError, PermissionError):
                    if replace_attempt < replace_retries - 1:
                        time.sleep(1.0 * (replace_attempt + 1))
                        continue
                    raise
        except (OSError, PermissionError):
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    # 루프는 항상 return True 또는 raise로 종료됨 (도달 불가 코드 제거)
