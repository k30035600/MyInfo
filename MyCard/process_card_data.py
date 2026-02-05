# -*- coding: utf-8 -*-
"""
process_card_data.py — 카드 전용. (은행 관련 역할 없음)

[역할]
- 카드 엑셀 원본을 표준 형식 DataFrame으로 읽기
  → 카드 Source → card_before.xlsx 만들 때 사용
- 카드 파일 통합: .source 폴더의 카드 엑셀을 모아 card_before.xlsx 생성
- 신용카드 Source → card_before: .source 폴더 엑셀 읽기
  → 행의 컬럼이 모두 공백이면 skip
  → HEADER_TO_STANDARD에 해당하는 행은 헤더 행으로 간주, 해당 행에서 인덱스 취득 후 다음 헤더 행이 나올 때까지 그 인덱스로 card_before 컬럼에 매핑
  → 카드사는 파일명에서 취득, 할부 0은 공백 처리
  → 카테고리는 card_category.xlsx 키워드로 분류 (파일 없으면 생성)

[기능]
- integrate_card_excel(): Source 루트 *.xls/*.xlsx만 모아 card_before.xlsx 생성
- create_category_table: card_category.xlsx 생성·갱신 (분류 규칙)

[카테고리 테이블 분류 구분]
- 은행거래(bank_category): 분류 = 전처리, 후처리, 거래방법, 거래지점
- 신용카드(card_category): 분류 = 계정과목, 업종분류 (본 모듈)

.source는 .xls, .xlsx만 취급.
"""
import pandas as pd
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

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
SOURCE_DATA_DIR = os.path.join(PROJECT_ROOT, '.source')
SOURCE_CARD_DIR = os.path.join(PROJECT_ROOT, '.source', 'Card')

CARD_BEFORE_FILE = "card_before.xlsx"
CATEGORY_FILE = "card_category.xlsx"
# card_before.xlsx 컬럼 8개 (카테고리는 가맹점명 기반 card_category.xlsx로 분류)
CARD_BEFORE_COLUMNS = [
    '카드사', '카드번호', '이용일', '이용금액', '가맹점명', '사업자번호', '할부', '카테고리'
]
EXCEL_EXTENSIONS = ('*.xls', '*.xlsx')
SEARCH_COLUMNS = ['적요', '내용', '거래점', '송금메모', '가맹점명']
# .source 헤더명 → card_before.xlsx 표준 컬럼 (카테고리는 card_category.xlsx 키워드로 분류)
# 헤더 행에서 인덱스를 취득하고, 다음 헤더 행이 나올 때까지 해당 인덱스로 매핑
HEADER_TO_STANDARD = {
    '카드사': ['카드사', '카드명'],
    '카드번호': ['카드번호'],
    '이용일': ['이용일', '이용일자', '승인일', '승인일자', '거래일', '거래일자', '매출일', '매출일자', '확정일', '확정일자'],
    '이용금액': ['이용금액', '승인금액', '매출금액', '거래금액'],
    '가맹점명': ['가맹점명', '이용처', '승인가맹점'],
    '사업자번호': ['사업자번호', '가맹점사업자번호', '가맹점 사업자번호', '사업자등록번호'],
    '할부': ['할부', '할부기간'],
}
# 금액 컬럼으로 간주할 헤더 키워드 (포함 시 숫자로 변환)
AMOUNT_COLUMN_KEYWORDS = ('금액', '입금', '출금', '잔액')

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

def clean_amount(value):
    """금액 데이터 정리 (쉼표 제거, 숫자 변환)."""
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


def normalize_brackets(text):
    """괄호 쌍 정규화: (( → (, )) → (, 불균형 시 보정."""
    if not text:
        return text
    text = text.replace('((', '(')
    text = text.replace('))', ')')
    open_count = text.count('(')
    close_count = text.count(')')
    if open_count > close_count:
        text = text + ')' * (open_count - close_count)
    elif close_count > open_count:
        text = '(' * (close_count - open_count) + text
    return text


def remove_numbers(text):
    """문자열에서 숫자 제거."""
    if not text:
        return text
    return re.sub(r'\d+', '', text)


