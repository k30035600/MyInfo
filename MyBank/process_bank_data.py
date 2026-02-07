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
            print(f"[bank] _safe_read_excel: 손상된 xlsx로 빈 데이터 반환 - {path}: {e}", flush=True)
            return pd.DataFrame() if default_empty else None
        raise


def _bank_before_is_empty():
    """bank_before가 없거나, 0바이트이거나, 데이터 행이 없으면 True."""
    if not os.path.exists(INPUT_FILE):
        print(f"[bank] _bank_before_is_empty: True (파일 없음) path={INPUT_FILE}", flush=True)
        return True
    if os.path.getsize(INPUT_FILE) == 0:
        print(f"[bank] _bank_before_is_empty: True (0바이트) path={INPUT_FILE}", flush=True)
        return True
    df = _safe_read_excel(INPUT_FILE, default_empty=True)
    if df is None or df.empty:
        print(f"[bank] _bank_before_is_empty: True (읽기 실패 또는 empty) path={INPUT_FILE}", flush=True)
        return True
    if len(df) <= 1:
        print(f"[bank] _bank_before_is_empty: True (행 수 <= 1) path={INPUT_FILE}, len={len(df)}", flush=True)
        return True
    return False


def ensure_all_bank_files():
    """bank_before, info_category, bank_after 파일이 없으면 생성. 있으면 그대로 사용. before/after는 MyBank 폴더."""
    # 1. bank_before.xlsx: 없거나 비어 있으면 .source/Bank 통합 실행
    empty = _bank_before_is_empty()
    print(f"[bank] ensure_all_bank_files: _bank_before_is_empty={empty}", flush=True)
    if empty:
        print(f"[bank] ensure_all_bank_files: integrate_bank_transactions() 호출", flush=True)
        integrate_bank_transactions()
        return

    # 2. info_category.xlsx: 없으면 생성, 있으면 마이그레이션(거래방법/거래지점 행 제거)
    if not INFO_CATEGORY_FILE or not os.path.exists(INFO_CATEGORY_FILE):
        try:
            df = _safe_read_excel(INPUT_FILE, default_empty=True)
            if df is not None and not df.empty:
                create_category_table(df)
            else:
                empty_cat = pd.DataFrame(columns=['분류', '키워드', '카테고리'])
                if os.path.exists(INFO_CATEGORY_FILE):
                    full = _safe_read_excel(INFO_CATEGORY_FILE, default_empty=True)
                    if full is not None and not full.empty:
                        full = full.fillna('')
                        if '구분' in full.columns:
                            full = full.drop(columns=['구분'], errors='ignore')
                        out = full[['분류', '키워드', '카테고리']].copy() if all(c in full.columns for c in ['분류', '키워드', '카테고리']) else empty_cat
                    else:
                        out = empty_cat
                    out.to_excel(INFO_CATEGORY_FILE, index=False, engine='openpyxl')
                else:
                    empty_cat.to_excel(INFO_CATEGORY_FILE, index=False, engine='openpyxl')
        except Exception as e:
            print(f"오류: info_category 생성 실패 - {e}")
    else:
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
    """NaN 값 처리 및 안전한 문자열 변환"""
    if pd.isna(value) or value is None:
        return ""
    val = str(value).strip()
    if val.lower() in ['nan', 'na', 'n', 'none', '']:
        return ""
    
    val = val.replace('((', '(')
    val = val.replace('))', ')')
    val = val.replace('__', '_')
    val = val.replace('{}', '')
    val = val.replace('[]', '')
    val = val.replace('주식회사', '(주)')
    
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
        result_df['구분'] = df['구분'] if '구분' in df.columns else ''
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
        result_df['구분'] = ''
        
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
        result_df['구분'] = ''
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
    print(f"[bank] integrate_bank_transactions: source_dir={source_dir}, bank_files 수={len(bank_files)}", flush=True)
    if not bank_files:
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
    if bank_files and not all_data:
        print(f"[경고] .source/Bank 파일 {len(bank_files)}개 중 읽기 성공한 데이터가 없습니다. 위 오류를 확인하세요.", flush=True)

    if not all_data:
        print(f"[bank] integrate_bank_transactions: all_data 없음 → 빈 combined_df 저장 output_file={output_file}", flush=True)
        combined_df = pd.DataFrame(columns=['거래일', '거래시간', '은행명', '계좌번호', '입금액', '출금액', '잔액',
                                           '구분', '적요', '내용', '거래점', '송금메모', '메모', '카테고리'])
        combined_df.to_excel(output_file, index=False, engine='openpyxl')
        try:
            empty_cat = pd.DataFrame(columns=['분류', '키워드', '카테고리'])
            if os.path.exists(INFO_CATEGORY_FILE):
                full = _safe_read_excel(INFO_CATEGORY_FILE, default_empty=True)
                if full is not None and not full.empty:
                    full = full.fillna('')
                    if '구분' in full.columns:
                        full = full.drop(columns=['구분'], errors='ignore')
                    out = full[['분류', '키워드', '카테고리']].copy() if all(c in full.columns for c in ['분류', '키워드', '카테고리']) else empty_cat
                else:
                    out = empty_cat
                out.to_excel(INFO_CATEGORY_FILE, index=False, engine='openpyxl')
            else:
                empty_cat.to_excel(INFO_CATEGORY_FILE, index=False, engine='openpyxl')
        except Exception as e:
            print(f"오류: 빈 info_category 생성 실패 - {e}")
        try:
            classify_and_save(input_file=output_file, output_file=OUTPUT_FILE)
        except Exception as e:
            print(f"오류: bank_after.xlsx 생성 실패 (빈 통합) - {e}")
        return combined_df

    combined_df = pd.concat(all_data, ignore_index=True)
    print(f"[bank] integrate_bank_transactions: concat 후 combined_df.shape={combined_df.shape}", flush=True)

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

    # bank_before에서는 카테고리 분류 작업을 하지 않음. 카테고리 컬럼만 두고 비움 (분류는 bank_after에서만)
    if '카테고리' not in combined_df.columns:
        combined_df['카테고리'] = ''
    else:
        combined_df['카테고리'] = ''

    # 적요의 "-"를 공백으로 변경
    if '적요' in combined_df.columns:
        combined_df['적요'] = combined_df['적요'].astype(str).str.replace('-', ' ', regex=False)

    # 구분 컬럼에 "취소된 거래"는 "취소"로 변경 (bank_after에서 검색 문자열로 사용)
    if '구분' in combined_df.columns:
        combined_df['구분'] = combined_df['구분'].astype(str).str.replace('취소된 거래', '취소', regex=False)

    # 컬럼 순서 정리
    column_order = ['거래일', '거래시간', '은행명', '계좌번호', '입금액', '출금액', '잔액',
                   '구분', '적요', '내용', '거래점', '송금메모', '메모', '카테고리']
    existing_columns = [col for col in column_order if col in combined_df.columns]
    for col in combined_df.columns:
        if col not in existing_columns:
            existing_columns.append(col)
    combined_df = combined_df[existing_columns]

    # 파일 저장
    print(f"[bank] integrate_bank_transactions: 저장 output_file={output_file}, rows={len(combined_df)}", flush=True)
    combined_df.to_excel(output_file, index=False, engine='openpyxl')

    if not combined_df.empty:
        try:
            create_category_table(combined_df)
        except Exception as e:
            print(f"오류: info_category(은행거래) 생성 실패 - {e}")
    else:
        try:
            empty_category_df = pd.DataFrame(columns=['분류', '키워드', '카테고리'])
            if os.path.exists(INFO_CATEGORY_FILE):
                full = _safe_read_excel(INFO_CATEGORY_FILE, default_empty=True)
                if full is not None and not full.empty:
                    full = full.fillna('')
                    if '구분' in full.columns:
                        full = full.drop(columns=['구분'], errors='ignore')
                    out = full[['분류', '키워드', '카테고리']].copy() if all(c in full.columns for c in ['분류', '키워드', '카테고리']) else empty_category_df
                else:
                    out = empty_category_df
                out.to_excel(INFO_CATEGORY_FILE, index=False, engine='openpyxl')
            else:
                empty_category_df.to_excel(INFO_CATEGORY_FILE, index=False, engine='openpyxl')
        except Exception as e:
            print(f"오류: 빈 info_category 생성 실패 - {e}")

    # bank_after.xlsx 자동 생성
    try:
        classify_and_save(input_file=output_file, output_file=OUTPUT_FILE)
    except Exception as e:
        print(f"오류: bank_after.xlsx 생성 실패 - {e}")

    return combined_df


