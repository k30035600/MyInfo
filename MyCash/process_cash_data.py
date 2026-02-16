# -*- coding: utf-8 -*-
"""
process_cash_data.py — 금융정보(MyCash) 전용. (카드 관련 역할 없음)

[역할]
- 카테고리: MyInfo/.source/category_table.json(금융정보 구분) 사용
- cash_after.xlsx는 bank_after + card_after 병합으로만 생성(cash_app.merge_bank_card_to_cash_after).
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

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, '..'))
# 금융정보 원본 업로드용: .source/Cash
SOURCE_CASH_DIR = os.path.join(PROJECT_ROOT, '.source', 'Cash')
CATEGORY_TABLE_FILE = os.path.join(os.environ.get('MYINFO_ROOT', PROJECT_ROOT), '.source', 'category_table.json')
CASH_CATEGORY_LABEL = '금융정보'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
try:
    from category_table_defaults import get_default_rules
except ImportError:
    get_default_rules = None
try:
    from category_table_io import (
        load_category_table as load_category_table_io,
        normalize_category_df,
        normalize_주식회사_for_match,
        CATEGORY_TABLE_COLUMNS,
    )
except ImportError:
    import json as _json
    def load_category_table(path, default_empty=True):
        path = str(path).replace('.xlsx', '.json') if path else None
        if not path or not os.path.exists(path): return pd.DataFrame(columns=['분류', '키워드', '카테고리']) if default_empty else None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = _json.load(f)
            return pd.DataFrame(data) if data else (pd.DataFrame(columns=['분류', '키워드', '카테고리']) if default_empty else None)
        except Exception:
            return pd.DataFrame(columns=['분류', '키워드', '카테고리']) if default_empty else None
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
    load_category_table_io = load_category_table
    CATEGORY_TABLE_COLUMNS = ['분류', '키워드', '카테고리']

OUTPUT_FILE = "cash_after.xlsx"


def ensure_all_cash_files():
    """금융정보에서는 category_table.json을 생성하지 않음. cash_after는 bank/card 병합(merge_bank_card)으로만 생성."""
    pass


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

def load_category_table():
    """category_table.json 로드 및 category_tables 구성 (구분 없음). 금융정보에서는 전처리/후처리 미적용, 계정과목·기타거래용으로만 사용. 파일 없으면 빈 dict 반환."""
    if not CATEGORY_TABLE_FILE or not os.path.exists(CATEGORY_TABLE_FILE):
        return {}
    category_df = load_category_table_io(CATEGORY_TABLE_FILE, default_empty=True)
    if category_df is None or category_df.empty:
        return {}
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
    """입력 파일 → cash_after 생성. 금융정보에서는 전처리/후처리 없음. 계정과목·기타거래만 적용. cash_after는 보통 bank/card 병합으로만 생성."""
    if input_file is None:
        input_file = os.path.join(_SCRIPT_DIR, "cash_before.xlsx")
    if output_file is None:
        output_file = os.path.join(_SCRIPT_DIR, OUTPUT_FILE)
    try:
        df = pd.read_excel(input_file, engine='openpyxl')
    except Exception as e:
        print(f"오류: {input_file} 읽기 실패 - {e}")
        return False

    # 금융정보에서는 category_table.json을 생성하지 않음. 전처리/후처리 없이 계정과목·기타거래만 사용.
    category_tables = load_category_table()

    df["before_text"] = df.apply(create_before_text, axis=1)

    for col in ['적요', '내용', '거래점', '송금메모']:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: safe_str(v))

    df["입출금"] = df.apply(classify_1st_category, axis=1)
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

def main():
    """전체 워크플로우 실행. cash_after는 bank/card 병합으로만 생성."""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == 'classify':
            success = classify_and_save()
            if not success:
                print("카테고리 분류 중 오류가 발생했습니다.")
            return
    ensure_all_cash_files()

if __name__ == '__main__':
    main()
