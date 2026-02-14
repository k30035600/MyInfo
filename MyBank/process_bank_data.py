# -*- coding: utf-8 -*-
"""
process_bank_data.py — 은행용 코드 전용. (카드 관련 역할 없음)

[역할]
- 은행 파일 통합: .source 폴더의 은행 엑셀을 모아 bank_before.xlsx 생성
- 카테고리: MyInfo/info_category.xlsx(은행거래 구분) 사용
- 분류·저장: bank_before → bank_after.xlsx (전처리/후처리·계정과목 적용)

.source는 .xls, .xlsx만 취급. (파일명에 국민/신한/하나 포함)
"""
import pandas as pd
import os
import re
import sys
import time
import unicodedata
import zipfile
from pathlib import Path

# Windows 한글 깨짐 방지: 콘솔 코드페이지만 UTF-8(65001) 설정 (stdout 교체 시 버퍼 닫힘 주의)
if sys.platform == 'win32':
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:
        pass

# =========================================================
# 기본 설정
# =========================================================

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.environ.get('MYINFO_ROOT') or os.path.normpath(os.path.join(_SCRIPT_DIR, '..'))
INFO_CATEGORY_FILE = os.path.join(_PROJECT_ROOT, 'info_category.xlsx') if _PROJECT_ROOT else None
# info_category.xlsx 손상 방지: 원자적 쓰기(임시파일+replace)+락
if _PROJECT_ROOT and _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
try:
    from info_category_defaults import get_default_rules
except ImportError:
    get_default_rules = None
try:
    from info_category_io import (
        safe_write_info_category_xlsx,
        load_info_category,
        create_empty_info_category,
        normalize_category_df,
        normalize_주식회사_for_match,
        INFO_CATEGORY_COLUMNS,
    )
except ImportError:
    def safe_write_info_category_xlsx(path, df, engine='openpyxl'):
        df.to_excel(path, index=False, engine=engine)
    def load_info_category(path, default_empty=True):
        if not path or not os.path.exists(path): return pd.DataFrame(columns=['분류', '키워드', '카테고리']) if default_empty else None
        return pd.read_excel(path, engine='openpyxl')
    def create_empty_info_category(path):
        pd.DataFrame(columns=['분류', '키워드', '카테고리']).to_excel(path, index=False, engine='openpyxl')
    def normalize_category_df(df):
        if df is None or df.empty: return pd.DataFrame(columns=['분류', '키워드', '카테고리'])
        df = df.fillna(''); df = df.drop(columns=['구분'], errors='ignore')
        for c in ['분류', '키워드', '카테고리']: df[c] = df[c] if c in df.columns else ''
        return df[['분류', '키워드', '카테고리']].copy()
    INFO_CATEGORY_COLUMNS = ['분류', '키워드', '카테고리']
    def normalize_주식회사_for_match(text):
        if text is None or (isinstance(text, str) and not str(text).strip()):
            return '' if text is None else str(text).strip()
        val = str(text).strip()
        val = re.sub(r'[\s/]*주식회사[\s/]*', '(주)', val)
        val = re.sub(r'[\s/]*㈜[\s/]*', '(주)', val)
        val = re.sub(r'(\(주\)[\s/]*)+', '(주)', val)
        return val
# 원본 은행 파일: .source/Bank. before/after: MyBank 폴더
SOURCE_BANK_DIR = os.path.join(_PROJECT_ROOT, '.source', 'Bank') if _PROJECT_ROOT else None
INPUT_FILE = os.path.join(_SCRIPT_DIR, 'bank_before.xlsx')
OUTPUT_FILE = os.path.join(_SCRIPT_DIR, 'bank_after.xlsx')


def _is_bad_zip_error(e):
    msg = str(e).lower()
    return isinstance(e, zipfile.BadZipFile) or 'not a zip file' in msg or 'bad zip' in msg


def _safe_read_excel(path, default_empty=True):
    """손상된 xlsx(not a zip file, decompress 오류 등) 시 빈 DataFrame 반환."""
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame() if default_empty else None
    try:
        return pd.read_excel(path, engine='openpyxl')
    except Exception as e:
        msg = str(e).lower()
        if (_is_bad_zip_error(e) or 'zip' in msg or 'not a zip' in msg or 'bad zip' in msg
                or 'decompress' in msg or 'invalid block' in msg or 'error -3' in msg):
            return pd.DataFrame() if default_empty else None
        raise


def _bank_before_is_empty():
    """bank_before가 없거나, 0바이트이거나, 데이터 행이 없으면 True."""
    if not os.path.exists(INPUT_FILE):
        return True
    if os.path.getsize(INPUT_FILE) == 0:
        return True
    df = _safe_read_excel(INPUT_FILE, default_empty=True)
    if df is None or df.empty:
        return True
    if len(df) <= 1:
        return True
    return False


def ensure_all_bank_files():
    """bank_before, info_category, bank_after 파일이 없으면 생성. 있으면 그대로 사용. before/after는 MyBank 폴더."""
    # 1. bank_before.xlsx: 없거나 비어 있으면 .source/Bank 통합 실행
    empty = _bank_before_is_empty()
    if empty:
        integrate_bank_transactions()
        return

    # 2. info_category.xlsx: 없으면 생성, 손상 시 백업 후 재생성, 있으면 마이그레이션(거래방법/거래지점 행 제거)
    if not INFO_CATEGORY_FILE:
        pass
    elif not os.path.exists(INFO_CATEGORY_FILE):
        try:
            df = _safe_read_excel(INPUT_FILE, default_empty=True)
            if df is not None and not df.empty:
                create_category_table(df)
            else:
                create_empty_info_category(INFO_CATEGORY_FILE)
        except Exception as e:
            print(f"오류: info_category 생성 실패 - {e}")
    else:
        # 파일 존재: 읽기 시도 후 손상이면 백업하고 기본 파일 재생성
        full = load_info_category(INFO_CATEGORY_FILE, default_empty=True)
        if (full is None or full.empty) and os.path.getsize(INFO_CATEGORY_FILE) > 0:
            try:
                import shutil
                backup_path = INFO_CATEGORY_FILE + '.bak'
                shutil.move(INFO_CATEGORY_FILE, backup_path)
                df = _safe_read_excel(INPUT_FILE, default_empty=True)
                create_category_table(df if df is not None and not df.empty else pd.DataFrame())
            except Exception as e:
                print(f"오류: info_category 손상 복구 실패 - {e}", flush=True)
        elif full is not None and not full.empty:
            try:
                migrate_bank_category_file(INFO_CATEGORY_FILE)
            except Exception as e:
                if not _is_bad_zip_error(e):
                    print(f"오류: info_category 마이그레이션 실패 - {e}")

    # 3. bank_after.xlsx: 없으면 생성
    if not os.path.exists(OUTPUT_FILE):
        try:
            classify_and_save()
        except Exception as e:
            print(f"오류: bank_after.xlsx 생성 실패 - {e}")