def _business_number_digits(value):
    """사업자번호 셀 값에서 숫자만 추출(10자리). Excel 숫자형(1234567890.0)·9자리(앞 0 제거) 보정."""
    if pd.isna(value) or value == '':
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        n = int(float(value))
        if n < 0 or n >= 10 ** 10:
            return None
        return str(n).zfill(10) if n < 10 ** 9 else str(n)
    s = str(value).strip()
    digits = re.sub(r'\D', '', s)
    if len(digits) == 8:
        return digits.zfill(10)
    if len(digits) == 9:
        return digits.zfill(10)
    if len(digits) == 10:
        return digits
    return None


def _normalize_business_number(value):
    """사업자번호를 000-00-00000 형식으로만 정규화. card_before에는 이 형식만 저장(신한 숫자형·9자리 보정)."""
    digits = _business_number_digits(value)
    if digits is None:
        return ''
    return f'{digits[:3]}-{digits[3:5]}-{digits[5:]}'


def _normalize_할부(val):
    """할부를 숫자(int) 또는 일시불('')로 정규화. 0/일시불 → '', 3/6/12 등 → int. '3개월' 등에서 숫자만 추출."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ''
    s = str(val).strip()
    if s in ('', '0', '일시불'):
        return ''
    try:
        n = int(float(val))
        return '' if n == 0 else n
    except (TypeError, ValueError):
        pass
    m = re.match(r'^(\d+)', s)
    if m:
        n = int(m.group(1))
        return '' if n == 0 else n
    return ''


# =========================================================
# 1. 카드 엑셀 원본 읽기 + 카드 파일 통합 → card_before.xlsx
# =========================================================

def _card_excel_files(source_dir):
    """Source 루트 폴더에서만 .xls, .xlsx 파일 목록 수집."""
    out = []
    if not source_dir.exists():
        return out
    for ext in EXCEL_EXTENSIONS:
        out.extend(source_dir.glob(ext))
    return sorted(set(out), key=lambda p: (str(p), p.name))


def _amount_columns_to_numeric(df):
    """컬럼명에 금액·입금·출금·잔액이 포함된 컬럼을 숫자형으로 변환."""
    for col in df.columns:
        if any(kw in str(col) for kw in AMOUNT_COLUMN_KEYWORDS):
            df[col] = df[col].map(clean_amount)
    return df


def _card_company_from_filename(file_name):
    """파일명에서 카드사명 취득. 첫 '_' 앞 부분 또는 확장자 제거한 이름."""
    stem = Path(file_name).stem.strip()
    if not stem:
        return ''
    if '_' in stem:
        return stem.split('_')[0].strip()
    return stem


def _normalize_header_string(s):
    """헤더 문자열 정규화 (공백·BOM·줄바꿈 통일)."""
    if pd.isna(s) or s == '':
        return ''
    sh = str(s).strip().strip('\ufeff\ufffe').replace('\n', ' ').replace('\r', ' ')
    return re.sub(r'\s+', ' ', sh).strip()


def _map_source_header_to_standard(source_header):
    """Source 엑셀 헤더명 → card_before 표준 컬럼 (카테고리는 card_category로 채움)."""
    sh = _normalize_header_string(source_header)
    if not sh:
        return None
    sh_compact = sh.replace(' ', '')
    for std_col, keywords in HEADER_TO_STANDARD.items():
        for kw in keywords:
            kw_c = kw.replace(' ', '')
            if kw_c in sh_compact or sh_compact in kw_c or kw in sh or sh in kw:
                return std_col
    return None


# .source에서 헤더로 쓰이는 문자열 집합 (헤더인 행 판별용)
_HEADER_LIKE_STRINGS = None


def _get_header_like_strings():
    """HEADER_TO_STANDARD 키워드 + 표준 컬럼명 모음."""
    global _HEADER_LIKE_STRINGS
    if _HEADER_LIKE_STRINGS is not None:
        return _HEADER_LIKE_STRINGS
    s = set(CARD_BEFORE_COLUMNS)
    for keywords in HEADER_TO_STANDARD.values():
        for kw in keywords:
            s.add(str(kw).strip())
    _HEADER_LIKE_STRINGS = s
    return s


def _looks_like_header_row(row, columns):
    """행이 헤더 행인지 판별. columns: 검사할 컬럼 인덱스/키 iterable (source_columns 또는 range(num_cols))."""
    header_set = _get_header_like_strings()
    match_count = 0
    non_empty = 0
    for c in columns:
        val = row.get(c, row.get(str(c)))
        if pd.isna(val) or str(val).strip() == '':
            continue
        non_empty += 1
        cell = str(val).strip()
        if cell in header_set:
            match_count += 1
        else:
            for kw in header_set:
                if kw in cell or cell in kw:
                    match_count += 1
                    break
    if non_empty == 0:
        return False
    return match_count >= 2 and match_count >= non_empty * 0.5


def _build_mapping_from_header_row(row):
    """헤더 행에서 컬럼 인덱스 → 표준 컬럼 매핑 구함. 다음 헤더 행이 나올 때까지 사용."""
    idx_to_std = {}
    for i in row.index:
        try:
            col_idx = int(i)
        except (TypeError, ValueError):
            continue
        val = row.get(i, row.get(str(i)))
        std_col = _map_source_header_to_standard(val)
        if std_col:
            idx_to_std[col_idx] = std_col
    return idx_to_std


def _row_as_dict(row_tuple, num_cols):
    """itertuples() 결과를 row.get(i)/row.index 호환 dict로 변환. header=None이면 _0,_1,_2,… (0-based)."""
    d = {}
    for i in range(num_cols):
        v = getattr(row_tuple, '_' + str(i), None)
        if v is None:
            v = getattr(row_tuple, '_' + str(i + 1), None)
        d[i] = v
    d['index'] = list(range(num_cols))

    class RowLike:
        __slots__ = ('_d', 'index')

        def get(self, i, default=None):
            return self._d.get(i, self._d.get(str(i), default))

    r = RowLike()
    r._d = d
    r.index = d['index']
    return r


def _row_from_mapping(row, idx_to_std, card_company_from_file):
    """인덱스 매핑으로 한 행을 표준 8컬럼 dict로 변환. 카드사는 파일명에서, 할부 0은 공백."""
    new_row = {col: '' for col in CARD_BEFORE_COLUMNS}
    for i in sorted(idx_to_std.keys()):
        std_col = idx_to_std[i]
        if new_row[std_col]:
            continue
        val = row.get(i, row.get(str(i)))
        if pd.notna(val) and str(val).strip() != '':
            if std_col == '이용일' and not _is_date_like_value(val):
                # 신한카드: 데이터 행 맨 앞 순번 컬럼(1,2,3…)인 경우 인접 컬럼(거래일) 사용
                alt = row.get(i + 1, row.get(str(i + 1)))
                if pd.notna(alt) and str(alt).strip() != '' and _is_date_like_value(alt):
                    new_row['이용일'] = str(alt).strip()
                continue
            new_row[std_col] = str(val).strip()
    if card_company_from_file:
        new_row['카드사'] = card_company_from_file
    return _normalize_row_values(new_row)


def _normalize_row_values(new_row):
    """표준 행의 이용금액·사업자번호·할부·이용일 값을 정규화."""
    for col in CARD_BEFORE_COLUMNS:
        if col == '이용금액' and new_row.get(col) and str(new_row[col]).replace(',', '').replace('-', '').strip():
            try:
                new_row[col] = clean_amount(new_row[col])
            except Exception:
                pass
        elif col == '사업자번호' and new_row.get(col):
            new_row[col] = _normalize_business_number(new_row[col])
        elif col == '할부':
            new_row[col] = _normalize_할부(new_row[col])
        elif col == '이용일' and new_row.get(col):
            new_row[col] = _normalize_date_value(new_row[col])
    return new_row


def _normalize_date_value(val):
    """이용일 값을 YYYY-MM-DD 형식으로 정규화."""
    if pd.isna(val) or val == '' or (isinstance(val, str) and not str(val).strip()):
        return str(val).strip() if val else ''
    try:
        if hasattr(val, 'strftime'):
            return val.strftime('%Y-%m-%d')
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            n = int(float(val))
            if n >= 1000:
                base = datetime(1899, 12, 30)
                return (base + timedelta(days=n)).strftime('%Y-%m-%d')
            return str(val).strip()
        s = str(val).strip()
        if re.match(r'^\d{4}-\d{2}-\d{2}', s):
            return s[:10]
        if '/' in s or '-' in s or ('.' in s and re.match(r'^\d{4}\.\d', s)):
            parts = re.split(r'[/\-.]', s)
            if len(parts) >= 3:
                a, b, c = [x.zfill(2) for x in parts[:3]]
                if len(a) == 2:
                    y = int(a)
                    year = (2000 + y) if y < 50 else (1900 + y)
                    return f'{year}-{b}-{c}'
                return f'{a}-{b}-{c}' if len(a) == 4 else s
        return s
    except Exception:
        return str(val).strip()


def _is_date_like_value(val):
    """이용일로 쓸 만한 값인지 판별. 0/1 같은 코드·순번은 False."""
    if pd.isna(val) or val == '':
        return False
    s = str(val).strip()
    if not s:
        return False
    if hasattr(val, 'strftime'):
        return True
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        n = int(float(val))
        if n < 1000:  # Excel serial이 아닌 작은 숫자(코드/순번)
            return False
        return True
    # 문자열: 슬래시·하이픈 포함이면 날짜 형식 (25/12/09, 2025-12-09 등)
    if '/' in s or '-' in s:
        return True
    # 현대카드 등 yyyy.mm.dd 형식 (1.0 같은 순번 제외)
    if '.' in s and re.match(r'^\d{4}\.\d', s):
        return True
    if s.isdigit() and int(s) < 1000:
        return False
    return True


def _row_to_standard_columns(row, source_columns):
    """.source 한 행(Series)을 표준 8컬럼 dict로 변환."""
    new_row = {col: '' for col in CARD_BEFORE_COLUMNS}
    for src_col in source_columns:
        std_col = _map_source_header_to_standard(src_col)
        if std_col is None:
            continue
        val = row.get(src_col, row.get(str(src_col)))
        if pd.notna(val) and str(val).strip() != '':
            if not new_row[std_col]:
                # 이용일은 날짜 형태인 값만 채움 (0/1/71 등은 매출일·이용일자 등이 덮어쓰도록 건너뜀)
                if std_col == '이용일' and not _is_date_like_value(val):
                    continue
                new_row[std_col] = str(val).strip()
    return _normalize_row_values(new_row)


def _extract_rows_from_sheet(df, card_company_from_file):
    """시트 DataFrame에서 표준 8컬럼 행 리스트 추출."""
    rows = []
    num_cols = len(df.columns)
    idx_to_std = None
    for row_tuple in df.itertuples(index=False):
        row = _row_as_dict(row_tuple, num_cols)
        if all(pd.isna(row.get(i, None)) or str(row.get(i, '')).strip() == '' for i in range(num_cols)):
            continue
        if idx_to_std is None:
            idx_to_std = _build_mapping_from_header_row(row)
            continue
        if _looks_like_header_row(row, range(num_cols)):
            idx_to_std = _build_mapping_from_header_row(row)
            continue
        new_row = _row_from_mapping(row, idx_to_std, card_company_from_file)
        if all(not v or (isinstance(v, str) and not str(v).strip()) for v in new_row.values()):
            continue
        card_no = new_row.get('카드번호', '')
        if not card_no or (isinstance(card_no, str) and not str(card_no).strip()):
            continue
        rows.append(new_row)
    return rows


def _postprocess_combined_df(df):
    """통합 DataFrame 후처리: 가맹점명 채우기, 할부 정규화."""
    if df.empty:
        return df
    required = ['카드사', '카드번호', '이용일', '이용금액', '가맹점명']
    if all(c in df.columns for c in required):
        empty_merchant = (df['가맹점명'].fillna('').astype(str).str.strip() == '')
        has_card = (
            df['카드사'].notna() & (df['카드사'].astype(str).str.strip() != '') &
            df['카드번호'].notna() & (df['카드번호'].astype(str).str.strip() != '') &
            df['이용일'].notna() & (df['이용일'].astype(str).str.strip() != '') &
            df['이용금액'].notna() & empty_merchant
        )
        df.loc[has_card, '가맹점명'] = df.loc[has_card, '카드사']
    if '할부' in df.columns:
        df['할부'] = df['할부'].apply(
            lambda v: '' if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ('', '0', '일시불') else v
        )
    return df


def integrate_card_excel(output_file=None, base_dir=None, skip_write=False):
    """MyInfo/.source/Card 의 카드 엑셀을 모아 MyInfo/.source/card_before.xlsx 생성.

    - 테이블 헤더: 카드사, 카드번호, 이용일, 이용금액, 가맹점명, 사업자번호, 할부, 카테고리 (card_before.xlsx 8컬럼)
    - skip_write=True 이면 파일 쓰지 않고 DataFrame만 반환.

    base_dir: 무시됨. 원본은 .source/Card, 출력은 Source/ 사용.
    """
    source_dir = Path(SOURCE_CARD_DIR)
    output_path = Path(SOURCE_DATA_DIR) / (output_file or CARD_BEFORE_FILE)

    all_rows = []
    for file_path in _card_excel_files(source_dir):
        name = file_path.name
        suf = file_path.suffix.lower()
        card_company_from_file = _card_company_from_filename(name)
        try:
            engine = 'xlrd' if suf == '.xls' else 'openpyxl'
            xls = pd.ExcelFile(file_path, engine=engine)
            for sheet_name in xls.sheet_names:
                try:
                    df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, engine=engine)
                    if df is not None and not df.empty:
                        all_rows.extend(_extract_rows_from_sheet(df, card_company_from_file))
                except Exception as e:
                    print(f"오류: {name} 시트 '{sheet_name}' 읽기 실패 - {e}")
        except Exception as e:
            print(f"오류: {name} 처리 실패 - {e}")

    combined_df = pd.DataFrame(all_rows, columns=CARD_BEFORE_COLUMNS) if all_rows else pd.DataFrame(columns=CARD_BEFORE_COLUMNS)
    combined_df = _postprocess_combined_df(combined_df)

    if not skip_write:
        try:
            if combined_df.empty:
                combined_df.to_excel(output_path, index=False, engine='openpyxl')
            else:
                safe_write_excel(combined_df, str(output_path))
        except Exception as e:
            print(f"오류: {output_path} 저장 실패 - {e}")
    return combined_df


# =========================================================
# 2. 카테고리 테이블 생성: card_before.xlsx 내용을 보고 card_category.xlsx 생성
# =========================================================

# card_category.xlsx 기본 규칙: 가맹점명 키워드로 계정과목 분류 (분류, 키워드, 카테고리)
# 계정과목 기준 정렬(가나다). 선매칭(파리바게뜨/베이커리, 씨유, 이마트/롯데마트)은 병원·기타잡비(마트)보다 먼저 적용.
_PRECEDENCE_RULES = [  # 병원 등보다 먼저 매칭 (파리바게뜨 국제성모병원점, 씨유 국제성모병원, 이마트/롯데마트는 주식비/부식비)
    {'분류': '계정과목', '키워드': '파리바게뜨/베이커리', '카테고리': '외식/회식/간식'},
    {'분류': '계정과목', '키워드': '씨유/CU', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '(주)이마트/롯데마트/식자재/이마트', '카테고리': '주식비/부식비'},
]
DEFAULT_CARD_CATEGORY_ROWS = [
    *_PRECEDENCE_RULES,
    # 계정과목 기준 정렬 (가나다순)
    # 가전/가구/의류/생필품
    {'분류': '계정과목', '키워드': '가전/의류/가구/023/나눔과어울림', '카테고리': '가전/가구/의류/생필품'},
    {'분류': '계정과목', '키워드': '비와이씨/삼성전자/현대아울렛/나무다움/어패럴', '카테고리': '가전/가구/의류/생필품'},
    {'분류': '계정과목', '키워드': '스퀘어/자라/공영쇼핑/스퀘어/쇼핑/에이비씨/이랜드', '카테고리': '가전/가구/의류/생필품'},
    {'분류': '계정과목', '키워드': '몰테일/이케아/버킷/신세계/올리브영', '카테고리': '가전/가구/의류/생필품'},
    # 차량유지/교통비
    {'분류': '계정과목', '키워드': '버스/택시/차량유지/자동차/지하철/칼텍스/자동차보험/차량보험', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '북서울에너지/피킹/도로공사/티머니/에이티씨', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '인천30/인천32/시설공단/문학터널/문학개발/주유소', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '만월산/선학현대/후불교통/로드801/에너지/시설안전', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '파킹/현대오일/태리/코레일/철도', '카테고리': '차량유지/교통비'},
    {'분류': '계정과목', '키워드': '시설관리/기아오토큐/시설공단/국민오일', '카테고리': '차량유지/교통비'},
    # 귀금속
    {'분류': '계정과목', '키워드': '금은방/귀금속/거래소', '카테고리': '귀금속'},
    # 기타잡비
    {'분류': '계정과목', '키워드': '클락에이/CU/GS/마트/쿠팡/네이버/후이즈/타이거', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '토스/쇼핑몰/쇼핑/보타나/공공기관/결재대행/결제대행', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': 'NICE/SMS/면세점/에이치/제이디/라프/씨유/플라워', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '엠에스/세탁소/세븐일레븐/법원/미앤미/헤어/지에스', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '예스이십사/코리아세븐/건설기술/티몬/에이스', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '다온나/아이지/미니스톱/우체국/월드/이투유/나이스', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '더에덴/옥션/나래/로그인/메트로/홈엔/ARS/카카오', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '와이에스/다날/홈마트/슈퍼/로웰/유니윌/코페이', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '스테이지/이마트24/부경/에스씨/부경/목욕탕/구글', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '다이소/빈티지/마이리얼/홈쇼핑/올댓/그릇/로스', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '컬리페이/키오스크/에스지씨/에델/크린토피아/미성', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '블랙벤자민/LIVING/슬립/세탁/만물/그릇/유진/두찜', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '티무/황실/KICC/KCP/마이/플래티넘/몽실/가위', '카테고리': '기타잡비'},
    {'분류': '계정과목', '키워드': '이니시스/메머드', '카테고리': '기타잡비'},
    # 레저/휴양/취미/오락
    {'분류': '계정과목', '키워드': '오락/취미/레저/휴양/교보문고', '카테고리': '레저/휴양/취미/오락'},
    {'분류': '계정과목', '키워드': '중국동방/CGV', '카테고리': '레저/휴양/취미/오락'},
    # 외식/회식/간식
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
    # 의료비
    {'분류': '계정과목', '키워드': '병원/의원/치과/약국/건강보험/나사렛/레푸스/메디컬', '카테고리': '의료비'},
    {'분류': '계정과목', '키워드': '이비인후과/신경외과/정형외과/엄마손/워너독', '카테고리': '의료비'},
    {'분류': '계정과목', '키워드': '견생냥품/동물의료/안과', '카테고리': '의료비'},
    # 제세공과금
    {'분류': '계정과목', '키워드': '국세/지방세/세외/주민세/행정안전부/연수구청', '카테고리': '제세공과금'},
    {'분류': '계정과목', '키워드': '소득세/교육청/소액합산/행정복지/자동차세/취득세', '카테고리': '제세공과금'},
    {'분류': '계정과목', '키워드': '지자체/곡공기관/인천광역시/부가가치세/전몰', '카테고리': '제세공과금'},
    # 주거비/통신비
    {'분류': '계정과목', '키워드': '수도/전기/한국전력/가스/통신/관리비/케이티/SK/수신료', '카테고리': '주거비/통신비'},
    # 주식비/부식비 (이마트/롯데마트/식자재는 _PRECEDENCE_RULES에서 선매칭)
    {'분류': '계정과목', '키워드': '주식/부식/반찬/농산물/SSG/건어물/씨푸드/웅이/과일/야채/코스트코/홈플러스', '카테고리': '주식비/부식비'},
    {'분류': '계정과목', '키워드': '정육점/세계로/생선/푸줏간/우아한/성필립보', '카테고리': '주식비/부식비'},
    # 현금처리
    {'분류': '계정과목', '키워드': '현금/서비스/대출', '카테고리': '현금처리'},
    {'분류': '계정과목', '키워드': '신한은행/하나은행/신한카드/리볼빙', '카테고리': '현금처리'},
    # 업종분류
    {'분류': '업종분류', '키워드': '369101', '카테고리': '귀금속및관련제품제조업'},
    {'분류': '업종분류', '키워드': '512293', '카테고리': '복권발행및판매업'},
    {'분류': '업종분류', '키워드': '513934', '카테고리': '시계및귀금속제품도매업'},
    {'분류': '업종분류', '키워드': '522082/924906', '카테고리': '복권발행및판매업'},
    {'분류': '업종분류', '키워드': '924917', '카테고리': '기타사행시설관리및운영업'},
    {'분류': '업종분류', '키워드': '552201/552202/552203/552204/552206', '카테고리': '일반유흥주점업'},
    {'분류': '업종분류', '키워드': '552207/552208/552209/552210/552211/552211/552211', '카테고리': '기타주점업'},
    {'분류': '업종분류', '키워드': '513942/523931', '카테고리': '운동및경기용품도매업'},
    {'분류': '업종분류', '키워드': '551001', '카테고리': '호텔업'},
    {'분류': '업종분류', '키워드': '621000', '카테고리': '항공여객운송업'},
    {'분류': '업종분류', '키워드': '621001', '카테고리': '항공화물운송업'},
    {'분류': '업종분류', '키워드': '630101', '카테고리': '항공및육상화물취급업'},
    {'분류': '업종분류', '키워드': '921904', '카테고리': '무도장운영업'},
    {'분류': '업종분류', '키워드': '924303', '카테고리': '골프장운영업'},
    {'분류': '업종분류', '키워드': '924307', '카테고리': '골프연습장운영업'},
    {'분류': '업종분류', '키워드': '924308', '카테고리': '골프연습장운영업'},
]


def create_category_table(df=None, category_filepath=None):
    """card_category.xlsx 생성 (신용카드 전용). 분류 = 계정과목, 업종분류. MyInfo/.source에 저장.
    df 없어도 기본 규칙으로 생성. category_filepath: 저장 경로. None이면 .source/card_category.xlsx."""
    category_data = list(DEFAULT_CARD_CATEGORY_ROWS)

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

    if category_filepath:
        out_path = str(Path(category_filepath).resolve())
    else:
        out_path = str(Path(SOURCE_DATA_DIR) / CATEGORY_FILE)
    try:
        parent_dir = os.path.dirname(out_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        if len(category_df) == 0:
            category_df = pd.DataFrame(columns=['분류', '키워드', '카테고리'])

        category_df.to_excel(out_path, index=False, engine='openpyxl')

        if not os.path.exists(out_path):
            raise FileNotFoundError(f"오류: 파일 생성 후에도 {out_path} 파일이 존재하지 않습니다.")

    except PermissionError as e:
        print(f"오류: 파일 쓰기 권한이 없습니다 - {out_path}")
        raise
    except Exception as e:
        print(f"오류: card_category.xlsx 파일 생성 실패 - {e}")
        raise

    return category_df


def apply_category_from_merchant(df, category_df):
    """가맹점명을 기초로 card_category 규칙(분류, 키워드, 카테고리)을 적용해 df['카테고리'] 채움.
    계정과목 분류를 먼저 적용하고, 키워드(슬래시 구분)가 가맹점명에 포함되면 해당 카테고리 할당.
    벡터화로 행 단위 iterrows 제거하여 대용량에서 속도 개선."""
    if df is None or df.empty or category_df is None or category_df.empty:
        return df
    if '가맹점명' not in df.columns:
        return df
    if '카테고리' not in df.columns:
        df = df.copy()
        df['카테고리'] = ''
    # 컬럼명 공백 제거
    category_df = category_df.copy()
    category_df.columns = [str(c).strip() for c in category_df.columns]
    need_cols = ['분류', '키워드', '카테고리']
    if not all(c in category_df.columns for c in need_cols):
        return df
    # 선매칭 규칙(_PRECEDENCE_RULES)을 항상 맨 앞에 붙여 Excel에 없어도 이마트/롯데마트 → 주식비/부식비 적용
    precedence_df = pd.DataFrame(_PRECEDENCE_RULES)
    precedence_df = precedence_df[need_cols] if all(c in precedence_df.columns for c in need_cols) else pd.DataFrame(columns=need_cols)
    if len(precedence_df) > 0:
        category_df = pd.concat([precedence_df, category_df], ignore_index=True)
        category_df = category_df.drop_duplicates(subset=need_cols, keep='first').reset_index(drop=True)
    # 계정과목 우선 적용 (가맹점명 기반 분류), 그 다음 업종분류 등
    order = ['계정과목', '업종분류']
    precedence_keys = {
        (str(r.get('분류', '')).strip(), str(r.get('키워드', '')).strip(), str(r.get('카테고리', '')).strip())
        for r in _PRECEDENCE_RULES
    }
    # 주식비/부식비 중 이마트/롯데마트/식자재 키워드 포함 행도 선매칭 (예전 Excel 호환)
    def is_precedence(row):
        key = (str(row.get('분류', '')).strip(), str(row.get('키워드', '')).strip(), str(row.get('카테고리', '')).strip())
        if key in precedence_keys:
            return True
        if key[0] == '계정과목' and key[2] == '주식비/부식비' and key[1]:
            kw = key[1]
            if '롯데마트' in kw or '(주)이마트' in kw or '식자재' in kw:
                return True
        return False
    cat_sorted = category_df.copy()
    cat_sorted['_order'] = cat_sorted['분류'].apply(
        lambda x: order.index(str(x).strip()) if str(x).strip() in order else 999
    )
    cat_sorted['_priority'] = cat_sorted.apply(lambda row: 0 if is_precedence(row) else 1, axis=1)
    cat_sorted = cat_sorted.sort_values(['_order', '_priority']).drop(columns=['_order', '_priority'], errors='ignore')
    df = df.copy()
    # 카테고리 컬럼을 object로 변환해 문자열 할당 시 FutureWarning 방지 (Excel 로드 시 float64인 경우)
    df['카테고리'] = df['카테고리'].astype(object)
    # 가맹점명 시리즈 (NaN은 빈 문자열)
    merchants = df['가맹점명'].fillna('').astype(str).apply(safe_str)
    # 1단계: 선매칭 규칙만 먼저 적용(덮어쓰기). iterrows/Excel 순서 무관.
    for rule in _PRECEDENCE_RULES:
        kw_str = safe_str(rule.get('키워드', ''))
        if not kw_str:
            continue
        kws = [k.strip() for k in kw_str.split('/') if k.strip()]
        if not kws:
            continue
        r_match = pd.Series(False, index=df.index)
        for kw in kws:
            if not kw:
                continue
            # "이마트" 단독 키워드: 이마트24(기타잡비) 제외, "이마트"만 주식비/부식비
            if kw == '이마트':
                r_match |= (merchants.str.contains('이마트', regex=False) & ~merchants.str.contains('이마트24', regex=False))
            else:
                r_match |= merchants.str.contains(re.escape(kw), regex=False)
        if r_match.any():
            df.loc[r_match, '카테고리'] = safe_str(rule.get('카테고리', ''))
    # 2단계: 나머지 규칙은 빈 행만 채움
    empty_mask = (df['카테고리'].fillna('').astype(str).str.strip() == '')
    for _, cat_row in cat_sorted.iterrows():
        keywords_str = safe_str(cat_row.get('키워드', ''))
        if not keywords_str:
            continue
        keywords = [k.strip() for k in keywords_str.split('/') if k.strip()]
        if not keywords:
            continue
        cat_val = safe_str(cat_row.get('카테고리', ''))
        rule_match = pd.Series(False, index=df.index)
        for kw in keywords:
            if kw:
                rule_match |= merchants.str.contains(re.escape(kw), regex=False)
        # 선매칭 규칙: 매칭되는 행은 빈 여부와 관계없이 덮어씀. 그 외: 빈 행만 채움.
        is_prec = is_precedence(cat_row)
        rule_mask = rule_match if is_prec else (rule_match & empty_mask)
        if rule_mask.any():
            df.loc[rule_mask, '카테고리'] = cat_val
            empty_mask = empty_mask & ~rule_mask
        if not empty_mask.any():
            break
    return df


# =========================================================
# 3. 메인 함수
# =========================================================

def main():
    """카드 전용: integrate_card_excel 실행."""
    if len(sys.argv) > 1 and sys.argv[1] == 'integrate_card':
        integrate_card_excel()
        return
    integrate_card_excel()


if __name__ == '__main__':
    main()

