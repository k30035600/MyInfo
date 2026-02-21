# -*- coding: utf-8 -*-
"""
MyCash (금융정보) Flask 앱 (cash_app.py)

목적:
  - 금융정보 병합작업 페이지(/): 전처리전(은행)·전처리후(신용카드)·업종분류 조회·금융정보(은행+카드) 병합조회·그래프.
  - 금융정보 업종분류 페이지(/category): linkage_table(업종분류) + cash_after(적용후) 테이블·필터·출력.
  - cash_after 생성: bank_after + card_after 병합 후 linkage_table·위험도(1~10호) 적용. 병합작업 페이지 "병합작업 다시 실행" 또는 API POST /api/generate-category.

주요 데이터:
  - cash_after.json: MyCash 폴더. 병합 결과만 저장(전처리/후처리는 은행·카드에서 완료).
  - linkage_table.json: MyInfo/.source. 업종분류 매칭용.
  - category_table.json: 금융정보에서는 카테고리 정의 테이블(입력/수정/삭제)용으로만 사용.

유지보수 시 참고:
  - ensure_working_directory: API 호출 시 cwd를 MyCash로 고정(통합 서버에서 다른 앱과 경로 충돌 방지).
  - 캐시: _cash_after_cache만. table(category_table, linkage_table)은 캐시 사용하지 않음.
"""
from flask import Flask, render_template, jsonify, request, make_response, redirect
import traceback
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import io
import os
from datetime import datetime
import json

# ----- UTF-8 인코딩 (Windows 콘솔용) -----
if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

app = Flask(__name__)

# JSON 인코딩 설정 (한글 지원)
app.json.ensure_ascii = False
app.config['JSON_AS_ASCII'] = False

# ----- 경로·출력 컬럼 상수 (모듈 로드 시 한 번 계산) -----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, '..'))
# category_table: MyInfo/.source (금융정보에서는 카테고리 정의 테이블용만, 업종 매칭은 linkage_table)
CATEGORY_TABLE_PATH = str(Path(PROJECT_ROOT) / '.source' / 'category_table.json')
# 금융정보 업종분류: MyInfo/.source/linkage_table.json만 사용 (xlsx 없으면 xlsx에서 json 생성)
LINKAGE_TABLE_JSON = str(Path(PROJECT_ROOT) / '.source' / 'linkage_table.json')
# 원본 업로드용: .source/Cash. after: MyCash 폴더 JSON (cash_before 미사용)
SOURCE_CASH_DIR = os.path.join(PROJECT_ROOT, '.source', 'Cash')
CASH_AFTER_PATH = os.path.join(SCRIPT_DIR, 'cash_after.json')
# 금융정보(MyCash): card·cash 테이블 연동만 하지 않음. 은행/카드 데이터 불러와 병합(cash_after 생성)은 진행.
MYCASH_ONLY_NO_BANK_CARD_LINK = False
# 금융정보 병합작업전/전처리후: 은행거래·신용카드 after 파일 (MYCASH_ONLY_NO_BANK_CARD_LINK 시 미사용)
BANK_AFTER_PATH = Path(PROJECT_ROOT) / 'MyBank' / 'bank_after.json'
CARD_AFTER_PATH = Path(PROJECT_ROOT) / 'MyCard' / 'card_after.json'

try:
    from data_json_io import safe_read_data_json, safe_write_data_json
except ImportError:
    safe_read_data_json = None
    safe_write_data_json = None

# 전처리전(은행거래) 출력 컬럼 · 계좌번호 1.0, 기타거래 2.0 (index.html LEFT_WIDTHS) — bank_after의 기타거래 출력
BANK_AFTER_DISPLAY_COLUMNS = ['은행명', '계좌번호', '거래일', '거래시간', '입금액', '출금액', '취소', '기타거래', '카테고리']
# 전처리후(신용카드) 출력 컬럼 · 카드번호 1.0, 가맹점명 2.0 (index.html RIGHT_WIDTHS) — card_after의 가맹점명 출력
CARD_AFTER_DISPLAY_COLUMNS = ['카드사', '카드번호', '이용일', '이용시간', '입금액', '출금액', '취소', '가맹점명', '카테고리']
# 업종분류조회(cash_after) 테이블 출력 11컬럼 · 계좌번호 1.0, 기타거래 2.0 (index.html QUERY_WIDTHS)
CATEGORY_QUERY_DISPLAY_COLUMNS = ['금융사', '계좌번호', '거래일', '거래시간', '입금액', '출금액', '취소', '기타거래', '키워드', '카테고리', '사업자번호']
# 업종분류 적용후(cash_after) 테이블 출력 15컬럼 · 사업자번호 뒤 구분(폐업만), 위험도키워드, 위험도분류, 위험도
CATEGORY_APPLIED_DISPLAY_COLUMNS = ['금융사', '계좌번호', '거래일', '거래시간', '입금액', '출금액', '취소', '기타거래', '키워드', '카테고리', '사업자번호', '구분', '출처', '위험도키워드', '위험도분류', '위험도']
# cash_after 생성 시 저장 컬럼. 구분 = '폐업' 또는 ''. 출처 = '은행거래'|'신용카드'(요약용)
CASH_AFTER_CREATION_COLUMNS = ['금융사', '계좌번호', '거래일', '거래시간', '입금액', '출금액', '취소', '기타거래', '키워드', '카테고리', '사업자번호', '구분', '출처', '위험도키워드', '위험도분류', '위험도']
# category_table.json 단일 테이블(구분 없음, category_table_io로 읽기/쓰기)
try:
    from category_table_io import (
        load_category_table, normalize_category_df, CATEGORY_TABLE_COLUMNS,
        get_category_table as _io_get_category_table,
        apply_category_action,
    )
except ImportError:
    from category_table_fallback import (
        load_category_table, normalize_category_df, CATEGORY_TABLE_COLUMNS,
        get_category_table as _io_get_category_table,
        apply_category_action,
    )

# 전처리후 은행 필터: 드롭다운 값 → 실제 데이터에 있을 수 있는 은행명 별칭
# 적용 위치: get_processed_data() 등에서 사용하는 DataFrame의 '은행명' 컬럼 (금융정보는 cash_after 기준)
BANK_FILTER_ALIASES = {
    '국민은행': ['국민은행', 'KB국민은행', '한국주택은행', '국민', '국민 은행'],
    '신한은행': ['신한은행', '신한'],
    '하나은행': ['하나은행', '하나'],
}

# ----- 데코레이터·JSON/데이터 유틸 (공통 모듈 사용) -----
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from shared_app_utils import (
    make_ensure_working_directory,
    json_safe as _json_safe,
    format_bytes,
)
ensure_working_directory = make_ensure_working_directory(SCRIPT_DIR)

# ----- 파일·캐시 로드 (원본 목록, 전처리후, cash_after, bank_after, card_after) -----
def load_source_files():
    """MyInfo/.source/Cash 의 원본 파일 목록 가져오기. .xls, .xlsx만 취급."""
    source_dir = Path(SOURCE_CASH_DIR)
    if not source_dir.exists():
        current_dir = os.getcwd()
        print(f"[WARNING] .source/Cash 폴더를 찾을 수 없습니다. 현재 작업 디렉토리: {current_dir}, .source/Cash 경로: {source_dir}", flush=True)
        return []
    files = []
    paths = sorted(
        list(source_dir.glob('*.xls')) + list(source_dir.glob('*.xlsx')),
        key=lambda p: (p.name, str(p))
    )
    for file_path in paths:
        file_info = {
            'filename': file_path.name,
            'path': str(file_path),
            'sheets': []
        }
        
        try:
            xls = pd.ExcelFile(file_path)
            for sheet_name in xls.sheet_names:
                file_info['sheets'].append({
                    'name': sheet_name,
                    'filename': file_path.name
                })
        except Exception:
            # .source는 .xls, .xlsx만 취급. 읽기 실패 시 스킵
            continue
        
        files.append(file_info)
    
    return files

def load_processed_file():
    """금융정보는 cash_after만 사용. cash_before 미사용으로 항상 빈 DataFrame 반환."""
    return pd.DataFrame()

# cash_after 대용량 JSON 캐시 (재생성 버튼 시에만 무효화, 서버 종료까지 재사용)
_cash_after_cache = None
_cash_after_cache_mtime = None

def load_category_file():
    """업종분류 적용 파일 로드 (MyCash/cash_after.json). 캐시 있으면 재사용, 재생성 시에만 파일 재읽기."""
    global _cash_after_cache, _cash_after_cache_mtime
    try:
        category_file = Path(CASH_AFTER_PATH)
        if not category_file.exists():
            _cash_after_cache = None
            _cash_after_cache_mtime = None
            return pd.DataFrame()
        if _cash_after_cache is not None:
            df = _cash_after_cache.copy()
            if not df.empty and '은행명' not in df.columns and '금융사' in df.columns:
                df['은행명'] = df['금융사'].fillna('').astype(str).str.strip()
            return df
        try:
            mtime = category_file.stat().st_mtime
        except OSError:
            mtime = None
        try:
            if safe_read_data_json and CASH_AFTER_PATH.endswith('.json'):
                df = safe_read_data_json(CASH_AFTER_PATH, default_empty=True)
            else:
                df = pd.read_excel(str(category_file), engine='openpyxl')
            if df is None:
                df = pd.DataFrame()
            if not df.empty:
                df = df.copy()
                # 구 컬럼명 → 신규 컬럼명 (업종코드/업종키워드→위험도키워드, 업종분류→위험도분류)
                if '업종코드' in df.columns and '위험도키워드' not in df.columns:
                    df = df.rename(columns={'업종코드': '위험도키워드'})
                if '업종키워드' in df.columns and '위험도키워드' not in df.columns:
                    df = df.rename(columns={'업종키워드': '위험도키워드'})
                if '업종분류' in df.columns and '위험도분류' not in df.columns:
                    df = df.rename(columns={'업종분류': '위험도분류'})
                # 위험도: 빈 값/NaN/문자열 → 0.1 보정 (최소 0.1 보장)
                if '위험도' in df.columns:
                    def _norm_위험도(v):
                        if v is None or v == '' or (isinstance(v, float) and pd.isna(v)):
                            return 0.1
                        try:
                            f = float(v)
                            return max(0.1, f) if f >= 0 else 0.1
                        except (TypeError, ValueError):
                            return 0.1
                    df['위험도'] = df['위험도'].apply(_norm_위험도)
                if '은행명' not in df.columns and '금융사' in df.columns:
                    df['은행명'] = df['금융사'].fillna('').astype(str).str.strip()
                _cash_after_cache = df
                _cash_after_cache_mtime = mtime
                return df.copy()
            return df
        except Exception as e:
            print(f"Error reading {category_file}: {str(e)}")
            return pd.DataFrame()
    except Exception as e:
        print(f"Error in load_category_file: {str(e)}")
        return pd.DataFrame()

def load_bank_after_file():
    """전처리전(은행거래)용: MyBank/bank_after 로드. 출력용 컬럼만 정규화하여 반환."""
    try:
        path = BANK_AFTER_PATH
        if not path.exists():
            return pd.DataFrame()
        if safe_read_data_json and str(path).endswith('.json'):
            df = safe_read_data_json(str(path), default_empty=True)
        else:
            df = pd.read_excel(str(path), engine='openpyxl')
        if df is None:
            df = pd.DataFrame()
        if df.empty:
            return df
        # 구분 → 취소. 출력은 기타거래 컬럼(bank_after 기타거래)
        if '구분' in df.columns and '취소' not in df.columns:
            df = df.rename(columns={'구분': '취소'})
        if '기타거래' not in df.columns:
            if '가맹점명' in df.columns:
                df['기타거래'] = df['가맹점명'].fillna('').astype(str).str.strip()
            elif '내용' in df.columns:
                df['기타거래'] = df['내용'].fillna('').astype(str).str.strip()
            elif '거래점' in df.columns:
                df['기타거래'] = df['거래점'].fillna('').astype(str).str.strip()
            else:
                df['기타거래'] = ''
        for c in BANK_AFTER_DISPLAY_COLUMNS:
            if c not in df.columns:
                df[c] = '' if c != '입금액' and c != '출금액' else 0
        return df[BANK_AFTER_DISPLAY_COLUMNS].copy()
    except Exception as e:
        print(f"오류: bank_after 로드 실패 - {e}", flush=True)
        return pd.DataFrame()

