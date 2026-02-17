# -*- coding: utf-8 -*-
"""
category_table.json → category_table.xlsx 내보내기 (복구/백업용).
위치: readme(삭제하지 말것)/ 에서 참고/유틸로 보관.
실행: 프로젝트 루트(MyInfo)에서
  python "readme(삭제하지 말것)/export_category_table_to_xlsx.py"
"""
import os
import sys

# 스크립트가 readme 안에 있으므로 부모 = 프로젝트 루트
_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_script_dir)
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
