# -*- coding: utf-8 -*-
"""
category_table.json 읽기/쓰기 통합 모듈.

- load_category_table: JSON 안전 읽기 (손상 시 빈 DataFrame 반환)
- get_category_table: 로드 + 정규화 후 (df, file_existed) 반환
- apply_category_action: add/update/delete 수행, (success, error_msg, count) 반환
- create_empty_category_table: 빈 [분류, 키워드, 카테고리] JSON 생성·저장
- safe_write_category_table: 원자적 JSON 쓰기 + 동시 쓰기 방지
- normalize_category_df: 구분 제거, 컬럼 보장, fillna
"""
import json
import os
import re
import time
import unicodedata
import tempfile
import threading

import pandas as pd

try:
    from category_constants import CATEGORY_TABLE_COLUMNS, VALID_CHASU
except ImportError:
    CATEGORY_TABLE_COLUMNS = ['분류', '키워드', '카테고리']
    VALID_CHASU = (
        '전처리', '후처리', '계정과목', '신용카드', '가상자산',
        '증권투자', '해외송금', '심야구분', '금전대부',
    )

# 기본 파일명 (경로는 get_category_table_path로 .source/category_table.json)
CATEGORY_TABLE_FILENAME = 'category_table.json'

_lock = threading.Lock()


def _json_path(path):
    """path가 .xlsx면 .json으로 바꿔 반환 (마이그레이션용)."""
    if not path:
        return path
    path = os.path.normpath(os.path.abspath(path))
    if path.lower().endswith('.xlsx'):
        return os.path.join(os.path.dirname(path), CATEGORY_TABLE_FILENAME)
    return path


def _xlsx_path_from_json(json_path):
    """category_table.json 경로에서 category_table.xlsx 경로 반환 (구버전 마이그레이션용)."""
    if not json_path:
        return None
    base = os.path.splitext(os.path.normpath(json_path))[0]
    return base + '.xlsx'


def load_category_table(path, default_empty=True):
    """
    category_table.json 안전 읽기. path가 .xlsx로 오면 .json 경로로 변환.
    json 없고 xlsx 있으면 xlsx 읽어서 json으로 저장 후 DataFrame 반환.
    손상/없음 시 빈 DataFrame 또는 None 반환.
    """
    path = _json_path(path)
    if not path:
        return pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS) if default_empty else None
    xlsx_path = _xlsx_path_from_json(path)
    # 1회 마이그레이션: json 없고 xlsx 있으면 xlsx → json 변환
    if not os.path.exists(path) or (os.path.exists(path) and os.path.getsize(path) == 0):
        if xlsx_path and os.path.exists(xlsx_path) and os.path.getsize(xlsx_path) > 0:
            try:
                df_old = pd.read_excel(xlsx_path, engine='openpyxl')
                if df_old is not None and not df_old.empty:
                    df_old = normalize_category_df(df_old)
                    safe_write_category_table(path, df_old)
                    return df_old
            except Exception:
                pass
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS) if default_empty else None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not data or not isinstance(data, list):
            return pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS) if default_empty else None
        df = pd.DataFrame(data)
        if df.empty:
            return pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS) if default_empty else None
        for c in CATEGORY_TABLE_COLUMNS:
            if c not in df.columns:
                df[c] = ''
        # 카테고리테이블에서는 업종분류 미사용 — 반환 전 제거
        if '분류' in df.columns and (df['분류'].astype(str).str.strip() == '업종분류').any():
            df = df[df['분류'].astype(str).str.strip() != '업종분류'].copy()
        return df
    except (json.JSONDecodeError, TypeError, IOError):
        return pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS) if default_empty else None


def create_empty_category_table(path):
    """빈 category_table.json 생성·저장. 기존 파일이 있으면 덮어쓰지 않고 load→normalize→save."""
    path = _json_path(path)
    if not path:
        return
    empty = pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        full = load_category_table(path, default_empty=True)
        if full is not None and not full.empty:
            full = normalize_category_df(full)
            if not full.empty:
                safe_write_category_table(path, full)
                return
    safe_write_category_table(path, empty)


def get_category_table_path(project_root=None):
    """MyInfo 프로젝트 루트 기준 .source/category_table.json 경로 반환."""
    if project_root:
        return os.path.normpath(os.path.join(project_root, '.source', CATEGORY_TABLE_FILENAME))
    root = os.environ.get('MYINFO_ROOT') or os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.'))
    return os.path.normpath(os.path.join(root, '.source', CATEGORY_TABLE_FILENAME))


def normalize_category_df(df):
    """구분 컬럼 제거, [분류, 키워드, 카테고리] 보장, fillna('')."""
    if df is None or df.empty:
        return pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS)
    df = df.copy().fillna('')
    if '구분' in df.columns:
        df = df.drop(columns=['구분'], errors='ignore')
    for c in CATEGORY_TABLE_COLUMNS:
        if c not in df.columns:
            df[c] = ''
    return df[CATEGORY_TABLE_COLUMNS].copy()


