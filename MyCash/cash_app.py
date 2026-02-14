# -*- coding: utf-8 -*-
from flask import Flask, render_template, jsonify, request, make_response, redirect
import traceback
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import io
import os
import shutil
from functools import wraps
from datetime import datetime

# UTF-8 인코딩 설정 (Windows 콘솔용)
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

# 스크립트 디렉토리 (모듈 로드 시 한 번만 계산)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, '..'))
# category: MyInfo/info_category.xlsx 하나만 사용
INFO_CATEGORY_PATH = str(Path(PROJECT_ROOT) / 'info_category.xlsx')
# 원본 업로드용: .source/Cash. after: MyCash 폴더 (cash_before 미사용)
SOURCE_CASH_DIR = os.path.join(PROJECT_ROOT, '.source', 'Cash')
CASH_AFTER_PATH = os.path.join(SCRIPT_DIR, 'cash_after.xlsx')
# 금융정보(MyCash): card·cash 테이블 연동만 하지 않음. 은행/카드 데이터 불러와 병합(cash_after 생성)은 진행.
MYCASH_ONLY_NO_BANK_CARD_LINK = False
# 금융정보 전처리전/전처리후: 은행거래·신용카드 after 파일 (MYCASH_ONLY_NO_BANK_CARD_LINK 시 미사용)
BANK_AFTER_PATH = Path(PROJECT_ROOT) / 'MyBank' / 'bank_after.xlsx'
CARD_AFTER_PATH = Path(PROJECT_ROOT) / 'MyCard' / 'card_after.xlsx'

# 전처리전(은행거래) 출력 컬럼 · 계좌번호 1.0, 기타거래 2.0 (index.html LEFT_WIDTHS) — bank_after의 기타거래 출력
BANK_AFTER_DISPLAY_COLUMNS = ['은행명', '계좌번호', '거래일', '거래시간', '입금액', '출금액', '취소', '기타거래', '카테고리']
# 전처리후(신용카드) 출력 컬럼 · 카드번호 1.0, 가맹점명 2.0 (index.html RIGHT_WIDTHS) — card_after의 가맹점명 출력
CARD_AFTER_DISPLAY_COLUMNS = ['카드사', '카드번호', '이용일', '이용시간', '입금액', '출금액', '취소', '가맹점명', '카테고리']
# 카테고리조회(cash_after) 테이블 출력 11컬럼 · 계좌번호 1.0, 기타거래 2.0 (index.html QUERY_WIDTHS)
CATEGORY_QUERY_DISPLAY_COLUMNS = ['금융사', '계좌번호', '거래일', '거래시간', '입금액', '출금액', '취소', '기타거래', '키워드', '카테고리', '사업자번호']
# 카테고리 적용후(cash_after) 테이블 출력 15컬럼 · 사업자번호 뒤 구분(폐업만), 업종코드, 업종분류, 위험도
CATEGORY_APPLIED_DISPLAY_COLUMNS = ['금융사', '계좌번호', '거래일', '거래시간', '입금액', '출금액', '취소', '기타거래', '키워드', '카테고리', '사업자번호', '구분', '업종코드', '업종분류', '위험도']
# cash_after 생성 시 저장 컬럼. 구분 = '폐업' 또는 ''
CASH_AFTER_CREATION_COLUMNS = ['금융사', '계좌번호', '거래일', '거래시간', '입금액', '출금액', '취소', '기타거래', '키워드', '카테고리', '사업자번호', '구분', '업종코드', '업종분류', '위험도']
# info_category.xlsx 단일 테이블(구분 없음, info_category_io로 읽기/쓰기)
try:
    from info_category_io import (
        load_info_category, normalize_category_df, INFO_CATEGORY_COLUMNS,
        get_category_table as _io_get_category_table,
        apply_category_action,
    )
