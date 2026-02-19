# -*- coding: utf-8 -*-
"""
process_card_data.py — 카드 전용. source → 전처리 → before / before → 계정과목 → 후처리 → after.

[전체 흐름]
  [before 생성] integrate_card_excel():
    (1) source: .source/Card 엑셀 읽기·통합
    (2) 전처리: category_table '전처리' 규칙으로 가맹점명·카드사 치환
    (3) before: 전처리만 반영하여 card_before.xlsx 저장 (후처리·계정과목 미적용)

  [after 생성] card_app._create_card_after():  (전처리후 다시 실행 시 호출)
    (4) before 파일 읽기
    (5) 계정과목 분류: category_table '계정과목' 규칙으로 키워드·카테고리 채움 (apply_category_from_merchant)
    (6) 후처리: category_table '후처리' 규칙으로 가맹점명·카드사 치환
    (7) after: card_after 저장

[카테고리 테이블 분류 구분]
- 전처리/후처리: 가맹점명·카드사 등 텍스트 치환
- 계정과목: 가맹점명 기반 키워드 매칭으로 카테고리 부여
.source는 .xls, .xlsx만 취급.
"""
import numpy as np
import pandas as pd
import os
import re
import sys
import unicodedata
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

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, '..'))
SOURCE_DATA_DIR = os.path.join(PROJECT_ROOT, '.source')
SOURCE_CARD_DIR = os.path.join(PROJECT_ROOT, '.source', 'Card')

CARD_BEFORE_FILE = "card_before.json"
# card_before.xlsx 컬럼 (추출 시 이용금액 사용 → 저장 전 입금액/출금액/취소로 변환)
_EXTRACT_COLUMNS = [
    '카드사', '카드번호', '이용일', '이용시간', '이용금액', '가맹점명', '사업자번호', '구분', '취소여부'
]
CARD_BEFORE_COLUMNS = [
    '카드사', '카드번호', '이용일', '이용시간', '입금액', '출금액', '취소', '가맹점명', '사업자번호', '구분'
]
EXCEL_EXTENSIONS = ('*.xls', '*.xlsx')
SEARCH_COLUMNS = ['적요', '내용', '거래점', '송금메모', '가맹점명']
# .source 헤더명 → card_before.xlsx 표준 컬럼 (카테고리는 category_table 신용카드 규칙으로 분류)
# 헤더 행에서 인덱스를 취득하고, 다음 헤더 행이 나올 때까지 해당 인덱스로 매핑
HEADER_TO_STANDARD = {
    '카드사': ['카드사', '카드명'],
    '카드번호': ['카드번호'],
    '이용일': ['이용일', '이용일자', '승인일', '승인일자', '거래일', '거래일자', '매출일', '매출일자', '확정일', '확정일자'],
    '이용시간': ['이용시간', '승인시간', '거래시간', '승인시각', '이용시각'],
    '이용금액': ['이용금액', '승인금액', '매출금액', '거래금액'],
    '취소여부': ['취소여부', '취소'],
    '가맹점명': ['가맹점명', '이용처', '승인가맹점'],
    '사업자번호': ['사업자번호', '가맹점사업자번호', '가맹점 사업자번호', '사업자등록번호'],
    # 할부 컬럼은 사용하지 않음. 구분은 과세유형 '폐업'일 때만 '폐업' 저장 (아래 과세유형_헤더키워드로 처리)
}
과세유형_헤더키워드 = '과세유형'
# 금액 컬럼으로 간주할 헤더 키워드 (포함 시 숫자로 변환)
AMOUNT_COLUMN_KEYWORDS = ('금액', '입금', '출금', '잔액')

try:
    from excel_io import safe_write_excel
except ImportError:
    safe_write_excel = None
try:
    from category_table_io import normalize_주식회사_for_match