def load_card_after_file():
    """전처리후(신용카드)용: MyCard/card_after 로드. 출력용 컬럼만 정규화하여 반환."""
    try:
        path = CARD_AFTER_PATH
        if not path.exists():
            return pd.DataFrame()
        if safe_read_data_json and str(path).endswith('.json'):
            df = safe_read_data_json(str(path), default_empty=True)
        else:
            df = pd.read_excel(str(path), engine='openpyxl')
        if df is None:
            df = pd.DataFrame()
        if df.empty:
            return df
        # 출력은 가맹점명(card_after 가맹점명). 가맹점명 없으면 빈 컬럼 추가
        if '가맹점명' not in df.columns:
            df['가맹점명'] = ''
        for c in CARD_AFTER_DISPLAY_COLUMNS:
            if c not in df.columns:
                df[c] = '' if c not in ('입금액', '출금액') else 0
        return df[CARD_AFTER_DISPLAY_COLUMNS].copy()
    except Exception as e:
        print(f"오류: card_after 로드 실패 - {e}", flush=True)
        return pd.DataFrame()

def _safe_keyword(val):
    """키워드 값을 cash_after에 저장할 때 항상 문자열로 반환 (NaN/None → '')."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ''
    return str(val).strip()


def _str_strip(val):
    """값을 문자열로 정규화 (NaN/None → '', 그 외 strip). 업종코드 등에 사용."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ''
    return str(val).strip()


def _safe_구분(val):
    """card_after 구분 값을 cash_after에 저장할 때 '폐업'만 유지, 그 외·결측은 ''."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ''
    s = str(val).strip()
    return '폐업' if s == '폐업' else ''


def _safe_사업자번호(val):
    """사업자번호/사업자번호를 cash_after에 저장할 때 문자열로 반환 (NaN/float → 적절히 변환)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ''
    s = str(val).strip()
    if s in ('', 'nan', 'None'):
        return ''
    if s.endswith('.0'):
        s = s[:-2]
    return s


# ----- cash_after 병합: DataFrame 변환·업종분류·위험도 적용·저장 -----
def _dataframe_to_cash_after_creation(df_bank, df_card):
    """은행거래(bank_after) + 신용카드(card_after)를 병합하여 cash_after 생성용 DataFrame 반환. 키워드는 bank/card에서 반드시 복사."""
    rows = []
    def add_bank():
        if df_bank is None or df_bank.empty:
            return
        kw_col = '키워드' if '키워드' in df_bank.columns else None
        has_위험도키워드 = '위험도키워드' in df_bank.columns or '업종키워드' in df_bank.columns or '업종코드' in df_bank.columns
        col_code = '위험도키워드' if '위험도키워드' in df_bank.columns else ('업종키워드' if '업종키워드' in df_bank.columns else '업종코드')
        for _, r in df_bank.iterrows():
            kw = _safe_keyword(r.get(kw_col) if kw_col else r.get('키워드', ''))
            rows.append({
                '금융사': r.get('은행명', '') or '',
                '계좌번호': r.get('계좌번호', '') or '',
                '거래일': r.get('거래일', '') or '',
                '거래시간': r.get('거래시간', '') or '',
                '입금액': r.get('입금액', 0) or 0,
                '출금액': r.get('출금액', 0) or 0,
                '취소': r.get('취소', '') or r.get('구분', '') or '',
                '기타거래': (r.get('기타거래') or '').strip() or '',  # bank: bank_after 기타거래만 (없으면 "")
                '키워드': kw,
                '카테고리': r.get('카테고리', '') or '',
                '사업자번호': '',
                '구분': '',  # 구분은 폐업만 저장, 은행은 해당 없음
                '출처': '은행거래',
                '위험도키워드': _str_strip(r.get(col_code) or r.get('업종코드') or r.get('업종키워드')) if has_위험도키워드 else '',
                '위험도분류': '',
                '위험도': '',
            })
    def add_card():
        if df_card is None or df_card.empty:
            return
        kw_col = '키워드' if '키워드' in df_card.columns else None
        has_code = '위험도키워드' in df_card.columns or '업종키워드' in df_card.columns or '업종코드' in df_card.columns
        col_c = '위험도키워드' if '위험도키워드' in df_card.columns else ('업종키워드' if '업종키워드' in df_card.columns else '업종코드')
        for _, r in df_card.iterrows():
            kw = _safe_keyword(r.get(kw_col) if kw_col else r.get('키워드', ''))
            rows.append({
                '금융사': r.get('카드사', '') or '',
                '계좌번호': r.get('카드번호', '') or '',
                '거래일': r.get('이용일', '') or '',
                '거래시간': r.get('이용시간', '') or '',
                '입금액': r.get('입금액', 0) or 0,
                '출금액': r.get('출금액', 0) or 0,
                '취소': r.get('취소', '') or '',
                '기타거래': (r.get('가맹점명') or '').strip() or '',  # card: 가맹점명만 (없으면 "")
                '키워드': kw,
                '카테고리': r.get('카테고리', '') or '',
                '사업자번호': _safe_사업자번호(r.get('사업자번호')),
                '구분': _safe_구분(r.get('구분')),  # 폐업만 유지, 그 외 ''
                '출처': '신용카드',
                '위험도키워드': _str_strip(r.get(col_c) or r.get('업종코드') or r.get('업종키워드')) if has_code else '',
                '위험도분류': '',
                '위험도': '',
            })
    add_bank()
    add_card()
    if not rows:
        return pd.DataFrame(columns=CASH_AFTER_CREATION_COLUMNS)
    out = pd.DataFrame(rows)
    for c in CASH_AFTER_CREATION_COLUMNS:
        if c not in out.columns:
            out[c] = '' if c not in ('입금액', '출금액') else 0
    # 키워드 컬럼이 반드시 문자열로 채워지도록 보장 (NaN/결측 없음)
    out['키워드'] = out['키워드'].fillna('').astype(str).str.strip()
    return out[CASH_AFTER_CREATION_COLUMNS].copy()


def _apply_업종분류_from_linkage(df):
    """cash_after DataFrame에 대해: linkage_table.json만 사용. 위험도키워드(구 업종코드)로 위험도분류·위험도(리스크) 매칭. in-place 수정."""
    code_col = '위험도키워드' if '위험도키워드' in df.columns else ('업종키워드' if '업종키워드' in df.columns else '업종코드')
    분류_col = '위험도분류' if '위험도분류' in df.columns else '업종분류'
    if df is None or df.empty or code_col not in df.columns:
        return
    try:
        from linkage_table_io import get_linkage_map_for_apply
        code_to_업종분류, code_to_리스크 = get_linkage_map_for_apply()
        n_keys = len(code_to_업종분류) if code_to_업종분류 else 0
        _log_cash_after("linkage 맵 로드 완료 (%d개 키), 행별 매칭 시작 (%d행)" % (n_keys, len(df)))
        if not code_to_업종분류:
            return
        # 위험도 컬럼이 병합 시 ''로 채워져 str dtype이면, 0/float 대입 시 오류 나므로 미리 float로 통일
        if '위험도' in df.columns:
            df['위험도'] = pd.to_numeric(df['위험도'], errors='coerce').fillna(0).astype(float)
        codes = df[code_col].fillna('').astype(str).str.strip()
        for i in df.index:
            c = codes.at[i] if i in codes.index else ''
            if c:
                업종분류_val = code_to_업종분류.get(c, '')
                리스크_str = code_to_리스크.get(c, '')
                try:
                    위험도_val = float(리스크_str) if 리스크_str else (5 if 업종분류_val else 0)
                except (ValueError, TypeError):
                    위험도_val = 5 if 업종분류_val else 0
                df.at[i, 분류_col] = 업종분류_val
                df.at[i, '위험도'] = 위험도_val
            else:
                df.at[i, '위험도'] = 0
        _log_cash_after("linkage 행별 매칭 완료")
    except Exception as e:
        _log_cash_after("linkage 매칭 예외(무시): %s" % e)
        print(f"위험도분류(linkage) 매칭 적용 중 오류(무시): {e}", flush=True)


# 금융정보 종합의견: 가상자산·증권투자·금전대부 매칭 시 위험도 5.0
RISK_CATEGORY_CHASU = ('가상자산', '증권투자', '금전대부')


def _apply_risk_category_by_keywords(df):
    """cash_after DataFrame에 대해: category_table의 가상자산/증권투자/금전대부 규칙으로
    기타거래·키워드·금융사 텍스트를 매칭하여 업종분류·위험도 5.0 설정. in-place 수정."""
    if df is None or df.empty:
        return
    try:
        cat_df = load_category_table(CATEGORY_TABLE_PATH, default_empty=True)
        if cat_df is None or cat_df.empty or '분류' not in cat_df.columns:
            return
        cat_df = normalize_category_df(cat_df)
        risk_rows = cat_df[cat_df['분류'].fillna('').astype(str).str.strip().isin(RISK_CATEGORY_CHASU)]
        if risk_rows.empty:
            return
        # 컬럼 존재 여부
        col_기타 = '기타거래' if '기타거래' in df.columns else None
        col_kw = '키워드' if '키워드' in df.columns else None
        col_금융 = '금융사' if '금융사' in df.columns else None
        for i in df.index:
            parts = []
            if col_기타:
                parts.append(str(df.at[i, col_기타] or '').strip())
            if col_kw:
                parts.append(str(df.at[i, col_kw] or '').strip())
            if col_금융:
                parts.append(str(df.at[i, col_금융] or '').strip())
            search_text = ' '.join(parts)
            if not search_text:
                continue
            for _, r in risk_rows.iterrows():
                kw = (r.get('키워드') or '')
                if isinstance(kw, float) and pd.isna(kw):
                    kw = ''
                kw = str(kw).strip()
                if not kw:
                    continue
                cat = (r.get('카테고리') or '')
                if isinstance(cat, float) and pd.isna(cat):
                    cat = ''
                cat = str(cat).strip()
                for part in kw.replace(' ', '').split('/'):
                    key = part.strip()
                    if key and key in search_text:
                        분류_col = '위험도분류' if '위험도분류' in df.columns else '업종분류'
                        df.at[i, 분류_col] = cat
                        df.at[i, '위험도'] = 5.0
                        break
                else:
                    continue
                break
    except Exception as e:
        print(f"고위험 분류(가상자산/증권/금전대부) 매칭 적용 중 오류(무시): {e}", flush=True)


# API 요청 중 로그 파일 경로 (ensure_working_directory로 cwd=MyCash일 때 사용, 같은 파일에 확실히 기록)
_cash_after_log_path_request = None

def _cash_after_log_path():
    """cash_after_progress.log 경로. 요청 중이면 cwd 기준(MyCash), 아니면 cash_after.json 기준."""
    if _cash_after_log_path_request:
        return _cash_after_log_path_request
    return os.path.join(os.path.dirname(os.path.abspath(CASH_AFTER_PATH)), "cash_after_progress.log")


def _log_cash_after(msg):
    """cash_after 생성 단계를 콘솔·파일 모두에 출력 (매 줄 즉시 flush로 저장)."""
    ts = datetime.now().strftime('%H:%M:%S')
    line = "[cash_after %s] %s\n" % (ts, msg)
    print(line.rstrip(), flush=True)
    log_path = _cash_after_log_path()
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
    except Exception as e:
        print("[cash_after] 로그 파일 쓰기 실패: %s (경로: %s)" % (e, log_path), flush=True)


