# -*- coding: utf-8 -*-
"""
info_category.xlsx 읽기/쓰기 통합 모듈.

- load_info_category: 안전한 읽기 (손상된 zip 시 빈 DataFrame 반환)
- get_category_table: 로드 + 정규화 후 (df, file_existed) 반환
- apply_category_action: add/update/delete 수행, (success, error_msg, count) 반환
- create_empty_info_category: 빈 [분류, 키워드, 카테고리] 생성·저장
- safe_write_info_category_xlsx: 원자적 쓰기 + 동시 쓰기 방지
- normalize_category_df: 구분 제거, 컬럼 보장, fillna
"""
import os
import re
import time
import unicodedata
import zipfile

import pandas as pd

# 표준 컬럼 (은행·신용카드·금융정보 공통)
INFO_CATEGORY_COLUMNS = ['분류', '키워드', '카테고리']

# 분류 허용값 (입력/수정 시 검증)
VALID_CHASU = ('전처리', '후처리', '계정과목', '업종분류', '신용카드', '가상자산', '증권투자', '해외송금', '심야구분', '금전대부')


def _is_bad_zip_error(e):
    """손상된 xlsx(zip) 읽기 오류인지 확인."""
    msg = str(e).lower()
    return (
        isinstance(e, zipfile.BadZipFile)
        or 'not a zip file' in msg or 'bad zip' in msg or 'badzip' in msg
        or 'decompress' in msg or 'invalid block' in msg or 'error -3' in msg
    )


def load_info_category(path, default_empty=True):
    """info_category.xlsx 안전 읽기. 손상 시 빈 DataFrame 반환. path 없으면 default_empty에 따라 반환."""
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame(columns=INFO_CATEGORY_COLUMNS) if default_empty else None
    try:
        df = pd.read_excel(path, engine='openpyxl')
        return df if df is not None else (pd.DataFrame(columns=INFO_CATEGORY_COLUMNS) if default_empty else None)
    except Exception as e:
        if _is_bad_zip_error(e):
            return pd.DataFrame(columns=INFO_CATEGORY_COLUMNS) if default_empty else None
        msg = str(e).lower()
        if 'zip' in msg or 'not a zip' in msg or 'decompress' in msg or 'invalid block' in msg:
            return pd.DataFrame(columns=INFO_CATEGORY_COLUMNS) if default_empty else None
        raise


def create_empty_info_category(path):
    """빈 info_category.xlsx 생성·저장. 기존 파일이 있으면 덮어쓰지 않고 load→normalize→save."""
    empty = pd.DataFrame(columns=INFO_CATEGORY_COLUMNS)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        full = load_info_category(path, default_empty=True)
        if full is not None and not full.empty:
            full = normalize_category_df(full)
            if not full.empty:
                safe_write_info_category_xlsx(path, full)
                return
    safe_write_info_category_xlsx(path, empty)


def get_info_category_path(project_root=None):
    """MyInfo 프로젝트 루트 기준 info_category.xlsx 경로 반환."""
    if project_root:
        return os.path.normpath(os.path.join(project_root, 'info_category.xlsx'))
    root = os.environ.get('MYINFO_ROOT') or os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.'))
    return os.path.normpath(os.path.join(root, 'info_category.xlsx'))


def normalize_category_df(df):
    """구분 컬럼 제거, [분류, 키워드, 카테고리] 보장, fillna('')."""
    if df is None or df.empty:
        return pd.DataFrame(columns=INFO_CATEGORY_COLUMNS)
    df = df.copy().fillna('')
    if '구분' in df.columns:
        df = df.drop(columns=['구분'], errors='ignore')
    for c in INFO_CATEGORY_COLUMNS:
        if c not in df.columns:
            df[c] = ''
    return df[INFO_CATEGORY_COLUMNS].copy()


