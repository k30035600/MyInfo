# -*- coding: utf-8 -*-
"""
process_cash_data.py — 금융정보(MyCash) 전용. (카드 관련 역할 없음)

[역할]
- 금융(은행) 파일 통합: .source 폴더의 은행 엑셀을 모아 cash_before.xlsx 생성
- 카테고리: MyInfo/info_category.xlsx(금융정보 구분) 사용
- 분류·저장: cash_before → cash_after.xlsx (입출금, 카테고리, 기타거래)

.source는 .xls, .xlsx만 취급. (파일명에 국민/신한/하나 포함)
"""
import pandas as pd
import os
import re
import unicodedata
import sys
import time
from pathlib import Path

from MyBank.process_bank_data import apply_category_from_bank

# Windows 콘솔 인코딩 설정 (한글 출력을 위한 UTF-8 설정)
if sys.platform == 'win32':
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8')
        if sys.stderr.encoding != 'utf-8':
            sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# =========================================================
# 기본 설정
# =========================================================

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, '..'))
# 금융정보 원본 업로드용: .source/Cash
SOURCE_CASH_DIR = os.path.join(PROJECT_ROOT, '.source', 'Cash')
INFO_CATEGORY_FILE = os.path.join(os.environ.get('MYINFO_ROOT', PROJECT_ROOT), 'info_category.xlsx')
CASH_CATEGORY_LABEL = '금융정보'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
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
    def normalize_주식회사_for_match(text):
        if text is None or (isinstance(text, str) and not str(text).strip()): return '' if text is None else str(text).strip()
        val = str(text).strip()
        val = re.sub(r'[\s/]*주식회사[\s/]*', '(주)', val)
        val = re.sub(r'[\s/]*㈜[\s/]*', '(주)', val)
        val = re.sub(r'(\(주\)[\s/]*)+', '(주)', val)
        return val
    INFO_CATEGORY_COLUMNS = ['분류', '키워드', '카테고리']

INPUT_FILE = "cash_before.xlsx"
OUTPUT_FILE = "cash_after.xlsx"


def ensure_all_cash_files():
    """cash_before, info_category(금융정보) 파일이 없으면 생성. cash_after는 bank/card 병합(merge_bank_card)으로만 생성."""
    input_path = os.path.join(_SCRIPT_DIR, INPUT_FILE)

    if not os.path.exists(input_path) or (os.path.exists(input_path) and os.path.getsize(input_path) == 0):
        integrate_cash_transactions()
        return

    need_cash_section = not (INFO_CATEGORY_FILE and os.path.exists(INFO_CATEGORY_FILE))

    if need_cash_section:
        try:
            df = pd.read_excel(input_path, engine='openpyxl')
            if not df.empty:
                create_category_table(df)
            else:
                create_empty_info_category(INFO_CATEGORY_FILE)
        except Exception as e:
            print(f"오류: info_category(금융정보) 생성 실패 - {e}")


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
    val = val.replace('[]', '')
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

# =========================================================
# 1. 은행 파일 읽기 함수들
# =========================================================

def read_kb_file_excel(file_path):
    """국민은행 Excel(.xlsx) 파일 읽기."""
    xls = pd.ExcelFile(file_path)
    all_data = []
    for sheet_name in xls.sheet_names:
        df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        header_row = None
        for idx in range(min(15, len(df_raw))):
            cell = df_raw.iloc[idx, 0]
            if pd.notna(cell) and ('거래일시' in str(cell) or '거래일자' in str(cell)):
                header_row = idx
                break
        if header_row is None:
            continue
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)
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
        df_info = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=10)
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
    """신한은행 파일 읽기"""
    xls = pd.ExcelFile(file_path)
    all_data = []
    
    for sheet_name in xls.sheet_names:
        df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        header_row = None
        for idx in range(min(15, len(df_raw))):
            if pd.notna(df_raw.iloc[idx, 0]) and '거래일자' in str(df_raw.iloc[idx, 0]):
                header_row = idx
                break
        
        if header_row is None:
            continue
        
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)
        df = df[df['거래일자'].notna()].copy()
        df = df[df['거래일자'] != ''].copy()
        
        account_number = None
        df_info = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=5)
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
    """하나은행 파일 읽기"""
    xls = pd.ExcelFile(file_path)
    all_data = []
    
    for sheet_name in xls.sheet_names:
        df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        header_row = None
        for idx in range(min(15, len(df_raw))):
            if pd.notna(df_raw.iloc[idx, 0]) and ('거래일시' in str(df_raw.iloc[idx, 0]) or '거래일' in str(df_raw.iloc[idx, 0])):
                header_row = idx
                break
        
        if header_row is None:
            continue
        
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row)
        df = df[df['거래일시'].notna()].copy()
        
        account_number = None
        df_info = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=5)
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
# 2. 은행 파일 통합 함수 (integrate_cash_transactions)
# =========================================================

def _cash_excel_files(source_dir):
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