# =========================================================
# 유틸리티 함수
# =========================================================

def safe_str(value):
    """NaN 값 처리 및 안전한 문자열 변환. 전처리/후처리 매칭용으로 주식회사·㈜ → (주) 통일."""
    if pd.isna(value) or value is None:
        return ""
    val = str(value).strip()
    if val.lower() in ['nan', 'na', 'n', 'none', '']:
        return ""
    val = normalize_주식회사_for_match(val)
    val = val.replace('((', '(')
    val = val.replace('))', ')')
    val = val.replace('__', '_')
    val = val.replace('{}', '')
    if val.count('(') != val.count(')'):
        if val.count('(') > val.count(')'):
            val = val.replace('(', '')
        elif val.count(')') > val.count('('):
            val = val.replace(')', '')
    return val

def normalize_text(text):
    """텍스트 정규화 (대소문자 구분)"""
    if not text:
        return ""
    return str(text).strip()

def clean_amount(value):
    """금액 데이터 정리 (쉼표 제거, 숫자 변환)"""
    if pd.isna(value) or value == '' or value == 0:
        return 0
    if isinstance(value, (int, float)):
        return float(value)
    value_str = str(value).replace(',', '').strip()
    if value_str == '' or value_str == '-':
        return 0
    try:
        return float(value_str)
    except (ValueError, TypeError):
        return 0

def safe_write_excel(df, filepath, max_retries=3):
    """파일 쓰기 시 권한 오류 방지를 위한 안전한 쓰기 함수"""
    for attempt in range(max_retries):
        try:
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    time.sleep(0.1)
                except PermissionError:
                    if attempt < max_retries - 1:
                        time.sleep(0.5)
                        continue
                    else:
                        raise PermissionError(f"파일을 삭제할 수 없습니다: {filepath}")
            
            df.to_excel(filepath, index=False, engine='openpyxl')
            return True
        except PermissionError as e:
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue
            else:
                raise e
        except Exception as e:
            raise e
    return False

# 마지막 통합 실패 시 오류 메시지 (bank_app에서 안내용)
LAST_INTEGRATE_ERROR = None
# 마지막 카테고리 분류(bank_after) 실패 시 오류 메시지
LAST_CLASSIFY_ERROR = None

# =========================================================
# 1. 은행 파일 읽기 함수들 (integrate_bank_transactions.py)
# =========================================================

def _excel_engine(path):
    """파일 확장자에 맞는 엔진 반환. .xls → xlrd, .xlsx → openpyxl"""
    suf = (path.suffix if hasattr(path, 'suffix') else os.path.splitext(str(path))[1]).lower()
    return 'xlrd' if suf == '.xls' else 'openpyxl'

def read_kb_file_excel(file_path):
    """국민은행 Excel(.xlsx) 파일 읽기."""
    path = Path(file_path)
    engine = _excel_engine(path)
    xls = pd.ExcelFile(file_path, engine=engine)
    all_data = []
    for sheet_name in xls.sheet_names:
        df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, engine=engine)
        header_row = None
        for idx in range(min(15, len(df_raw))):
            cell = df_raw.iloc[idx, 0]
            if pd.notna(cell) and ('거래일시' in str(cell) or '거래일자' in str(cell)):
                header_row = idx
                break
        if header_row is None:
            continue
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row, engine=engine)
        date_col = None
        for c in df.columns:
            s = str(c)
            if '거래일시' in s or '거래일자' in s:
                date_col = c
                break
        if date_col is None:
            continue
        df = df[df[date_col].notna()].copy()
        df = df[df[date_col].astype(str).str.strip() != ''].copy()
        df = df[df[date_col].astype(str) != '합계'].copy()

        account_number = None
        df_info = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=10, engine=engine)
        for idx in range(len(df_info)):
            for col in df_info.columns:
                value = str(df_info.iloc[idx, col])
                if '계좌번호' in value or '285102' in value:
                    m = re.search(r'(\d{6}-\d{2}-\d{6})', value)
                    if m:
                        account_number = m.group(1)
                    break
            if account_number:
                break
        if not account_number:
            m = re.search(r'(\d{6}-\d{2}-\d{6})', str(file_path))
            if m:
                account_number = m.group(1)

        bank_name = '국민은행'
        if '거래일시' in str(date_col):
            df['거래일'] = df[date_col].astype(str).str.split(' ').str[0]
            df['거래시간'] = df[date_col].astype(str).str.split(' ').str[1]
            df['거래시간'] = df['거래시간'].fillna('')
        else:
            df['거래일'] = df[date_col].astype(str)
            df['거래시간'] = ''

        result_df = pd.DataFrame()
        result_df['거래일'] = df['거래일']
        result_df['거래시간'] = df['거래시간']
        result_df['적요'] = df['적요'] if '적요' in df.columns else ''
        result_df['출금액'] = df['출금액'] if '출금액' in df.columns else 0
        result_df['입금액'] = df['입금액'] if '입금액' in df.columns else 0
        result_df['잔액'] = df['잔액'] if '잔액' in df.columns else 0
        result_df['거래점'] = df['거래점'] if '거래점' in df.columns else ''
        result_df['취소'] = df['구분'] if '구분' in df.columns else (df['취소'] if '취소' in df.columns else '')
        content_col = None
        for c in df.columns:
            if '보낸분' in str(c) or '받는분' in str(c) or '내용' in str(c):
                content_col = c
                break
        result_df['내용'] = df[content_col].fillna('') if content_col else ''
        result_df['송금메모'] = df['송금메모'].fillna('') if '송금메모' in df.columns else ''
        result_df['메모'] = df['메모'].fillna('') if '메모' in df.columns else ''
        result_df['은행명'] = bank_name
        result_df['계좌번호'] = account_number
        result_df = result_df[result_df['거래일'].notna()].copy()
        result_df = result_df[result_df['거래일'].astype(str).str.strip() != ''].copy()
        all_data.append(result_df)

    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return None