except ImportError:
    def normalize_주식회사_for_match(text):
        if text is None or (isinstance(text, str) and not str(text).strip()):
            return '' if text is None else str(text).strip()
        val = str(text).strip()
        val = re.sub(r'[\s/]*주식회사[\s/]*', '(주)', val)
        val = re.sub(r'[\s/]*㈜[\s/]*', '(주)', val)
        val = re.sub(r'(\(주\)[\s/]*)+', '(주)', val)
        return val


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

if safe_write_excel is None:
    def safe_write_excel(df, filepath, max_retries=3):
        import time as _t
        for attempt in range(max_retries):
            try:
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                        _t.sleep(0.1)
                    except PermissionError:
                        if attempt < max_retries - 1:
                            _t.sleep(0.5)
                            continue
                        raise PermissionError(f"파일을 삭제할 수 없습니다: {filepath}")
                df.to_excel(filepath, index=False, engine='openpyxl')
                return True
            except PermissionError as e:
                if attempt < max_retries - 1:
                    _t.sleep(0.5)
                    continue
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


def _normalize_구분(val):
    """구분(할부)을 숫자(int) 또는 일시불('')로 정규화. 0/일시불 → '', 3/6/12 등 → int. '3개월' 등에서 숫자만 추출."""
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
    """Source 엑셀 헤더명 → card_before 표준 컬럼 (카테고리는 category_table 신용카드 규칙으로 채움)."""
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
    """HEADER_TO_STANDARD 키워드 + 표준 컬럼명 + 과세유형(헤더 행 판별용)."""
    global _HEADER_LIKE_STRINGS
    if _HEADER_LIKE_STRINGS is not None:
        return _HEADER_LIKE_STRINGS
    s = set(_EXTRACT_COLUMNS) | set(CARD_BEFORE_COLUMNS)
    for keywords in HEADER_TO_STANDARD.values():
        for kw in keywords:
            s.add(str(kw).strip())
    s.add(과세유형_헤더키워드)  # 신한카드 등 '과세유형' 있는 행을 헤더로 인식
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
    """헤더 행에서 컬럼 인덱스 → 표준 컬럼 매핑 구함. 과세유형 컬럼 인덱스도 반환(폐업→구분 저장용)."""
    idx_to_std = {}
    idx_과세유형 = None
    for i in row.index:
        try:
            col_idx = int(i)
        except (TypeError, ValueError):
            continue
        val = row.get(i, row.get(str(i)))
        raw = _normalize_header_string(val)
        # 전각/공백 제거 후 '과세유형' 포함 여부로 컬럼 인덱스 저장 (신한카드 등)
        if raw:
            raw_compact = _normalize_fullwidth(raw).replace(' ', '')
            if 과세유형_헤더키워드 in raw_compact:
                idx_과세유형 = col_idx
        std_col = _map_source_header_to_standard(val)
        if std_col:
            idx_to_std[col_idx] = std_col
    return (idx_to_std, idx_과세유형)


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


def _row_from_mapping(row, idx_to_std, card_company_from_file, idx_과세유형=None):
    """인덱스 매핑으로 한 행을 추출용 컬럼 dict로 변환. 카드사는 파일명에서. 구분은 할부 미사용, 과세유형 '폐업'일 때만 '폐업' 저장."""
    new_row = {col: '' for col in _EXTRACT_COLUMNS}
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
    if idx_과세유형 is not None:
        v = row.get(idx_과세유형, row.get(str(idx_과세유형)))
        if pd.notna(v):
            v_norm = _normalize_fullwidth(str(v).strip())
            if v_norm == '폐업' or '폐업' in v_norm:
                new_row['구분'] = '폐업'
    if card_company_from_file:
        new_row['카드사'] = card_company_from_file
    return _normalize_row_values(new_row)


def _normalize_fullwidth(val):
    """전각(Fullwidth) 문자 → 반각(Halfwidth) 변환 (예: ＳＫＴ５３２２ → SKT5322)."""
    if pd.isna(val) or val == '':
        return val
    return unicodedata.normalize('NFKC', str(val).strip())