def normalize_fullwidth(val):
    """전각(Fullwidth) → 반각(Halfwidth) 변환 (예: ＳＫＴ５３２２ → SKT5322)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return val if val is not None else ''
    return unicodedata.normalize('NFKC', str(val).strip())


def normalize_주식회사_for_match(text):
    """전처리/후처리 매칭용: '주식회사'·' 주식회사 / 주식회사'·㈜ 등 → '(주)'로 통일, 연속 (주)는 하나로."""
    if text is None or (isinstance(text, str) and not text.strip()):
        return '' if text is None else str(text).strip()
    val = str(text).strip()
    val = re.sub(r'[\s/]*주식회사[\s/]*', '(주)', val)
    val = re.sub(r'[\s/]*㈜[\s/]*', '(주)', val)
    val = re.sub(r'(\(주\)[\s/]*)+', '(주)', val)
    return val


def get_category_table(path):
    """
    category_table.json 로드 → 정규화 후 반환.
    Returns: (df, file_existed)
    """
    path = _json_path(os.path.normpath(os.path.abspath(path)) if path else None)
    file_existed = bool(path and os.path.exists(path) and os.path.getsize(path) > 0)
    if not path or not file_existed:
        return (pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS), False)
    full_df = load_category_table(path, default_empty=True)
    if full_df is None or full_df.empty:
        return (pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS), file_existed)
    df = normalize_category_df(full_df)
    df = df.fillna('') if df is not None else pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS)
    for c in CATEGORY_TABLE_COLUMNS:
        if c not in df.columns:
            df[c] = ''
    # 카테고리테이블에서는 업종분류 미사용 — 행 제거
    if '분류' in df.columns and (df['분류'].astype(str).str.strip() == '업종분류').any():
        df = df[df['분류'].astype(str).str.strip() != '업종분류'].copy()
    return (df, file_existed)


def apply_category_action(path, action, data):
    """
    add/update/delete 수행. Flask request와 무관한 순수 로직.
    Args:
        path: category_table.json 경로
        action: 'add' | 'update' | 'delete'
        data: {'분류','키워드','카테고리'} 및 update/delete 시 original_분류, original_키워드, original_카테고리
    Returns:
        (success: bool, error_msg: str|None, count: int)
    """
    path = _json_path(os.path.normpath(os.path.abspath(path)) if path else None)
    if not path:
        return (False, 'path is required', 0)
    df, _ = get_category_table(path)
    for c in CATEGORY_TABLE_COLUMNS:
        if c not in df.columns:
            df[c] = ''
    df = df.fillna('')
    if action == 'add':
        분류_val = normalize_fullwidth(data.get('분류', '')).strip()
        if 분류_val and 분류_val not in VALID_CHASU:
            return (False, f'분류는 {", ".join(VALID_CHASU)}만 입력할 수 있습니다.', 0)
        new_row = {
            '분류': normalize_fullwidth(data.get('분류', '')),
            '키워드': normalize_fullwidth(data.get('키워드', '')),
            '카테고리': normalize_fullwidth(data.get('카테고리', ''))
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    elif action == 'update':
        original_분류 = data.get('original_분류', '')
        original_keyword = data.get('original_키워드', '')
        original_category = data.get('original_카테고리', '')
        new_분류 = normalize_fullwidth(data.get('분류', '')).strip()
        if new_분류 and new_분류 not in VALID_CHASU:
            return (False, f'분류는 {", ".join(VALID_CHASU)}만 입력할 수 있습니다.', 0)
        new_keyword = normalize_fullwidth(data.get('키워드', ''))
        new_category = normalize_fullwidth(data.get('카테고리', ''))
        mask = ((df['분류'] == original_분류) & (df['키워드'] == original_keyword) & (df['카테고리'] == original_category))
        if mask.any():
            df.loc[mask, '분류'] = new_분류
            df.loc[mask, '키워드'] = new_keyword
            df.loc[mask, '카테고리'] = new_category
        else:
            return (False, '수정할 데이터를 찾을 수 없습니다.', 0)
    elif action == 'delete':
        분류값 = data.get('original_분류', data.get('분류', ''))
        keyword = data.get('original_키워드', data.get('키워드', ''))
        category = data.get('original_카테고리', data.get('카테고리', ''))
        df = df[~((df['분류'] == 분류값) & (df['키워드'] == keyword) & (df['카테고리'] == category))]
    else:
        return (False, f'unknown action: {action}', 0)
    # 카테고리테이블에서는 업종분류 미사용 — 저장 전 해당 행 제거
    if '분류' in df.columns and (df['분류'].astype(str).str.strip() == '업종분류').any():
        df = df[df['분류'].astype(str).str.strip() != '업종분류'].copy()
    safe_write_category_table(path, df)
    return (True, None, len(df))


def safe_write_category_table(path, df):
    """
    DataFrame을 path(category_table.json)에 원자적으로 저장.
    임시 파일에 쓴 뒤 성공 시에만 기존 파일을 교체. 동시 쓰기는 락으로 직렬화.
    WinError 5(액세스 거부) 시 재시도 후, 실패 시 안내 메시지 예외.
    """
    if df is None:
        raise ValueError("df is required")
    path = _json_path(path)
    if path is None or not path:
        raise ValueError("path is required")
    path = os.path.normpath(os.path.abspath(path))
    dirpath = os.path.dirname(path)
    if not os.path.isdir(dirpath):
        os.makedirs(dirpath, exist_ok=True)
    with _lock:
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(suffix='.json', prefix='.cat_tbl_', dir=dirpath)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    records = df[CATEGORY_TABLE_COLUMNS].copy().fillna('').to_dict('records')
                    json.dump(records, f, ensure_ascii=False, indent=2)
            except Exception:
                if tmp and os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                raise
            last_err = None
            for attempt in range(3):
                try:
                    os.replace(tmp, path)
                    tmp = None
                    break
                except (OSError, PermissionError) as e:
                    last_err = e
                    if getattr(e, 'winerror', None) == 5 or (hasattr(e, 'errno') and e.errno == 5):
                        if attempt < 2:
                            time.sleep(0.5 * (attempt + 1))
                            continue
                        raise PermissionError(
                            "category_table.json 저장 실패(파일이 사용 중일 수 있음). "
                            "다른 프로그램에서 category_table.json을 닫고, 동기화가 끝날 때까지 기다린 뒤 다시 시도해 주세요. 원인: " + str(e)
                        ) from e
                    raise
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