def read_sh_file(file_path):
    """신한은행 파일 읽기 (.xls, .xlsx). .xls는 xlrd 필요."""
    path = Path(file_path)
    engine = _excel_engine(path)
    xls = pd.ExcelFile(file_path, engine=engine)
    all_data = []
    
    for sheet_name in xls.sheet_names:
        df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, engine=engine)
        header_row = None
        for idx in range(min(15, len(df_raw))):
            if pd.notna(df_raw.iloc[idx, 0]) and '거래일자' in str(df_raw.iloc[idx, 0]):
                header_row = idx
                break
        
        if header_row is None:
            continue
        
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row, engine=engine)
        df = df[df['거래일자'].notna()].copy()
        df = df[df['거래일자'] != ''].copy()
        
        account_number = None
        df_info = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=5, engine=engine)
        for idx in range(len(df_info)):
            for col in df_info.columns:
                value = str(df_info.iloc[idx, col])
                if '계좌번호' in value or '110-478' in value:
                    match = re.search(r'(\d{3}-\d{3}-\d{6})', value)
                    if match:
                        account_number = match.group(1)
                    break
            if account_number:
                break
        
        if not account_number:
            match = re.search(r'(\d{3}-\d{3}-\d{6})', str(file_path))
            if match:
                account_number = match.group(1)
        
        bank_name = '신한은행'
        
        result_df = pd.DataFrame(index=df.index)
        result_df['거래일'] = df['거래일자'] if '거래일자' in df.columns else ''
        result_df['거래시간'] = df['거래시간'].fillna('') if '거래시간' in df.columns else ''
        result_df['적요'] = df['적요'] if '적요' in df.columns else ''
        result_df['출금액'] = df['출금(원)'] if '출금(원)' in df.columns else (df['출금액'] if '출금액' in df.columns else 0)
        result_df['입금액'] = df['입금(원)'] if '입금(원)' in df.columns else (df['입금액'] if '입금액' in df.columns else 0)
        result_df['잔액'] = df['잔액(원)'] if '잔액(원)' in df.columns else (df['잔액'] if '잔액' in df.columns else 0)
        result_df['거래점'] = df['거래점'] if '거래점' in df.columns else ''
        result_df['취소'] = ''
        
        if '내용' in df.columns:
            result_df['내용'] = df['내용'].fillna('')
        else:
            content_found = False
            for col in df.columns:
                col_str = str(col).lower()
                if any(keyword in col_str for keyword in ['내용', '거래처', '상대방', '받는분', '보낸분', '거래상대방']):
                    result_df['내용'] = df[col].fillna('')
                    content_found = True
                    break
            
            if not content_found and len(df.columns) > 5:
                result_df['내용'] = df[df.columns[5]].fillna('')
            elif not content_found and len(df.columns) > 4:
                result_df['내용'] = df[df.columns[4]].fillna('')
            else:
                result_df['내용'] = ''
        
        result_df['송금메모'] = ''
        result_df['메모'] = df['메모'].fillna('') if '메모' in df.columns else ''
        result_df['은행명'] = bank_name
        result_df['계좌번호'] = account_number
        
        result_df = result_df[result_df['거래일'].notna()].copy()
        result_df = result_df[result_df['거래일'] != ''].copy()
        
        all_data.append(result_df)
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return None

def read_hana_file(file_path):
    """하나은행 파일 읽기 (.xls, .xlsx). .xls는 xlrd 필요."""
    path = Path(file_path)
    engine = _excel_engine(path)
    xls = pd.ExcelFile(file_path, engine=engine)
    all_data = []
    
    for sheet_name in xls.sheet_names:
        df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, engine=engine)
        header_row = None
        for idx in range(min(15, len(df_raw))):
            if pd.notna(df_raw.iloc[idx, 0]) and ('거래일시' in str(df_raw.iloc[idx, 0]) or '거래일' in str(df_raw.iloc[idx, 0])):
                header_row = idx
                break
        
        if header_row is None:
            continue
        
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row, engine=engine)
        df = df[df['거래일시'].notna()].copy()
        
        account_number = None
        df_info = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=5, engine=engine)
        for idx in range(len(df_info)):
            for col in df_info.columns:
                value = str(df_info.iloc[idx, col])
                if '계좌번호' in value or '433-910' in value:
                    match = re.search(r'(\d{3}-\d{6}-\d{5})', value)
                    if match:
                        account_number = match.group(1)
                    break
            if account_number:
                break
        
        if not account_number:
            match = re.search(r'(\d{3}-\d{6}-\d{5})', str(file_path))
            if match:
                account_number = match.group(1)
        
        bank_name = '하나은행'
        
        df['거래일'] = df['거래일시'].astype(str).str.split(' ').str[0]
        df['거래시간'] = df['거래일시'].astype(str).str.split(' ').str[1]
        df['거래시간'] = df['거래시간'].fillna('')
        
        df = df[df['거래일'].notna()].copy()
        df = df[df['거래일'] != ''].copy()
        
        result_df = pd.DataFrame()
        result_df['거래일'] = df['거래일']
        result_df['거래시간'] = df['거래시간']
        result_df['적요'] = df['적요'] if '적요' in df.columns else ''
        result_df['출금액'] = df['출금액'] if '출금액' in df.columns else 0
        result_df['입금액'] = df['입금액'] if '입금액' in df.columns else 0
        result_df['잔액'] = df['잔액'] if '잔액' in df.columns else 0
        result_df['거래점'] = df['거래점'] if '거래점' in df.columns else ''
        result_df['취소'] = ''
        result_df['내용'] = df['내용'].fillna('') if '내용' in df.columns else ''
        result_df['송금메모'] = ''
        result_df['메모'] = ''
        result_df['은행명'] = bank_name
        result_df['계좌번호'] = account_number
        
        all_data.append(result_df)
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return None

# =========================================================
# 2. 은행 파일 통합 함수 (integrate_bank_transactions.py)
# =========================================================

def _bank_excel_files(source_dir):
    """ .source 폴더에서 은행 거래 .xls, .xlsx 파일 목록. .xls, .xlsx만 취급. (파일명에 국민/신한/하나 포함)"""
    out = []
    if not source_dir.exists():
        return out
    for ext in ('*.xls', '*.xlsx'):
        for p in source_dir.glob(ext):
            n = p.name
            if '국민은행' in n or '신한은행' in n or '하나은행' in n:
                out.append(p)
    return sorted(set(out), key=lambda p: (p.name, str(p)))