def _normalize_row_values(new_row):
    """표준 행의 이용금액·사업자번호·구분·이용일 값을 정규화."""
    for col in ['카드사', '카드번호', '가맹점명']:
        if new_row.get(col):
            new_row[col] = _normalize_fullwidth(new_row[col])
    for col in _EXTRACT_COLUMNS:
        if col == '이용금액' and new_row.get(col) and str(new_row[col]).replace(',', '').replace('-', '').strip():
            try:
                new_row[col] = clean_amount(new_row[col])
            except Exception:
                pass
        elif col == '사업자번호' and new_row.get(col):
            new_row[col] = _normalize_business_number(new_row[col])
        elif col == '구분':
            # 구분은 과세유형 '폐업'일 때만 '폐업'. 할부 컬럼은 사용하지 않으므로 그 외는 공백 유지
            if str(new_row.get(col, '')).strip() != '폐업':
                new_row[col] = ''
        elif col == '이용일' and new_row.get(col):
            date_part, time_part = _split_datetime_value(new_row[col])
            new_row[col] = _normalize_date_value(date_part) if date_part else _normalize_date_value(new_row[col])
            if time_part and not (new_row.get('이용시간') and str(new_row.get('이용시간', '')).strip()):
                new_row['이용시간'] = _normalize_time_value(time_part)
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


def _split_datetime_value(val):
    """이용일 컬럼에 'yy/mm/dd'만 있거나 'yy/mm/dd hh:mm:ss' 등이 섞인 경우 날짜/시간 분리.
    반환: (date_str, time_str). 시간이 없으면 time_str은 ''."""
    if pd.isna(val) or val == '' or (isinstance(val, str) and not str(val).strip()):
        return ('', '')
    s = str(val).strip()
    if not s:
        return ('', '')
    # 공백 또는 T로 구분된 날짜+시간 패턴
    if ' ' in s:
        parts = s.split(None, 1)
        if len(parts) == 2 and re.search(r'\d{1,2}:\d{1,2}', parts[1]):
            return (parts[0].strip(), parts[1].strip())
    if 'T' in s and re.search(r'\d{1,2}:\d{1,2}', s):
        idx = s.index('T')
        return (s[:idx].strip(), s[idx + 1:].strip())
    return (s, '')


def _normalize_time_value(val):
    """시간 문자열을 hh:mm 또는 hh:mm:ss 형식으로 정규화."""
    if pd.isna(val) or val == '' or (isinstance(val, str) and not str(val).strip()):
        return ''
    s = str(val).strip()
    m = re.match(r'^(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?', s)
    if m:
        h, mi = m.group(1).zfill(2), m.group(2).zfill(2)
        sec = m.group(3)
        if sec is not None:
            return f'{h}:{mi}:{sec.zfill(2)}'
        return f'{h}:{mi}:00'
    return s


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
    """.source 한 행(Series)을 추출용 컬럼 dict로 변환."""
    new_row = {col: '' for col in _EXTRACT_COLUMNS}
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
    """시트 DataFrame에서 추출용 행 리스트 추출 (이용금액 포함)."""
    rows = []
    num_cols = len(df.columns)
    idx_to_std = None
    idx_과세유형 = None
    for row_tuple in df.itertuples(index=False):
        row = _row_as_dict(row_tuple, num_cols)
        if all(pd.isna(row.get(i, None)) or str(row.get(i, '')).strip() == '' for i in range(num_cols)):
            continue
        if idx_to_std is None:
            idx_to_std, idx_과세유형 = _build_mapping_from_header_row(row)
            continue
        if _looks_like_header_row(row, range(num_cols)):
            new_map, new_과세 = _build_mapping_from_header_row(row)
            for idx, std_col in list(idx_to_std.items()):
                if idx not in new_map:
                    new_map[idx] = std_col
            idx_to_std = new_map
            idx_과세유형 = new_과세 if new_과세 is not None else idx_과세유형
            continue
        new_row = _row_from_mapping(row, idx_to_std, card_company_from_file, idx_과세유형)
        if all(not v or (isinstance(v, str) and not str(v).strip()) for v in new_row.values()):
            continue
        card_no = new_row.get('카드번호', '')
        if not card_no or (isinstance(card_no, str) and not str(card_no).strip()):
            continue
        rows.append(new_row)
    return rows