def integrate_cash_transactions(output_file=None):
    """MyInfo/.source/Cash 의 은행 파일을 통합하여 MyCash/cash_before.xlsx 생성."""
    if output_file is None:
        output_file = os.path.join(_SCRIPT_DIR, INPUT_FILE)
    source_dir = Path(SOURCE_CASH_DIR)
    all_data = []
    bank_files = _cash_excel_files(source_dir)

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
            print(f"오류: {name} 처리 실패 - {e}")

    if not all_data:
        combined_df = pd.DataFrame(columns=['거래일', '거래시간', '은행명', '계좌번호', '입금액', '출금액', '잔액',
                                           '구분', '적요', '내용', '거래점', '송금메모', '메모', '카테고리'])
        combined_df.to_excel(output_file, index=False, engine='openpyxl')
        try:
            create_empty_info_category(INFO_CATEGORY_FILE)
        except Exception as e:
            print(f"오류: 빈 info_category(금융정보) 생성 실패 - {e}")
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

    # 메모 컬럼을 카테고리로 변경
    if '카테고리' not in combined_df.columns:
        if '메모' in combined_df.columns:
            combined_df['카테고리'] = combined_df['메모'].fillna('')
        else:
            combined_df['카테고리'] = ''

    # 적요의 "-"를 공백으로 변경
    if '적요' in combined_df.columns:
        combined_df['적요'] = combined_df['적요'].astype(str).str.replace('-', ' ', regex=False)

    # 입금/출금 금액에 따라 카테고리에 "입금"/"출금" 추가
    for idx in combined_df.index:
        deposit_value = combined_df.at[idx, '입금액'] if '입금액' in combined_df.columns else 0
        withdraw_value = combined_df.at[idx, '출금액'] if '출금액' in combined_df.columns else 0

        try:
            deposit_value = float(deposit_value) if pd.notna(deposit_value) else 0
            withdraw_value = float(withdraw_value) if pd.notna(withdraw_value) else 0
        except (ValueError, TypeError):
            deposit_value = 0
            withdraw_value = 0

        if deposit_value > 0 or withdraw_value > 0:
            current_category = str(combined_df.at[idx, '카테고리']) if pd.notna(combined_df.at[idx, '카테고리']) else ''

            if deposit_value > 0:
                if current_category:
                    current_category = current_category + ' ' + '입금'
                else:
                    current_category = '입금'

            if withdraw_value > 0:
                if current_category:
                    current_category = current_category + ' ' + '출금'
                else:
                    current_category = '출금'

            combined_df.at[idx, '카테고리'] = current_category

    # 구분 컬럼에 "취소된 거래"는 "취소"로 변경
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
    combined_df.to_excel(output_file, index=False, engine='openpyxl')

    if not combined_df.empty:
        try:
            create_category_table(combined_df)
        except Exception as e:
            print(f"오류: info_category(금융정보) 생성 실패 - {e}")
    else:
        try:
            create_empty_info_category(INFO_CATEGORY_FILE)
        except Exception as e:
            print(f"오류: 빈 info_category(금융정보) 생성 실패 - {e}")

    return combined_df


# =========================================================
# 3. 카테고리 테이블 생성 함수
# =========================================================

def create_category_table(df):
    """cash_before 데이터를 기반으로 info_category.xlsx(금융정보 구분) 생성. category_create.md 파싱 또는 기본값 사용."""
    fn = get_default_rules if get_default_rules else (lambda d: __import__('info_category_defaults').get_default_rules(d))
    unique_category_data = fn('cash')
    category_df = pd.DataFrame(unique_category_data)
    category_df = category_df.drop_duplicates(subset=['분류', '키워드', '카테고리'], keep='first')

    try:
        if len(category_df) == 0:
            category_df = pd.DataFrame(columns=INFO_CATEGORY_COLUMNS)
        out = category_df[INFO_CATEGORY_COLUMNS].copy()
        if INFO_CATEGORY_FILE and os.path.exists(INFO_CATEGORY_FILE):
            full = load_info_category(INFO_CATEGORY_FILE, default_empty=True)
            if full is not None and not full.empty:
                full = normalize_category_df(full)
                if not full.empty:
                    out = pd.concat([full, out], ignore_index=True).drop_duplicates(subset=INFO_CATEGORY_COLUMNS, keep='first')
        safe_write_info_category_xlsx(INFO_CATEGORY_FILE, out)
        if INFO_CATEGORY_FILE and not os.path.exists(INFO_CATEGORY_FILE):
            raise FileNotFoundError(f"오류: 파일 생성 후에도 {INFO_CATEGORY_FILE} 파일이 존재하지 않습니다.")
    except PermissionError as e:
        print(f"오류: 파일 쓰기 권한이 없습니다 - {INFO_CATEGORY_FILE}")
        raise
    except Exception as e:
        print(f"오류: info_category 생성 실패 - {e}")
        raise
    return category_df

# =========================================================
# 4. 분류 함수들
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
                        for col in ['적요', '내용', '거래점', '송금메모']:
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

