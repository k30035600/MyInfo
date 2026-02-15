# -*- coding: utf-8 -*-
"""
linkage_table.xlsx → linkage_table.json 생성 및 로드.

- MyInfo/.source에 linkage_table.json이 없으면 linkage_table.xlsx를 읽어 JSON 생성.
- 컬럼: 업종분류, 리스크, 업종코드, 업종코드세세분류 (업종분류가 공백이면 skip).
"""
import os
import json
from pathlib import Path

import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, '.'))
SOURCE_DIR = os.path.join(PROJECT_ROOT, '.source')
LINKAGE_XLSX = os.path.join(SOURCE_DIR, 'linkage_table.xlsx')
LINKAGE_JSON = os.path.join(SOURCE_DIR, 'linkage_table.json')

REQUIRED_COLUMNS = ['업종분류', '리스크', '업종코드', '업종코드세세분류']
# 엑셀 헤더 이름이 다를 수 있음 (공백 등)
COLUMN_RENAME = {'업종코드 세세분류': '업종코드세세분류'}


def _str_clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ''
    return str(v).strip()


def _업종코드_문자6자(v):
    """업종분류 생성 시 업종코드는 문자(숫자 6자)로 저장. 숫자면 6자리 문자열로."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ''
    s = str(v).strip()
    if not s:
        return ''
    try:
        n = int(float(s))
        return str(n).zfill(6)
    except (ValueError, TypeError):
        return s


def ensure_linkage_table_json():
    """MyInfo/.source/linkage_table.json이 없으면 linkage_table.xlsx를 읽어 JSON 생성."""
    if os.path.exists(LINKAGE_JSON) and os.path.getsize(LINKAGE_JSON) > 0:
        return True
    if not os.path.exists(LINKAGE_XLSX):
        return False
    try:
        df = pd.read_excel(LINKAGE_XLSX, engine='openpyxl')
        df = df.rename(columns=COLUMN_RENAME)
        for col in REQUIRED_COLUMNS:
            if col not in df.columns:
                return False
        rows = []
        for _, r in df.iterrows():
            업종분류 = _str_clean(r.get('업종분류'))
            if not 업종분류:
                continue
            rows.append({
                '업종분류': 업종분류,
                '리스크': _str_clean(r.get('리스크')),
                '업종코드': _업종코드_문자6자(r.get('업종코드')),
                '업종코드세세분류': _str_clean(r.get('업종코드세세분류')),
            })
        os.makedirs(SOURCE_DIR, exist_ok=True)
        with open(LINKAGE_JSON, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=0)
        return True
    except Exception:
        return False


def get_linkage_table_data():
    """
    linkage_table.json 로드. 없으면 xlsx에서 생성 후 로드.
    반환: list of dict with keys 업종분류, 리스크, 업종코드, 업종코드세세분류.
    표시용으로 '업종코드_업종코드세세분류' 연결 문자열 추가.
    """
    ensure_linkage_table_json()
    if not os.path.exists(LINKAGE_JSON) or os.path.getsize(LINKAGE_JSON) == 0:
        return []
    try:
        with open(LINKAGE_JSON, 'r', encoding='utf-8') as f:
            rows = json.load(f)
    except Exception:
        return []
    out = []
    for r in rows:
        업종코드 = _업종코드_문자6자(r.get('업종코드', '')) or _str_clean(r.get('업종코드', ''))
        세세 = _str_clean(r.get('업종코드세세분류', ''))
        combined = f"{업종코드}_{세세}" if 세세 else 업종코드
        out.append({
            '업종분류': _str_clean(r.get('업종분류', '')),
            '리스크': _str_clean(r.get('리스크', '')),
            '업종코드': 업종코드,
            '업종코드세세분류': 세세,
            '업종코드_업종코드세세분류': combined,
        })
    # 리스크 내림차순 (숫자면 큰 값 먼저, 그 외는 문자열이면 나중에)
    def _risk_sort_key(x):
        r = (x.get('리스크') or '').strip()
        try:
            return (0, -float(r))
        except (ValueError, TypeError):
            return (1, r)
    out.sort(key=_risk_sort_key)
    return out


def get_linkage_map_for_apply():
    """
    cash_after 적용용: 업종코드 → (업종분류, 리스크) 매핑.
    반환: (code_to_업종분류: dict, code_to_리스크: dict)
    """
    data = get_linkage_table_data()
    code_to_업종분류 = {}
    code_to_리스크 = {}
    for r in data:
        코드 = (r.get('업종코드') or '').strip()
        if not 코드:
            continue
        code_to_업종분류[코드] = (r.get('업종분류') or '').strip()
        code_to_리스크[코드] = (r.get('리스크') or '').strip()
    return code_to_업종분류, code_to_리스크