except ImportError:
    def load_info_category(path, default_empty=True):
        if not path or not Path(path).exists(): return pd.DataFrame(columns=['분류', '키워드', '카테고리']) if default_empty else None
        return pd.read_excel(path, engine='openpyxl')
    def normalize_category_df(df):
        if df is None or df.empty: return pd.DataFrame(columns=['분류', '키워드', '카테고리'])
        df = df.copy().fillna(''); df = df.drop(columns=['구분'], errors='ignore')
        for c in ['분류', '키워드', '카테고리']: df[c] = df[c] if c in df.columns else ''
        return df[['분류', '키워드', '카테고리']].copy()
    INFO_CATEGORY_COLUMNS = ['분류', '키워드', '카테고리']

    def _io_get_category_table(path):
        cols = INFO_CATEGORY_COLUMNS
        pe = bool(path and os.path.exists(path) and os.path.getsize(path) > 0)
        if not pe: return (pd.DataFrame(columns=cols), False)
        full = load_info_category(path, default_empty=True)
        if full is None or full.empty: return (pd.DataFrame(columns=cols), pe)
        df = normalize_category_df(full).fillna('')
        for c in cols: df[c] = df[c] if c in df.columns else ''
        return (df, pe)

    def _n(v):
        import unicodedata
        if v is None or (isinstance(v, str) and not str(v).strip()): return '' if v is None else v
        return unicodedata.normalize('NFKC', str(v).strip())
    _VALID = ('전처리', '후처리', '계정과목', '업종분류', '신용카드', '가상자산', '증권투자', '해외송금', '심야구분', '금전대부')

    def apply_category_action(path, action, data):
        try:
            df, _ = _io_get_category_table(path)
            df = df.fillna('')
            if action == 'add':
                v = _n(data.get('분류', '')).strip()
                if v and v not in _VALID: return (False, f'분류는 {", ".join(_VALID)}만 입력할 수 있습니다.', 0)
                df = pd.concat([df, pd.DataFrame([{'분류': _n(data.get('분류','')), '키워드': _n(data.get('키워드','')), '카테고리': _n(data.get('카테고리',''))}])], ignore_index=True)
            elif action == 'update':
                o1, o2, o3 = data.get('original_분류',''), data.get('original_키워드',''), data.get('original_카테고리','')
                v = _n(data.get('분류','')).strip()
                if v and v not in _VALID: return (False, f'분류는 {", ".join(_VALID)}만 입력할 수 있습니다.', 0)
                mask = (df['분류']==o1)&(df['키워드']==o2)&(df['카테고리']==o3)
                if mask.any(): df.loc[mask, '분류'], df.loc[mask, '키워드'], df.loc[mask, '카테고리'] = v, _n(data.get('키워드','')), _n(data.get('카테고리',''))
                else: return (False, '수정할 데이터를 찾을 수 없습니다.', 0)
            elif action == 'delete':
                df = df[~((df['분류']==data.get('original_분류',data.get('분류','')))&(df['키워드']==data.get('original_키워드',data.get('키워드','')))&(df['카테고리']==data.get('original_카테고리',data.get('카테고리',''))))]
            else: return (False, f'unknown action: {action}', 0)
            df.to_excel(str(path), index=False, engine='openpyxl')
            return (True, None, len(df))
        except Exception as e: return (False, str(e), 0)

# 전처리후 은행 필터: 드롭다운 값 → 실제 데이터에 있을 수 있는 은행명 별칭
# 적용 위치: get_processed_data() 등에서 사용하는 DataFrame의 '은행명' 컬럼 (금융정보는 cash_after 기준)
BANK_FILTER_ALIASES = {
    '국민은행': ['국민은행', 'KB국민은행', '한국주택은행', '국민', '국민 은행'],
    '신한은행': ['신한은행', '신한'],
    '하나은행': ['하나은행', '하나'],
}