def integrate_bank_transactions(output_file=None):
    """ .source/Bank 폴더의 은행 파일들을 통합하여 bank_before.xlsx 생성. .xls, .xlsx만 취급."""
    if output_file is None:
        output_file = INPUT_FILE

    source_dir = Path(os.path.abspath(SOURCE_BANK_DIR)) if SOURCE_BANK_DIR else Path('.source', 'Bank').resolve()
    if not source_dir.exists():
        try:
            source_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"오류: .source/Bank 폴더 생성 실패 - {source_dir}: {e}", flush=True)
    global LAST_INTEGRATE_ERROR
    LAST_INTEGRATE_ERROR = None
    all_data = []
    read_errors = []
    bank_files = _bank_excel_files(source_dir)
    all_xls_xlsx = list(source_dir.glob('*.xls')) + list(source_dir.glob('*.xlsx')) if source_dir.exists() else []
    if not bank_files:
        if all_xls_xlsx:
            LAST_INTEGRATE_ERROR = (
                '파일명에 국민은행, 신한은행, 하나은행 중 하나가 포함되어야 합니다. '
                f'(현재 .source/Bank에 .xls/.xlsx {len(all_xls_xlsx)}개 있으나 해당하는 파일 없음)'
            )
        print(f"[경고] 은행 파일이 없습니다. 경로 확인: {source_dir}", flush=True)

    for file_path in bank_files:
        name = file_path.name
        suf = file_path.suffix.lower()
        try:
            if '국민은행' in name:
                if suf == '.xlsx':
                    df = read_kb_file_excel(file_path)
                else:
                    continue  # 국민은행 .xls 미지원, .xlsx만 사용
            elif '신한은행' in name:
                df = read_sh_file(file_path)
            elif '하나은행' in name:
                df = read_hana_file(file_path)
            else:
                df = None
            if df is not None and len(df) > 0:
                all_data.append(df)
        except Exception as e:
            err_str = str(e).strip()
            if 'xlrd' in err_str or 'No module' in err_str:
                err_str = err_str + ' ( .xls 파일은 pip install xlrd 필요 )'
            read_errors.append(f"{name}: {err_str}")
            print(f"오류: {name} 처리 실패 - {e}", flush=True)
            import traceback
            traceback.print_exc()
    if bank_files and not all_data and read_errors:
        LAST_INTEGRATE_ERROR = ' | '.join(read_errors[:5])
        if len(read_errors) > 5:
            LAST_INTEGRATE_ERROR += f' ... 외 {len(read_errors)-5}건'
    elif bank_files and not all_data:
        # 예외 없이 스킵됐거나 빈 DataFrame 반환된 경우 (파일명·형식·시트 구조 등)
        LAST_INTEGRATE_ERROR = (
            '파일명에 국민은행/신한은행/하나은행이 포함되어야 합니다. '
            '국민은행은 .xlsx만 지원(.xls 미지원). '
            '또는 파일을 읽었지만 데이터 행이 없거나 시트 구조가 맞지 않습니다.'
        )
        print(f"[경고] .source/Bank 파일 {len(bank_files)}개 중 읽기 성공한 데이터가 없습니다. 위 오류를 확인하세요.", flush=True)

    if not all_data:
        combined_df = pd.DataFrame(columns=['거래일', '거래시간', '은행명', '계좌번호', '입금액', '출금액', '잔액',
                                           '취소', '적요', '내용', '송금메모', '거래점'])
        combined_df.to_excel(output_file, index=False, engine='openpyxl')
        try:
            classify_and_save(input_file=output_file, output_file=OUTPUT_FILE)
        except Exception as e:
            print(f"오류: bank_after.xlsx 생성 실패 (빈 통합) - {e}")
        return combined_df

    combined_df = pd.concat(all_data, ignore_index=True)

    # 금액 데이터 정리
    combined_df['출금액'] = combined_df['출금액'].apply(clean_amount)
    combined_df['입금액'] = combined_df['입금액'].apply(clean_amount)
    combined_df['잔액'] = combined_df['잔액'].apply(clean_amount)

    # 정렬
    combined_df['거래일_정렬용'] = pd.to_datetime(combined_df['거래일'], errors='coerce')
    combined_df = combined_df.sort_values(['거래일_정렬용', '거래시간', '은행명', '계좌번호'], na_position='last')
    combined_df = combined_df.drop('거래일_정렬용', axis=1)

    # 거래일이 없는 행 제거
    combined_df = combined_df[combined_df['거래일'].notna()].copy()
    combined_df = combined_df[combined_df['거래일'] != ''].copy()

    # 메모/카테고리 컬럼 제거 (bank_before에는 포함하지 않음)
    combined_df = combined_df.drop(columns=['메모', '카테고리'], errors='ignore')

    # 적요/내용/송금메모/거래점: 전각→반각 변환
    for col in ['적요', '내용', '송금메모', '거래점']:
        if col in combined_df.columns:
            combined_df[col] = combined_df[col].fillna('').astype(str).apply(
                lambda s: unicodedata.normalize('NFKC', s) if s else ''
            )

    # 적요의 "-"를 공백으로 변경
    if '적요' in combined_df.columns:
        combined_df['적요'] = combined_df['적요'].astype(str).str.replace('-', ' ', regex=False)

    # bank_before 생성 시 컬럼명 통일: 구분 → 취소 (소스에 구분만 있는 경우 대비)
    if '구분' in combined_df.columns and '취소' not in combined_df.columns:
        combined_df = combined_df.rename(columns={'구분': '취소'})
    elif '구분' in combined_df.columns and '취소' in combined_df.columns:
        combined_df = combined_df.drop(columns=['구분'], errors='ignore')

    # 취소 컬럼에 "취소된 거래"는 "취소"로 변경 (bank_after에서 검색 문자열로 사용)
    if '취소' in combined_df.columns:
        combined_df['취소'] = combined_df['취소'].astype(str).str.replace('취소된 거래', '취소', regex=False)

    # 적요/내용/송금메모가 모두 비어있으면 거래점을 송금메모에 저장
    if all(c in combined_df.columns for c in ['적요', '내용', '송금메모', '거래점']):
        empty_mask = (
            combined_df['적요'].fillna('').astype(str).str.strip() == ''
        ) & (
            combined_df['내용'].fillna('').astype(str).str.strip() == ''
        ) & (
            combined_df['송금메모'].fillna('').astype(str).str.strip() == ''
        ) & (
            combined_df['거래점'].fillna('').astype(str).str.strip() != ''
        )
        combined_df.loc[empty_mask, '송금메모'] = combined_df.loc[empty_mask, '거래점']

    # 컬럼 순서 정리 (메모/카테고리 제외)
    column_order = ['거래일', '거래시간', '은행명', '계좌번호', '입금액', '출금액', '잔액',
                   '취소', '적요', '내용', '송금메모', '거래점']
    existing_columns = [col for col in column_order if col in combined_df.columns]
    for col in combined_df.columns:
        if col not in existing_columns:
            existing_columns.append(col)
    combined_df = combined_df[existing_columns]

    # 파일 저장 (bank_before에는 키워드/카테고리 분류 없음; after 생성 시에만 참여)
    combined_df.to_excel(output_file, index=False, engine='openpyxl')

    # bank_after.xlsx 생성 시 info_category 사용·키워드/카테고리 분류 적용
    try:
        classify_and_save(input_file=output_file, output_file=OUTPUT_FILE)
    except Exception as e:
        print(f"오류: bank_after.xlsx 생성 실패 - {e}")

    return combined_df