def normalize_fullwidth(val):
    """전각(Fullwidth) → 반각(Halfwidth) 변환 (예: ＳＫＴ５３２２ → SKT5322)."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return val if val is not None else ''
    return unicodedata.normalize('NFKC', str(val).strip())


def normalize_주식회사_for_match(text):
    """전처리/후처리 매칭용: '주식회사'·' 주식회사 / 주식회사'·㈜ 등 → '(주)'로 통일, 연속 (주)는 하나로.
    category 키워드와 데이터 텍스트를 같은 규칙으로 정규화해 매칭이 되도록 함."""
    if text is None or (isinstance(text, str) and not text.strip()):
        return '' if text is None else str(text).strip()
    val = str(text).strip()
    # 주식회사 (공백/슬래시 앞뒤 포함) → (주)
    val = re.sub(r'[\s/]*주식회사[\s/]*', '(주)', val)
    # ㈜ (공백/슬래시 앞뒤 포함) → (주)
    val = re.sub(r'[\s/]*㈜[\s/]*', '(주)', val)
    # 연속 (주) (공백/슬래시로 구분) → 하나의 (주)
    val = re.sub(r'(\(주\)[\s/]*)+', '(주)', val)
    return val


def get_category_table(path):
    """
    info_category.xlsx 로드 → 정규화 후 반환.
    Returns: (df, file_existed)
    """
    path = os.path.normpath(os.path.abspath(path)) if path else None
    file_existed = bool(path and os.path.exists(path) and os.path.getsize(path) > 0)
    if not path or not file_existed:
        return (pd.DataFrame(columns=INFO_CATEGORY_COLUMNS), False)
    full_df = load_info_category(path, default_empty=True)
    if full_df is None or full_df.empty:
        return (pd.DataFrame(columns=INFO_CATEGORY_COLUMNS), file_existed)
    df = normalize_category_df(full_df)
    df = df.fillna('') if df is not None else pd.DataFrame(columns=INFO_CATEGORY_COLUMNS)
    for c in INFO_CATEGORY_COLUMNS:
        if c not in df.columns:
            df[c] = ''
    return (df, file_existed)


def apply_category_action(path, action, data):
    """
    add/update/delete 수행. Flask request와 무관한 순수 로직.
    Args:
        path: info_category.xlsx 경로
        action: 'add' | 'update' | 'delete'
        data: {'분류','키워드','카테고리'} 및 update/delete 시 original_분류, original_키워드, original_카테고리
    Returns:
        (success: bool, error_msg: str|None, count: int)
        success=True면 error_msg=None
    """
    path = os.path.normpath(os.path.abspath(path)) if path else None
    if not path:
        return (False, 'path is required', 0)
    df, _ = get_category_table(path)
    for c in INFO_CATEGORY_COLUMNS:
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
    safe_write_info_category_xlsx(path, df)
    return (True, None, len(df))


import tempfile
import threading

_lock = threading.Lock()


def safe_write_info_category_xlsx(path, df, engine='openpyxl'):
    """
    DataFrame을 path에 원자적으로 저장.
    임시 파일에 쓴 뒤 성공 시에만 기존 파일을 교체하여, 쓰기 중단/크래시 시에도 기존 파일이 유지됨.
    동일 프로세스 내 동시 쓰기는 락으로 직렬화.
    WinError 5(액세스 거부) 시 재시도 후, 실패 시 안내 메시지를 담은 예외 발생.
    """
    if path is None or not path:
        raise ValueError("path is required")
    path = os.path.normpath(os.path.abspath(path))
    dirpath = os.path.dirname(path)
    if not os.path.isdir(dirpath):
        os.makedirs(dirpath, exist_ok=True)
    with _lock:
        fd, tmp = None, None
        try:
            fd, tmp = tempfile.mkstemp(suffix='.xlsx', prefix='.info_cat_', dir=dirpath)
            os.close(fd)
            fd = None
            df.to_excel(tmp, index=False, engine=engine)
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
                            f"info_category.xlsx 저장 실패(파일이 사용 중일 수 있음). "
                            f"Excel에서 info_category.xlsx를 닫고, OneDrive 동기화가 끝날 때까지 기다린 뒤 다시 시도해 주세요. 원인: {e}"
                        ) from e
                    raise
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