def ensure_working_directory(func):
    """데코레이터: API 엔드포인트에서 작업 디렉토리를 스크립트 위치로 보장"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        original_cwd = os.getcwd()
        try:
            os.chdir(SCRIPT_DIR)
            return func(*args, **kwargs)
        finally:
            os.chdir(original_cwd)
    return wrapper

def _json_safe(obj):
    """JSON 직렬화: NaN/NaT, numpy, datetime → Python 타입"""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(x) for x in obj]
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

def load_category_file():
    """카테고리 적용 파일 로드 (MyCash/cash_after.xlsx). cash_after는 금융사 컬럼이면 은행명으로 복사해 API 호환."""
    try:
        category_file = Path(CASH_AFTER_PATH)
        if category_file.exists():
            try:
                df = pd.read_excel(str(category_file), engine='openpyxl')
                if not df.empty and '은행명' not in df.columns and '금융사' in df.columns:
                    df = df.copy()
                    df['은행명'] = df['금융사'].fillna('').astype(str).str.strip()
                return df
            except Exception as e:
                print(f"Error reading {category_file}: {str(e)}")
                return pd.DataFrame()
        return pd.DataFrame()
    except Exception as e:
        print(f"Error in load_category_file: {str(e)}")
        return pd.DataFrame()

def load_bank_after_file():
    """전처리전(은행거래)용: MyBank/bank_after.xlsx 로드. 출력용 컬럼만 정규화하여 반환."""
    try:
        path = BANK_AFTER_PATH
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_excel(str(path), engine='openpyxl')
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
        print(f"오류: bank_after.xlsx 로드 실패 - {e}", flush=True)
        return pd.DataFrame()

def load_card_after_file():
    """전처리후(신용카드)용: MyCard/card_after.xlsx 로드. 출력용 컬럼만 정규화하여 반환."""
    try:
        path = CARD_AFTER_PATH
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_excel(str(path), engine='openpyxl')
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
        print(f"오류: card_after.xlsx 로드 실패 - {e}", flush=True)
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


def _dataframe_to_cash_after_creation(df_bank, df_card):
    """은행거래(bank_after) + 신용카드(card_after)를 통합하여 cash_after 생성용 DataFrame 반환. 키워드는 bank/card에서 반드시 복사."""
    rows = []
    def add_bank():
        if df_bank is None or df_bank.empty:
            return
        kw_col = '키워드' if '키워드' in df_bank.columns else None
        has_업종코드 = '업종코드' in df_bank.columns
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
                '업종코드': _str_strip(r.get('업종코드')) if has_업종코드 else '',
                '업종분류': '',
                '위험도': '',
            })
    def add_card():
        if df_card is None or df_card.empty:
            return
        kw_col = '키워드' if '키워드' in df_card.columns else None
        has_업종코드 = '업종코드' in df_card.columns
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
                '업종코드': _str_strip(r.get('업종코드')) if has_업종코드 else '',
                '업종분류': '',
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


def _apply_업종분류_from_category(df):
    """cash_after DataFrame에 대해: 업종코드가 있는 행은 info_category.xlsx의 업종분류(분류='업종분류')에서
    키워드와 매칭하여 카테고리를 업종분류에 채우고, 위험도는 매칭 시 5, 미매칭/업종코드 없음 시 0. in-place 수정."""
    if df is None or df.empty or '업종코드' not in df.columns:
        return
    try:
        cat_df = load_info_category(INFO_CATEGORY_PATH, default_empty=True)
        if cat_df is None or cat_df.empty or '분류' not in cat_df.columns:
            return
        cat_df = normalize_category_df(cat_df)
        업종분류_rows = cat_df[cat_df['분류'].fillna('').astype(str).str.strip() == '업종분류']
        if 업종분류_rows.empty:
            return
        # 키워드가 '552201/552202' 형태일 수 있음 → 각 코드별로 카테고리 매핑 (먼저 나온 것 우선)
        code_to_category = {}
        for _, r in 업종분류_rows.iterrows():
            kw = (r.get('키워드') or '')
            if isinstance(kw, float) and pd.isna(kw):
                kw = ''
            kw = str(kw).strip()
            cat = (r.get('카테고리') or '')
            if isinstance(cat, float) and pd.isna(cat):
                cat = ''
            cat = str(cat).strip()
            for part in kw.replace(' ', '').split('/'):
                code = part.strip()
                if code and code not in code_to_category:
                    code_to_category[code] = cat
        if not code_to_category:
            return
        # 각 행: 업종코드가 있으면 매칭 후 업종분류·위험도 설정
        codes = df['업종코드'].fillna('').astype(str).str.strip()
        for i in df.index:
            c = codes.at[i] if i in codes.index else ''
            if c:
                업종분류_val = code_to_category.get(c, '')
                위험도_val = 5 if 업종분류_val else 0
                df.at[i, '업종분류'] = 업종분류_val
                df.at[i, '위험도'] = 위험도_val
            else:
                df.at[i, '위험도'] = 0
    except Exception as e:
        print(f"업종분류 매칭 적용 중 오류(무시): {e}", flush=True)


# 금융정보 고급분석: 가상자산·증권투자·금전대부 매칭 시 위험도 5.0
RISK_CATEGORY_CHASU = ('가상자산', '증권투자', '금전대부')


def _apply_risk_category_by_keywords(df):
    """cash_after DataFrame에 대해: info_category의 가상자산/증권투자/금전대부 규칙으로
    기타거래·키워드·금융사 텍스트를 매칭하여 업종분류·위험도 5.0 설정. in-place 수정."""
    if df is None or df.empty:
        return
    try:
        cat_df = load_info_category(INFO_CATEGORY_PATH, default_empty=True)
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
                        df.at[i, '업종분류'] = cat
                        df.at[i, '위험도'] = 5.0
                        break
                else:
                    continue
                break
    except Exception as e:
        print(f"고위험 분류(가상자산/증권/금전대부) 매칭 적용 중 오류(무시): {e}", flush=True)


def _load_bank_after_for_merge():
    """cash_after 병합용: MyBank/bank_after.xlsx 전체 컬럼 로드. 키워드 컬럼이 반드시 있도록 보장하고 NaN은 ''로 채움."""
    try:
        if not BANK_AFTER_PATH.exists():
            return pd.DataFrame()
        df = pd.read_excel(str(BANK_AFTER_PATH), engine='openpyxl')
        if df.empty:
            return df
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
        print(f"오류: bank_after.xlsx 병합용 로드 실패 - {e}", flush=True)
        return pd.DataFrame()

def merge_bank_card_to_cash_after():
    """bank_after.xlsx + card_after.xlsx를 병합하여 cash_after.xlsx 생성.
    은행거래/신용카드의 키워드·카테고리를 그대로 저장(키워드는 _load_bank_after_for_merge로 풀 컬럼 로드). 성공 시 True.
    기존 cash_after.xlsx가 있으면 백업(cash_after_backup_YYYYMMDD_HHMMSS.xlsx) 후 재생성."""
    try:
        category_file = Path(CASH_AFTER_PATH)
        if category_file.exists() and category_file.stat().st_size > 0:
            backup_dir = category_file.parent
            backup_name = f"cash_after_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            backup_path = backup_dir / backup_name
            shutil.copy2(str(category_file), str(backup_path))
            print(f"기존 cash_after.xlsx 백업: {backup_path}", flush=True)
        df_bank = _load_bank_after_for_merge()
        df_card_raw = pd.DataFrame()
        if CARD_AFTER_PATH.exists():
            try:
                df_card_raw = pd.read_excel(str(CARD_AFTER_PATH), engine='openpyxl')
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
            except Exception:
                pass
        if df_bank.empty and df_card_raw.empty:
            return (False, 'bank_after.xlsx와 card_after.xlsx가 모두 없거나 비어 있어 병합할 수 없습니다. 은행·신용카드 전처리에서 각각 생성 후 시도하세요.')
        df = _dataframe_to_cash_after_creation(df_bank, df_card_raw if not df_card_raw.empty else None)
        if df.empty:
            return (False, '병합 결과 데이터가 비어 있습니다.')
        _apply_업종분류_from_category(df)
        _apply_risk_category_by_keywords(df)
        df.to_excel(str(CASH_AFTER_PATH), index=False, engine='openpyxl')
        return (True, None)
    except Exception as e:
        print(f"오류: cash_after.xlsx 병합 생성 실패 - {e}", flush=True)
        traceback.print_exc()
        return (False, str(e))

@app.route('/')
def index():
    workspace_path = str(SCRIPT_DIR)  # 전처리전 작업폴더(MyCash 경로)
    resp = make_response(render_template('index.html', workspace_path=workspace_path))
    # 전처리 페이지 캐시 방지: 네비게이션 갱신이 바로 반영되도록
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/source-files')
@ensure_working_directory
def get_source_files():
    """원본 파일 목록 반환. MyInfo/.source/Cash 의 .xls, .xlsx만 취급."""
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

@app.route('/api/category-applied-data')
@ensure_working_directory
def get_category_applied_data():
    """카테고리 적용된 데이터 반환 (필터링 지원). cash_after.xlsx 존재하면 사용만, 없으면 생성하지 않음. 생성은 /api/generate-category(생성 필터)에서 백업 후 수행."""
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
        
        # 통합 컬럼 정규화: 은행명/카드사 → 금융사, 계좌번호/카드번호 → 계좌번호, 거래일/이용일 → 거래일, 거래시간/이용시간 → 거래시간, 기타거래/가맹점명 → 기타거래
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
        
        # 행 정렬: 거래일 → 거래시간 → 금융사
        sort_cols = [c for c in ['거래일', '거래시간', '금융사'] if c in df.columns]
        if sort_cols:
            try:
                df = df.sort_values(by=sort_cols, na_position='last')
            except Exception:
                pass
        # 카테고리 적용후 테이블 출력 15컬럼 (구분, 업종코드, 업종분류, 위험도 포함)
        for c in CATEGORY_APPLIED_DISPLAY_COLUMNS:
            if c not in df.columns:
                df[c] = '' if c not in ('입금액', '출금액') else 0
        df = df[CATEGORY_APPLIED_DISPLAY_COLUMNS].copy()
        
        # 필수 컬럼 확인
        required_columns = ['입금액', '출금액']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns and not df.empty:
            for col in missing_columns:
                df[col] = 0
        
        # 집계 계산
        count = len(df)
        deposit_amount = df['입금액'].sum() if not df.empty and '입금액' in df.columns else 0
        withdraw_amount = df['출금액'].sum() if not df.empty and '출금액' in df.columns else 0
        
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

# 카테고리: MyInfo/info_category.xlsx 단일 테이블(구분 없음)
@app.route('/api/bank_category')
@ensure_working_directory
def get_category_table():
    """info_category.xlsx 전체 반환 (구분 없음)."""
    path = str(Path(INFO_CATEGORY_PATH))
    try:
        _path_added = False
        try:
            _dir_str = str(SCRIPT_DIR)
            if _dir_str not in sys.path:
                sys.path.insert(0, _dir_str)
                _path_added = True
            import process_cash_data as _pbd
            _pbd.ensure_all_cash_files()
        except Exception:
            pass
        finally:
            if _path_added and str(SCRIPT_DIR) in sys.path:
                sys.path.remove(str(SCRIPT_DIR))
        df, _ = _io_get_category_table(path)
        data = df.to_dict('records')
        response = jsonify({
            'data': data,
            'columns': ['분류', '키워드', '카테고리'],
            'count': len(df),
            'file_exists': True
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        response = jsonify({
            'error': str(e),
            'data': [],
            'file_exists': Path(INFO_CATEGORY_PATH).exists()
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500

@app.route('/api/bank_category', methods=['POST'])
@ensure_working_directory
def save_category_table():
    """info_category.xlsx 전체 갱신 (구분 없음)"""
    path = str(Path(INFO_CATEGORY_PATH))
    try:
        data = request.json or {}
        action = data.get('action', 'add')
        success, error_msg, count = apply_category_action(path, action, data)
        if not success:
            return jsonify({'success': False, 'error': error_msg}), 400
        try:
            from info_category_defaults import sync_category_create_from_xlsx
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
@app.route('/analysis/basic')
def analysis_basic():
    """기본 기능 분석 페이지"""
    return render_template('analysis_basic.html')

@app.route('/analysis/print')
def print_analysis_redirect():
    """구 URL 호환: /analysis/print → /analysis/basic 리다이렉트"""
    return redirect('/cash/analysis/basic', code=302)

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
        if bank_filter and '은행명' in df.columns:
            df = df[df['은행명'] == bank_filter]

        total_deposit = df['입금액'].sum()
        total_withdraw = df['출금액'].sum()
        net_balance = total_deposit - total_withdraw
        # 거래건수 = 은행거래 건수 + 신용카드 건수
        total_count = len(df)
        # 입금건수 = 은행거래 건수, 출금건수 = 신용카드 건수. 구분에 은행/신용카드 없으면 입금·출금 건수로 대체
        if '구분' in df.columns and ((df['구분'].fillna('').astype(str).str.strip() == '은행거래').any() or (df['구분'].fillna('').astype(str).str.strip() == '신용카드').any()):
            deposit_count = int((df['구분'].fillna('').astype(str).str.strip() == '은행거래').sum())
            withdraw_count = int((df['구분'].fillna('').astype(str).str.strip() == '신용카드').sum())
        else:
            deposit_count = len(df[df['입금액'] > 0])
            withdraw_count = len(df[df['출금액'] > 0])

        response = jsonify({
            'total_deposit': int(total_deposit),
            'total_withdraw': int(total_withdraw),
            'net_balance': int(net_balance),
            'total_count': total_count,
            'deposit_count': deposit_count,
            'withdraw_count': withdraw_count
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

@app.route('/api/generate-category', methods=['POST'])
@ensure_working_directory
def generate_category():
    """cash_after.xlsx 생성: 은행(bank_after) + 신용카드(card_after) 병합."""
    try:
        output_path = Path(CASH_AFTER_PATH)
        if output_path.exists() and output_path.stat().st_size > 0:
            try:
                bak_path = output_path.with_suffix(output_path.suffix + '.bak')
                shutil.copy2(str(output_path), str(bak_path))
            except Exception:
                pass
        ok, err_msg = merge_bank_card_to_cash_after()
        if not ok:
            return jsonify({
                'success': False,
                'error': err_msg or '카테고리 분류 중 오류가 발생했습니다.'
            }), 500
        output_path = Path(CASH_AFTER_PATH)
        if output_path.exists():
            try:
                df = pd.read_excel(str(output_path), engine='openpyxl')
                return jsonify({
                    'success': True,
                    'message': f'카테고리 생성 완료: {len(df)}건',
                    'count': len(df)
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'cash_after.xlsx 파일을 읽을 수 없습니다: {str(e)}'
                }), 500
        return jsonify({
            'success': False,
            'error': f'cash_after.xlsx 파일이 생성되지 않았습니다. 경로: {output_path}'
        }), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/help')
def help():
    """금융거래 고급분석 페이지"""
    return render_template('help.html')

if __name__ == '__main__':
    # 현재 디렉토리를 스크립트 위치로 변경
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    app.run(debug=True, port=5001, host='127.0.0.1')