def _load_prepost_rules(category_path=None):
    """category_table.json에서 전처리/후처리 규칙만 로드. 반환: (전처리_list, 후처리_list), 각 항목은 {'키워드': str, '카테고리': str}."""
    path = Path(category_path or os.path.join(PROJECT_ROOT, '.source', 'category_table.json'))
    if not path.exists():
        return [], []
    try:
        from category_table_io import load_category_table, normalize_category_df
        full = load_category_table(str(path), default_empty=True)
        if full is None or full.empty:
            return [], []
        full = normalize_category_df(full).fillna('')
        full.columns = [str(c).strip() for c in full.columns]
        if '분류' not in full.columns or '키워드' not in full.columns or '카테고리' not in full.columns:
            return [], []
        전처리 = []
        후처리 = []
        for _, row in full.iterrows():
            분류 = str(row.get('분류', '')).strip()
            키워드 = str(row.get('키워드', '')).strip()
            카테고리 = str(row.get('카테고리', '')).strip()
            if not 키워드:
                continue
            if 분류 == '전처리':
                전처리.append({'키워드': 키워드, '카테고리': 카테고리})
            elif 분류 == '후처리':
                후처리.append({'키워드': 키워드, '카테고리': 카테고리})
        # 긴 키워드 먼저 적용 (부분 치환 방지)
        전처리.sort(key=lambda x: len(x['키워드']), reverse=True)
        후처리.sort(key=lambda x: len(x['키워드']), reverse=True)
        return 전처리, 후처리
    except Exception as e:
        print(f"전처리/후처리 규칙 로드 실패: {e}", flush=True)
        return [], []


def _apply_rules_to_columns(df, columns_to_apply, rule_list):
    """지정 규칙 리스트만 컬럼에 적용 (전처리 또는 후처리). 키워드가 등장하는 부분을 카테고리로 치환(셀 전체가 키워드여도 치환)."""
    if df is None or df.empty or not columns_to_apply or not rule_list:
        return df
    df = df.copy()
    for col in columns_to_apply:
        if col not in df.columns:
            continue
        df[col] = df[col].fillna('').astype(str).apply(lambda v: safe_str(v))
    for col in columns_to_apply:
        if col not in df.columns:
            continue
        for rule in rule_list:
            kw = rule['키워드']
            cat = rule['카테고리']
            if not kw:
                continue
            kw_norm = normalize_주식회사_for_match(kw)
            if not kw_norm:
                continue
            df[col] = df[col].fillna('').astype(str).str.replace(kw_norm, cat, regex=False)
    return df


def _apply_전처리_only_to_columns(df, columns_to_apply):
    """card_before 저장 전 전처리만 적용 (가맹점명·카드사 등)."""
    전처리, _ = _load_prepost_rules()
    return _apply_rules_to_columns(df, columns_to_apply, 전처리 or [])


def _apply_후처리_only_to_columns(df, columns_to_apply):
    """card_after 생성 전 후처리만 적용 (가맹점명·카드사 등)."""
    _, 후처리 = _load_prepost_rules()
    return _apply_rules_to_columns(df, columns_to_apply, 후처리 or [])


