# -*- coding: utf-8 -*-
"""
category_table_io를 import할 수 없을 때 사용하는 폴백 구현.
은행/카드/금융정보 앱 및 process_* 모듈에서 ImportError 시 단일 소스로 사용하여 유지보수 부담을 줄임.
"""
import json
import os
import re
import unicodedata
import pandas as pd

try:
    from category_constants import CATEGORY_TABLE_COLUMNS, VALID_CHASU
except ImportError:
    CATEGORY_TABLE_COLUMNS = ['분류', '키워드', '카테고리']
    VALID_CHASU = (
        '전처리', '후처리', '계정과목', '신용카드', '가상자산',
        '증권투자', '해외송금', '심야구분', '금전대부',
    )


def _norm_path(path):
    if not path:
        return None
    return str(path).replace('.xlsx', '.json').strip() or None


def _n(val):
    if val is None or (isinstance(val, str) and not val.strip()):
        return '' if val is None else str(val).strip()
    return unicodedata.normalize('NFKC', str(val).strip())


def load_category_table(path, default_empty=True):
    """JSON 파일에서 카테고리 테이블 로드 (폴백)."""
    path = _norm_path(path)
    if not path or not os.path.exists(path):
        return pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS) if default_empty else None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return pd.DataFrame(data) if data else (
            pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS) if default_empty else None
        )
    except Exception:
        return pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS) if default_empty else None


def normalize_category_df(df):
    """구분 제거, 표준 컬럼 보장 (폴백)."""
    if df is None or df.empty:
        return pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS)
    df = df.copy().fillna('')
    df = df.drop(columns=['구분'], errors='ignore')
    for c in CATEGORY_TABLE_COLUMNS:
        if c not in df.columns:
            df[c] = ''
    return df[CATEGORY_TABLE_COLUMNS].copy()


def get_category_table(path):
    """(df, file_existed) 반환 (폴백). 앱에서 _io_get_category_table 별칭으로 사용."""
    path = _norm_path(path)
    file_existed = bool(path and os.path.exists(path) and os.path.getsize(path) > 0)
    if not path or not file_existed:
        return (pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS), False)
    full = load_category_table(path, default_empty=True)
    if full is None or full.empty:
        return (pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS), file_existed)
    df = normalize_category_df(full).fillna('')
    for c in CATEGORY_TABLE_COLUMNS:
        if c not in df.columns:
            df[c] = ''
    return (df, file_existed)


def apply_category_action(path, action, data):
    """add/update/delete 수행 (폴백)."""
    path = _norm_path(path)
    if not path:
        return (False, 'path is required', 0)
    try:
        df, _ = get_category_table(path)
        df = df.fillna('')
        if action == 'add':
            v = _n(data.get('분류', '')).strip()
            if v and v not in VALID_CHASU:
                return (False, f'분류는 {", ".join(VALID_CHASU)}만 입력할 수 있습니다.', 0)
            df = pd.concat([df, pd.DataFrame([{
                '분류': _n(data.get('분류', '')),
                '키워드': _n(data.get('키워드', '')),
                '카테고리': _n(data.get('카테고리', '')),
            }])], ignore_index=True)
        elif action == 'update':
            o1, o2, o3 = data.get('original_분류', ''), data.get('original_키워드', ''), data.get('original_카테고리', '')
            v = _n(data.get('분류', '')).strip()
            if v and v not in VALID_CHASU:
                return (False, f'분류는 {", ".join(VALID_CHASU)}만 입력할 수 있습니다.', 0)
            mask = (df['분류'] == o1) & (df['키워드'] == o2) & (df['카테고리'] == o3)
            if mask.any():
                df.loc[mask, '분류'] = v
                df.loc[mask, '키워드'] = _n(data.get('키워드', ''))
                df.loc[mask, '카테고리'] = _n(data.get('카테고리', ''))
            else:
                return (False, '수정할 데이터를 찾을 수 없습니다.', 0)
        elif action == 'delete':
            o1 = data.get('original_분류', data.get('분류', ''))
            o2 = data.get('original_키워드', data.get('키워드', ''))
            o3 = data.get('original_카테고리', data.get('카테고리', ''))
            df = df[~((df['분류'] == o1) & (df['키워드'] == o2) & (df['카테고리'] == o3))]
        else:
            return (False, f'unknown action: {action}', 0)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(
                df[CATEGORY_TABLE_COLUMNS].fillna('').to_dict('records'),
                f, ensure_ascii=False, indent=2
            )
        return (True, None, len(df))
    except Exception as e:
        return (False, str(e), 0)