def classify_transaction_type(row_idx, df, category_tables):
    """거래방법 분류"""
    row = df.iloc[row_idx]
    before_text_raw = row.get("before_text", "")
    before_text = normalize_text(before_text_raw)
    in_amt = row.get("입금액", 0) or 0

    result = "기타"

    if "거래방법" in category_tables:
        category_table = category_tables["거래방법"]
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
                        result = category_str
                        if category_str == "대출" and in_amt > 0:
                            result = "잡수입"
                        updated_text = before_text.replace(keyword, "").strip()
                        df.at[row_idx, "before_text"] = updated_text
                        break

    return result

def classify_branch(row_idx, df, category_tables):
    """거래지점 분류"""
    row = df.iloc[row_idx]
    before_text_raw = row.get("before_text", "")
    before_text = normalize_text(before_text_raw)

    result = None

    if "거래지점" in category_tables:
        category_table = category_tables["거래지점"]
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
                        result = category_str
                        updated_text = before_text.replace(keyword, "").strip()
                        df.at[row_idx, "before_text"] = updated_text
                        break

    if result is None:
        bank_name = safe_str(row.get("은행명", "")).strip()
        거래점 = safe_str(row.get("거래점", "")).strip()

        if bank_name and 거래점:
            result = f"{bank_name}({거래점})"
        elif bank_name:
            result = bank_name
        elif 거래점:
            result = f"({거래점})"
        else:
            result = "미분류"

    return result

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

    branch = safe_str(row.get("거래지점", ""))
    if branch and branch != "미분류":
        excluded_texts.append(branch)
        bracket_matches = re.findall(r'\(([^)]+)\)', branch)
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
    """info_category.xlsx 로드 및 category_tables 구성 (구분 없음, 거래방법/거래지점 미사용)"""
    if not INFO_CATEGORY_FILE or not os.path.exists(INFO_CATEGORY_FILE):
        return None
    category_df = load_info_category(INFO_CATEGORY_FILE, default_empty=True)
    if category_df is None or category_df.empty:
        return None
    category_df = normalize_category_df(category_df)
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
    """cash_before → cash_after 생성. info_category의 전처리/후처리·기타거래 적용 (거래방법/거래지점 미사용). before/after는 MyCash 폴더."""
    if input_file is None:
        input_file = os.path.join(_SCRIPT_DIR, INPUT_FILE)
    if output_file is None:
        output_file = os.path.join(_SCRIPT_DIR, OUTPUT_FILE)
    try:
        df = pd.read_excel(input_file, engine='openpyxl')
    except Exception as e:
        print(f"오류: {input_file} 읽기 실패 - {e}")
        return False

    if not INFO_CATEGORY_FILE or not os.path.exists(INFO_CATEGORY_FILE):
        try:
            if not df.empty:
                create_category_table(df)
            else:
                create_empty_info_category(INFO_CATEGORY_FILE)
        except Exception as e:
            print(f"오류: info_category(금융정보) 생성 실패 - {e}")
            return False

    category_tables = load_category_table()
    if category_tables is None:
        print(f"오류: {INFO_CATEGORY_FILE} 로드 실패")
        return False

    df["before_text"] = df.apply(create_before_text, axis=1)

    # 전처리/후처리 매칭 전에 적요·내용·거래점·송금메모를 주식회사→(주) 등으로 정규화
    for col in ['적요', '내용', '거래점', '송금메모']:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: safe_str(v))

    df["입출금"] = df.apply(classify_1st_category, axis=1)
    df.index.to_series().apply(lambda idx: classify_2_chasu(idx, df, category_tables, create_before_text))
    if '계정과목' in category_tables:
        apply_category_from_bank(df, category_tables['계정과목'])
    else:
        if '카테고리' not in df.columns:
            df['카테고리'] = '미분류'
    df["기타거래"] = df.index.to_series().apply(lambda idx: classify_etc(idx, df, category_tables))

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

    # 구분/적요/내용/거래점/송금메모/기타거래: space 1개 이상이면 space 1개로 치환
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

    for col in ['구분', '적요', '내용', '거래점', '송금메모', '기타거래']:
        if col in result_df.columns:
            result_df[col] = result_df[col].apply(normalize_spaces)

    try:
        success = safe_write_excel(result_df, output_file)
        if not success:
            print(f"오류: 파일 저장 실패 - {output_file}")
            return False
    except Exception as e:
        print(f"오류: 파일 저장 중 예외 발생 - {e}")
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
            integrate_cash_transactions()
            return
        elif command == 'classify':
            success = classify_and_save()
            if not success:
                print("카테고리 분류 중 오류가 발생했습니다.")
            return

    cash_before_path = os.path.join(_SCRIPT_DIR, INPUT_FILE)
    if not os.path.exists(cash_before_path) or os.path.getsize(cash_before_path) == 0:
        integrate_cash_transactions()
    else:
        classify_and_save()

if __name__ == '__main__':
    main()
