# -*- coding: utf-8 -*-
"""
linkage_table.xlsx → linkage_table.json 생성 및 로드.

- MyInfo/.source에 linkage_table.json이 없으면 linkage_table.xlsx를 읽어 JSON 생성.
- 컬럼: 업종분류, 업종리스크, 업종코드, 업종코드세세분류 (업종분류가 공백이면 skip).
- 업종코드는 숫자일 경우 소수점 없이 문자로 저장. 리스크는 업종리스크로 소수점 1자리.
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

REQUIRED_COLUMNS = ['업종분류', '업종리스크', '업종코드', '업종코드세세분류']
# 엑셀 헤더 이름이 다를 수 있음 (공백 등). 구 컬럼명 호환
COLUMN_RENAME = {'업종코드 세세분류': '업종코드세세분류', '리스크': '업종리스크'}


def _str_clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ''
    return str(v).strip()


def _업종코드_문자_소수점없음(v):
    """업종코드는 문자로 저장. 숫자면 소수점 없이 정수 문자열로 (예: 369101.0 → 369101)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ''
    s = str(v).strip()
    if not s:
        return ''
    try:
        n = float(s)
        if n == int(n):
            return str(int(n))
        return s
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
            risk_val = _str_clean(r.get('업종리스크') or r.get('리스크'))
            try:
                risk_val = format(float(risk_val), '.1f') if risk_val else ''
            except (ValueError, TypeError):
                pass
            rows.append({
                '업종분류': 업종분류,
                '업종리스크': risk_val,
                '업종코드': _업종코드_문자_소수점없음(r.get('업종코드')),
                '업종코드세세분류': _str_clean(r.get('업종코드세세분류')),
            })
        os.makedirs(SOURCE_DIR, exist_ok=True)
        with open(LINKAGE_JSON, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=0)
        return True
    except Exception:
        return False


def _risk_value_1decimal(v):
    """업종리스크 값 소수점 1자리로 정규화."""
    v = _str_clean(v)
    if not v:
        return ''
    try:
        return format(float(v), '.1f')
    except (ValueError, TypeError):
        return v


def get_linkage_table_data():
    """
    linkage_table.json 로드. 없으면 xlsx에서 생성 후 로드.
    반환: list of dict with keys 업종분류, 업종리스크, 업종코드, 업종코드세세분류.
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
    # 1호·2호 행 (업종리스크, 업종분류, 업종코드 "", 업종코드세세분류). 해당 행이 있으면 수정, 없으면 추가.
    ROW_1HO = {'업종분류': '분류제외지표', '업종리스크': '0.1', '업종코드': '', '업종코드세세분류': '2호~10호에 해당하지 않는 거래'}
    ROW_2HO = {'업종분류': '심야폐업지표', '업종리스크': '0.5', '업종코드': '', '업종코드세세분류': '심야 및 폐업에 해당하는 거래'}
    _1ho_names = ('분류제외지표', '업종분류 제외')
    _2ho_names = ('심야폐업지표', '심야/폐업지표', '심야사용 의심')

    new_rows = []
    has_1ho, has_2ho = False, False
    for r in rows:
        분류 = _str_clean(r.get('업종분류'))
        if 분류 in _1ho_names:
            if not has_1ho:
                new_rows.append(ROW_1HO.copy())
                has_1ho = True
            continue
        if 분류 in _2ho_names:
            if not has_2ho:
                new_rows.append(ROW_2HO.copy())
                has_2ho = True
            continue
        new_rows.append(r)
    if not has_1ho:
        new_rows.append(ROW_1HO.copy())
    if not has_2ho:
        new_rows.append(ROW_2HO.copy())
    rows = new_rows
    try:
        os.makedirs(SOURCE_DIR, exist_ok=True)
        with open(LINKAGE_JSON, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=0)
    except Exception:
        pass

    out = []
    for r in rows:
        업종코드 = _업종코드_문자_소수점없음(r.get('업종코드', '')) or _str_clean(r.get('업종코드', ''))
        세세 = _str_clean(r.get('업종코드세세분류', ''))
        combined = f"{업종코드}_{세세}" if (업종코드 and 세세) else (세세 if 세세 else 업종코드)
        risk_val = _risk_value_1decimal(r.get('업종리스크') or r.get('리스크', ''))
        out.append({
            '업종분류': _str_clean(r.get('업종분류', '')),
            '업종리스크': risk_val,
            '업종코드': 업종코드,
            '업종코드세세분류': 세세,
            '업종코드_업종코드세세분류': combined,
        })
    # 업종리스크 내림차순 (숫자면 큰 값 먼저)
    def _risk_sort_key(x):
        r = (x.get('업종리스크') or '').strip()
        try:
            return (0, -float(r))
        except (ValueError, TypeError):
            return (1, r)
    out.sort(key=_risk_sort_key)
    return out


def get_linkage_map_for_apply():
    """
    cash_after 적용용: 업종코드 → (업종분류, 업종리스크) 매핑.
    반환: (code_to_업종분류: dict, code_to_리스크: dict)  # code_to_리스크 값은 업종리스크(소수점 1자리)
    """
    data = get_linkage_table_data()
    code_to_업종분류 = {}
    code_to_리스크 = {}
    for r in data:
        코드 = (r.get('업종코드') or '').strip()
        if not 코드:
            continue
        code_to_업종분류[코드] = (r.get('업종분류') or '').strip()
        code_to_리스크[코드] = (r.get('업종리스크') or '').strip()
    return code_to_업종분류, code_to_리스크


def export_linkage_table_to_xlsx(json_path=None, xlsx_path=None):
    """
    linkage_table.json 내용을 xlsx로 내보냄. 백업·엑셀 편집용.
    json_path/xlsx_path 생략 시 .source/linkage_table.json, .source/linkage_table.xlsx 사용.
    Returns: (success: bool, xlsx_path: str|None, error_msg: str|None)
    """
    jpath = json_path or LINKAGE_JSON
    xpath = xlsx_path or LINKAGE_XLSX
    if not os.path.exists(jpath) or os.path.getsize(jpath) == 0:
        return (False, None, "linkage_table.json이 없거나 비어 있습니다.")
    try:
        with open(jpath, 'r', encoding='utf-8') as f:
            rows = json.load(f)
        if not rows:
            return (False, None, "linkage_table.json 데이터가 비어 있습니다.")
        # 컬럼 통일: 리스크 → 업종리스크, 업종코드 소수점 제거
        out = []
        for r in rows:
            out.append({
                '업종분류': _str_clean(r.get('업종분류', '')),
                '업종리스크': _risk_value_1decimal(r.get('업종리스크') or r.get('리스크', '')),
                '업종코드': _업종코드_문자_소수점없음(r.get('업종코드', '')) or _str_clean(r.get('업종코드', '')),
                '업종코드세세분류': _str_clean(r.get('업종코드세세분류', '')),
            })
        df = pd.DataFrame(out)
        os.makedirs(os.path.dirname(xpath), exist_ok=True)
        df.to_excel(xpath, index=False, engine='openpyxl')
        return (True, xpath, None)
    except Exception as e:
        return (False, xpath, str(e))
