# -*- coding: utf-8 -*-
"""
cash_after 생성 후 적용하는 위험도 지표 1~10호.

1호를 기본값으로 두고, 2호 → 3호 → … → 10호 순차 적용하며 조건 만족 시 덮어씀.

- 1호: 분류제외지표, 0.1 — 2~10호에 해당하지 않은 거래.
- 2호: 심야폐업지표, 0.5 — 금액 무관, 심야구분이거나 폐업이면 모두 해당. 구분이 폐업이면 2호만 사용.
- 3~10호: 자료소명·비정형·…·사행성. 구분이 폐업인 행은 3~10호 적용 시 skip(폐업은 2호로 유지).
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import pandas as pd


DEFAULT_RISK = 0.1  # 1호 기본 위험도
CLASS_1호 = '분류제외지표'
CLASS_2호 = '심야폐업지표'

# 5~10호 위험도분류명 (category_table.json 분류 "업종분류"에서 카테고리와 매칭)
CLASS_5호 = '투기성지표'
CLASS_6호 = '사기파산지표'
CLASS_7호 = '가상자산지표'
CLASS_8호 = '자산은닉지표'
CLASS_9호 = '과소비지표'
CLASS_10호 = '사행성지표'
RISK_CLASSES_5_10 = (CLASS_5호, CLASS_6호, CLASS_7호, CLASS_8호, CLASS_9호, CLASS_10호)


def _num(val, default: float = 0.0) -> float:
    if val is None or val == '' or (isinstance(val, float) and pd.isna(val)):
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _str(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ''
    return str(val).strip()


def _search_text(row, cols: List[str]) -> str:
    parts = []
    for c in cols:
        if c not in row.index:
            continue
        v = row[c]
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        parts.append(_str(v))
    return ' '.join(parts)


def _search_text_dedup(row, cols: List[str]) -> str:
    raw = _search_text(row, cols)
    if not raw:
        return ''
    tokens = raw.split()
    seen = set()
    unique = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return ' '.join(unique)


def _keyword_match(text: str, keywords: List[str]) -> bool:
    if not text:
        return False
    t = text.lower()
    for kw in keywords:
        if kw.lower() in t:
            return True
    return False


def _matched_keyword(text: str, keywords: List[str]) -> str:
    if not text:
        return ''
    t = text.lower()
    for kw in keywords:
        if kw.lower() in t:
            return kw
    return ''


def _parse_time_to_minutes(t: str) -> Optional[int]:
    """거래시간 문자열을 0~1439(자정 기준 분)로 변환. None이면 인식 불가."""
    if t is None or (isinstance(t, float) and pd.isna(t)):
        return None
    s = _str(t).replace(' ', '')
    if not s:
        return None
    # HH:MM:SS or HHMMSS or HHMM
    parts = s.replace(':', '').replace('.', '')[:6]
    if len(parts) < 4:
        return None
    try:
        h = int(parts[:2]) if len(parts) >= 2 else 0
        m = int(parts[2:4]) if len(parts) >= 4 else 0
        if h < 0 or h > 23 or m < 0 or m > 59:
            return None
        return h * 60 + m
    except ValueError:
        return None


def _load_simya_range(category_table_path: Optional[str]) -> Optional[Tuple[int, int]]:
    """category_table에서 심야구분 키워드(예: 22:00:00/06:00:00) 로드. (시작분, 종료분) 0~1439. 넘침 구간이면 (22*60, 24*60), (0, 6*60) 형태로 (1320, 360) 반환."""
    if not category_table_path or not os.path.isfile(category_table_path):
        return None
    try:
        with open(category_table_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, list):
        return None
    for item in data:
        if not isinstance(item, dict):
            continue
        if _str(item.get('분류')) != '심야구분':
            continue
        kw = _str(item.get('키워드', ''))
        if '/' not in kw:
            continue
        parts = kw.split('/')
        if len(parts) != 2:
            continue
        start_s = parts[0].strip()
        end_s = parts[1].strip()
        # "22:00:00" -> 22*60+0 = 1320, "06:00:00" -> 6*60 = 360
        def to_min(x):
            x = x.replace(':', '').replace('.', '')[:4]
            if len(x) < 4:
                return None
            try:
                h, m = int(x[:2]), int(x[2:4])
                if 0 <= h <= 23 and 0 <= m <= 59:
                    return h * 60 + m
            except ValueError:
                pass
            return None
        start_m = to_min(start_s)
        end_m = to_min(end_s)
        if start_m is None or end_m is None:
            continue
        return (start_m, end_m)
    return None


def _is_simya(거래시간_str, simya_range: Optional[Tuple[int, int]]) -> bool:
    """거래시간이 심야 구간에 해당하면 True."""
    if simya_range is None:
        return False
    start_m, end_m = simya_range
    t = _parse_time_to_minutes(거래시간_str)
    if t is None:
        return False
    if start_m <= end_m:
        return start_m <= t < end_m
    # 넘침 (예: 22:00~06:00 → start_m=1320, end_m=360)
    return t >= start_m or t < end_m


def _load_업종분류_keywords(category_table_path: Optional[str]) -> Dict[str, List[str]]:
    """category_table.json에서 분류='업종분류'인 행만 추려, 카테고리(위험도분류명)별 키워드 리스트 반환.
    키워드 컬럼은 쉼표·슬래시·줄바꿈으로 구분된 문자열로 파싱."""
    result: Dict[str, List[str]] = {cls: [] for cls in RISK_CLASSES_5_10}
    if not category_table_path or not os.path.isfile(category_table_path):
        return result
    try:
        with open(category_table_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return result
    if not isinstance(data, list):
        return result
    for item in data:
        if not isinstance(item, dict):
            continue
        if _str(item.get('분류')) != '업종분류':
            continue
        cat = _str(item.get('카테고리', ''))
        if cat not in result:
            continue
        kw_raw = item.get('키워드', '')
        if kw_raw is None or (isinstance(kw_raw, float) and pd.isna(kw_raw)):
            kw_raw = ''
        kw_str = str(kw_raw).strip()
        if not kw_str:
            continue
        # 쉼표·슬래시·줄바꿈으로 분리 후 공백 제거. '분류5호' 등 라벨은 검색 키워드에서 제외
        for sep in (',', '/', '\n', '\r'):
            kw_str = kw_str.replace(sep, ' ')
        raw = [t.strip() for t in kw_str.split() if t.strip()]
        tokens = [t for t in raw if not (len(t) >= 4 and t.startswith('분류') and t.endswith('호'))]
        if tokens:
            result[cat] = tokens
    return result


def apply_risk_indicators(df: pd.DataFrame, category_table_path: Optional[str] = None) -> None:
    """
    cash_after DataFrame에 대해 1~10호 위험도 지표 적용. in-place 수정.
    1호를 기본값으로 두고, 2호~10호를 순차 적용하며 조건 만족 시 덮어씀.
    """
    if df is None or df.empty:
        return
    if '입금액' not in df.columns or '출금액' not in df.columns:
        return

    분류_col = '위험도분류' if '위험도분류' in df.columns else ('업종분류' if '업종분류' in df.columns else None)
    has_업종 = 분류_col is not None
    if has_업종 and 분류_col != '위험도분류':
        df['위험도분류'] = df[분류_col].fillna('')
    elif not has_업종:
        df['위험도분류'] = ''
        분류_col = '위험도분류'
    has_위험도 = '위험도' in df.columns
    if not has_위험도:
        df['위험도'] = DEFAULT_RISK
    # 1호를 기본값으로 설정(이후 2~10호 순차 적용 시 덮어씀)
    df['위험도'] = DEFAULT_RISK
    df['위험도분류'] = CLASS_1호
    if '위험도키워드' not in df.columns:
        if '업종키워드' in df.columns:
            df['위험도키워드'] = df['업종키워드'].fillna('').astype(str).str.strip()
        elif '업종코드' in df.columns:
            df['위험도키워드'] = df['업종코드'].fillna('').astype(str).str.strip()
        else:
            df['위험도키워드'] = ''

    if '키워드' not in df.columns:
        df['키워드'] = ''
    if '카테고리' not in df.columns:
        df['카테고리'] = ''
    kw_series = df['키워드'].fillna('').astype(str).str.strip()

    sort_1 = [c for c in ['키워드', '거래일'] if c in df.columns]
    if sort_1:
        df.sort_values(by=sort_1, ascending=True, inplace=True, na_position='last')

    # ---------- 2호: 심야폐업지표 0.5 — 금액 무관, 심야구분이거나 폐업이면 모두 2호 ----------
    # 심야구분: category_table.json에서 분류='심야구분'인 행의 키워드(예: 22:00:00/06:00:00)로 시간 구간 로드.
    # 폐업: cash_after의 '구분' 컬럼이 '폐업'인 행. 2호 해당 행은 3~10호 조건을 보지 않음.
    if '거래시간' not in df.columns:
        df['거래시간'] = ''
    if '구분' not in df.columns:
        df['구분'] = ''
    simya_range = _load_simya_range(category_table_path)
    keywords_5_10 = _load_업종분류_keywords(category_table_path)

    df['_2호적용'] = False
    for i in df.index:
        is_폐업 = _str(df.at[i, '구분']).strip() == '폐업'
        is_simya = _is_simya(df.at[i, '거래시간'], simya_range)
        if not is_폐업 and not is_simya:
            continue
        df.at[i, '_2호적용'] = True
        if has_업종:
            df.at[i, '위험도분류'] = CLASS_2호
        if has_위험도:
            df.at[i, '위험도'] = 0.5

    # ---------- 3호: 자료소명지표 1.0 (2호 해당 행은 skip) ----------
    out_5m = df['출금액'].apply(_num) >= 5_000_000
    for i in df.index:
        if df.at[i, '_2호적용']:
            continue
        if out_5m[i]:
            kw_val = _str(df.at[i, '키워드']) or (_str(df.at[i, '기타거래']) if '기타거래' in df.columns else '') or _str(df.at[i, '키워드'])
            df.at[i, '위험도키워드'] = kw_val
            if has_업종:
                df.at[i, '위험도분류'] = '자료소명지표'
            if has_위험도:
                df.at[i, '위험도'] = 1.0

    # 4호: 비정형지표 1.5 (기존 2호)
    out_only_1m = (df['출금액'].apply(_num) >= 1_000_000) & (df['입금액'].apply(_num) <= 0)
    df['_kw'] = kw_series
    count_per_kw = df.loc[out_only_1m].groupby('_kw').size()
    kw_3_or_more = set(count_per_kw[count_per_kw >= 3].index)
    df['_4호대상'] = df['_kw'].isin(kw_3_or_more) & out_only_1m
    for i in df.index:
        if df.at[i, '_2호적용']:
            continue
        if df.at[i, '_4호대상']:
            kw_val = _str(df.at[i, '키워드']) or (_str(df.at[i, '기타거래']) if '기타거래' in df.columns else '') or _str(df.at[i, '키워드'])
            df.at[i, '위험도키워드'] = kw_val
            if has_업종:
                df.at[i, '위험도분류'] = '비정형지표'
            if has_위험도:
                df.at[i, '위험도'] = 1.5

    sort_2 = [c for c in ['카테고리', '키워드', '거래일'] if c in df.columns]
    if sort_2:
        df.sort_values(by=sort_2, ascending=True, inplace=True, na_position='last')

    SEARCH_COLS = ['카테고리', '키워드', '기타거래']

    # 5호: 투기성지표 2.0 (2호 해당 행은 skip). 키워드는 category_table 분류 '업종분류' 카테고리 '투기성지표'에서 로드.
    kw5 = keywords_5_10.get(CLASS_5호, [])
    for i in df.index:
        if df.at[i, '_2호적용']:
            continue
        row = df.loc[i]
        inp, out = _num(row.get('입금액')), _num(row.get('출금액'))
        text = _search_text_dedup(row, SEARCH_COLS)
        if out >= 500_000 and inp <= 0 and kw5 and _keyword_match(text, kw5):
            df.at[i, '위험도키워드'] = _matched_keyword(text, kw5)
            if has_업종:
                df.at[i, '위험도분류'] = CLASS_5호
            if has_위험도:
                df.at[i, '위험도'] = 2.0

    # 6호: 사기파산지표 2.5 (2호 해당 행은 skip). 키워드는 category_table 업종분류 '사기파산지표'에서 로드.
    kw6 = keywords_5_10.get(CLASS_6호, [])
    for i in df.index:
        if df.at[i, '_2호적용']:
            continue
        row = df.loc[i]
        inp, out = _num(row.get('입금액')), _num(row.get('출금액'))
        text = _search_text_dedup(row, SEARCH_COLS)
        if out >= 500_000 and inp <= 0 and kw6 and _keyword_match(text, kw6):
            df.at[i, '위험도키워드'] = _matched_keyword(text, kw6)
            if has_업종:
                df.at[i, '위험도분류'] = CLASS_6호
            if has_위험도:
                df.at[i, '위험도'] = 2.5

    # 7호: 가상자산지표 3.0 (2호 해당 행은 skip). 키워드는 category_table 업종분류 '가상자산지표'에서 로드.
    kw7 = keywords_5_10.get(CLASS_7호, [])
    for i in df.index:
        if df.at[i, '_2호적용']:
            continue
        row = df.loc[i]
        inp, out = _num(row.get('입금액')), _num(row.get('출금액'))
        if out >= 500_000 and inp <= 0:
            cat = _str(row.get('카테고리', ''))
            text = _search_text_dedup(row, SEARCH_COLS)
            if '가상자산' in cat:
                df.at[i, '위험도키워드'] = '가상자산'
                if has_업종:
                    df.at[i, '위험도분류'] = CLASS_7호
                if has_위험도:
                    df.at[i, '위험도'] = 3.0
            elif kw7 and _keyword_match(text, kw7):
                df.at[i, '위험도키워드'] = _matched_keyword(text, kw7)
                if has_업종:
                    df.at[i, '위험도분류'] = CLASS_7호
                if has_위험도:
                    df.at[i, '위험도'] = 3.0

    # 8호: 자산은닉지표 3.5 (2호 해당 행은 skip). 키워드는 category_table 업종분류 '자산은닉지표'에서 로드.
    kw8 = keywords_5_10.get(CLASS_8호, [])
    for i in df.index:
        if df.at[i, '_2호적용']:
            continue
        row = df.loc[i]
        inp, out = _num(row.get('입금액')), _num(row.get('출금액'))
        text = _search_text_dedup(row, SEARCH_COLS)
        if out >= 500_000 and inp <= 0 and kw8 and _keyword_match(text, kw8):
            df.at[i, '위험도키워드'] = _matched_keyword(text, kw8)
            if has_업종:
                df.at[i, '위험도분류'] = CLASS_8호
            if has_위험도:
                df.at[i, '위험도'] = 3.5

    # 9호: 과소비지표 4.0 (2호 해당 행은 skip). 키워드는 category_table 업종분류 '과소비지표'에서 로드.
    kw9 = keywords_5_10.get(CLASS_9호, [])
    for i in df.index:
        if df.at[i, '_2호적용']:
            continue
        row = df.loc[i]
        inp, out = _num(row.get('입금액')), _num(row.get('출금액'))
        text = _search_text_dedup(row, SEARCH_COLS)
        if out >= 300_000 and inp <= 0 and kw9 and _keyword_match(text, kw9):
            df.at[i, '위험도키워드'] = _matched_keyword(text, kw9)
            if has_업종:
                df.at[i, '위험도분류'] = CLASS_9호
            if has_위험도:
                df.at[i, '위험도'] = 4.0

    # 10호: 사행성지표 5.0 (2호 해당 행은 skip). 키워드는 category_table 업종분류 '사행성지표'에서 로드.
    kw10 = keywords_5_10.get(CLASS_10호, [])
    for i in df.index:
        if df.at[i, '_2호적용']:
            continue
        row = df.loc[i]
        inp, out = _num(row.get('입금액')), _num(row.get('출금액'))
        text = _search_text_dedup(row, SEARCH_COLS)
        if out >= 100_000 and inp <= 0 and kw10 and _keyword_match(text, kw10):
            df.at[i, '위험도키워드'] = _matched_keyword(text, kw10)
            if has_업종:
                df.at[i, '위험도분류'] = CLASS_10호
            if has_위험도:
                df.at[i, '위험도'] = 5.0

    df.drop(columns=['_kw', '_4호대상', '_2호적용'], errors='ignore', inplace=True)

    if has_위험도:
        df['위험도'] = df['위험도'].apply(lambda v: max(DEFAULT_RISK, _num(v, DEFAULT_RISK)))


def get_risk_indicators_document() -> str:
    """위험도 지표 1~10호 요약 문서용 텍스트."""
    lines = [
        "1호. 분류제외지표: 금액제한 없음, 2~10호에 해당하지 않은 거래, 위험도 0.1",
        "2호. 심야폐업지표: 금액 무관, 심야구분이거나 폐업이면 2호만 적용(3~10호 미적용), 위험도 0.5",
        "3호. 자료소명지표: 출금 500만원 이상, 해당 행 키워드를 위험도키워드로 저장, 위험도 1.0",
        "4호. 비정형지표: 출금만 100만원 이상, 동일 키워드 3회 이상, 위험도 1.5",
        "5호. 투기성지표: 출금만 50만원 이상, 위험도 2.0 (키워드: category_table 분류 업종분류 카테고리 투기성지표)",
        "6호. 사기파산지표: 출금만 50만원 이상, 위험도 2.5 (키워드: category_table 업종분류 사기파산지표)",
        "7호. 가상자산지표: 출금만 50만원 이상, 위험도 3.0 (카테고리 가상자산 또는 category_table 업종분류 가상자산지표)",
        "8호. 자산은닉지표: 출금만 50만원 이상, 위험도 3.5 (키워드: category_table 업종분류 자산은닉지표)",
        "9호. 과소비지표: 출금만 30만원 이상, 위험도 4.0 (키워드: category_table 업종분류 과소비지표)",
        "10호. 사행성지표: 출금만 10만원 이상, 위험도 5.0 (키워드: category_table 업종분류 사행성지표)",
    ]
    return "\n".join(lines)
