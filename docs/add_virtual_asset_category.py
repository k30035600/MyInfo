# -*- coding: utf-8 -*-
"""가상자산 회사 목록을 category_table.json에 추가 (분류=가상자산).
위치: readme(삭제하지 말것)/ 에서 참고/유틸로 보관.
실행: 프로젝트 루트(MyInfo)에서
  python "readme(삭제하지 말것)/add_virtual_asset_category.py"
"""
import os
import sys
import pandas as pd

# 스크립트가 readme 안에 있으므로 부모 = 프로젝트 루트
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from category_table_io import (
    load_category_table,
    normalize_category_df,
    safe_write_category_table,
    get_category_table_path,
    CATEGORY_TABLE_COLUMNS,
)

# 분류, 키워드, 카테고리
VIRTUAL_ASSET_ROWS = [
    ('가상자산', '두나무(주)/업비트', '119-86-54968'),
    ('가상자산', '(주)코빗/코빗', '220-88-61399'),
    ('가상자산', '(주)코인원/코인원', '261-81-07437'),
    ('가상자산', '(주)빗썸/빗썸', '220-88-71844'),
    ('가상자산', '(주)한국디지털거래소/플라이빗', '194-87-00761'),
    ('가상자산', '(주)스트리미/고팍스', '432-87-00120'),
    ('가상자산', '차일들리(주)/BTX', '729-86-01268'),
    ('가상자산', '(주)포블게이트/포블', '136-87-01478'),
    ('가상자산', '㈜코어닥스/코어닥스', '894-86-01183'),
    ('가상자산', '(주)그레이브릿지/비블록', '155-86-01720'),
    ('가상자산', '(주)포리스닥스코리아리미티드/오케이비트', '885-88-00694'),
    ('가상자산', '(주)골든퓨쳐스/빗크몬', '791-81-00992'),
    ('가상자산', '(주)프라뱅/프라뱅', '681-81-01205'),
    ('가상자산', '(주)보라비트/보라비트', '280-88-00977'),
    ('가상자산', '(주)한국디지털에셋/코다(KODA)', '618-81-36254'),
    ('가상자산', '(주)한국디지털자산수탁/케이닥(KDAC)', '809-86-01583'),
    ('가상자산', '(주)월렛원/오하이월렛', '636-88-00831'),
    ('가상자산', '하이퍼리즘유한책임회사/하이퍼리즘', '477-86-01090'),
    ('가상자산', '㈜가디언홀딩스/오아시스거래소', '826-81-00997'),
    ('가상자산', '(주)마인드시프트/커스텔라', '634-86-01747'),
    ('가상자산', '(주)인피닛블록/인피닛블록', '306-88-02374'),
    ('가상자산', '㈜디에스알브이랩스/디에스알브이랩스', '659-87-01307'),
    ('가상자산', '비댁스(주)/비댁스', '376-88-02126'),
    ('가상자산', '㈜인피니티익스체인지코리아/INEX(인엑스)', '783-81-02738'),
    ('가상자산', '㈜웨이브릿지/웨이브릿지프라임', '767-88-01245'),
    ('가상자산', '㈜해피블록/바우맨', '712-86-02691'),
    ('가상자산', '㈜블로세이프/로빗', '741-86-02855'),
]

def main():
    path = get_category_table_path(PROJECT_ROOT)
    full = load_category_table(path, default_empty=True)
    if full is None:
        full = pd.DataFrame(columns=CATEGORY_TABLE_COLUMNS)
    full = normalize_category_df(full)

    new_df = pd.DataFrame(VIRTUAL_ASSET_ROWS, columns=CATEGORY_TABLE_COLUMNS)
    key_cols = ['분류', '키워드', '카테고리']
    combined = pd.concat([full, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=key_cols, keep='first')
    safe_write_category_table(path, combined)
    print(f"저장 완료: {path} (가상자산 {len(VIRTUAL_ASSET_ROWS)}건 반영)")

if __name__ == '__main__':
    main()
