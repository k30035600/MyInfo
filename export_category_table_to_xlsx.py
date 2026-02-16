# -*- coding: utf-8 -*-
"""
category_table.json → category_table.xlsx 내보내기 (복구/백업용).
실행: 프로젝트 루트에서 python export_category_table_to_xlsx.py
"""
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

from category_table_io import export_category_table_to_xlsx, get_category_table_path

if __name__ == '__main__':
    ok, xlsx_path, err = export_category_table_to_xlsx(get_category_table_path())
    if ok:
        print(f"저장됨: {xlsx_path}")
    else:
        print(f"실패: {err}")
        sys.exit(1)
