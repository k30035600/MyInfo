# -*- coding: utf-8 -*-
"""
cash_after 생성 후 적용하는 위험도 지표 1~8호.

- 모든 행의 위험도는 최소 0.1.
- 1호부터 8호까지 순차 적용. 1호 제외하고 2~8호는 (카테고리+키워드)+기타거래로 매칭.
- 매칭 시 해당 행의 위험도키워드(매칭된 키워드 또는 지표명)·위험도분류·위험도를 설정(나중 호수가 덮어씀).
- 매칭된 키워드/위험도분류/위험도는 cash_after의 위험도키워드/위험도분류/위험도에 저장.
"""
from __future__ import annotations

from typing import List, Optional

import pandas as pd


DEFAULT_RISK = 0.1  # 모든 행 기본 위험도


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
    """(카테고리+키워드)+기타거래 결합 후 공백 기준 동일단어(토큰) 제거, 순서 유지."""
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
    """텍스트에서 처음 매칭된 키워드를 반환. 없으면 빈 문자열."""
    if not text:
        return ''
    t = text.lower()
    for kw in keywords:
        if kw.lower() in t:
            return kw
    return ''


def apply_risk_indicators(df: pd.DataFrame) -> None:
    """
    cash_after DataFrame에 대해 1~8호 위험도 지표를 순서대로 적용. in-place 수정.
    - 먼저 모든 행 위험도를 0.1로 초기화.
    - 1호 → 8호 순으로 매칭 시 위험도키워드(매칭키워드)·위험도분류·위험도 설정(나중 호수가 덮어씀).
    - 키워드/기타거래(및 5호는 카테고리)로 매칭. 매칭 결과는 cash_after 위험도키워드/위험도분류/위험도에 저장.
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
    else:
        df['위험도'] = DEFAULT_RISK
    # 매칭 시 위험도키워드에 저장할 컬럼 (없으면 생성, 구 컬럼명 호환)
    if '위험도키워드' not in df.columns:
        if '업종키워드' in df.columns:
            df['위험도키워드'] = df['업종키워드'].fillna('').astype(str).str.strip()
        elif '업종코드' in df.columns:
            df['위험도키워드'] = df['업종코드'].fillna('').astype(str).str.strip()
        else:
            df['위험도키워드'] = ''

    # 키워드·카테고리 컬럼(특정인·위험도키워드 저장용; 2~8호는 (카테고리+키워드)+기타거래로 매칭)
    if '키워드' not in df.columns:
        df['키워드'] = ''
    if '카테고리' not in df.columns:
        df['카테고리'] = ''
    kw_series = df['키워드'].fillna('').astype(str).str.strip()

    # 위험도분류 적용 전: 카테고리·키워드·거래일 올림차순 정렬
    sort_cols = [c for c in ['카테고리', '키워드', '거래일'] if c in df.columns]
    if sort_cols:
        df.sort_values(by=sort_cols, ascending=True, inplace=True, na_position='last')

    # 2~8호 매칭용 검색 텍스트: (카테고리+키워드)+기타거래, 동일단어(공백 기준 토큰) 제거
    SEARCH_COLS_2_8 = ['카테고리', '키워드', '기타거래']

    # 1호: 자료소명지표 1.0 — 출금 1000만원 이상, 해당 행의 키워드를 위험도키워드로 저장
    out_10m = df['출금액'].apply(_num) >= 10_000_000
    for i in df.index:
        if out_10m[i]:
            kw_val = _str(df.at[i, '키워드']) or _str(df.at[i, '기타거래']) if '기타거래' in df.columns else _str(df.at[i, '키워드'])
            df.at[i, '위험도키워드'] = kw_val
            if has_업종:
                df.at[i, '위험도분류'] = '자료소명지표'
            if has_위험도:
                df.at[i, '위험도'] = 1.0

    # 2호: 비정형지표 1.5 — 출금만존재, 100만원 이상, 5회 이상 (특정인=키워드 기준), 해당 키워드를 위험도키워드로 저장
    out_only_1m = (df['출금액'].apply(_num) >= 1_000_000) & (df['입금액'].apply(_num) <= 0)
    df['_kw'] = kw_series
    count_per_kw = df.loc[out_only_1m].groupby('_kw').size()
    kw_5_or_more = set(count_per_kw[count_per_kw >= 5].index)
    df['_2호대상'] = df['_kw'].isin(kw_5_or_more) & out_only_1m
    for i in df.index:
        if df.at[i, '_2호대상']:
            kw_val = _str(df.at[i, '키워드']) or _str(df.at[i, '기타거래']) if '기타거래' in df.columns else _str(df.at[i, '키워드'])
            df.at[i, '위험도키워드'] = kw_val
            if has_업종:
                df.at[i, '위험도분류'] = '비정형지표'
            if has_위험도:
                df.at[i, '위험도'] = 1.5

    # 3호: 투기성지표 2.0 — 입출금 50만원 이상, 키워드: 증권/선물/자산운용/위탁/증권입금 (하나증권금융센터 제외)
    kw3 = ['증권', '선물', '자산운용', '위탁', '증권입금']
    exclude3 = '하나증권금융센터'  # 증권에서 제외(카드사 금융센터 명칭)
    for i in df.index:
        row = df.loc[i]
        inp, out = _num(row.get('입금액')), _num(row.get('출금액'))
        text = _search_text_dedup(row, SEARCH_COLS_2_8)
        if (inp >= 500_000 or out >= 500_000) and _keyword_match(text, kw3):
            matched = _matched_keyword(text, kw3)
            if matched == '증권' and exclude3 in text:
                continue  # 하나증권금융센터는 증권(3호)에서 제외
            df.at[i, '위험도키워드'] = matched
            if has_업종:
                df.at[i, '위험도분류'] = '투기성지표'
            if has_위험도:
                df.at[i, '위험도'] = 2.0

    # 4호: 사기파산지표 2.5 — 입출금 50만원 이상, 키워드: 대부/P2P/카드깡/원리금 상환
    kw4 = ['대부', 'P2P', '카드깡', '원리금']
    for i in df.index:
        row = df.loc[i]
        inp, out = _num(row.get('입금액')), _num(row.get('출금액'))
        text = _search_text_dedup(row, SEARCH_COLS_2_8)
        if (inp >= 500_000 or out >= 500_000) and _keyword_match(text, kw4):
            matched = _matched_keyword(text, kw4)
            df.at[i, '위험도키워드'] = matched
            if has_업종:
                df.at[i, '위험도분류'] = '사기파산지표'
            if has_위험도:
                df.at[i, '위험도'] = 2.5

    # 5호: 가상자산지표 3.0 — 입출금 50만원 이상, 카테고리 가상자산 또는 키워드: 업비트/빗썸/코인원/코빗 등
    kw5 = ['업비트', '빗썸', '코인원', '코빗', '가상자산', 'VASP', '거래소', '코인', '비트코인', '암호화폐']
    for i in df.index:
        row = df.loc[i]
        inp, out = _num(row.get('입금액')), _num(row.get('출금액'))
        if inp >= 500_000 or out >= 500_000:
            cat = _str(row.get('카테고리', ''))
            text = _search_text_dedup(row, SEARCH_COLS_2_8)
            if '가상자산' in cat:
                df.at[i, '위험도키워드'] = '가상자산'
                if has_업종:
                    df.at[i, '위험도분류'] = '가상자산지표'
                if has_위험도:
                    df.at[i, '위험도'] = 3.0
            elif _keyword_match(text, kw5):
                matched = _matched_keyword(text, kw5)
                df.at[i, '위험도키워드'] = matched
                if has_업종:
                    df.at[i, '위험도분류'] = '가상자산지표'
                if has_위험도:
                    df.at[i, '위험도'] = 3.0

    # 6호: 자산은닉지표 3.5 — 출금만 50만원 이상, 키워드: 해외송금/Wise/SWIFT 등
    kw6 = ['해외송금', '고액현금인출', '외화송금', '영문성명', 'Wise', 'TransferWise', 'SWIFT']
    for i in df.index:
        row = df.loc[i]
        inp, out = _num(row.get('입금액')), _num(row.get('출금액'))
        text = _search_text_dedup(row, SEARCH_COLS_2_8)
        if out >= 500_000 and inp <= 0 and _keyword_match(text, kw6):
            matched = _matched_keyword(text, kw6)
            df.at[i, '위험도키워드'] = matched
            if has_업종:
                df.at[i, '위험도분류'] = '자산은닉지표'
            if has_위험도:
                df.at[i, '위험도'] = 3.5

    # 7호: 과소비지표 4.0 — 출금만 30만원 이상, 키워드: 백화점/명품/귀금속/유흥/고가가전/고가가구/유흥주점/무도장/콜라텍/댄스홀
    kw7 = ['백화점', '명품', '귀금속', '유흥', '고가가전', '고가가구', '유흥주점', '무도장', '콜라텍', '댄스홀']
    for i in df.index:
        row = df.loc[i]
        inp, out = _num(row.get('입금액')), _num(row.get('출금액'))
        text = _search_text_dedup(row, SEARCH_COLS_2_8)
        if out >= 300_000 and inp <= 0 and _keyword_match(text, kw7):
            matched = _matched_keyword(text, kw7)
            df.at[i, '위험도키워드'] = matched
            if has_업종:
                df.at[i, '위험도분류'] = '과소비지표'
            if has_위험도:
                df.at[i, '위험도'] = 4.0

    # 8호: 사행성지표 5.0 — 출금만 10만원 이상, 키워드: 경마/복권/사설도박/도박기계/사행성게임기/오락기구/휴게텔/키스방/대화방/안마/마사지
    kw8 = ['경마', '복권', '사설도박', '도박기계', '사행성게임기', '오락기구', '휴게텔', '키스방', '대화방', '안마', '마사지', '사행성', '도박']
    for i in df.index:
        row = df.loc[i]
        inp, out = _num(row.get('입금액')), _num(row.get('출금액'))
        text = _search_text_dedup(row, SEARCH_COLS_2_8)
        if out >= 100_000 and inp <= 0 and _keyword_match(text, kw8):
            matched = _matched_keyword(text, kw8)
            df.at[i, '위험도키워드'] = matched
            if has_업종:
                df.at[i, '위험도분류'] = '사행성지표'
            if has_위험도:
                df.at[i, '위험도'] = 5.0

    # 보조 컬럼 제거
    df.drop(columns=['_kw', '_2호대상'], errors='ignore', inplace=True)

    # 위험도는 최소 0.1 보장 (혹시 0 이하가 되지 않도록)
    if has_위험도:
        df['위험도'] = df['위험도'].apply(lambda v: max(DEFAULT_RISK, _num(v, DEFAULT_RISK)))


def get_risk_indicators_document() -> str:
    """위험도 지표 1~8호 요약 문서용 텍스트 반환."""
    lines = [
        "1호. 자료소명지표: 출금 1000만원 이상, 해당 행 키워드를 위험도키워드로 저장, 위험도 1.0",
        "2호. 비정형지표: 출금만존재, 100만원 이상, 5회 이상 (특정인=키워드 기준), 해당 키워드를 위험도키워드로 저장, 위험도 1.5",
        "3호. 투기성지표: 입출금 50만원 이상, 위험도 2.0 (증권/선물/자산운용/위탁/증권입금)",
        "4호. 사기파산지표: 입출금 50만원 이상, 위험도 2.5 (대부/P2P/카드깡/원리금 상환)",
        "5호. 가상자산지표: 입출금 50만원 이상, 위험도 3.0 (카테고리 가상자산, 업비트/빗썸/코인원/코빗 등)",
        "6호. 자산은닉지표: 출금만 50만원 이상, 위험도 3.5 (해외송금/Wise/SWIFT 등)",
        "7호. 과소비지표: 출금만 30만원 이상, 위험도 4.0 (백화점/명품/귀금속/유흥/고가가전/고가가구/유흥주점/무도장/콜라텍/댄스홀)",
        "8호. 사행성지표: 출금만 10만원 이상, 위험도 5.0 (경마/복권/사설도박/도박기계/사행성게임기/오락기구/휴게텔/키스방/대화방/안마/마사지)",
    ]
    return "\n".join(lines)