def _ensure_progress_log_file():
    """진행 로그 파일이 없으면 생성 (생성 시도 전에도 파일이 있도록). 헤더에 경로 기록."""
    try:
        log_path = _cash_after_log_path()
        if not os.path.isfile(log_path):
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("[cash_after] 진행 로그 (cash_after 생성 시도 시 아래에 단계가 기록됩니다)\n")
                f.write("[cash_after] 로그 경로: %s\n" % os.path.abspath(log_path))
    except Exception as e:
        print("[cash_after] 로그 파일 생성 실패: %s" % e, flush=True)


def _load_bank_after_for_merge():
    """cash_after 병합용: MyBank/bank_after.json 전체 컬럼 로드. 키워드 컬럼이 반드시 있도록 보장하고 NaN은 ''로 채움."""
    try:
        if not BANK_AFTER_PATH.exists():
            _log_cash_after("bank_after 파일 없음 (경로: %s)" % BANK_AFTER_PATH)
            return pd.DataFrame()
        if safe_read_data_json and str(BANK_AFTER_PATH).endswith('.json'):
            df = safe_read_data_json(str(BANK_AFTER_PATH), default_empty=True)
        else:
            df = pd.read_excel(str(BANK_AFTER_PATH), engine='openpyxl')
        if df is None:
            df = pd.DataFrame()
        if df.empty:
            _log_cash_after("bank_after 로드 완료: 0건")
            return df
        _log_cash_after("bank_after 로드 완료: %d건" % len(df))
        if '구분' in df.columns and '취소' not in df.columns:
            df = df.rename(columns={'구분': '취소'})
        if '가맹점명' not in df.columns:
            if '내용' in df.columns:
                df['가맹점명'] = df['내용'].fillna('')
            elif '거래점' in df.columns:
                df['가맹점명'] = df['거래점'].fillna('')
            else:
                df['가맹점명'] = ''
        if '키워드' not in df.columns:
            df['키워드'] = ''
        df['키워드'] = df['키워드'].fillna('').astype(str).str.strip()
        return df
    except Exception as e:
        print(f"오류: bank_after 병합용 로드 실패 - {e}", flush=True)
        return pd.DataFrame()

def merge_bank_card_to_cash_after():
    """bank_after + card_after를 병합하여 cash_after.json 생성. 둘 중 하나라도 있으면 생성 가능.
    금융정보(MyCash)에는 전처리·계정과목분류·후처리 없음. 은행/카드 after의 키워드·카테고리를 그대로 사용하고,
    업종분류(linkage_table)·위험도만 추가 적용. .bak 생성하지 않음. 성공 시 True.
    병합 시작 시 금융정보(은행+카드) 병합조회 테이블(cash_after.json)을 초기화한 뒤 병합작업을 진행한다."""
    try:
        _log_cash_after("========== cash_after 생성 시작 ==========")
        global _cash_after_cache, _cash_after_cache_mtime
        _cash_after_cache = None
        _cash_after_cache_mtime = None
        _log_cash_after("캐시 초기화 완료")
        # 금융정보(은행+카드) 병합조회 테이블(cash_after.json) 초기화 후 병합 시작
        if safe_write_data_json and CASH_AFTER_PATH.endswith('.json'):
            try:
                safe_write_data_json(CASH_AFTER_PATH, pd.DataFrame())
                _log_cash_after("cash_after.json 초기화 완료(0건), 병합작업 시작")
            except Exception as ex:
                _log_cash_after("cash_after.json 초기화 쓰기 무시: %s" % ex)
        _log_cash_after("(1/6) bank_after 로드 중: %s" % BANK_AFTER_PATH)
        df_bank = _load_bank_after_for_merge()
        df_card_raw = pd.DataFrame()
        _log_cash_after("(2/6) card_after 로드 중: %s" % CARD_AFTER_PATH)
        if CARD_AFTER_PATH.exists():
            try:
                if safe_read_data_json and str(CARD_AFTER_PATH).endswith('.json'):
                    df_card_raw = safe_read_data_json(str(CARD_AFTER_PATH), default_empty=True)
                else:
                    df_card_raw = pd.read_excel(str(CARD_AFTER_PATH), engine='openpyxl')
                if df_card_raw is None:
                    df_card_raw = pd.DataFrame()
                df_card_raw.columns = df_card_raw.columns.astype(str).str.strip()
                # cash_after 기타거래 = card_after의 가맹점명(가맹점). 키워드 컬럼은 별도 유지.
                if '기타거래' not in df_card_raw.columns and '가맹점명' in df_card_raw.columns:
                    df_card_raw['기타거래'] = df_card_raw['가맹점명'].fillna('').astype(str).str.strip()
                if '키워드' not in df_card_raw.columns:
                    df_card_raw['키워드'] = ''
                df_card_raw['키워드'] = df_card_raw['키워드'].fillna('').astype(str).str.strip()
                if '구분' not in df_card_raw.columns:
                    df_card_raw['구분'] = ''
                else:
                    df_card_raw['구분'] = df_card_raw['구분'].fillna('').astype(str).str.strip()
                if '사업자번호' not in df_card_raw.columns:
                    if '사업자등록번호' in df_card_raw.columns:
                        df_card_raw['사업자번호'] = df_card_raw['사업자등록번호'].fillna('').astype(str).str.strip()
                    else:
                        df_card_raw['사업자번호'] = ''
                else:
                    df_card_raw['사업자번호'] = df_card_raw['사업자번호'].fillna('').astype(str).str.strip()
            except Exception as ex:
                _log_cash_after("card_after 로드 예외: %s" % ex)
        if not df_card_raw.empty:
            _log_cash_after("card_after 로드 완료: %d건" % len(df_card_raw))
        else:
            _log_cash_after("card_after 없음 또는 0건")
        # 둘 중 하나라도 있으면 cash_after 생성 (한쪽만 있어도 병합)
        if df_bank.empty and df_card_raw.empty:
            _log_cash_after("실패: bank_after·card_after 모두 없음")
            _log_cash_after("========== cash_after 생성 종료 (실패: 병합할 데이터 없음) ==========")
            return (False, 'bank_after와 card_after가 모두 없거나 비어 있어 병합할 수 없습니다. 은행 또는 신용카드 전처리에서 병합작업 다시 실행 후, 금융정보에서 병합작업 다시 실행을 시도하세요.')
        _log_cash_after("(3/6) bank+card DataFrame 병합 중")
        df = _dataframe_to_cash_after_creation(df_bank, df_card_raw if not df_card_raw.empty else None)
        if df.empty:
            _log_cash_after("실패: 병합 결과 0건")
            _log_cash_after("========== cash_after 생성 종료 (실패: 병합 0건) ==========")
            return (False, '병합 결과 데이터가 비어 있습니다.')
        _log_cash_after("병합 완료: %d건" % len(df))
        _log_cash_after("(4/6) linkage_table 업종분류·위험도 매칭 적용 중")
        _apply_업종분류_from_linkage(df)
        _log_cash_after("linkage_table 매칭 완료")
        _log_cash_after("(5/6) 위험도 지표 1~10호 적용 중")
        try:
            if SCRIPT_DIR not in sys.path:
                sys.path.insert(0, SCRIPT_DIR)
            from risk_indicators import apply_risk_indicators
            apply_risk_indicators(df, category_table_path=CATEGORY_TABLE_PATH)
            _log_cash_after("위험도 지표 1~10호 적용 완료")
        except Exception as e:
            _log_cash_after("위험도 지표 적용 예외: %s" % e)
            print(f"위험도 지표(1~10호) 적용 중 오류: {e}", flush=True)
            traceback.print_exc()
        # 저장 전 위험도 최소 0.1 보장
        if '위험도' in df.columns:
            _log_cash_after("위험도 최소 0.1 보정 적용 중 (%d행)" % len(df))
            def _min_risk(v):
                if v is None or v == '' or (isinstance(v, float) and pd.isna(v)):
                    return 0.1
                try:
                    return max(0.1, float(v))
                except (TypeError, ValueError):
                    return 0.1
            df['위험도'] = df['위험도'].apply(_min_risk)
            _log_cash_after("위험도 최소 0.1 보정 완료")
        out_path = Path(CASH_AFTER_PATH)
        _log_cash_after("(6/6) 파일 저장 중: %s" % out_path)
        if safe_write_data_json and CASH_AFTER_PATH.endswith('.json'):
            if not safe_write_data_json(CASH_AFTER_PATH, df):
                _log_cash_after("실패: cash_after.json 쓰기 실패")
                _log_cash_after("========== cash_after 생성 종료 (실패: 파일 쓰기) ==========")
                return (False, 'cash_after 파일 쓰기 실패')
            _log_cash_after("cash_after.json 저장 완료 (%d건)" % len(df))
        else:
            _log_cash_after("Excel 저장 모드로 저장 중")
            df.to_excel(str(CASH_AFTER_PATH), index=False, engine='openpyxl')
        _log_cash_after("캐시 초기화 중 (_cash_after_cache 비우기)")
        _cash_after_cache = None
        _cash_after_cache_mtime = None
        _log_cash_after("캐시 초기화 완료")
        _log_cash_after("========== cash_after 생성 종료 (성공): %d건 ==========" % len(df))
        return (True, None)
    except Exception as e:
        _log_cash_after("오류: 병합 생성 실패 - %s" % e)
        _log_cash_after("========== cash_after 생성 종료 (예외) ==========")
        print(f"오류: cash_after 병합 생성 실패 - {e}", flush=True)
        traceback.print_exc()
        return (False, str(e))

def _delete_cash_after_on_enter():
    """cash_after.json 삭제 및 캐시 초기화. 재생성(merge_bank_card_to_cash_after) 시에만 호출됨."""
    global _cash_after_cache, _cash_after_cache_mtime
    try:
        if os.path.isfile(CASH_AFTER_PATH):
            os.remove(CASH_AFTER_PATH)
    except OSError:
        pass
    _cash_after_cache = None
    _cash_after_cache_mtime = None


# ----- 페이지 라우트: 전처리(/)·업종분류(/category)·분석·도움말 -----
@app.route('/')
def index():
    """금융정보 병합작업 페이지. 전처리전(은행)·전처리후(신용카드)·업종분류 조회·금융정보 병합조회(은행+카드)·그래프. cash_after는 진입 시 삭제하지 않음."""
    workspace_path = str(SCRIPT_DIR)  # 전처리전 작업폴더(MyCash 경로)
    # 업종분류(linkage) 테이블: 서버에서 HTML로 렌더링 (데이터 적은 고정 표 통일)
    linkage_table_data = []
    try:
        from linkage_table_io import get_linkage_table_data
        linkage_table_data = get_linkage_table_data() or []
    except Exception:
        pass
    resp = make_response(render_template(
        'index.html',
        workspace_path=workspace_path,
        linkage_table_data=linkage_table_data,
    ))
    # 전처리 페이지 캐시 방지: 네비게이션 갱신이 바로 반영되도록
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/favicon.ico')
def favicon():
    return '', 204

