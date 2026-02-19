# -*- coding: utf-8 -*-
"""Excel 파일 안전 쓰기 공통 모듈. process_bank_data, process_card_data, process_cash_data, card_app에서 사용."""
import os
import time


def safe_write_excel(df, filepath, max_retries=3):
    """파일 쓰기 시 권한 오류 방지를 위한 안전한 Excel 쓰기. openpyxl 사용."""
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
                    raise PermissionError(f"파일을 삭제할 수 없습니다: {filepath}")
            df.to_excel(filepath, index=False, engine='openpyxl')
            return True
        except PermissionError as e:
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue
            raise e
        except Exception as e:
            raise e
    return False
