# -*- coding: utf-8 -*-
"""입금액 검증: card_before.xlsx에서 전처리 API와 동일한 로직으로 입금액 합계 확인"""
import sys
import os
import pandas as pd
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

# card_app의 함수 임포트
from card_app import load_card_before_file, _card_deposit_withdraw_from_이용금액
import card_app

def main():
    df = load_card_before_file()
    if df.empty:
        print("card_before.xlsx가 비어있거나 없습니다.")
        return
    
    # get_processed_data와 동일한 필터 (카드번호 16자 이하 제외)
    if '카드번호' in df.columns:
        before_count = len(df)
        df = df[df['카드번호'].astype(str).str.strip().str.len() > 16]
        print(f"카드번호 16자 이하 제외: {before_count} → {len(df)} 행")
    
    # 입금액/출금액 계산
    _card_deposit_withdraw_from_이용금액(df)
    
    deposit = int(df['입금액'].sum())
    withdraw = int(df['출금액'].sum())
    
    print(f"\n=== 입금액 검증 결과 ===")
    print(f"입금액 합계: {deposit:,}원")
    print(f"출금액 합계: {withdraw:,}원")
    
    # 이용금액 기준으로도 검증 (입금 = 이용금액 < 0 또는 현금처리)
    if '이용금액' in df.columns:
        amt = pd.to_numeric(df['이용금액'], errors='coerce')
        cat = df['카테고리'].fillna('').astype(str).str.strip() if '카테고리' in df.columns else pd.Series(['']*len(df), index=df.index)
        현금처리 = (cat == '현금처리')
        입금행 = (amt < 0) | 현금처리
        입금_이용금액합 = amt[입금행].abs().sum()
        print(f"\n이용금액 기준 입금 (amt<0 또는 현금처리): {int(입금_이용금액합):,}원")
        print(f"입금 건수: {입금행.sum()}")
    
    # 입금액 컬럼 합계와 비교
    입금액합 = df['입금액'].sum()
    print(f"\n입금액 컬럼 합계: {int(입금액합):,}원")
    
    # 입금 행 상세 (이용금액<0 또는 현금처리)
    if '이용금액' in df.columns:
        입금df = df[df['입금액'] > 0][['이용일', '이용금액', '가맹점명', '카테고리', '입금액']].copy()
        입금df = 입금df.sort_values('입금액', ascending=False)
        print(f"\n=== 입금 행 상세 (총 {len(입금df)}건) ===")
        for i, row in 입금df.iterrows():
            print(f"  {row['이용일']} | {int(row['입금액']):>10,}원 | {str(row['카테고리'])[:12]:12} | {str(row['가맹점명'])[:30]}")

if __name__ == '__main__':
    main()