# =========================================================
# 3. 카테고리 테이블 생성 (info_category.xlsx 단일 테이블, 구분 없음)
# 전처리, 후처리, 계정과목만 사용 (거래방법/거래지점 미사용)
# category_create.md 파싱 또는 info_category_defaults 코드 기본값 사용
# =========================================================


def create_category_table(df):
    """bank_before 데이터를 기반으로 info_category.xlsx 생성(구분 없음). 전처리·후처리·계정과목만 사용."""
    load_rules = get_default_rules
    if load_rules is None:
        from info_category_defaults import get_default_rules as load_rules
    unique_category_data = load_rules('bank')

    # DataFrame 생성 (get_default_rules에서 이미 중복 제거됨)
    category_df = pd.DataFrame(unique_category_data)
    category_df = category_df.drop_duplicates(subset=['분류', '키워드', '카테고리'], keep='first')

    try:
        if len(category_df) == 0:
            category_df = pd.DataFrame(columns=INFO_CATEGORY_COLUMNS)
        out = category_df[INFO_CATEGORY_COLUMNS].copy()
        if os.path.exists(INFO_CATEGORY_FILE):
            full = load_info_category(INFO_CATEGORY_FILE, default_empty=True)
            if full is not None and not full.empty:
                full = normalize_category_df(full)
                if not full.empty:
                    out = pd.concat([full, out], ignore_index=True).drop_duplicates(subset=INFO_CATEGORY_COLUMNS, keep='first')
        safe_write_info_category_xlsx(INFO_CATEGORY_FILE, out)
        if not os.path.exists(INFO_CATEGORY_FILE):
            raise FileNotFoundError(f"오류: 파일 생성 후에도 {INFO_CATEGORY_FILE} 파일이 존재하지 않습니다.")
    except PermissionError as e:
        print(f"오류: 파일 쓰기 권한이 없습니다 - {INFO_CATEGORY_FILE}")
        raise
    except Exception as e:
        print(f"오류: info_category 생성 실패 - {e}")
        raise

    return category_df


def migrate_bank_category_file(category_filepath=None):
    """info_category에서 거래방법/거래지점 행 제거, 계정과목 보강 후 저장 (구분 없음)."""
    path = str(Path(category_filepath).resolve()) if category_filepath else (INFO_CATEGORY_FILE or '')
    if not path or not os.path.exists(path):
        return
    full_df = load_info_category(path, default_empty=True)
    if full_df is None or full_df.empty:
        return
    category_df = normalize_category_df(full_df)
    if category_df.empty:
        return
    분류_col = category_df['분류'].astype(str).str.strip()
    keep_mask = ~분류_col.isin(['거래방법', '거래지점'])
    migrated_df = category_df.loc[keep_mask].copy()
    계정과목_mask = (migrated_df['분류'].astype(str).str.strip() == '계정과목')
    if not 계정과목_mask.any() or 계정과목_mask.sum() < 10:
        account_rows = pd.DataFrame(_DEFAULT_BANK_ACCOUNT_RULES)
        existing_account = migrated_df[계정과목_mask] if 계정과목_mask.any() else pd.DataFrame(columns=INFO_CATEGORY_COLUMNS)
        other_rows = migrated_df[~계정과목_mask]
        combined = pd.concat([existing_account, account_rows], ignore_index=True).drop_duplicates(subset=INFO_CATEGORY_COLUMNS, keep='first')
        migrated_df = pd.concat([other_rows, combined], ignore_index=True)
    migrated_df = migrated_df.drop_duplicates(subset=INFO_CATEGORY_COLUMNS, keep='first')
    try:
        safe_write_info_category_xlsx(path, migrated_df)
    except Exception as e:
        print(f"오류: info_category 마이그레이션 저장 실패 - {e}")
        raise


def _bank_row_search_text(row):
    """카테고리 매칭용 검색 문자열 생성 (취소, 적요, 내용, 송금메모, 거래점, 메모). 공백 정규화하여 키워드 매칭률 향상."""
    parts = []
    for col in ['취소', '적요', '내용', '송금메모', '거래점', '메모']:
        parts.append(safe_str(row.get(col, '')))
    text = '#'.join(p for p in parts if p)
    # 연속 공백 1개로 축소 (Excel/복사 시 공백 차이 보정)
    if text:
        text = re.sub(r'\s+', ' ', text).strip()
    return text


def apply_category_from_bank(df, category_df):
    """계정과목 규칙 적용: 기타거래를 맨 처음 할당한 뒤, 계정과목에 매칭되면 해당 계정과목으로 덮어씀.
    기타거래 컬럼만 사용해 키워드 매칭."""
    if df is None or df.empty or category_df is None or category_df.empty:
        return df
    need_cols = ['분류', '키워드', '카테고리']
    category_df = category_df.copy()
    category_df.columns = [str(c).strip() for c in category_df.columns]
    if not all(c in category_df.columns for c in need_cols):
        return df
    # 계정과목만 사용
    account_df = category_df[category_df['분류'].astype(str).str.strip() == '계정과목'].copy()
    if account_df.empty:
        return df
    if '카테고리' not in df.columns:
        df = df.copy()
        df['카테고리'] = ''
    if '키워드' not in df.columns:
        df['키워드'] = ''
    df = df.copy()
    df['카테고리'] = df['카테고리'].astype(object)
    df['키워드'] = df['키워드'].astype(object)
    if '기타거래' not in df.columns:
        return df
    search_series = df['기타거래'].fillna('').astype(str)

    # 1단계: 먼저 전체를 '기타거래'로 할당
    df['카테고리'] = '기타거래'

    # 2단계: 행별 최대 키워드 길이 기준 정렬(긴 것 먼저). 매칭된 키워드가 더 긴 경우에만 덮어씀.
    account_df = account_df.copy()

    def _max_kw_len(s):
        parts = [k.strip() for k in str(s).split('/') if k.strip()]
        return max(len(k) for k in parts) if parts else 0
    account_df['_max_klen'] = account_df['키워드'].apply(_max_kw_len)
    account_df = account_df.sort_values('_max_klen', ascending=False).drop(columns=['_max_klen'], errors='ignore')

    df['_matched_kw_len'] = 0
    for _, cat_row in account_df.iterrows():
        cat_val = safe_str(cat_row.get('카테고리', '')).strip() or '기타거래'
        keywords_str = safe_str(cat_row.get('키워드', ''))
        if not keywords_str:
            continue
        keywords = [re.sub(r'\s+', ' ', k.strip()) for k in keywords_str.split('/') if k.strip()]
        if not keywords:
            continue
        rule_match = pd.Series(False, index=df.index)
        for kw in keywords:
            if kw:
                rule_match |= search_series.str.contains(re.escape(kw), regex=False, na=False)
        # 행별로 매칭된 키워드 중 가장 긴 것
        def longest_matched(text):
            t = str(text)
            matched = [k for k in keywords if k and k in t]
            return max(matched, key=len) if matched else ''
        matched_kw = search_series.apply(longest_matched)
        matched_len = matched_kw.str.len()
        fill_mask = rule_match & (
            (df['카테고리'].fillna('').astype(str) == '기타거래') | (matched_len > df['_matched_kw_len'])
        )
        if fill_mask.any():
            df.loc[fill_mask, '카테고리'] = cat_val
            df.loc[fill_mask, '키워드'] = matched_kw.loc[fill_mask]
            df.loc[fill_mask, '_matched_kw_len'] = matched_len.loc[fill_mask]
    df = df.drop(columns=['_matched_kw_len'], errors='ignore')
    return df