# ----- API: 원본·전처리·업종분류 데이터 (목록, bank_after, card_after, category-applied, linkage) -----
@app.route('/api/source-files')
@ensure_working_directory
def get_source_files():
    """원본 파일 목록. MyInfo/.source/Cash 의 .xls, .xlsx만."""
    try:
        current_dir = os.getcwd()
        source_dir = Path(SOURCE_CASH_DIR)
        if not source_dir.exists():
            return jsonify({
                'error': f'.source/Cash 폴더를 찾을 수 없습니다.\n현재 작업 디렉토리: {current_dir}\n.source/Cash 경로: {source_dir}',
                'files': []
            }), 404
        
        files = load_source_files()
        response = jsonify({
            'files': files,
            'count': len(files)
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        current_dir = os.getcwd()
        return jsonify({
            'error': f'파일 목록 로드 중 오류가 발생했습니다: {str(e)}\n현재 작업 디렉토리: {current_dir}\n스크립트 디렉토리: {SCRIPT_DIR}',
            'files': []
        }), 500

def _df_memory_bytes(df):
    """DataFrame 메모리 바이트 수 (deep=True)."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return 0
    try:
        return int(df.memory_usage(deep=True).sum())
    except Exception:
        return 0

def _list_memory_bytes(data):
    """list of dict 대략적 바이트 수 (JSON 직렬화 기준)."""
    if not data:
        return 0
    try:
        return len(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    except Exception:
        return 0

@app.route('/api/cache-info')
def get_cache_info():
    """캐시 이름·크기·총메모리 (금융정보 병합정보 헤더 표시용)."""
    try:
        caches = []
        total = 0
        if _cash_after_cache is not None:
            b = _df_memory_bytes(_cash_after_cache)
            total += b
            caches.append({'name': 'cash_after', 'size_bytes': b})
        for c in caches:
            c['size_human'] = format_bytes(c['size_bytes'])
        return jsonify({
            'app': 'MyCash',
            'caches': caches,
            'total_bytes': total,
            'total_human': format_bytes(total),
        })
    except Exception as e:
        return jsonify({'app': 'MyCash', 'caches': [], 'total_bytes': 0, 'total_human': '0 B', 'error': str(e)})

@app.route('/api/bank-after-data')
@ensure_working_directory
def get_bank_after_data():
    """전처리전(은행거래): MyBank/bank_after.xlsx 로드."""
    try:
        df = load_bank_after_file()
        category_file_exists = Path(CASH_AFTER_PATH).exists()
        if df.empty:
            return jsonify({
                'error': 'MyBank/bank_after.xlsx가 없거나 비어 있습니다. 은행거래 전처리를 먼저 실행하세요.',
                'count': 0,
                'deposit_amount': 0,
                'withdraw_amount': 0,
                'data': [],
                'file_exists': category_file_exists
            }), 200
        bank_filter = (request.args.get('bank') or '').strip()
        date_filter = (request.args.get('date') or '').strip()
        account_filter = (request.args.get('account') or '').strip()
        if bank_filter and '은행명' in df.columns:
            allowed = set(BANK_FILTER_ALIASES.get(bank_filter, [bank_filter]))
            s = df['은행명'].fillna('').astype(str).str.strip()
            df = df[s.isin(allowed)].copy()
        if date_filter and '거래일' in df.columns:
            d = date_filter.replace('-', '').replace('/', '')
            if len(d) > 8:
                d = d[:8]
            s = df['거래일'].astype(str).str.replace(r'[\s\-/.]', '', regex=True)
            df = df[s.str.startswith(d, na=False)]
        if account_filter and '계좌번호' in df.columns:
            df = df[df['계좌번호'].fillna('').astype(str).str.strip() == account_filter]
        count = len(df)
        deposit_amount = df['입금액'].sum() if not df.empty else 0
        withdraw_amount = df['출금액'].sum() if not df.empty else 0
        df = df.where(pd.notna(df), None)
        data = df.to_dict('records')
        data = _json_safe(data)
        response = jsonify({
            'count': count,
            'deposit_amount': int(deposit_amount),
            'withdraw_amount': int(withdraw_amount),
            'data': data,
            'file_exists': category_file_exists
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'count': 0,
            'deposit_amount': 0,
            'withdraw_amount': 0,
            'data': [],
            'file_exists': Path(CASH_AFTER_PATH).exists()
        }), 500

@app.route('/api/processed-data')
@ensure_working_directory
def get_processed_data():
    """전처리후(신용카드): MyCard/card_after.xlsx 로드."""
    try:
        df = load_card_after_file()
        category_file_exists = Path(CASH_AFTER_PATH).exists()
        if df.empty:
            return jsonify({
                'error': 'MyCard/card_after.xlsx가 없거나 비어 있습니다. 신용카드 전처리를 먼저 실행하세요.',
                'count': 0,
                'deposit_amount': 0,
                'withdraw_amount': 0,
                'data': [],
                'file_exists': category_file_exists
            }), 200
        bank_filter = (request.args.get('bank') or '').strip()
        date_filter = (request.args.get('date') or '').strip()
        account_filter = (request.args.get('account') or '').strip()
        if bank_filter and '카드사' in df.columns:
            df = df[df['카드사'].fillna('').astype(str).str.strip() == bank_filter]
        if date_filter and '이용일' in df.columns:
            d = date_filter.replace('-', '').replace('/', '')[:6]
            df = df[df['이용일'].astype(str).str.replace(r'[\s\-/.]', '', regex=True).str.startswith(d)]
        if account_filter and '카드번호' in df.columns:
            df = df[df['카드번호'].fillna('').astype(str).str.strip() == account_filter]
        total = len(df)
        deposit_amount = df['입금액'].sum() if not df.empty else 0
        withdraw_amount = df['출금액'].sum() if not df.empty else 0
        df = df.where(pd.notna(df), None)
        limit = request.args.get('limit', type=int)
        offset = request.args.get('offset', type=int) or 0
        if limit and limit > 0:
            df_slice = df.iloc[offset:offset + limit]
        else:
            df_slice = df.iloc[offset:]
        data = df_slice.to_dict('records')
        data = _json_safe(data)
        response = jsonify({
            'total': total,
            'count': len(data),
            'deposit_amount': int(deposit_amount),
            'withdraw_amount': int(withdraw_amount),
            'data': data,
            'file_exists': category_file_exists
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'count': 0,
            'deposit_amount': 0,
            'withdraw_amount': 0,
            'data': [],
            'file_exists': Path(CASH_AFTER_PATH).exists()
        }), 500

@app.route('/api/category-applied-data')
@ensure_working_directory
def get_category_applied_data():
    """업종분류 적용된 데이터 반환 (필터링 지원). cash_after 존재하면 사용만, 없으면 생성하지 않음. 생성은 /api/generate-category(생성 필터)에서 백업 후 수행."""
    try:
        cash_after_path = Path(CASH_AFTER_PATH).resolve()
        category_file_exists = cash_after_path.exists() and cash_after_path.stat().st_size > 0
        
        try:
            df = load_category_file()
        except Exception as e:
            print(f"Error loading category file: {str(e)}")
            traceback.print_exc()
            df = pd.DataFrame()
        
        if df.empty:
            response = jsonify({
                'count': 0,
                'deposit_amount': 0,
                'withdraw_amount': 0,
                'data': [],
                'file_exists': category_file_exists
            })
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response
        
        # 병합 컬럼 정규화: 은행명/카드사 → 금융사, 계좌번호/카드번호 → 계좌번호, 거래일/이용일 → 거래일, 거래시간/이용시간 → 거래시간, 기타거래/가맹점명 → 기타거래
        if '금융사' not in df.columns:
            if '은행명' in df.columns:
                df['금융사'] = df['은행명'].fillna('')
            elif '카드사' in df.columns:
                df['금융사'] = df['카드사'].fillna('')
            else:
                df['금융사'] = ''
        if '계좌번호' not in df.columns and '카드번호' in df.columns:
            df['계좌번호'] = df['카드번호'].fillna('').astype(str)
        if '거래일' not in df.columns and '이용일' in df.columns:
            df['거래일'] = df['이용일'].fillna('')
        if '거래시간' not in df.columns and '이용시간' in df.columns:
            df['거래시간'] = df['이용시간'].fillna('')
        if '기타거래' not in df.columns and '가맹점명' in df.columns:
            df['기타거래'] = df['가맹점명'].fillna('')
        if '취소' not in df.columns and '구분' in df.columns:
            df['취소'] = df['구분'].fillna('')
        if '사업자번호' not in df.columns and '사업자등록번호' in df.columns:
            df['사업자번호'] = df['사업자등록번호'].fillna('').astype(str)
        if '키워드' not in df.columns:
            df['키워드'] = ''
        # 구분: 화면에는 '폐업' 또는 빈 값만 표시. 예전에 저장된 '은행거래'/'신용카드'는 표시 시 제거
        if '구분' in df.columns:
            g = df['구분'].fillna('').astype(str).str.strip()
            df = df.copy()
            df.loc[g.isin(('은행거래', '신용카드')), '구분'] = ''
        
        bank_filter = (request.args.get('bank') or '').strip()
        date_filter = request.args.get('date', '')
        account_filter = (request.args.get('account') or '').strip()
        
        if bank_filter and '금융사' in df.columns:
            df = df[df['금융사'].fillna('').astype(str).str.strip() == bank_filter]
        if account_filter and '계좌번호' in df.columns:
            df = df[df['계좌번호'].fillna('').astype(str).str.strip() == account_filter]
        if date_filter and '거래일' in df.columns:
            try:
                d = date_filter.replace('-', '').replace('/', '')[:8]
                s = df['거래일'].astype(str).str.replace(r'[\s\-/.]', '', regex=True)
                df = df[s.str.startswith(d, na=False)]
            except Exception:
                pass
        
        # 위험도 최소값 필터 (금융정보 종합분석: 위험도 0.1 이상만, min_risk 쿼리로 지정)
        min_risk = request.args.get('min_risk', '')
        if min_risk != '' and '위험도' in df.columns:
            try:
                threshold = float(min_risk)
                df = df[df['위험도'].fillna(0).astype(float) >= threshold]
            except (TypeError, ValueError):
                pass
        
        # 행 정렬: 위험도(내림) → 거래일(내림) → 거래시간·금융사 (1호·출금 500만원 이상 등이 앞에 오도록, 페이지네이션 시 누락 방지)
        try:
            sort_by = []
            ascending = []
            if '위험도' in df.columns:
                sort_by.append('위험도')
                ascending.append(False)
            for c in ['거래일', '거래시간', '금융사']:
                if c in df.columns:
                    sort_by.append(c)
                    ascending.append(False if c == '거래일' else True)
            if sort_by:
                df = df.sort_values(by=sort_by, ascending=ascending, na_position='last')
        except Exception:
            pass
        # 업종분류 적용후 테이블 출력 15컬럼 (구분, 위험도키워드, 위험도분류, 위험도 포함)
        for c in CATEGORY_APPLIED_DISPLAY_COLUMNS:
            if c not in df.columns:
                df[c] = '' if c not in ('입금액', '출금액') else 0
        df = df[CATEGORY_APPLIED_DISPLAY_COLUMNS].copy()
        # 집계는 컬럼 제한 전에 계산 (응답 total/deposit_amount/withdraw_amount용)
        total = len(df)
        deposit_amount = df['입금액'].sum() if not df.empty and '입금액' in df.columns else 0
        withdraw_amount = df['출금액'].sum() if not df.empty and '출금액' in df.columns else 0
        # 선택: columns 파라미터로 필요한 컬럼만 반환 (페이로드 축소로 로딩 단축)
        cols_param = request.args.get('columns', '').strip()
        if cols_param:
            want = [c.strip() for c in cols_param.split(',') if c.strip() and c.strip() in df.columns]
            if want:
                df = df[want].copy()
        # 필수 컬럼 확인 (data에 입금/출금 포함 시)
        required_columns = ['입금액', '출금액']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns and not df.empty:
            for col in missing_columns:
                df[col] = 0
        
        df = df.where(pd.notna(df), None)
        # 페이지네이션: limit/offset (limit 생략 또는 0이면 전체 반환)
        limit = request.args.get('limit', type=int)
        offset = request.args.get('offset', type=int) or 0
        if limit and limit > 0:
            df_slice = df.iloc[offset:offset + limit]
        else:
            df_slice = df.iloc[offset:]
        data = df_slice.to_dict('records')
        data = _json_safe(data)
        response = jsonify({
            'total': total,
            'count': len(data),
            'deposit_amount': int(deposit_amount),
            'withdraw_amount': int(withdraw_amount),
            'data': data,
            'file_exists': category_file_exists
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        category_file_exists = Path(CASH_AFTER_PATH).exists()
        return jsonify({
            'error': str(e),
            'count': 0,
            'deposit_amount': 0,
            'withdraw_amount': 0,
            'data': [],
            'file_exists': category_file_exists
        }), 500

@app.route('/api/source-data')
@ensure_working_directory
def get_source_data():
    """원본 파일 데이터 반환 (필터링 지원). MyInfo/.source/Cash 의 .xls, .xlsx만 취급."""
    try:
        source_dir = Path(SOURCE_CASH_DIR)
        current_dir = os.getcwd()
        if not source_dir.exists():
            return jsonify({
                'error': f'.source/Cash 폴더를 찾을 수 없습니다.\n현재 작업 디렉토리: {current_dir}\n.source/Cash 경로: {source_dir}',
                'count': 0,
                'deposit_amount': 0,
                'withdraw_amount': 0,
                'files': []
            }), 404
        
        # 필터 파라미터
        bank_filter = request.args.get('bank', '')
        date_filter = request.args.get('date', '')
        
        all_data = []
        count = 0
        deposit_amount = 0
        withdraw_amount = 0
        
        # .source는 .xls, .xlsx만 취급
        xls_files = list(source_dir.glob('*.xls')) + list(source_dir.glob('*.xlsx'))
        xls_files = sorted(set(xls_files), key=lambda p: (p.name, str(p)))
        if not xls_files:
            return jsonify({
                'error': f'.source/Cash 폴더에 .xls, .xlsx 파일이 없습니다.\n현재 작업 디렉토리: {current_dir}\n.source/Cash 경로: {source_dir}',
                'count': 0,
                'deposit_amount': 0,
                'withdraw_amount': 0,
                'files': []
            }), 404
        
        for file_path in xls_files:
            # 은행명 추출
            filename = file_path.name
            bank_name = None
            if '국민은행' in filename:
                bank_name = '국민은행'
            elif '신한은행' in filename:
                bank_name = '신한은행'
            elif '하나은행' in filename:
                bank_name = '하나은행'
            
            # 은행 필터 적용
            if bank_filter and bank_name != bank_filter:
                continue
            
            try:
                # 엑셀 파일 읽기
                xls = pd.ExcelFile(file_path)
                for sheet_name in xls.sheet_names:
                    try:
                        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
                        
                        df = df.where(pd.notna(df), None)
                        data_dict = df.to_dict('records')
                        data_dict = _json_safe(data_dict)
                        sheet_data = {
                            'filename': filename,
                            'sheet_name': sheet_name,
                            'bank': bank_name,
                            'data': data_dict
                        }
                        all_data.append(sheet_data)
                        count += len(data_dict)
                    except Exception:
                        continue
            except Exception:
                # .source는 .xls, .xlsx만 취급. 읽기 실패 시 스킵
                continue
        
        response = jsonify({
            'count': count,
            'deposit_amount': int(deposit_amount),
            'withdraw_amount': int(withdraw_amount),
            'files': all_data
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        response = jsonify({
            'error': str(e),
            'count': 0,
            'deposit_amount': 0,
            'withdraw_amount': 0,
            'files': []
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500

# 카테고리 페이지 라우트
@app.route('/category')
def category():
    """카테고리 페이지"""
    return render_template('category.html')

# 카테고리: MyInfo/.source/category_table.json 단일 테이블(구분 없음)
@app.route('/api/bank_category')
@ensure_working_directory
def get_category_table():
    """category_table.json 전체 반환 (구분 없음)."""
    path = str(Path(CATEGORY_TABLE_PATH))
    try:
        # 금융정보에서는 category_table.json을 생성하지 않음. 있으면 읽기만 함.
        df, file_existed = _io_get_category_table(path)
        data = df.to_dict('records')
        response = jsonify({
            'data': data,
            'columns': ['분류', '키워드', '카테고리'],
            'count': len(df),
            'file_exists': file_existed
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        response = jsonify({
            'error': str(e),
            'data': [],
            'file_exists': Path(CATEGORY_TABLE_PATH).exists()
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500

# table은 캐시를 사용하지 않는다. category_table, linkage_table 모두 매 요청 시 파일에서 읽음.

@app.route('/api/linkage-table')
@ensure_working_directory
def get_linkage_table():
    """업종분류 조회용: linkage_table.json 반환. 캐시 없이 매 요청 시 파일에서 읽음."""
    try:
        from linkage_table_io import get_linkage_table_data
        data = get_linkage_table_data()
        response = jsonify({
            'data': data,
            'columns': ['업종분류', '업종리스크', '업종코드_업종코드세세분류'],
            'count': len(data),
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        response = jsonify({
            'error': str(e),
            'data': [],
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500

@app.route('/api/bank_category', methods=['POST'])
@ensure_working_directory
def save_category_table():
    """category_table.json 전체 갱신 (구분 없음)"""
    path = str(Path(CATEGORY_TABLE_PATH))
    try:
        data = request.json or {}
        action = data.get('action', 'add')
        success, error_msg, count = apply_category_action(path, action, data)
        if not success:
            return jsonify({'success': False, 'error': error_msg}), 400
        try:
            from category_table_defaults import sync_category_create_from_xlsx
            sync_category_create_from_xlsx(path)
        except Exception:
            pass
        response = jsonify({
            'success': True,
            'message': '카테고리 테이블이 업데이트되었습니다.',
            'count': count
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        response = jsonify({
            'success': False,
            'error': str(e)
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500

# 분석 페이지 라우트
# ----- 페이지: 금융정보 종합분석·인쇄 -----
@app.route('/analysis/basic')
def analysis_basic():
    """기본 기능 분석 페이지"""
    return render_template('analysis_basic.html')

@app.route('/analysis/print')
@ensure_working_directory
def print_analysis():
    """금융정보 종합분석 인쇄용 페이지 (출력일, 금융사/전체, 전체 합계, 위험도 테이블, 세부내역 테이블, 위험도 원그래프, 종합의견)."""
    try:
        bank_filter = (request.args.get('bank') or '').strip()
        df = load_category_file()
        if df.empty:
            return "데이터가 없습니다. cash_after를 생성한 뒤 다시 시도하세요.", 400

        # 컬럼 정규화 (get_category_applied_data와 동일)
        if '금융사' not in df.columns:
            if '은행명' in df.columns:
                df['금융사'] = df['은행명'].fillna('')
            elif '카드사' in df.columns:
                df['금융사'] = df['카드사'].fillna('')
            else:
                df['금융사'] = ''
        if '계좌번호' not in df.columns and '카드번호' in df.columns:
            df['계좌번호'] = df['카드번호'].fillna('').astype(str)
        if '거래일' not in df.columns and '이용일' in df.columns:
            df['거래일'] = df['이용일'].fillna('')
        if '거래시간' not in df.columns and '이용시간' in df.columns:
            df['거래시간'] = df['이용시간'].fillna('')
        if '기타거래' not in df.columns and '가맹점명' in df.columns:
            df['기타거래'] = df['가맹점명'].fillna('')

        if bank_filter and '금융사' in df.columns:
            df = df[df['금융사'].fillna('').astype(str).str.strip() == bank_filter]

        # 위험도 0.1 이상만 (종합분석과 동일)
        if '위험도' in df.columns:
            try:
                risk = df['위험도'].fillna(0).astype(float)
                df = df.loc[risk >= 0.1]
            except (TypeError, ValueError):
                pass

        total_count = len(df)
        total_deposit = int(df['입금액'].sum()) if not df.empty and '입금액' in df.columns else 0
        total_withdraw = int(df['출금액'].sum()) if not df.empty and '출금액' in df.columns else 0
        src_col = '출처' if '출처' in df.columns else '구분'
        if not df.empty and src_col in df.columns:
            src_trim = df[src_col].fillna('').astype(str).str.strip()
            bank_mask = src_trim == '은행거래'
            card_mask = src_trim == '신용카드'
            print_bank_count = int(bank_mask.sum())
            print_card_count = int(card_mask.sum())
            print_bank_withdraw = int(df.loc[bank_mask, '출금액'].sum()) if '출금액' in df.columns else 0
            print_card_withdraw = int(df.loc[card_mask, '출금액'].sum()) if '출금액' in df.columns else 0
        else:
            print_bank_count = print_card_count = 0
            print_bank_withdraw = print_card_withdraw = 0
        if (print_bank_count == 0 and print_card_count == 0) and not df.empty and total_count > 0 and '금융사' in df.columns:
            bank_names = {'국민은행', '신한은행', '하나은행'}
            gu = df['금융사'].fillna('').astype(str).str.strip()
            print_bank_count = int(gu.isin(bank_names).sum())
            print_card_count = total_count - print_bank_count
            print_bank_withdraw = int(df.loc[gu.isin(bank_names), '출금액'].sum()) if '출금액' in df.columns else 0
            print_card_withdraw = total_withdraw - print_bank_withdraw

        # 1호~10호 고정 순서 및 인쇄용 표시명
        RISK_ORDER_PRINT = ['분류제외지표', '심야폐업지표', '자료소명지표', '비정형지표', '투기성지표', '사기파산지표', '가상자산지표', '자산은닉지표', '과소비지표', '사행성지표']
        RISK_DISPLAY_PRINT = ['1호(업종분류제외)', '2호(심야폐업지표)', '3호(자료소명지표)', '4호(비정형지표)', '5호(투기성지표)', '6호(사기파산지표)', '7호(가상자산지표)', '8호(자산은닉지표)', '9호(과소비지표)', '10호(사행성지표)']
        RISK_DEFAULT_VAL = [0.1, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]

        # 위험도분류별 집계 (1호~10호 모두 출력, 인쇄용 표시명)
        risk_classification_rows = []
        if not df.empty and '위험도분류' in df.columns:
            col = '위험도분류'
            raw_to_key = lambda x: (x.strip() if x and str(x).strip() else '분류제외지표')
            df_key = df[col].fillna('').astype(str).apply(raw_to_key)
            grp = df.groupby(df_key).agg({'입금액': 'sum', '출금액': 'sum', '위험도': 'min'}).reset_index()
            grp = grp.rename(columns={col: 'classification', '입금액': 'deposit', '출금액': 'withdraw', '위험도': 'risk'})
            by_cls = {r['classification']: r for _, r in grp.iterrows()}
            for i, cls in enumerate(RISK_ORDER_PRINT):
                r = by_cls.get(cls, {})
                rv = r.get('risk')
                risk_val = float(rv) if pd.notna(rv) and rv != '' else RISK_DEFAULT_VAL[i]
                risk_classification_rows.append({
                    'classification': RISK_DISPLAY_PRINT[i],
                    'risk': risk_val,
                    'count': int(len(df[df_key == cls])) if cls in by_cls else 0,
                    'deposit': int(r.get('deposit', 0)),
                    'withdraw': int(r.get('withdraw', 0))
                })
        else:
            risk_classification_rows = [{'classification': RISK_DISPLAY_PRINT[i], 'risk': RISK_DEFAULT_VAL[i], 'count': 0, 'deposit': 0, 'withdraw': 0} for i in range(10)]

        # 세부내역: 위험도 내림 → 거래일 내림, 인쇄용 10행 + 위험도(1호~10호) 표시
        risk_detail_rows = []
        risk_detail_total_count = 0
        risk_detail_deposit_sum = 0
        risk_detail_withdraw_sum = 0
        if not df.empty:
            for c in ['금융사', '거래일', '기타거래', '입금액', '출금액']:
                if c not in df.columns:
                    df[c] = 0 if c in ('입금액', '출금액') else ''
            if '위험도분류' not in df.columns:
                df['위험도분류'] = ''
            try:
                df_sorted = df.sort_values(
                    by=['위험도', '거래일'] if '거래일' in df.columns else ['위험도'],
                    ascending=[False, False],
                    na_position='last'
                )
            except Exception:
                df_sorted = df
            risk_detail_total_count = len(df_sorted)
            risk_detail_deposit_sum = int(df_sorted['입금액'].sum()) if '입금액' in df_sorted.columns else 0
            risk_detail_withdraw_sum = int(df_sorted['출금액'].sum()) if '출금액' in df_sorted.columns else 0
            df_slice = df_sorted.head(10)
            for _, row in df_slice.iterrows():
                raw_cls = str(row.get('위험도분류', '')).strip() or '분류제외지표'
                try:
                    idx = RISK_ORDER_PRINT.index(raw_cls)
                    cls_display = RISK_DISPLAY_PRINT[idx]
                except ValueError:
                    cls_display = raw_cls
                risk_detail_rows.append({
                    '금융사': str(row.get('금융사', '')),
                    '거래일': str(row.get('거래일', '')),
                    '기타거래': str(row.get('기타거래', '')),
                    '위험도분류_display': cls_display,
                    '출금액': int(row.get('출금액', 0) or 0)
                })

        # 원그래프용: 위험도분류별 출금액 (출금액 > 0만) + SVG path (인쇄용 원그래프)
        risk_pie_data = [{'label': r['classification'], 'value': r['withdraw']} for r in risk_classification_rows if r['withdraw'] > 0]
        import math
        pie_total = sum(p['value'] for p in risk_pie_data)
        risk_pie_slices = []
        if pie_total and pie_total > 0:
            colors = ['#1976d2', '#2e7d32', '#ed6c02', '#c62828', '#6a1b9a', '#00838f', '#558b2f', '#ad1457', '#283593', '#1565c0']
            cx, cy, r = 100, 100, 80
            cum = 0
            for i, p in enumerate(risk_pie_data):
                pct = (p['value'] / pie_total) * 100
                a1 = cum * 3.6 - 90
                a2 = (cum + pct) * 3.6 - 90
                cum += pct
                rad1, rad2 = math.radians(a1), math.radians(a2)
                x1 = cx + r * math.cos(rad1)
                y1 = cy + r * math.sin(rad1)
                x2 = cx + r * math.cos(rad2)
                y2 = cy + r * math.sin(rad2)
                large = 1 if pct > 50 else 0
                path_d = 'M %g %g L %g %g A %g %g 0 %d 1 %g %g Z' % (cx, cy, x1, y1, r, r, large, x2, y2)
                risk_pie_slices.append({'path_d': path_d, 'color': colors[i % len(colors)], 'label': p['label'], 'value': p['value'], 'pct': round(pct, 1)})
        else:
            risk_pie_slices = []

        return render_template('print_analysis.html',
                             report_date=datetime.now().strftime('%Y-%m-%d'),
                             bank_filter=bank_filter or '전체',
                             total_count=total_count,
                             total_deposit=total_deposit,
                             total_withdraw=total_withdraw,
                             bank_count=print_bank_count,
                             bank_withdraw=print_bank_withdraw,
                             card_count=print_card_count,
                             card_withdraw=print_card_withdraw,
                             risk_classification_rows=risk_classification_rows,
                             risk_detail_rows=risk_detail_rows,
                             risk_detail_total_count=risk_detail_total_count,
                             risk_detail_deposit_sum=risk_detail_deposit_sum,
                             risk_detail_withdraw_sum=risk_detail_withdraw_sum,
                             risk_pie_data=risk_pie_data,
                             risk_pie_slices=risk_pie_slices)
    except Exception as e:
        traceback.print_exc()
        return "오류 발생: " + str(e), 500

@app.route('/analysis/opinion')
def analysis_opinion_fragment():
    """금융정보 검토 종합의견 프래그먼트 (종합분석 페이지 iframe용, 헤더·네비 없음)."""
    return render_template('opinion_fragment.html')

# 분석 API 라우트
@app.route('/api/analysis/summary')
@ensure_working_directory
def get_analysis_summary():
    """전체 통계 요약 (cash_after 기준). 합계건수=전체 행 수(은행거래+신용카드), 은행거래=은행거래 행 수, 신용카드=신용카드 행 수, 입금합계/출금합계=전체 합계, 순잔액=입금합계−출금합계."""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({
                'total_deposit': 0,
                'total_withdraw': 0,
                'net_balance': 0,
                'total_count': 0,
                'deposit_count': 0,
                'withdraw_count': 0
            })
        bank_filter = request.args.get('bank', '')
        if bank_filter and '금융사' in df.columns:
            df = df[df['금융사'].fillna('').astype(str).str.strip() == bank_filter]
        elif bank_filter and '은행명' in df.columns:
            df = df[df['은행명'] == bank_filter]

        # 금융정보 종합분석: 합계·건수는 위험도 0.1 이상만 반영
        if '위험도' in df.columns:
            try:
                risk = df['위험도'].fillna(0).astype(float)
                df = df.loc[risk >= 0.1]
            except (TypeError, ValueError):
                pass

        total_deposit = int(df['입금액'].sum()) if '입금액' in df.columns else 0
        total_withdraw = int(df['출금액'].sum()) if '출금액' in df.columns else 0
        net_balance = total_deposit - total_withdraw
        total_count = len(df)
        # 출처(은행거래/신용카드) 기준 건수·출금합계. 출처 없으면 금융사로 은행/신용 구분
        src_col = '출처' if '출처' in df.columns else '구분'
        if src_col in df.columns:
            src_trim = df[src_col].fillna('').astype(str).str.strip()
            bank_mask = src_trim == '은행거래'
            card_mask = src_trim == '신용카드'
            bank_count = int(bank_mask.sum())
            card_count = int(card_mask.sum())
            bank_withdraw = int(df.loc[bank_mask, '출금액'].sum()) if '출금액' in df.columns else 0
            card_withdraw = int(df.loc[card_mask, '출금액'].sum()) if '출금액' in df.columns else 0
        else:
            bank_count = card_count = 0
            bank_withdraw = card_withdraw = 0
        if (bank_count == 0 and card_count == 0) and total_count > 0 and '금융사' in df.columns:
            bank_names = {'국민은행', '신한은행', '하나은행'}
            gu = df['금융사'].fillna('').astype(str).str.strip()
            bank_count = int(gu.isin(bank_names).sum())
            card_count = total_count - bank_count
            bank_withdraw = int(df.loc[gu.isin(bank_names), '출금액'].sum()) if '출금액' in df.columns else 0
            card_withdraw = total_withdraw - bank_withdraw
        deposit_count = bank_count
        withdraw_count = card_count

        response = jsonify({
            'total_deposit': total_deposit,
            'total_withdraw': total_withdraw,
            'net_balance': net_balance,
            'total_count': total_count,
            'deposit_count': deposit_count,
            'withdraw_count': withdraw_count,
            'bank_count': bank_count,
            'bank_withdraw': bank_withdraw,
            'card_count': card_count,
            'card_withdraw': card_withdraw
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/by-category')
@ensure_working_directory
def get_analysis_by_category():
    """적요별 분석 (카테고리 파일 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'data': []})
        
        # 은행 필터: 은행전체일 경우 전체 집계, 특정 은행 선택 시 해당 은행 집계
        bank_filter = request.args.get('bank', '')
        if bank_filter:
            df = df[df['은행명'] == bank_filter]
        
        # 카테고리분류를 입출금으로 매핑
        if '카테고리분류' in df.columns and '입출금' not in df.columns:
            df['입출금'] = df['카테고리분류']
        
        # 카테고리 필터 (여러 필터 지원)
        classification_filter = request.args.get('입출금', '')
        transaction_type_filter = request.args.get('거래유형', '')
        transaction_target_filter = ''
        
        # 기존 방식 지원 (하위 호환성)
        category_type = request.args.get('category_type', '')
        category_value = request.args.get('category_value', '')
        if category_type and category_value:
            if category_type in df.columns:
                df = df[df[category_type] == category_value]
        
        # 새로운 방식 (여러 필터 동시 적용)
        if classification_filter and '입출금' in df.columns:
            df = df[df['입출금'] == classification_filter]
        if transaction_type_filter and '거래유형' in df.columns:
            df = df[df['거래유형'] == transaction_type_filter]
        
        # 적요별 입금/출금 집계 (입출금, 거래유형, 카테고리 정보도 포함)
        agg_dict = {
            '입금액': 'sum',
            '출금액': 'sum'
        }
        
        # 입출금, 거래유형, 카테고리, 은행명, 내용, 거래점이 있으면 첫 번째 값 사용 (대표값)
        if '입출금' in df.columns:
            agg_dict['입출금'] = 'first'
        if '거래유형' in df.columns:
            agg_dict['거래유형'] = 'first'
        if '카테고리' in df.columns:
            agg_dict['카테고리'] = 'first'
        if '은행명' in df.columns:
            agg_dict['은행명'] = 'first'
        if '내용' in df.columns:
            agg_dict['내용'] = 'first'
        if '거래점' in df.columns:
            agg_dict['거래점'] = 'first'
        
        category_stats = df.groupby('적요').agg(agg_dict).reset_index()
        
        # 차액 계산
        category_stats['차액'] = category_stats['입금액'] - category_stats['출금액']
        
        # 정렬: 차액 절대값 큰 순, 절대값 같으면 차액 큰 순, 차액 같으면 입금액 많은 순
        category_stats['차액_절대값'] = category_stats['차액'].abs()
        category_stats = category_stats.sort_values(['차액_절대값', '차액', '입금액'], ascending=[False, False, False])
        category_stats = category_stats.drop('차액_절대값', axis=1)
        
        # 데이터 포맷팅
        data = []
        for _, row in category_stats.iterrows():
            item = {
                'category': row['적요'] if pd.notna(row['적요']) and row['적요'] != '' else '(빈값)',
                'deposit': int(row['입금액']) if pd.notna(row['입금액']) else 0,
                'withdraw': int(row['출금액']) if pd.notna(row['출금액']) else 0,
                'balance': int(row['차액']) if pd.notna(row['차액']) else 0
            }
            # 입출금, 거래유형, 카테고리 정보 추가
            if '입출금' in row:
                item['classification'] = str(row['입출금']) if pd.notna(row['입출금']) and row['입출금'] != '' else '(빈값)'
            else:
                item['classification'] = '(빈값)'
            if '거래유형' in row:
                item['transactionType'] = str(row['거래유형']) if pd.notna(row['거래유형']) and row['거래유형'] != '' else '(빈값)'
            else:
                item['transactionType'] = '(빈값)'
            if '카테고리' in row:
                item['transactionTarget'] = str(row['카테고리']) if pd.notna(row['카테고리']) and row['카테고리'] != '' else '(빈값)'
            else:
                item['transactionTarget'] = '(빈값)'
            if '은행명' in row:
                item['bank'] = str(row['은행명']) if pd.notna(row['은행명']) and row['은행명'] != '' else '(빈값)'
            else:
                item['bank'] = '(빈값)'
            if '내용' in row:
                item['content'] = str(row['내용']) if pd.notna(row['내용']) and row['내용'] != '' else ''
            else:
                item['content'] = ''
            if '거래점' in row:
                item['transactionPoint'] = str(row['거래점']) if pd.notna(row['거래점']) and row['거래점'] != '' else ''
            else:
                item['transactionPoint'] = ''
            data.append(item)
        
        response = jsonify({'data': data})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/by-category-group')
@ensure_working_directory
def get_analysis_by_category_group():
    """카테고리 기준 분석 (입출금/거래유형/카테고리 기준 집계)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'data': []})
        
        # 카테고리분류를 입출금으로 매핑
        if '카테고리분류' in df.columns and '입출금' not in df.columns:
            df['입출금'] = df['카테고리분류']
        
        # 은행 필터
        bank_filter = request.args.get('bank', '')
        if bank_filter:
            df = df[df['은행명'] == bank_filter]
        
        # 카테고리 필터 (입출금/거래유형/카테고리)
        입출금_filter = request.args.get('입출금', '')
        거래유형_filter = request.args.get('거래유형', '')
        카테고리_filter = request.args.get('카테고리', '')
        if 입출금_filter and '입출금' in df.columns:
            df = df[df['입출금'] == 입출금_filter]
        if 거래유형_filter and '거래유형' in df.columns:
            df = df[df['거래유형'] == 거래유형_filter]
        if 카테고리_filter and '카테고리' in df.columns:
            df = df[df['카테고리'] == 카테고리_filter]
        groupby_columns = []
        if '입출금' in df.columns:
            groupby_columns.append('입출금')
        if '거래유형' in df.columns:
            groupby_columns.append('거래유형')
        if '카테고리' in df.columns:
            groupby_columns.append('카테고리')
        
        if not groupby_columns:
            return jsonify({'data': []})
        
        # 집계 (은행명도 포함하여 집계)
        category_stats = df.groupby(groupby_columns + ['은행명']).agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        
        # 차액 계산
        category_stats['차액'] = category_stats['입금액'] - category_stats['출금액']
        category_stats['총거래액'] = category_stats['입금액'] + category_stats['출금액']
        
        # 카테고리 그룹별로 다시 집계 (은행명은 가장 많은 거래가 있는 은행명 사용)
        category_final = []
        for category_group, group_df in category_stats.groupby(groupby_columns):
            # 가장 많은 거래액이 있는 은행명 선택
            main_bank_row = group_df.loc[group_df['총거래액'].idxmax()]
            main_bank = main_bank_row['은행명']
            
            # 카테고리 그룹별 합계
            total_deposit = group_df['입금액'].sum()
            total_withdraw = group_df['출금액'].sum()
            total_balance = total_deposit - total_withdraw
            
            item = {
                'deposit': int(total_deposit) if pd.notna(total_deposit) else 0,
                'withdraw': int(total_withdraw) if pd.notna(total_withdraw) else 0,
                'balance': int(total_balance) if pd.notna(total_balance) else 0,
                '은행명': str(main_bank) if pd.notna(main_bank) and main_bank != '' else '(빈값)'
            }
            
            # 각 카테고리 컬럼 추가
            if isinstance(category_group, tuple):
                for i, col in enumerate(groupby_columns):
                    value = category_group[i] if i < len(category_group) else None
                    if pd.notna(value) and value != '':
                        item[col] = str(value)
                    else:
                        item[col] = '(빈값)'
            else:
                if '입출금' in groupby_columns:
                    item['입출금'] = str(category_group) if pd.notna(category_group) and category_group != '' else '(빈값)'
                elif '거래유형' in groupby_columns:
                    item['거래유형'] = str(category_group) if pd.notna(category_group) and category_group != '' else '(빈값)'
                elif '카테고리' in groupby_columns:
                    item['카테고리'] = str(category_group) if pd.notna(category_group) and category_group != '' else '(빈값)'
            
            category_final.append(item)
        
        # 정렬: 차액 절대값 큰 순, 절대값 같으면 차액 큰 순, 차액 같으면 입금액 많은 순
        category_final_df = pd.DataFrame(category_final)
        category_final_df['차액_절대값'] = category_final_df['balance'].abs()
        category_final_df = category_final_df.sort_values(['차액_절대값', 'balance', 'deposit'], ascending=[False, False, False])
        category_final_df = category_final_df.drop('차액_절대값', axis=1)
        
        # 데이터 포맷팅
        data = category_final_df.to_dict('records')
        
        response = jsonify({'data': data})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/by-month')
@ensure_working_directory
def get_analysis_by_month():
    """월별 추이 분석 (카테고리 파일 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'months': [], 'deposit': [], 'withdraw': [], 'min_date': None, 'max_date': None})
        
        # 전체 데이터의 최소/최대 날짜 계산 (필터 적용 전)
        df_all = df.copy()
        df_all['거래일'] = pd.to_datetime(df_all['거래일'], errors='coerce')
        df_all = df_all[df_all['거래일'].notna()]
        min_date = df_all['거래일'].min()
        max_date = df_all['거래일'].max()
        
        # 은행 필터
        bank_filter = request.args.get('bank', '')
        if bank_filter:
            df = df[df['은행명'] == bank_filter]
        
        # 카테고리분류를 입출금으로 매핑
        if '카테고리분류' in df.columns and '입출금' not in df.columns:
            df['입출금'] = df['카테고리분류']
        
        # 카테고리 필터 (여러 필터 지원)
        classification_filter = request.args.get('입출금', '')
        transaction_type_filter = request.args.get('거래유형', '')
        transaction_target_filter = ''
        
        # 기존 방식 지원 (하위 호환성)
        category_type = request.args.get('category_type', '')
        category_value = request.args.get('category_value', '')
        if category_type and category_value:
            if category_type in df.columns:
                df = df[df[category_type] == category_value]
        
        # 새로운 방식 (여러 필터 동시 적용)
        if classification_filter and '입출금' in df.columns:
            df = df[df['입출금'] == classification_filter]
        if transaction_type_filter and '거래유형' in df.columns:
            df = df[df['거래유형'] == transaction_type_filter]
        
        df['거래일'] = pd.to_datetime(df['거래일'], errors='coerce')
        df = df[df['거래일'].notna()]
        df['거래월'] = df['거래일'].dt.to_period('M').astype(str)
        
        # 전체 기간의 모든 월 생성 (최소일부터 최대일까지)
        if pd.notna(min_date) and pd.notna(max_date):
            date_range = pd.period_range(start=min_date.to_period('M'), end=max_date.to_period('M'), freq='M')
            all_months = [str(period) for period in date_range]
        else:
            all_months = sorted(df['거래월'].unique().tolist())
        
        # 월별 집계
        monthly_stats = df.groupby('거래월').agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        
        # 모든 월에 대해 데이터 생성 (없는 월은 0)
        deposit_dict = dict(zip(monthly_stats['거래월'], monthly_stats['입금액']))
        withdraw_dict = dict(zip(monthly_stats['거래월'], monthly_stats['출금액']))
        
        deposit = [int(deposit_dict.get(month, 0)) if pd.notna(deposit_dict.get(month, 0)) else 0 for month in all_months]
        withdraw = [int(withdraw_dict.get(month, 0)) if pd.notna(withdraw_dict.get(month, 0)) else 0 for month in all_months]
        
        response = jsonify({
            'months': all_months,
            'deposit': deposit,
            'withdraw': withdraw,
            'min_date': str(min_date) if pd.notna(min_date) else None,
            'max_date': str(max_date) if pd.notna(max_date) else None
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/by-category-monthly')
@ensure_working_directory
def get_analysis_by_category_monthly():
    """카테고리별 월별 입출금 추이 분석"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'months': [], 'categories': []})
        
        # 카테고리분류를 입출금으로 매핑
        if '카테고리분류' in df.columns and '입출금' not in df.columns:
            df['입출금'] = df['카테고리분류']
        
        # 은행 필터
        bank_filter = request.args.get('bank', '')
        if bank_filter:
            df = df[df['은행명'] == bank_filter]
        
        # 카테고리 필터 (입출금/거래유형/카테고리)
        입출금_filter = request.args.get('입출금', '')
        거래유형_filter = request.args.get('거래유형', '')
        카테고리_filter = request.args.get('카테고리', '')
        if 입출금_filter and '입출금' in df.columns:
            df = df[df['입출금'] == 입출금_filter]
        if 거래유형_filter and '거래유형' in df.columns:
            df = df[df['거래유형'] == 거래유형_filter]
        if 카테고리_filter and '카테고리' in df.columns:
            df = df[df['카테고리'] == 카테고리_filter]
        df['거래일'] = pd.to_datetime(df['거래일'], errors='coerce')
        df = df[df['거래일'].notna()]
        df['거래월'] = df['거래일'].dt.to_period('M').astype(str)
        groupby_columns = []
        if '입출금' in df.columns:
            groupby_columns.append('입출금')
        if '거래유형' in df.columns:
            groupby_columns.append('거래유형')
        if '카테고리' in df.columns:
            groupby_columns.append('카테고리')
        
        if not groupby_columns:
            return jsonify({'months': [], 'categories': []})
        
        # 카테고리별 월별 집계
        monthly_by_category = df.groupby(groupby_columns + ['거래월']).agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        
        # 모든 월 목록 추출
        all_months = sorted(df['거래월'].unique().tolist())
        
        # 카테고리별 데이터 구성
        categories_data = []
        for category_group, group_df in monthly_by_category.groupby(groupby_columns):
            # 카테고리 라벨 생성 (거래유형/카테고리 포함)
            category_label_parts = []
            if isinstance(category_group, tuple):
                # 튜플인 경우 (여러 컬럼으로 그룹화된 경우)
                for i, col in enumerate(groupby_columns):
                    # 입출금은 제외하고 거래유형/카테고리 포함
                    if col in ['거래유형', '카테고리']:
                        value = category_group[i] if i < len(category_group) else None
                        if pd.notna(value) and value != '':
                            category_label_parts.append(str(value))
            else:
                # 단일 값인 경우 (거래유형/카테고리 중 하나)
                if pd.notna(category_group) and category_group != '':
                    category_label_parts.append(str(category_group))
            
            category_label = '_'.join(category_label_parts) if category_label_parts else '(빈값)'
            
            # 월별 데이터 매핑
            monthly_deposit = {}
            monthly_withdraw = {}
            for _, row in group_df.iterrows():
                month = row['거래월']
                monthly_deposit[month] = int(row['입금액']) if pd.notna(row['입금액']) else 0
                monthly_withdraw[month] = int(row['출금액']) if pd.notna(row['출금액']) else 0
            
            # 모든 월에 대해 데이터 생성 (없는 월은 0)
            deposit_data = [monthly_deposit.get(month, 0) for month in all_months]
            withdraw_data = [monthly_withdraw.get(month, 0) for month in all_months]
            
            # 총 입금액, 출금액, 차액 계산 (차액 절대값 기준 정렬용)
            total_deposit = sum(deposit_data)
            total_withdraw = sum(withdraw_data)
            total_balance = total_deposit - total_withdraw
            abs_balance = abs(total_balance)
            
            categories_data.append({
                'label': category_label,
                'deposit': deposit_data,
                'withdraw': withdraw_data,
                'total_deposit': total_deposit,
                'total_withdraw': total_withdraw,
                'total_balance': total_balance,
                'abs_balance': abs_balance
            })
        
        # 차액(절대값) 기준으로 정렬하고 상위 10개만 선택
        categories_data.sort(key=lambda x: x['abs_balance'], reverse=True)
        categories_data = categories_data[:10]
        
        response = jsonify({
            'months': all_months,
            'categories': categories_data
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e), 'months': [], 'categories': []}), 500

@app.route('/api/analysis/by-content')
@ensure_working_directory
def get_analysis_by_content():
    """내용별 분석"""
    try:
        df = load_processed_file()
        if df.empty:
            return jsonify({'deposit': [], 'withdraw': []})
        
        # 내용별 입금 (모든 거래처, 제한 없음)
        deposit_by_content = df.groupby('내용')['입금액'].sum().sort_values(ascending=False)
        deposit_data = [{'content': idx if idx else '(빈값)', 'amount': int(val)} for idx, val in deposit_by_content.items() if val > 0]
        
        # 내용별 출금 (모든 거래처, 제한 없음)
        withdraw_by_content = df.groupby('내용')['출금액'].sum().sort_values(ascending=False)
        withdraw_data = [{'content': idx if idx else '(빈값)', 'amount': int(val)} for idx, val in withdraw_by_content.items() if val > 0]
        
        response = jsonify({
            'deposit': deposit_data,
            'withdraw': withdraw_data
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/by-division')
@ensure_working_directory
def get_analysis_by_division():
    """구분별 분석"""
    try:
        df = load_processed_file()
        if df.empty:
            return jsonify({'data': []})
        
        division_stats = df.groupby('구분').agg({
            '입금액': 'sum',
            '출금액': 'sum',
            '거래일': 'count'
        }).reset_index()
        division_stats.columns = ['division', 'deposit', 'withdraw', 'count']
        division_stats = division_stats.fillna('')
        division_stats['deposit'] = division_stats['deposit'].astype(int)
        division_stats['withdraw'] = division_stats['withdraw'].astype(int)
        
        data = division_stats.to_dict('records')
        response = jsonify({'data': data})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/by-bank')
@ensure_working_directory
def get_analysis_by_bank():
    """은행/계좌별 분석 (카테고리 파일 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'bank': [], 'account': []})
        
        # 은행별 통계
        bank_stats = df.groupby('은행명').agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        bank_data = [{
            'bank': row['은행명'],
            'deposit': int(row['입금액']),
            'withdraw': int(row['출금액'])
        } for _, row in bank_stats.iterrows()]
        
        # 계좌별 통계
        account_stats = df.groupby(['은행명', '계좌번호']).agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        account_data = [{
            'bank': row['은행명'],
            'account': row['계좌번호'],
            'deposit': int(row['입금액']),
            'withdraw': int(row['출금액'])
        } for _, row in account_stats.iterrows()]
        
        response = jsonify({
            'bank': bank_data,
            'account': account_data
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/transactions-by-content')
@ensure_working_directory
def get_transactions_by_content():
    """거래처(내용)별 거래 내역"""
    try:
        df = load_processed_file()
        if df.empty:
            return jsonify({'deposit': [], 'withdraw': []})
        
        type_filter = request.args.get('type', 'deposit')  # 'deposit' or 'withdraw'
        limit = int(request.args.get('limit', 10))  # 상위 N개 거래처
        
        if type_filter == 'deposit':
            # 입금 상위 거래처
            top_contents = df[df['입금액'] > 0].groupby('내용')['입금액'].sum().sort_values(ascending=False).head(limit)
            top_content_list = top_contents.index.tolist()
            
            # 해당 거래처들의 모든 입금 거래 내역
            transactions = df[(df['내용'].isin(top_content_list)) & (df['입금액'] > 0)].copy()
            transactions = transactions.sort_values('입금액', ascending=False)
            
            transactions = transactions.where(pd.notna(transactions), None)
            data = transactions[['거래일', '은행명', '입금액', '구분', '적요', '내용', '거래점']].to_dict('records')
            data = _json_safe(data)
        else:
            top_contents = df[df['출금액'] > 0].groupby('내용')['출금액'].sum().sort_values(ascending=False).head(limit)
            top_content_list = top_contents.index.tolist()
            transactions = df[(df['내용'].isin(top_content_list)) & (df['출금액'] > 0)].copy()
            transactions = transactions.sort_values('출금액', ascending=False)
            transactions = transactions.where(pd.notna(transactions), None)
            data = transactions[['거래일', '은행명', '출금액', '구분', '적요', '내용', '거래점']].to_dict('records')
            data = _json_safe(data)
        response = jsonify({'data': data})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/transactions')
@ensure_working_directory
def get_analysis_transactions():
    """적요별 상세 거래 내역 반환 (카테고리 파일 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'data': [], 'deposit_total': 0, 'withdraw_total': 0, 'balance': 0, 'deposit_count': 0, 'withdraw_count': 0})
        
        transaction_type = request.args.get('type', 'deposit') # 'deposit' or 'withdraw'
        category_filter = request.args.get('category', '')  # 적요 필터
        content_filter = request.args.get('content', '')  # 거래처 필터 (하위 호환성)
        bank_filter = request.args.get('bank', '')
        
        # 적요 필터 우선, 없으면 거래처 필터 사용 (하위 호환성)
        if category_filter:
            filtered_df = df[df['적요'] == category_filter].copy()
        elif content_filter:
            filtered_df = df[df['내용'] == content_filter].copy()
        else:
            return jsonify({'data': [], 'deposit_total': 0, 'withdraw_total': 0, 'balance': 0, 'deposit_count': 0, 'withdraw_count': 0})
        
        # 은행 필터: 은행전체일 경우 전체 집계, 특정 은행 선택 시 해당 은행 집계
        if bank_filter:
            filtered_df = filtered_df[filtered_df['은행명'] == bank_filter].copy()
        
        # 카테고리 필터
        category_type = request.args.get('category_type', '')
        category_value = request.args.get('category_value', '')
        if category_type and category_value:
            if category_type in filtered_df.columns:
                filtered_df = filtered_df[filtered_df[category_type] == category_value].copy()
        
        # 적요별 입금/출금 합계 및 건수 계산
        deposit_total = filtered_df['입금액'].sum() if not filtered_df.empty else 0
        withdraw_total = filtered_df['출금액'].sum() if not filtered_df.empty else 0
        balance = deposit_total - withdraw_total
        deposit_count = len(filtered_df[filtered_df['입금액'] > 0]) if not filtered_df.empty else 0
        withdraw_count = len(filtered_df[filtered_df['출금액'] > 0]) if not filtered_df.empty else 0
        
        if transaction_type == 'detail':
            # 상세 모드: 거래일, 은행명, 입금액, 출금액, 내용
            detail_cols = ['거래일', '은행명', '입금액', '출금액']
            if '내용' in filtered_df.columns:
                detail_cols.append('내용')
            available_cols = [c for c in detail_cols if c in filtered_df.columns]
            result_df = filtered_df[available_cols].copy() if available_cols else filtered_df.copy()
        elif transaction_type == 'deposit':
            filtered_df = filtered_df[filtered_df['입금액'] > 0]
            # 필요한 컬럼만 선택
            result_df = filtered_df[['거래일', '은행명', '입금액', '구분', '적요', '내용', '거래점']].copy()
            result_df.rename(columns={'입금액': '금액'}, inplace=True)
        elif transaction_type == 'withdraw':
            filtered_df = filtered_df[filtered_df['출금액'] > 0]
            # 필요한 컬럼만 선택
            result_df = filtered_df[['거래일', '은행명', '출금액', '구분', '적요', '내용', '거래점']].copy()
            result_df.rename(columns={'출금액': '금액'}, inplace=True)
        else: # balance - 차액 상위순일 때는 입금과 출금 모두 표시
            # 입금과 출금이 모두 있는 행만 필터링
            deposit_df = filtered_df[filtered_df['입금액'] > 0].copy()
            withdraw_df = filtered_df[filtered_df['출금액'] > 0].copy()
            
            # 입금 데이터
            deposit_result = deposit_df[['거래일', '은행명', '입금액', '구분', '적요', '내용', '거래점']].copy()
            deposit_result.rename(columns={'입금액': '금액'}, inplace=True)
            deposit_result['거래유형'] = '입금'
            
            # 출금 데이터
            withdraw_result = withdraw_df[['거래일', '은행명', '출금액', '구분', '적요', '내용', '거래점']].copy()
            withdraw_result.rename(columns={'출금액': '금액'}, inplace=True)
            withdraw_result['거래유형'] = '출금'
            
            # 두 데이터프레임 합치기
            result_df = pd.concat([deposit_result, withdraw_result], ignore_index=True)
        
        # 거래일 순으로 정렬
        result_df = result_df.sort_values('거래일')
        
        result_df = result_df.where(pd.notna(result_df), None)
        data = result_df.to_dict('records')
        data = _json_safe(data)
        response = jsonify({
            'data': data,
            'deposit_total': int(deposit_total),
            'withdraw_total': int(withdraw_total),
            'balance': int(balance),
            'deposit_count': int(deposit_count),
            'withdraw_count': int(withdraw_count)
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/content-by-category')
@ensure_working_directory
def get_content_by_category():
    """적요별 거래처 목록 반환"""
    try:
        df = load_processed_file()
        if df.empty:
            return jsonify({'data': []})
        
        category_filter = request.args.get('category', '')
        
        if not category_filter:
            return jsonify({'data': []})
        
        # 적요별 입금 거래처 집계
        filtered_df = df[(df['적요'] == category_filter) & (df['입금액'] > 0)].copy()
        
        if filtered_df.empty:
            return jsonify({'data': []})
        
        # 거래처별 입금액 합계
        content_stats = filtered_df.groupby('내용')['입금액'].sum().sort_values(ascending=False).reset_index()
        
        data = []
        for _, row in content_stats.iterrows():
            data.append({
                'content': row['내용'] if pd.notna(row['내용']) and row['내용'] != '' else '(빈값)',
                'amount': int(row['입금액']) if pd.notna(row['입금액']) else 0
            })
        
        response = jsonify({'data': data})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/cash-after-date-range')
@ensure_working_directory
def get_cash_after_date_range():
    """cash_after 전체의 최소/최대 거래일 반환. 월별 입출금 추이 그래프 x축(시작일~종료일)용."""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'min_date': None, 'max_date': None})
        if '거래일' not in df.columns:
            return jsonify({'min_date': None, 'max_date': None})
        df = df.copy()
        df['거래일'] = pd.to_datetime(df['거래일'], errors='coerce')
        df = df[df['거래일'].notna()]
        if df.empty:
            return jsonify({'min_date': None, 'max_date': None})
        min_date = df['거래일'].min()
        max_date = df['거래일'].max()
        response = jsonify({
            'min_date': min_date.strftime('%Y-%m-%d') if pd.notna(min_date) else None,
            'max_date': max_date.strftime('%Y-%m-%d') if pd.notna(max_date) else None
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e), 'min_date': None, 'max_date': None}), 500


@app.route('/api/analysis/date-range')
@ensure_working_directory
def get_date_range():
    """전처리후 데이터의 최소/최대 거래일 반환"""
    try:
        df = load_processed_file()
        if df.empty:
            return jsonify({'min_date': None, 'max_date': None})
        
        # 거래일 컬럼 확인
        if '거래일' not in df.columns:
            return jsonify({'min_date': None, 'max_date': None})
        
        # 거래일을 날짜 형식으로 변환
        df['거래일'] = pd.to_datetime(df['거래일'], errors='coerce')
        df = df[df['거래일'].notna()]
        
        if df.empty:
            return jsonify({'min_date': None, 'max_date': None})
        
        min_date = df['거래일'].min()
        max_date = df['거래일'].max()
        
        response = jsonify({
            'min_date': min_date.strftime('%Y-%m-%d') if pd.notna(min_date) else None,
            'max_date': max_date.strftime('%Y-%m-%d') if pd.notna(max_date) else None
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e), 'min_date': None, 'max_date': None}), 500

# ----- API: cash_after 생성 (병합) -----
@app.route('/api/generate-category', methods=['POST'])
@ensure_working_directory
def generate_category():
    """cash_after 생성: bank_after + card_after 병합 후 linkage·위험도 적용. 임시 파일 쓰고 원자적 교체."""
    global _cash_after_log_path_request
    try:
        # 요청 처리 중에는 cwd=MyCash이므로 여기서 로그 경로 고정 (같은 파일에 확실히 기록)
        _cash_after_log_path_request = os.path.join(os.getcwd(), "cash_after_progress.log")
        _ensure_progress_log_file()
        _log_cash_after("API /api/generate-category 호출됨")
        ok, err_msg = merge_bank_card_to_cash_after()
        if not ok:
            return jsonify({
                'success': False,
                'error': err_msg or '카테고리 분류 중 오류가 발생했습니다.'
            }), 500
        output_path = Path(CASH_AFTER_PATH)
        if output_path.exists():
            try:
                if safe_read_data_json and CASH_AFTER_PATH.endswith('.json'):
                    df = safe_read_data_json(CASH_AFTER_PATH, default_empty=True)
                else:
                    df = pd.read_excel(str(output_path), engine='openpyxl')
                return jsonify({
                    'success': True,
                    'message': f'카테고리 생성 완료: {len(df)}건',
                    'count': len(df)
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'cash_after 파일을 읽을 수 없습니다: {str(e)}'
                }), 500
        return jsonify({
            'success': False,
            'error': f'cash_after 파일이 생성되지 않았습니다. 경로: {output_path}'
        }), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        _cash_after_log_path_request = None

@app.route('/help')
def help():
    """금융정보 도움말 페이지"""
    return render_template('help.html')

# 서버 기동 시 로그 파일이 있도록 미리 생성 (경로: MyCash/cash_after_progress.log)
_ensure_progress_log_file()

if __name__ == '__main__':
    # 현재 디렉토리를 스크립트 위치로 변경
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    app.run(debug=True, port=5001, host='127.0.0.1')