def _postprocess_combined_df(df):
    """통합 DataFrame 후처리: 가맹점명 채우기. 구분은 할부 미사용, '폐업'만 유지."""
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
        sh_mask = (
            df['카드사'].fillna('').astype(str).str.strip().str.contains('신한', na=False) &
            (df['가맹점명'].fillna('').astype(str).str.strip() == '신한카드')
        )
        df.loc[sh_mask, '가맹점명'] = '신한카드_카드론'
    # 구분: 할부 미사용. 과세유형 '폐업'만 '폐업' 유지, 그 외는 모두 공백
    if '구분' in df.columns:
        df['구분'] = df['구분'].apply(
            lambda v: '폐업' if v is not None and str(v).strip() == '폐업' else ''
        )
    return df


def integrate_card_excel(output_file=None, base_dir=None, skip_write=False):
    """MyInfo/.source/Card 의 카드 엑셀을 모아 MyCard/card_before.xlsx 생성.

    - 테이블 헤더: 카드사, 카드번호, 이용일, 이용시간, 입금액, 출금액, 취소, 가맹점명, 사업자번호, 구분
    - skip_write=True 이면 파일 쓰지 않고 DataFrame만 반환.

    base_dir: 무시됨. 원본: .source/Card, 출력: MyCard 폴더.
    """
    source_dir = Path(SOURCE_CARD_DIR)
    output_path = Path(_SCRIPT_DIR) / (output_file or CARD_BEFORE_FILE)

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

    extract_df = pd.DataFrame(all_rows, columns=_EXTRACT_COLUMNS) if all_rows else pd.DataFrame(columns=_EXTRACT_COLUMNS)
    extract_df = _postprocess_combined_df(extract_df)

    # 이용금액 → 입금액/출금액/취소 변환 (card_before 저장용)
    # - 취소여부 "Y"/"취소" → 취소, 입금액=절대값, 출금액=0
    # - 신한카드(취소여부 컬럼 없음) + 이용금액 음수 → 취소로 간주
    # - 그 외 음수 → 포인트/할인(입금): 취소 없음, 입금액=절대값, 출금액=0
    if extract_df.empty:
        combined_df = pd.DataFrame(columns=CARD_BEFORE_COLUMNS)
    else:
        if '이용금액' in extract_df.columns:
            amt = pd.to_numeric(extract_df['이용금액'], errors='coerce').fillna(0)
            has_cancel_col = '취소여부' in extract_df.columns
            if has_cancel_col:
                cancel_flag = extract_df['취소여부'].astype(str).str.strip()
                is_cancel_by_flag = (cancel_flag.str.upper() == 'Y') | (cancel_flag == '취소')
            else:
                is_cancel_by_flag = pd.Series(False, index=extract_df.index)
            # 신한카드: 취소여부 없을 때만 음수면 취소
            is_cancel_shinhan = ~has_cancel_col & (amt < 0)
            is_cancel = is_cancel_by_flag | is_cancel_shinhan
            # 입금액: 취소면 절대값, 취소 아닌데 음수면 포인트/할인 절대값, 나머지 0
            extract_df['취소'] = np.where(is_cancel, '취소', '')
            # 취소 컬럼은 문자만: 0/NaN이 들어가지 않도록 문자열로 통일 (Excel에 0으로 보이는 것 방지)
            extract_df['취소'] = extract_df['취소'].astype(str).replace('nan', '').replace('0', '')
            extract_df['입금액'] = np.where(is_cancel, amt.abs(), np.where(amt < 0, amt.abs(), 0))
            extract_df['출금액'] = np.where(is_cancel, 0, np.where(amt > 0, amt, 0))
            extract_df = extract_df.drop(columns=['이용금액'], errors='ignore')
            extract_df = extract_df.drop(columns=['취소여부'], errors='ignore')
        else:
            if '입금액' not in extract_df.columns:
                extract_df['입금액'] = 0
            if '출금액' not in extract_df.columns:
                extract_df['출금액'] = 0
            if '취소' not in extract_df.columns:
                extract_df['취소'] = ''
        combined_df = extract_df[[c for c in CARD_BEFORE_COLUMNS if c in extract_df.columns]].reindex(columns=CARD_BEFORE_COLUMNS).copy()

        # 이용시간 없으면 00:00:00으로 채움
        if '이용시간' in combined_df.columns:
            def _fill_이용시간(v):
                if v is None or (isinstance(v, float) and pd.isna(v)): return '00:00:00'
                s = str(v).strip()
                return '00:00:00' if not s else s
            combined_df['이용시간'] = combined_df['이용시간'].apply(_fill_이용시간)

        # 가맹점명 "신한카드_카드론": 출금액(상환)을 입금액으로 옮기고 출금액 0
        if '가맹점명' in combined_df.columns and '입금액' in combined_df.columns and '출금액' in combined_df.columns:
            cardron = (combined_df['가맹점명'].fillna('').astype(str).str.strip() == '신한카드_카드론')
            if cardron.any():
                combined_df.loc[cardron, '입금액'] = combined_df.loc[cardron, '출금액']
                combined_df.loc[cardron, '출금액'] = 0

        # 전처리: before.xlsx 저장 전에 수행 (가맹점명·카드사 치환)
        try:
            combined_df = _apply_전처리_only_to_columns(combined_df, ['가맹점명', '카드사'])
        except Exception as e:
            print(f"경고: 전처리 적용 중 오류(무시하고 저장) - {e}")
        # card_before.xlsx 저장 시 입금액은 절대값으로 보장
        if '입금액' in combined_df.columns:
            combined_df['입금액'] = pd.to_numeric(combined_df['입금액'], errors='coerce').fillna(0).abs()

    if not skip_write:
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if str(output_path).endswith('.json'):
                try:
                    from data_json_io import safe_write_data_json
                    safe_write_data_json(str(output_path), combined_df)
                except ImportError:
                    safe_write_excel(combined_df, str(output_path))
            else:
                if combined_df.empty:
                    combined_df.to_excel(output_path, index=False, engine='openpyxl')
                else:
                    safe_write_excel(combined_df, str(output_path))
        except Exception as e:
            print(f"오류: {output_path} 저장 실패 - {e}")
    return combined_df