# =========================================================
# 4. 분류 함수들 (classify_category.py, create_bank_after.py)
# =========================================================

def create_before_text(row):
    """before_text 생성"""
    bank_name = safe_str(row.get("은행명", ""))
    parts = []

    적요 = safe_str(row.get("적요", ""))
    if not 적요 and bank_name:
        적요 = bank_name
    parts.append(적요)

    내용 = safe_str(row.get("내용", ""))
    if not 내용 and bank_name:
        내용 = bank_name
    parts.append(내용)

    parts.append(safe_str(row.get("송금메모", "")))
    # 거래점은 카테고리 매칭용 검색 문자열에서 제외

    return "#".join([p for p in parts if p])

def classify_1st_category(row):
    """입출금 분류: 입금/출금/취소"""
    before_text = safe_str(row.get("before_text", ""))
    취소_val = safe_str(row.get("취소", ""))

    if "취소" in before_text or "취소된 거래" in before_text:
        return "취소"
    if "취소" in 취소_val or "취소된 거래" in 취소_val:
        return "취소"

    in_amt = row.get("입금액", 0) or 0
    out_amt = row.get("출금액", 0) or 0

    if out_amt > 0:
        return "출금"
    return "입금"

def classify_2_chasu(row_idx, df, category_tables, create_before_text_func):
    """전처리 분류 (계좌번호 등). 카테고리 키워드도 주식회사→(주) 정규화해 매칭."""
    row = df.iloc[row_idx]
    before_text_raw = row.get("before_text", "")
    before_text = normalize_text(before_text_raw)

    if "전처리" in category_tables:
        category_table = category_tables["전처리"]
        category_rows_list = list(category_table.iterrows())
        sorted_rows = sorted(category_rows_list, key=lambda x: len(str(x[1].get("키워드", ""))), reverse=True)

        for _, cat_row in sorted_rows:
            keyword_raw = cat_row.get("키워드", "")
            if pd.isna(keyword_raw) or not keyword_raw:
                continue

            keyword = normalize_text(keyword_raw)
            keyword_norm = normalize_주식회사_for_match(keyword)

            if keyword_norm and before_text and keyword_norm in before_text:
                category_raw = cat_row.get("카테고리", "")
                if pd.notna(category_raw):
                    category_str = str(category_raw).strip()
                    if category_str:
                        for col in ['적요', '내용', '송금메모']:
                            if col in df.columns:
                                cell_value = safe_str(df.iloc[row_idx].get(col, ""))
                                if keyword_norm in normalize_text(cell_value):
                                    df.at[row_idx, col] = category_str
                                    break
                        df.at[row_idx, "before_text"] = create_before_text_func(df.iloc[row_idx])
                        updated_text = normalize_text(df.iloc[row_idx].get("before_text", ""))
                        updated_text = updated_text.replace(keyword_norm, "").strip()
                        df.at[row_idx, "before_text"] = updated_text
                break


def apply_후처리_bank(df, category_tables):
    """은행거래 후처리: info_category 후처리 규칙으로 적요/내용/송금메모 컬럼의 키워드 → 카테고리 치환."""
    if df is None or df.empty or "후처리" not in category_tables:
        return df
    category_table = category_tables["후처리"]
    if category_table is None or category_table.empty:
        return df
    rules = []
    for _, row in category_table.iterrows():
        kw = str(row.get("키워드", "")).strip()
        cat = str(row.get("카테고리", "")).strip() if pd.notna(row.get("카테고리")) else ""
        if kw:
            kw_norm = normalize_주식회사_for_match(kw)
            if kw_norm:
                rules.append((kw_norm, cat))
    rules.sort(key=lambda x: len(x[0]), reverse=True)
    if not rules:
        return df
    df = df.copy()
    for col in ['적요', '내용', '송금메모']:
        if col not in df.columns:
            continue
        for kw_norm, cat in rules:
            df[col] = df[col].fillna('').astype(str).str.replace(re.escape(kw_norm), cat, regex=True)
    return df


def compute_기타거래(row):
    """기타거래: 취소(비어있지 않으면 '취소'만)/적요/내용/송금메모를 '_'로 연결, 중복 단어 제거, 연속 '_'·공백 정리. (거래점 제외)
    단, 취소/적요/내용/송금메모가 모두 스페이스나 널이면 거래점을 송금메모로 사용."""
    parts = []
    취소 = safe_str(row.get('취소', '')).strip()
    적요 = safe_str(row.get('적요', '')).strip()
    내용 = safe_str(row.get('내용', '')).strip()
    송금메모 = safe_str(row.get('송금메모', '')).strip()
    거래점 = safe_str(row.get('거래점', '')).strip()
    if not 취소 and not 적요 and not 내용 and not 송금메모 and 거래점:
        송금메모 = 거래점
    if 취소:
        parts.append('취소')
    for val in (적요, 내용, 송금메모):
        if val:
            parts.append(val)
    s = '_'.join(parts)
    # 중복 단어: 공백·'_'로 나눈 단어 중 처음 나온 것만 유지
    tokens = [w for w in re.split(r'[\s_]+', s) if w]
    seen = set()
    unique = []
    for w in tokens:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    s = '_'.join(unique)
    # '_' 2개 이상 → 1개
    s = re.sub(r'_+', '_', s)
    return s.strip('_')