# =========================================================
# 3. 카테고리 테이블 생성 (info_category.xlsx 단일 테이블, 구분 없음)
# 전처리, 후처리, 계정과목만 사용 (거래방법/거래지점 미사용)
# =========================================================

# 계정과목 기본 규칙
_DEFAULT_BANK_ACCOUNT_RULES = [
    {'분류': '계정과목', '키워드': '파리바게뜨/베이커리', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '씨유/CU', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '(주)이마트/롯데마트/식자재/이마트', '카테고리': '주식비/부식비'},
    {'분류': '계정과목', '키워드': '가전/의류/가구/023/나눔과어울림', '카테고리': '가전/가구/의류/생필품'},
    {'분류': '계정과목', '키워드': '비와이씨/삼성전자/현대아울렛/나무다움/어패럴', '카테고리': '가전/가구/의류/생필품'},
    {'분류': '계정과목', '키워드': '스퀘어/자라/공영쇼핑/에이비씨/이랜드', '카테고리': '가전/가구/의류/생필품'},
    {'분류': '계정과목', '키워드': '몰테일/이케아/버킷/신세계/올리브영', '카테고리': '가전/가구/의류/생필품'},
    {'분류': '계정과목', '키워드': '버스/택시/차량유지/자동차/지하철/칼텍스/자동차보험/차량보험', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '북서울에너지/피킹/도로공사/티머니/에이티씨', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '인천30/인천32/시설공단/문학터널/문학개발/주유소', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '만월산/선학현대/후불교통/로드801/에너지/시설안전', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '파킹/현대오일/태리/코레일/철도', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '시설관리/기아오토큐/시설공단/국민오일', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '금은방/귀금속/거래소', '카테고리': '귀금속'},
    {'분류': '계정과목', '키워드': '클락에이/CU/GS/마트/쿠팡/네이버/후이즈/타이거', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '토스/쇼핑몰/쇼핑/보타나/공공기관/결재대행/결제대행', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': 'NICE/SMS/면세점/에이치/제이디/라프/씨유/플라워', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '엠에스/세탁소/세븐일레븐/법원/미앤미/헤어/지에스', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '예스이십사/코리아세븐/건설기술/티몬/에이스', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '다온나/아이지/미니스톱/우체국/월드/이투유/나이스', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '더에덴/옥션/나래/로그인/메트로/홈엔/ARS/카카오', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '와이에스/다날/홈마트/슈퍼/로웰/유니윌/코페이', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '스테이지/이마트24/부경/에스씨/목욕탕/구글', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '다이소/빈티지/마이리얼/홈쇼핑/올댓/그릇/로스', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '컬리페이/키오스크/에스지씨/에델/크린토피아/미성', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '블랙벤자민/LIVING/슬립/세탁/만물/그릇/유진/두찜', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '티무/황실/KICC/KCP/마이/플래티넘/몽실/가위', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '이니시스/메머드', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '오락/취미/레저/휴양/교보문고', '카테고리': '레저/휴양/취미/오락'},
    {'분류': '계정과목', '키워드': '중국동방/CGV', '카테고리': '레저/휴양/취미/오락'},
    {'분류': '계정과목', '키워드': '외식/회식/간식/호치킨/콩닭/모밀방/상회/필/삼계탕', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '제주도/애월/바이/해장국/족발/연쭈/모미락/도미노', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '맛있는죽/맥도날드/새록/칼국수/순대/식당/롯데리아', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '오구본가/연탄/파리바게뜨/타이거/김치/수산/국수', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '선학사골/천상/메가/스타벅스/엔제리너스/리너스/추어탕', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '더달달/컴포즈/닭집/할매/동태촌/왕냉면/통닭/아구', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '추어탕/부대/부대찌게/보리밥/본죽/카페/안스/식당/이학', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '아방궁/돈풀/카페온/부원집/능허대/옹진/상사/국밥', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '뜰아래/솔도갈매기/미두야/소바/포베이/10월/조개', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '오케이/웨이업/산자락에/막국수/공간븟/굴사냥', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '닭곰탕/메밀국수/저푸른/닭소리/사계절/두루담채', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '콩세알/지에스/바로/손만두/멕시카나/청량산/연어', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '빽다방/패류/씨푸드/해장국/김밥/이디야/어시장', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '장수마을/어부장/동춘옥/푸드/공차/이학/두부/모밀', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '반점/닭강정/생오리/떡방아/마장동/자판기/민영', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '조개/불닭발/직화/던킨/얼음/다정이네/올댓/메고', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '미스터/스마일/투썸/대신기업/손만두/휴게소/매반', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '만강홍/페리카나/최부자네/부대/부대찌게/공간븟/야래향/송도갈매기', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '엔제리너스/리너스/물고기/낙지', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '병원/의원/치과/약국/건강보험/나사렛/레푸스/메디컬', '카테고리': '의료비'},
    {'분류': '계정과목', '키워드': '이비인후과/신경외과/정형외과/엄마손/워너독', '카테고리': '의료비'},
    {'분류': '계정과목', '키워드': '견생냥품/동물의료/안과', '카테고리': '의료비'},
    {'분류': '계정과목', '키워드': '국세/지방세/세외/주민세/행정안전부/연수구청', '카테고리': '제세공과금'},
    {'분류': '계정과목', '키워드': '소득세/교육청/소액합산/행정복지/자동차세/취득세', '카테고리': '제세공과금'},
    {'분류': '계정과목', '키워드': '지자체/곡공기관/인천광역시/부가가치세/전몰', '카테고리': '제세공과금'},
    {'분류': '계정과목', '키워드': '수도/전기/한국전력/가스/통신/관리비/케이티/SK/수신료', '카테고리': '주거비/통신비'},
    {'분류': '계정과목', '키워드': '주식/부식/반찬/농산물/SSG/건어물/씨푸드/웅이/과일/야채/코스트코/홈플러스', '카테고리': '주식비/부식비'},
    {'분류': '계정과목', '키워드': '정육점/세계로/생선/푸줏간/우아한/성필립보', '카테고리': '주식비/부식비'},
    {'분류': '계정과목', '키워드': '현금/서비스/대출', '카테고리': '현금처리'},
    {'분류': '계정과목', '키워드': '신한은행/하나은행/신한카드/리볼빙', '카테고리': '현금처리'},
]


def create_category_table(df):
    """bank_before 데이터를 기반으로 info_category.xlsx 생성(구분 없음). 전처리·후처리·계정과목만 사용."""
    category_data = []

    # 1. 전처리/후처리
    category_data.append({'분류': '전처리', '키워드': 'NH', '카테고리': '농협'})
    category_data.append({'분류': '전처리', '키워드': 'KB', '카테고리': '국민'})
    category_data.append({'분류': '전처리', '키워드': '한국주택은행', '카테고리': '국민은행'})
    category_data.append({'분류': '전처리', '키워드': '주금공', '카테고리': '주택금융공사'})
    category_data.append({'분류': '후처리', '키워드': '((', '카테고리': '('})
    category_data.append({'분류': '후처리', '키워드': '))', '카테고리': ')'})
    category_data.append({'분류': '후처리', '키워드': '[]', '카테고리': 'space'})

    # 2. 계정과목 (구분, 적요, 내용, 거래점, 송금메모 키워드 매칭용)
    category_data.extend(_DEFAULT_BANK_ACCOUNT_RULES)

    # 3. 중복 제거 및 DataFrame 생성
    seen_all = set()
    unique_category_data = []
    for item in category_data:
        분류 = str(item.get('분류', '')).strip()
        키워드 = str(item.get('키워드', '')).strip()
        카테고리 = str(item.get('카테고리', '')).strip()
        key = (분류, 키워드, 카테고리)
        if key not in seen_all:
            seen_all.add(key)
            unique_category_data.append({
                '분류': 분류,
                '키워드': 키워드,
                '카테고리': 카테고리
            })

    category_df = pd.DataFrame(unique_category_data)
    category_df = category_df.drop_duplicates(subset=['분류', '키워드', '카테고리'], keep='first')

    try:
        if len(category_df) == 0:
            category_df = pd.DataFrame(columns=['분류', '키워드', '카테고리'])
        out = category_df[['분류', '키워드', '카테고리']].copy()
        if os.path.exists(INFO_CATEGORY_FILE):
            full = _safe_read_excel(INFO_CATEGORY_FILE, default_empty=True)
            if full is not None and not full.empty:
                full = full.fillna('')
                if '구분' in full.columns:
                    full = full.drop(columns=['구분'], errors='ignore')
                if all(c in full.columns for c in ['분류', '키워드', '카테고리']):
                    out = pd.concat([full[['분류', '키워드', '카테고리']], out], ignore_index=True).drop_duplicates(subset=['분류', '키워드', '카테고리'], keep='first')
        out.to_excel(INFO_CATEGORY_FILE, index=False, engine='openpyxl')
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
    full_df = _safe_read_excel(path, default_empty=True)
    if full_df is None or full_df.empty:
        return
    full_df = full_df.fillna('')
    if '구분' in full_df.columns:
        full_df = full_df.drop(columns=['구분'], errors='ignore')
    if full_df.empty or '분류' not in full_df.columns:
        return
    category_df = full_df[['분류', '키워드', '카테고리']].copy() if all(c in full_df.columns for c in ['분류', '키워드', '카테고리']) else full_df
    분류_col = category_df['분류'].astype(str).str.strip()
    keep_mask = ~분류_col.isin(['거래방법', '거래지점'])
    migrated_df = category_df.loc[keep_mask].copy()
    계정과목_mask = (migrated_df['분류'].astype(str).str.strip() == '계정과목')
    if not 계정과목_mask.any() or 계정과목_mask.sum() < 10:
        account_rows = pd.DataFrame(_DEFAULT_BANK_ACCOUNT_RULES)
        existing_account = migrated_df[계정과목_mask] if 계정과목_mask.any() else pd.DataFrame(columns=['분류', '키워드', '카테고리'])
        other_rows = migrated_df[~계정과목_mask]
        combined = pd.concat([existing_account, account_rows], ignore_index=True).drop_duplicates(subset=['분류', '키워드', '카테고리'], keep='first')
        migrated_df = pd.concat([other_rows, combined], ignore_index=True)
    migrated_df = migrated_df.drop_duplicates(subset=['분류', '키워드', '카테고리'], keep='first')
    try:
        safe_write_excel(migrated_df, path)
    except Exception as e:
        print(f"오류: info_category 마이그레이션 저장 실패 - {e}")
        raise


def _bank_row_search_text(row):
    """카테고리 매칭용 검색 문자열 생성 (구분, 적요, 내용, 거래점, 송금메모, 메모). 공백 정규화하여 키워드 매칭률 향상."""
    parts = []
    for col in ['구분', '적요', '내용', '거래점', '송금메모', '메모']:
        parts.append(safe_str(row.get(col, '')))
    text = '#'.join(p for p in parts if p)
    # 연속 공백 1개로 축소 (Excel/복사 시 공백 차이 보정)
    if text:
        text = re.sub(r'\s+', ' ', text).strip()
    return text


def apply_category_from_bank(df, category_df):
    """구분·적요·내용·거래점·송금메모를 합친 문자열에 대해 bank_category 계정과목 규칙을 적용해 df['카테고리'] 채움.
    MyCard apply_category_from_merchant와 동일한 방식: 키워드(슬래시 구분)가 검색문자열에 포함되면 해당 카테고리 할당."""
    if df is None or df.empty or category_df is None or category_df.empty:
        print(f"[bank] apply_category_from_bank: 스킵 (df empty 또는 category_df empty) df.rows={len(df) if df is not None else 0}, cat.rows={len(category_df) if category_df is not None else 0}", flush=True)
        return df
    need_cols = ['분류', '키워드', '카테고리']
    category_df = category_df.copy()
    category_df.columns = [str(c).strip() for c in category_df.columns]
    if not all(c in category_df.columns for c in need_cols):
        print(f"[bank] apply_category_from_bank: 스킵 (need_cols 없음) columns={list(category_df.columns)}", flush=True)
        return df
    # 계정과목만 사용
    account_df = category_df[category_df['분류'].astype(str).str.strip() == '계정과목'].copy()
    if account_df.empty:
        print(f"[bank] apply_category_from_bank: 스킵 (계정과목 행 없음)", flush=True)
        return df
    print(f"[bank] apply_category_from_bank: df.rows={len(df)}, 계정과목 규칙 수={len(account_df)}", flush=True)
    if '카테고리' not in df.columns:
        df = df.copy()
        df['카테고리'] = ''
    df = df.copy()
    df['카테고리'] = df['카테고리'].astype(object)
    search_series = df.apply(_bank_row_search_text, axis=1)
    # 키워드 긴 순으로 정렬 (긴 키워드 우선 매칭)
    account_df = account_df.copy()
    account_df['_klen'] = account_df['키워드'].astype(str).str.len()
    account_df = account_df.sort_values('_klen', ascending=False).drop(columns=['_klen'], errors='ignore')
    empty_mask = (df['카테고리'].fillna('').astype(str).str.strip() == '')
    for _, cat_row in account_df.iterrows():
        keywords_str = safe_str(cat_row.get('키워드', ''))
        if not keywords_str:
            continue
        # 슬래시 구분 키워드, 각 키워드 공백 정규화(연속 공백 1개)
        keywords = [re.sub(r'\s+', ' ', k.strip()) for k in keywords_str.split('/') if k.strip()]
        if not keywords:
            continue
        cat_val = safe_str(cat_row.get('카테고리', ''))
        if not cat_val:
            continue
        for kw in keywords:
            if not kw:
                continue
            rule_match = search_series.str.contains(re.escape(kw), regex=False, na=False)
            fill_mask = rule_match & empty_mask
            if fill_mask.any():
                df.loc[fill_mask, '카테고리'] = cat_val
                empty_mask = empty_mask & ~fill_mask
        if not empty_mask.any():
            break
    # 미채움 행은 반드시 '미분류' (empty_mask 기준)
    still_empty_count = int(empty_mask.sum())
    if empty_mask.any():
        df.loc[empty_mask, '카테고리'] = '미분류'
    # 이중 보정: 컬럼 기준으로 아직 빈 값인 행도 '미분류' (pandas 반영 누락 방지)
    still_empty_fallback = (df['카테고리'].fillna('').astype(str).str.strip() == '')
    if still_empty_fallback.any():
        df.loc[still_empty_fallback, '카테고리'] = '미분류'
    filled_count = len(df) - still_empty_count
    print(f"[bank] apply_category_from_bank: 완료 채움={filled_count}, 미분류={still_empty_count}", flush=True)
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
        적요 = f"[{bank_name}]"
    parts.append(적요)

    내용 = safe_str(row.get("내용", ""))
    if not 내용 and bank_name:
        내용 = f"[{bank_name}]"
    parts.append(내용)

    parts.append(safe_str(row.get("거래점", "")))
    parts.append(safe_str(row.get("송금메모", "")))

    return "#".join([p for p in parts if p])

def classify_1st_category(row):
    """입출금 분류: 입금/출금/취소"""
    before_text = safe_str(row.get("before_text", ""))
    구분 = safe_str(row.get("구분", ""))

    if "취소" in before_text or "취소된 거래" in before_text:
        return "취소"
    if "취소" in 구분 or "취소된 거래" in 구분:
        return "취소"

    in_amt = row.get("입금액", 0) or 0
    out_amt = row.get("출금액", 0) or 0

    if out_amt > 0:
        return "출금"
    return "입금"

def classify_2_chasu(row_idx, df, category_tables, create_before_text_func):
    """전처리 분류 (계좌번호 등)"""
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

            if keyword and before_text and keyword in before_text:
                category_raw = cat_row.get("카테고리", "")
                if pd.notna(category_raw):
                    category_str = str(category_raw).strip()
                    if category_str:
                        for col in ['적요', '내용', '거래점', '송금메모']:
                            if col in df.columns:
                                cell_value = safe_str(df.iloc[row_idx].get(col, ""))
                                if keyword in normalize_text(cell_value):
                                    df.at[row_idx, col] = category_str
                                    break
                        df.at[row_idx, "before_text"] = create_before_text_func(df.iloc[row_idx])
                        updated_text = normalize_text(df.iloc[row_idx].get("before_text", ""))
                        updated_text = updated_text.replace(keyword, "").strip()
                        df.at[row_idx, "before_text"] = updated_text
                break

    # 계좌번호 처리
    account_columns = ['적요', '내용']
    for col in account_columns:
        if col not in df.columns:
            continue

        cell_value = safe_str(df.iloc[row_idx].get(col, ""))
        if not cell_value:
            continue

        if re.search(r'\[\d{8,}\]', cell_value):
            continue

        def wrap_account_numbers(text):
            pattern = r'(?<!\[)[A-Za-z]?\d{8,}(?!\])'
            matches = re.findall(pattern, text)
            for match in matches:
                wrapped = f'[{match}]'
                text = text.replace(match, wrapped, 1)
                break
            return text

        updated_value = wrap_account_numbers(cell_value)
        if updated_value != cell_value:
            df.at[row_idx, col] = updated_value
            df.at[row_idx, "before_text"] = create_before_text_func(df.iloc[row_idx])

def classify_etc(row_idx, df, category_tables):
    """기타거래 분류"""
    row = df.iloc[row_idx]
    before_text_raw = row.get("before_text", "")
    before_text = normalize_text(before_text_raw)

    if not before_text_raw or not before_text_raw.strip():
        적요 = safe_str(row.get("적요", ""))
        if 적요:
            return 적요[:30] if len(적요) > 30 else 적요
        return ""

    result = ""
    if "기타거래" in category_tables:
        category_table = category_tables["기타거래"]
        category_rows_list = list(category_table.iterrows())
        sorted_rows = sorted(category_rows_list, key=lambda x: len(str(x[1].get("키워드", ""))), reverse=True)

        for _, cat_row in sorted_rows:
            keyword_raw = cat_row.get("키워드", "")
            if pd.isna(keyword_raw) or not keyword_raw:
                continue

            keyword = normalize_text(keyword_raw)

            if keyword and before_text and keyword in before_text:
                category_raw = cat_row.get("카테고리", "")

                original_before_text = safe_str(row.get("before_text", ""))
                updated_before_text = original_before_text.replace(str(keyword_raw), "").strip()
                df.at[row_idx, "before_text"] = updated_before_text

                if pd.notna(category_raw):
                    category_str = str(category_raw).strip()
                    if category_str:
                        result = category_str

                break

    current_before_text = safe_str(row.get("before_text", ""))
    normalized_current = normalize_text(current_before_text)
    if normalized_current in ['space']:
        df.at[row_idx, "before_text"] = ""
        return ""

    if result:
        return result

    before_text = safe_str(row.get("before_text", ""))
    before_text = re.sub(r'\[[^\]]+\]', '', before_text)

    excluded_texts = []

    거래점 = safe_str(row.get("거래점", ""))
    if 거래점:
        excluded_texts.append(거래점)
        bracket_matches = re.findall(r'\(([^)]+)\)', 거래점)
        excluded_texts.extend(bracket_matches)

    bank_name = safe_str(row.get("은행명", ""))
    if bank_name:
        excluded_texts.append(bank_name)

    excluded_texts = list(set([t.strip() for t in excluded_texts if t.strip()]))
    excluded_texts.sort(key=len, reverse=True)

    remaining_text = before_text
    for excluded in excluded_texts:
        if excluded:
            pattern = re.escape(excluded)
            remaining_text = re.sub(r'\b' + pattern + r'\b', ' ', remaining_text, flags=re.IGNORECASE)
            remaining_text = remaining_text.replace(excluded, " ")

    remaining_text = re.sub(r'\s+', ' ', remaining_text).strip()
    remaining_text = remaining_text.replace('#', ' ').strip()

    if remaining_text:
        return remaining_text[:30] if len(remaining_text) > 30 else remaining_text

    return ""

# =========================================================
# 5. 메인 처리 함수
# =========================================================

def load_category_table():
    """info_category.xlsx 로드 및 category_tables 구성 (구분 없음, 거래방법/거래지점 미사용)."""
    if not INFO_CATEGORY_FILE or not os.path.exists(INFO_CATEGORY_FILE):
        return None
    category_df = _safe_read_excel(INFO_CATEGORY_FILE, default_empty=True)
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
    print(f"[bank] classify_and_save: input={input_file}, output={output_file}", flush=True)

    df = _safe_read_excel(input_file, default_empty=True)
    if df is None or df.empty:
        LAST_CLASSIFY_ERROR = f"{input_file} 읽기 실패(파일 없음 또는 손상)"
        print(f"오류: {LAST_CLASSIFY_ERROR}")
        return False
    # 컬럼명 앞뒤 공백 제거 (구분·적요·내용·거래점·송금메모 매칭 보장)
    df.columns = [str(c).strip() for c in df.columns]
    print(f"[bank] classify_and_save: df.shape={df.shape}", flush=True)

    if not INFO_CATEGORY_FILE or not os.path.exists(INFO_CATEGORY_FILE):
        try:
            if not df.empty:
                create_category_table(df)
            else:
                empty = pd.DataFrame(columns=['분류', '키워드', '카테고리'])
                if os.path.exists(INFO_CATEGORY_FILE):
                    full = _safe_read_excel(INFO_CATEGORY_FILE, default_empty=True)
                    if full is not None and not full.empty:
                        full = full.fillna('')
                        if '구분' in full.columns:
                            full = full.drop(columns=['구분'], errors='ignore')
                        out = full[['분류', '키워드', '카테고리']].copy() if all(c in full.columns for c in ['분류', '키워드', '카테고리']) else empty
                    else:
                        out = empty
                    out.to_excel(INFO_CATEGORY_FILE, index=False, engine='openpyxl')
                else:
                    empty.to_excel(INFO_CATEGORY_FILE, index=False, engine='openpyxl')
        except Exception as e:
            LAST_CLASSIFY_ERROR = f"info_category 생성 실패: {e}"
            print(f"오류: {LAST_CLASSIFY_ERROR}")
            return False

    category_tables = load_category_table()
    if category_tables is None:
        LAST_CLASSIFY_ERROR = f"{INFO_CATEGORY_FILE} 로드 실패(파일 없음 또는 비어 있음)"
        print(f"오류: {LAST_CLASSIFY_ERROR}")
        return False
    print(f"[bank] classify_and_save: category_tables keys={list(category_tables.keys()) if category_tables else None}", flush=True)

    try:
        df["before_text"] = df.apply(create_before_text, axis=1)
    except Exception as e:
        LAST_CLASSIFY_ERROR = f"before_text 생성 실패: {e}"
        print(f"오류: {LAST_CLASSIFY_ERROR}", flush=True)
        import traceback
        traceback.print_exc()
        return False

    df["입출금"] = df.apply(classify_1st_category, axis=1)
    try:
        df.index.to_series().apply(lambda idx: classify_2_chasu(idx, df, category_tables, create_before_text))
    except Exception as e:
        LAST_CLASSIFY_ERROR = f"전처리(차수) 분류 실패: {e}"
        print(f"오류: {LAST_CLASSIFY_ERROR}", flush=True)
        import traceback
        traceback.print_exc()
        return False
    # 카테고리: 계정과목 규칙 적용 (전 행을 비운 뒤 구분·적요·내용·거래점·송금메모로 키워드 매칭)
    if '계정과목' in category_tables:
        if '카테고리' not in df.columns:
            df['카테고리'] = ''
        df['카테고리'] = ''  # 기존 값 무시, info_category 계정과목만으로 재분류
        print(f"[bank] classify_and_save: apply_category_from_bank 호출 전 df.shape={df.shape}", flush=True)
        try:
            df = apply_category_from_bank(df, category_tables['계정과목'])
        except Exception as e:
            LAST_CLASSIFY_ERROR = f"계정과목(카테고리) 적용 실패: {e}"
            print(f"오류: {LAST_CLASSIFY_ERROR}", flush=True)
            import traceback
            traceback.print_exc()
            return False
        print(f"[bank] classify_and_save: apply_category_from_bank 호출 후 df.shape={df.shape}", flush=True)
    else:
        if '카테고리' not in df.columns:
            df['카테고리'] = '미분류'
        print(f"[bank] classify_and_save: 계정과목 없음 → 카테고리 미분류", flush=True)
    try:
        df["기타거래"] = df.index.to_series().apply(lambda idx: classify_etc(idx, df, category_tables))
    except Exception as e:
        LAST_CLASSIFY_ERROR = f"기타거래 분류 실패: {e}"
        print(f"오류: {LAST_CLASSIFY_ERROR}", flush=True)
        import traceback
        traceback.print_exc()
        return False

    output_columns = [
        '거래일', '거래시간', '은행명', '계좌번호', '입금액', '출금액', '잔액',
        '구분', '적요', '내용', '거래점', '송금메모',
        '입출금', '카테고리', '기타거래'
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
        words = text.split()
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

    # 구분/적요/내용/거래점/송금메모/기타거래: space 1개 이상이면 space 1개로 치환
    # \s + \u3000(전각공백) + \u00a0(넌브레이킹스페이스) 등 포함
    def normalize_spaces(value):
        if pd.isna(value):
            return value
        s = str(value)
        if not s:
            return ''
        # 모든 종류의 공백(반각, 전각, 탭 등) 1개 이상 → 공백 1개로 치환 후 trim
        s = re.sub(r'[\s\u3000\u00a0\u2002\u2003\u2009]+', ' ', s)
        return s.strip()

    for col in ['구분', '적요', '내용', '거래점', '송금메모', '기타거래']:
        if col in result_df.columns:
            result_df[col] = result_df[col].apply(normalize_spaces)

    try:
        out_dir = os.path.dirname(output_file)
        if out_dir and not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception as ex:
                print(f"오류: 출력 폴더 생성 실패 - {out_dir}: {ex}")
        print(f"[bank] classify_and_save: 저장 중 output_file={output_file}, result_df.shape={result_df.shape}", flush=True)
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