# 카테고리 분류: apply_category_from_merchant에서 계정과목만 사용, 키워드 길이 순, 기본값 기타거래


def create_category_table(df=None, category_filepath=None):
    """category_table.json 생성·갱신 (구분 없음). 분류 = 계정과목 등. category_create.md 파싱 또는 기본값 사용."""
    try:
        from category_table_defaults import get_default_rules
    except ImportError:
        _root = os.environ.get('MYINFO_ROOT') or os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from category_table_defaults import get_default_rules
    unique_category_data = get_default_rules('card')
    category_df = pd.DataFrame(unique_category_data).drop_duplicates(subset=['분류', '키워드', '카테고리'], keep='first')
    _root = os.environ.get('MYINFO_ROOT') or os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    default_info = os.path.join(_root, '.source', 'category_table.json')
    out_path = str(Path(category_filepath).resolve()) if category_filepath else default_info
    try:
        parent_dir = os.path.dirname(out_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        _root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from category_table_io import safe_write_category_table, load_category_table, normalize_category_df, CATEGORY_TABLE_COLUMNS
        if len(category_df) == 0:
            category_df = pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS)
        out = category_df[CATEGORY_TABLE_COLUMNS].copy()
        if os.path.exists(out_path):
            full = load_category_table(out_path, default_empty=True)
            if full is not None and not full.empty:
                full = normalize_category_df(full)
                if not full.empty:
                    out = pd.concat([full, out], ignore_index=True).drop_duplicates(subset=CATEGORY_TABLE_COLUMNS, keep='first')
        safe_write_category_table(out_path, out)
        if not os.path.exists(out_path):
            raise FileNotFoundError(f"오류: 파일 생성 후에도 {out_path} 파일이 존재하지 않습니다.")
    except PermissionError as e:
        print(f"오류: 파일 쓰기 권한이 없습니다 - {out_path}")
        raise
    except Exception as e:
        print(f"오류: category_table 생성 실패 - {e}")
        raise
    return category_df