# =========================================================
# 5. 메인 처리 함수
# =========================================================

def load_category_table():
    """info_category.xlsx 로드 및 category_tables 구성 (구분 없음, 거래방법/거래지점 미사용)."""
    if not INFO_CATEGORY_FILE or not os.path.exists(INFO_CATEGORY_FILE):
        return None
    category_df = load_info_category(INFO_CATEGORY_FILE, default_empty=True)
    if category_df is None or category_df.empty:
        return None
    category_df = category_df.fillna('')
    # 컬럼명 앞뒤 공백 제거 (Excel 등에서 올 수 있음)
    category_df.columns = [str(c).strip() for c in category_df.columns]
    if '구분' in category_df.columns:
        category_df = category_df.drop(columns=['구분'], errors='ignore')
    category_tables = {}
    분류_컬럼명 = '분류' if '분류' in category_df.columns else '차수'
    차수_분류_매핑 = {
        '1차': '입출금',
        '2차': '전처리',
        '6차': '기타거래'
    }

    for 값 in category_df[분류_컬럼명].unique():
        if pd.notna(값):
            값_str = str(값).strip()
            if 분류_컬럼명 == '차수' and 값_str in 차수_분류_매핑:
                분류명 = 차수_분류_매핑[값_str]
            else:
                분류명 = 값_str
            category_tables[분류명] = category_df[category_df[분류_컬럼명] == 값].copy()

    return category_tables

