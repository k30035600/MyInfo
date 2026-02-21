# -*- coding: utf-8 -*-
"""category_table.json 읽기/쓰기. load/get, apply_action, safe_write, normalize_category_df.

캐시 미적용: 코드에서 table은 캐시를 사용하지 않는다. category_table, linkage_table 모두 매 요청 시 파일에서 읽음.
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


# 업종분류 5~10호 행 (분류, 키워드, 카테고리). 있으면 수정, 없으면 추가.
_업종분류_RISK_ROWS = [
    {'분류': '업종분류', '키워드': '분류5호/증권/선물/자산운용/위탁/증권입금', '카테고리': '투기성지표'},
    {'분류': '업종분류', '키워드': '분류6호/대부/P2P/카드깡/원리금', '카테고리': '사기파산지표'},
    {'분류': '업종분류', '키워드': '분류7호/가상자산/업비트/빗썸/코인원/코빗/VASP/거래소/코인/비트코인/암호화폐', '카테고리': '가상자산지표'},
    {'분류': '업종분류', '키워드': '분류8호/해외송금/고액현금인출/외화송금/영문성명/Wise/TransferWise/SWIFT', '카테고리': '자산은닉지표'},
    {'분류': '업종분류', '키워드': '분류9호/백화점/명품/귀금속/유흥/고가가전/고가가구/유흥주점/무도장/콜라텍/댄스홀', '카테고리': '과소비지표'},
    {'분류': '업종분류', '키워드': '분류10호/경마/복권/사설도박/도박기계/사행성게임기/오락기구/휴게텔/키스방/대화방/안마/마사지/사행성/도박', '카테고리': '사행성지표'},
]


def _ensure_업종분류_risk_rows(path, df):
    """업종분류 5~10호 행을 df에 반영. (분류, 카테고리) 일치 행이 있으면 키워드 수정, 없으면 추가. 변경 시 저장."""
    if df is None:
        df = pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS)
    for c in CATEGORY_TABLE_COLUMNS:
        if c not in df.columns:
            df[c] = ''
    df = df.fillna('').copy()
    changed = False
    for row in _업종분류_RISK_ROWS:
        분류, 키워드, 카테고리 = row['분류'], row['키워드'], row['카테고리']
        mask = (df['분류'].astype(str).str.strip() == 분류) & (df['카테고리'].astype(str).str.strip() == 카테고리)
        if mask.any():
            idx = mask.idxmax()
            if (df.at[idx, '키워드'] or '').strip() != (키워드 or '').strip():
                df.at[idx, '키워드'] = 키워드
                changed = True
        else:
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            changed = True
    if changed and path:
        try:
            safe_write_category_table(path, df[CATEGORY_TABLE_COLUMNS])
        except Exception:
            pass
    return df


def load_category_table(path, default_empty=True):
    """JSON 안전 읽기. xlsx면 json 경로로 변환. 없/손상 시 빈 DataFrame 또는 None."""
    path = _json_path(path)
    if not path:
        return pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS) if default_empty else None
    xlsx_path = _xlsx_path_from_json(path)
    path_exists = os.path.exists(path)
    if not path_exists or (path_exists and os.path.getsize(path) == 0):
        if xlsx_path and os.path.exists(xlsx_path) and os.path.getsize(xlsx_path) > 0:
            try:
                df_old = pd.read_excel(xlsx_path, engine='openpyxl')
                if df_old is not None and not df_old.empty:
                    df_old = normalize_category_df(df_old)
                    safe_write_category_table(path, df_old)
                    return df_old
            except Exception:
                pass
        if not path_exists or os.path.getsize(path) == 0:
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
        df = _ensure_업종분류_risk_rows(path, df)
        return df
    except (json.JSONDecodeError, TypeError, IOError):
        return pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS) if default_empty else None


def create_empty_category_table(path):
    """빈 category_table.json 생성. 기존 있으면 덮어쓰지 않음."""
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
    """프로젝트 루트 기준 .source/category_table.json 경로."""
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
    safe_write_category_table(path, df)
    return (True, None, len(df))


def ensure_prepost_in_table(path):
    """
    category_table에 전처리/후처리 행이 하나도 없으면 기본 규칙을 앞에 보강해 저장 후 반환.
    은행·금융정보 분류 시 전처리/후처리가 비어 있으면 적용이 되지 않으므로, 파일 복구용으로 사용.
    Returns: 보강된 DataFrame (변경 없으면 기존 로드 결과 그대로).
    """
    path = _json_path(path)
    if not path or not os.path.exists(path):
        return load_category_table(path, default_empty=True)
    df = load_category_table(path, default_empty=True)
    if df is None or df.empty:
        return df
    df = normalize_category_df(df)
    if '분류' not in df.columns:
        return df
    분류_str = df['분류'].astype(str).str.strip()
    has_전 = (분류_str == '전처리').any()
    has_후 = (분류_str == '후처리').any()
    if has_전 and has_후:
        return df
    try:
        from category_table_defaults import get_default_rules
        rules = get_default_rules('bank')
        prepost = [r for r in rules if str(r.get('분류', '')).strip() in ('전처리', '후처리')]
    except Exception:
        prepost = []
    if not prepost:
        return df
    prepost_df = pd.DataFrame(prepost)
    for c in CATEGORY_TABLE_COLUMNS:
        if c not in prepost_df.columns:
            prepost_df[c] = ''
    prepost_df = prepost_df[CATEGORY_TABLE_COLUMNS].copy().fillna('')
    merged = pd.concat([prepost_df, df], ignore_index=True)
    merged = merged.drop_duplicates(subset=['분류', '키워드', '카테고리'], keep='first')
    merged = normalize_category_df(merged)
    safe_write_category_table(path, merged)
    return merged


def export_category_table_to_xlsx(path=None):
    """
    category_table.json 내용을 동일 경로의 category_table.xlsx로 내보냄.
    백업·엑셀 편집용. path 생략 시 get_category_table_path() 사용.
    Returns: (success: bool, xlsx_path: str|None, error_msg: str|None)
    """
    path = _json_path(path or get_category_table_path())
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        return (False, None, "category_table.json이 없거나 비어 있습니다.")
    xlsx_path = _xlsx_path_from_json(path)
    if not xlsx_path:
        return (False, None, "xlsx 경로를 만들 수 없습니다.")
    try:
        df = load_category_table(path, default_empty=False)
        if df is None or df.empty:
            return (False, None, "JSON 로드 결과가 비어 있습니다.")
        df = normalize_category_df(df)
        df.to_excel(xlsx_path, index=False, engine='openpyxl')
        return (True, xlsx_path, None)
    except Exception as e:
        return (False, xlsx_path, str(e))


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
            for attempt in range(5):
                try:
                    os.replace(tmp, path)
                    tmp = None
                    break
                except (OSError, PermissionError) as e:
                    last_err = e
                    if getattr(e, 'winerror', None) == 5 or (hasattr(e, 'errno') and e.errno == 5):
                        if attempt < 4:
                            time.sleep(1.0 * (attempt + 1))
                            continue
                        # Fallback: rename 실패 시 임시 파일 내용을 대상 경로에 직접 덮어쓰기 시도 (Windows 파일 잠금 완화)
                        try:
                            with open(tmp, 'r', encoding='utf-8') as rf:
                                content = rf.read()
                            with open(path, 'w', encoding='utf-8') as wf:
                                wf.write(content)
                            try:
                                os.remove(tmp)
                            except OSError:
                                pass
                            tmp = None
                            break
                        except Exception:
                            pass
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