def apply_category_from_merchant(df, category_df):
    """가맹점명을 기초로 category_table(신용카드) 규칙을 적용해 df['카테고리'] 채움.
    분류=계정과목만 사용. 키워드 길이 긴 순 적용. 기본값 기타거래, 매칭된 행만 계정과목으로 덮어씀."""
    if df is None or df.empty or category_df is None or category_df.empty:
        return df
    if '가맹점명' not in df.columns:
        return df
    if '카테고리' not in df.columns:
        df = df.copy()
        df['카테고리'] = ''
    if '키워드' not in df.columns:
        df['키워드'] = ''
    category_df = category_df.copy()
    category_df.columns = [str(c).strip() for c in category_df.columns]
    need_cols = ['분류', '키워드', '카테고리']
    if not all(c in category_df.columns for c in need_cols):
        return df
    # 계정과목만 사용. 행별 최대 키워드 길이 기준 정렬(긴 것 먼저). 매칭된 키워드가 더 긴 경우에만 덮어씀.
    account_mask = (category_df['분류'].astype(str).str.strip() == '계정과목')
    account_df = category_df.loc[account_mask].copy()
    if account_df.empty:
        return df
    def _max_kw_len(s):
        parts = [k.strip() for k in str(s).split('/') if k.strip()]
        return max(len(k) for k in parts) if parts else 0
    account_df['_max_klen'] = account_df['키워드'].apply(_max_kw_len)
    account_df = account_df.sort_values('_max_klen', ascending=False).drop(columns=['_max_klen'], errors='ignore')
    df = df.copy()
    df['카테고리'] = df['카테고리'].astype(object)
    df['키워드'] = df['키워드'].astype(object)
    df['카테고리'] = '기타거래'
    df['키워드'] = ''
    df['_matched_kw_len'] = 0
    merchants = df['가맹점명'].fillna('').astype(str).apply(safe_str)
    for _, cat_row in account_df.iterrows():
        cat_val = safe_str(cat_row.get('카테고리', '')).strip() or '기타거래'
        keywords_str = safe_str(cat_row.get('키워드', ''))
        if not keywords_str:
            continue
        keywords = [k.strip() for k in keywords_str.split('/') if k.strip()]
        if not keywords:
            continue
        # 키워드도 주식회사→(주) 정규화해 매칭 (데이터는 이미 safe_str로 정규화됨)
        keywords_norm = [normalize_주식회사_for_match(k) for k in keywords if k]
        if not keywords_norm:
            continue
        rule_match = pd.Series(False, index=df.index)
        for kw in keywords_norm:
            if kw:
                rule_match |= merchants.str.contains(re.escape(kw), regex=False, na=False)
        # 행별로 매칭된 키워드 중 가장 긴 것의 길이 (정규화된 키워드 기준)
        def longest_matched(m):
            matched = [k for k in keywords_norm if k and k in str(m)]
            return max(matched, key=len) if matched else ''
        matched_kw = merchants.apply(longest_matched)
        matched_len = matched_kw.str.len()
        # 기타거래(초기)이거나, 새로 매칭된 키워드가 기존보다 길 때만 덮어씀
        fill_mask = rule_match & (
            (df['카테고리'].fillna('').astype(str) == '기타거래') | (matched_len > df['_matched_kw_len'])
        )
        if fill_mask.any():
            df.loc[fill_mask, '카테고리'] = cat_val
            df.loc[fill_mask, '키워드'] = matched_kw.loc[fill_mask]
            df.loc[fill_mask, '_matched_kw_len'] = matched_len.loc[fill_mask]
    df = df.drop(columns=['_matched_kw_len'], errors='ignore')
    return df


def main():
    """카드 전용: integrate_card_excel 실행."""
    if len(sys.argv) > 1 and sys.argv[1] == 'integrate_card':
        integrate_card_excel()
        return
    integrate_card_excel()


if __name__ == '__main__':
    main()