def classify_and_save(input_file=None, output_file=None):
    """bank_before → bank_after 생성. info_category(은행거래)의 전처리/후처리·계정과목을 반드시 적용."""
    global LAST_CLASSIFY_ERROR
    LAST_CLASSIFY_ERROR = None
    if input_file is None:
        input_file = INPUT_FILE
    if output_file is None:
        output_file = OUTPUT_FILE
    # 구분 1: 파일 없음 → 경고, 콘솔 메시지, before 생성 수행
    if not os.path.exists(input_file):
        print(f"경고: bank_before.xlsx가 없습니다(파일 없음). before 생성 수행합니다.", flush=True)
        integrate_bank_transactions(output_file=input_file)
        if not os.path.exists(input_file) or os.path.getsize(input_file) == 0:
            LAST_CLASSIFY_ERROR = "bank_before.xlsx 생성 실패. .source/Bank 폴더와 원본 파일을 확인하세요."
            print(f"오류: {LAST_CLASSIFY_ERROR}", flush=True)
            return False
    elif os.path.getsize(input_file) == 0:
        print(f"경고: bank_before.xlsx가 비어 있습니다(파일 없음). before 생성 수행합니다.", flush=True)
        integrate_bank_transactions(output_file=input_file)
        if os.path.getsize(input_file) == 0:
            LAST_CLASSIFY_ERROR = "bank_before.xlsx 생성 후에도 비어 있습니다. .source/Bank 원본을 확인하세요."
            print(f"오류: {LAST_CLASSIFY_ERROR}", flush=True)
            return False

    # 여기서 파일은 존재하고 크기 > 0
    df = _safe_read_excel(input_file, default_empty=True)
    if df is None or df.empty:
        # 구분 2: 파일 손상 → 오류, 콘솔 메시지, bak 생성, before 재생성 수행
        print(f"오류: bank_before.xlsx 읽기 실패(파일 손상). bak 백업 후 before 재생성 수행합니다.", flush=True)
        import shutil
        p = Path(input_file)
        bak_path = str(p.with_suffix(p.suffix + '.bak'))
        try:
            shutil.copy2(input_file, bak_path)
        except Exception:
            pass
        try:
            if os.path.exists(input_file):
                os.unlink(input_file)
        except OSError:
            pass  # 사용 중이면 무시
        integrate_bank_transactions(output_file=input_file)
        df = _safe_read_excel(input_file, default_empty=True)
        if df is None or df.empty:
            LAST_CLASSIFY_ERROR = "bank_before.xlsx 재생성 후에도 읽기 실패. .source/Bank 원본을 확인하세요."
            print(f"오류: {LAST_CLASSIFY_ERROR}", flush=True)
            return False
    # 컬럼명 앞뒤 공백 제거 (취소·적요·내용·송금메모·거래점 매칭 보장)
    df.columns = [str(c).strip() for c in df.columns]
    # 기존 파일 호환: 구분 → 취소
    if '구분' in df.columns and '취소' not in df.columns:
        df = df.rename(columns={'구분': '취소'})

    if not INFO_CATEGORY_FILE or not os.path.exists(INFO_CATEGORY_FILE):
        try:
            if not df.empty:
                create_category_table(df)
            else:
                create_empty_info_category(INFO_CATEGORY_FILE)
        except Exception as e:
            LAST_CLASSIFY_ERROR = f"info_category 생성 실패: {e}"
            print(f"오류: {LAST_CLASSIFY_ERROR}")
            return False

    category_tables = load_category_table()
    if category_tables is None:
        # 손상된 xlsx(File is not a zip file) 등: 한 번만 백업 후 재생성 시도
        if INFO_CATEGORY_FILE and os.path.exists(INFO_CATEGORY_FILE) and os.path.getsize(INFO_CATEGORY_FILE) > 0:
            try:
                import shutil
                backup_path = INFO_CATEGORY_FILE + '.bak'
                shutil.move(INFO_CATEGORY_FILE, backup_path)
                create_category_table(df if not df.empty else pd.DataFrame())
                category_tables = load_category_table()
            except Exception as e:
                print(f"오류: info_category 손상 복구 실패 - {e}", flush=True)
        if category_tables is None:
            LAST_CLASSIFY_ERROR = f"{INFO_CATEGORY_FILE} 로드 실패(파일 없음 또는 비어 있음)"
            print(f"오류: {LAST_CLASSIFY_ERROR}")
            return False

    try:
        df["before_text"] = df.apply(create_before_text, axis=1)
    except Exception as e:
        LAST_CLASSIFY_ERROR = f"before_text 생성 실패: {e}"
        print(f"오류: {LAST_CLASSIFY_ERROR}", flush=True)
        import traceback
        traceback.print_exc()
        return False

    # 전처리/후처리 매칭 전에 적요·내용·송금메모를 주식회사→(주) 등으로 정규화 (후처리 키워드 매칭 보장)
    for col in ['적요', '내용', '송금메모']:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: safe_str(v))

    df["입출금"] = df.apply(classify_1st_category, axis=1)
    try:
        df.index.to_series().apply(lambda idx: classify_2_chasu(idx, df, category_tables, create_before_text))
    except Exception as e:
        LAST_CLASSIFY_ERROR = f"전처리(차수) 분류 실패: {e}"
        print(f"오류: {LAST_CLASSIFY_ERROR}", flush=True)
        import traceback
        traceback.print_exc()
        return False
    # 후처리: info_category 후처리 규칙으로 적요/내용/송금메모 치환 (키워드 → 카테고리)
    try:
        df = apply_후처리_bank(df, category_tables)
    except Exception as e:
        LAST_CLASSIFY_ERROR = f"후처리 적용 실패: {e}"
        print(f"오류: {LAST_CLASSIFY_ERROR}", flush=True)
        import traceback
        traceback.print_exc()
        return False
    # 기타거래를 키워드/카테고리 분류(적용) 전에 저장 (계정과목은 기타거래 컬럼만 사용)
    try:
        df["기타거래"] = df.apply(compute_기타거래, axis=1)
    except Exception as e:
        LAST_CLASSIFY_ERROR = f"기타거래 저장 실패: {e}"
        print(f"오류: {LAST_CLASSIFY_ERROR}", flush=True)
        import traceback
        traceback.print_exc()
        return False
    # 카테고리: 계정과목 규칙 적용 (위에서 저장한 기타거래 컬럼으로 키워드 매칭)
    if '계정과목' in category_tables:
        if '카테고리' not in df.columns:
            df['카테고리'] = ''
        df['카테고리'] = ''  # 기존 값 무시, info_category 계정과목만으로 재분류
        try:
            df = apply_category_from_bank(df, category_tables['계정과목'])
        except Exception as e:
            LAST_CLASSIFY_ERROR = f"계정과목(카테고리) 적용 실패: {e}"
            print(f"오류: {LAST_CLASSIFY_ERROR}", flush=True)
            import traceback
            traceback.print_exc()
            return False
    else:
        if '카테고리' not in df.columns:
            df['카테고리'] = '기타거래'
        if '키워드' not in df.columns:
            df['키워드'] = ''

    # 기타거래를 제일 먼저(첫 번째 컬럼) 저장
    output_columns = [
        '기타거래',
        '거래일', '거래시간', '은행명', '계좌번호', '입금액', '출금액', '잔액',
        '취소', '적요', '내용', '송금메모', '거래점',
        '입출금', '키워드', '카테고리'
    ]

    available_columns = [col for col in output_columns if col in df.columns]
    result_df = df[available_columns].copy()

    result_df = result_df.fillna('')

    def normalize_branch(value):
        if pd.isna(value) or not value:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        text = re.sub(r'\d+', '', text)
        text = text.replace('((', '(')
        text = text.replace('))', ')')
        open_count = text.count('(')
        close_count = text.count(')')
        if open_count > close_count:
            text = text + ')' * (open_count - close_count)
        elif close_count > open_count:
            text = '(' * (close_count - open_count) + text
        return text.strip()

    def normalize_etc(value):
        if pd.isna(value) or not value:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        text = re.sub(r'\(\s*\)', '', text)
        text = text.replace('((', '(')
        text = text.replace('))', ')')
        open_count = text.count('(')
        close_count = text.count(')')
        if open_count > close_count:
            text = text + ')' * (open_count - close_count)
        elif close_count > open_count:
            text = '(' * (close_count - open_count) + text
        text = re.sub(r'\s*\(주\)\s*', '(주)', text)
        text = re.sub(r'\s*㈜\s*', '(주)', text)
        words = [w for w in re.split(r'[\s_]+', text) if w]
        seen = set()
        result_words = []
        for word in words:
            word_clean = re.sub(r'[()]', '', word).strip()
            if word_clean and word_clean not in seen:
                seen.add(word_clean)
                result_words.append(word)
            elif not word_clean:
                if word not in result_words:
                    result_words.append(word)
        text = ' '.join(result_words)
        text = re.sub(r'\s+', ' ', text).strip()
        words_list = text.split()
        if len(words_list) >= 2:
            first_word = words_list[0]
            for i in range(1, len(words_list)):
                if words_list[i].startswith(first_word) or first_word.startswith(words_list[i]):
                    text = ' '.join(words_list[:i])
                    break
        return text

    if '기타거래' in result_df.columns:
        result_df['기타거래'] = result_df['기타거래'].apply(normalize_etc)

    # 취소/적요/내용/송금메모/거래점/기타거래: space 1개 이상이면 space 1개로 치환
    # \s + \u3000(전각공백) + \u00a0(넌브레이킹스페이스) 등 포함
    def normalize_spaces(value):
        if pd.isna(value):
            return value
        s = str(value)
        if not s:
            return ''
        # 전각(Fullwidth) 문자 → 반각(Halfwidth)으로 변환 (예: ＳＫＴ５３２２ → SKT5322)
        s = unicodedata.normalize('NFKC', s)
        # 모든 종류의 공백(반각, 전각, 탭 등) 1개 이상 → 공백 1개로 치환 후 trim
        s = re.sub(r'[\s\u3000\u00a0\u2002\u2003\u2009]+', ' ', s)
        return s.strip()

    for col in ['취소', '적요', '내용', '송금메모', '거래점', '기타거래']:
        if col in result_df.columns:
            result_df[col] = result_df[col].apply(normalize_spaces)

    try:
        out_dir = os.path.dirname(output_file)
        if out_dir and not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception as ex:
                print(f"오류: 출력 폴더 생성 실패 - {out_dir}: {ex}")
        success = safe_write_excel(result_df, output_file)
        if not success:
            LAST_CLASSIFY_ERROR = f"파일 저장 실패: {output_file} (쓰기 권한 또는 파일 사용 중 확인)"
            print(f"오류: {LAST_CLASSIFY_ERROR}")
            return False
    except PermissionError as e:
        LAST_CLASSIFY_ERROR = f"bank_after.xlsx 저장 권한 없음(Excel 등에서 파일을 닫아주세요): {e}"
        print(f"오류: {LAST_CLASSIFY_ERROR}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        LAST_CLASSIFY_ERROR = f"파일 저장 중 예외: {e}"
        print(f"오류: {LAST_CLASSIFY_ERROR}")
        import traceback
        traceback.print_exc()
        return False

    return True

# =========================================================
# 6. 메인 함수
# =========================================================

def main():
    """전체 워크플로우 실행"""
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == 'integrate':
            integrate_bank_transactions()
            return
        elif command == 'classify':
            success = classify_and_save()
            if not success:
                print("카테고리 분류 중 오류가 발생했습니다.")
            return

    if not os.path.exists(INPUT_FILE) or os.path.getsize(INPUT_FILE) == 0:
        integrate_bank_transactions()
    else:
        classify_and_save()

if __name__ == '__main__':
    main()
