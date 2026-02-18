# -*- coding: utf-8 -*-
from flask import Flask, render_template, jsonify, request, make_response, redirect
import traceback
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import io
import os
import shutil
import zipfile
from functools import wraps
from datetime import datetime

# Windows 한글 깨짐 방지: 콘솔 코드페이지만 UTF-8(65001) 설정 (stdout 교체 시 버퍼 닫힘 주의)
if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass

app = Flask(__name__)

# JSON 인코딩 설정 (한글 지원)
app.json.ensure_ascii = False
app.config['JSON_AS_ASCII'] = False

# 스크립트 디렉토리 (모듈 로드 시 한 번만 계산)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
try:
    from data_json_io import safe_read_data_json, safe_write_data_json
except ImportError:
    safe_read_data_json = None
    safe_write_data_json = None
# category: MyInfo/.source/category_table.json 하나만 사용 (category_table_io로 읽기/쓰기)
CATEGORY_TABLE_PATH = str(Path(PROJECT_ROOT) / '.source' / 'category_table.json')
try:
    from category_table_io import (
        load_category_table, normalize_category_df, CATEGORY_TABLE_COLUMNS,
        get_category_table as _io_get_category_table,
        apply_category_action,
    )
except ImportError:
    from category_table_fallback import (
        load_category_table, normalize_category_df, CATEGORY_TABLE_COLUMNS,
        get_category_table as _io_get_category_table,
        apply_category_action,
    )
# 원본 은행 파일: .source/Bank. before/after: MyBank 폴더 JSON (절대경로로 통일해 Errno 2 방지)
SOURCE_BANK_DIR = os.path.join(PROJECT_ROOT, '.source', 'Bank')
BANK_BEFORE_PATH = str(Path(SCRIPT_DIR).resolve() / 'bank_before.json')
BANK_AFTER_PATH = str(Path(SCRIPT_DIR).resolve() / 'bank_after.json')

# 전처리후 은행 필터: 드롭다운 값 → 실제 데이터에 있을 수 있는 은행명 별칭
# 적용 위치: get_processed_data()에서 load_processed_file()(bank_before.xlsx)로 읽은 DataFrame의 '은행명' 컬럼
BANK_FILTER_ALIASES = {
    '국민은행': ['국민은행', 'KB국민은행', '한국주택은행', '국민', '국민 은행'],
    '신한은행': ['신한은행', '신한'],
    '하나은행': ['하나은행', '하나'],
}


def _is_bad_zip_error(e):
    """openpyxl이 손상된/비xlsx 파일을 읽을 때 발생하는 오류인지 확인 (zip/decompress 손상 포함)."""
    msg = str(e).lower()
    return (
        isinstance(e, zipfile.BadZipFile)
        or 'not a zip file' in msg
        or 'bad zip' in msg
        or 'zip file' in msg
        or (('zip' in msg or 'badzip' in msg) and ('file' in msg or 'open' in msg))
        or 'decompress' in msg
        or 'invalid block' in msg
        or 'error -3' in msg
    )


def _remove_bad_data_file(path, recreate_empty=None):
    """손상된 데이터 파일 삭제. .bak 생성하지 않음. recreate_empty가 (columns리스트)이면 빈 JSON 재생성."""
    p = Path(path)
    if p.exists() and p.stat().st_size > 0:
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        except OSError as ex:
            winerr = getattr(ex, 'winerror', None)
            errno_val = getattr(ex, 'errno', None)
            if winerr == 32 or errno_val == 13:
                print(f"안내: {p.name}이(가) 다른 프로그램에서 열려 있어 삭제할 수 없습니다. 파일을 닫은 뒤 다시 시도하세요.", flush=True)
            elif winerr != 2 and errno_val != 2:
                print(f"삭제 실패 {p}: {ex}", flush=True)
    if recreate_empty is not None:
        try:
            from data_json_io import safe_write_data_json
            empty = pd.DataFrame(columns=recreate_empty)
            safe_write_data_json(p, empty)
        except Exception as ex:
            print(f"빈 데이터 파일 재생성 실패 {p}: {ex}", flush=True)


def _is_file_in_use_error(e):
    """다른 프로세스가 파일 사용 중으로 읽기 실패한 경우(백업/삭제 대상 아님)."""
    if isinstance(e, PermissionError):
        return True
    if isinstance(e, OSError):
        if getattr(e, 'winerror', None) == 32:
            return True
        if getattr(e, 'errno', None) in (13, 32):  # EACCES, EBUSY
            return True
    msg = str(e).lower()
    return '다른 프로세스' in msg or 'used by another' in msg or 'access is denied' in msg or '파일을 사용 중' in msg


def safe_read_excel(path, default_empty=True):
    """xlsx 파일을 안전하게 읽음. 손상/비xlsx 시에만 백업 후 빈 DataFrame 반환. 파일 없음·사용 중이면 백업하지 않음."""
    path = Path(path)
    if not path.exists():
        return pd.DataFrame() if default_empty else None
    if path.stat().st_size == 0:
        # 0바이트: 백업/삭제하지 않음(방금 생성 중이거나 비어 있는 상태일 수 있음)
        return pd.DataFrame() if default_empty else None
    try:
        return pd.read_excel(str(path), engine='openpyxl')
    except Exception as e:
        # 다른 프로세스 사용 중으로 읽기 실패한 경우: 백업/삭제하지 않고 빈 DataFrame만 반환
        if _is_file_in_use_error(e):
            return pd.DataFrame() if default_empty else None
        err_msg = str(e).lower()
        if _is_bad_zip_error(e):
            _remove_bad_data_file(path)
            return pd.DataFrame() if default_empty else None
        if 'zip' in err_msg or 'not a zip' in err_msg or 'decompress' in err_msg or 'invalid block' in err_msg:
            _remove_bad_data_file(path)
            return pd.DataFrame() if default_empty else None
        raise


def ensure_working_directory(func):
    """데코레이터: API 엔드포인트에서 작업 디렉토리를 스크립트 위치로 보장"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        original_cwd = os.getcwd()
        try:
            os.chdir(SCRIPT_DIR)
            return func(*args, **kwargs)
        finally:
            os.chdir(original_cwd)
    return wrapper

def _json_safe(obj):
    """JSON 직렬화: NaN/NaT, numpy, datetime → Python 타입"""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64, np.float32)):
        return None if pd.isna(obj) else float(obj)
    if isinstance(obj, float) and pd.isna(obj):
        return None
    if pd.isna(obj):
        return None
    if hasattr(obj, 'isoformat'):
        try:
            return obj.isoformat()
        except Exception:
            return str(obj)
    return obj

def load_source_files():
    """MyInfo/.source/Bank 의 원본 파일 목록 가져오기. .xls, .xlsx만 취급."""
    source_dir = Path(SOURCE_BANK_DIR)
    if not source_dir.exists():
        current_dir = os.getcwd()
        print(f"[WARNING] .source/Bank 폴더를 찾을 수 없습니다. 현재 작업 디렉토리: {current_dir}, .source/Bank 경로: {source_dir}", flush=True)
        return []
    files = []
    paths = sorted(
        list(source_dir.glob('*.xls')) + list(source_dir.glob('*.xlsx')),
        key=lambda p: (p.name, str(p))
    )
    for file_path in paths:
        file_info = {
            'filename': file_path.name,
            'path': str(file_path),
            'sheets': []
        }
        
        try:
            xls = pd.ExcelFile(file_path)
            for sheet_name in xls.sheet_names:
                file_info['sheets'].append({
                    'name': sheet_name,
                    'filename': file_path.name
                })
        except Exception:
            # .source는 .xls, .xlsx만 취급. 읽기 실패 시 스킵
            continue
        
        files.append(file_info)
    
    return files

# bank_before 대용량 JSON 캐시 (파일 mtime 기준 갱신)
_processed_file_cache = None
_processed_file_cache_mtime = None

def load_processed_file():
    """전처리된 파일 로드 (MyBank/bank_before.json). 손상 시 빈 DataFrame 반환. 대용량 시 캐시 사용."""
    global _processed_file_cache, _processed_file_cache_mtime
    try:
        path = Path(BANK_BEFORE_PATH)
        if not path.exists():
            _processed_file_cache = None
            _processed_file_cache_mtime = None
            return pd.DataFrame()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = None
        if _processed_file_cache is not None and mtime is not None and _processed_file_cache_mtime == mtime:
            return _processed_file_cache.copy()
        if safe_read_data_json:
            df = safe_read_data_json(BANK_BEFORE_PATH, default_empty=True)
        else:
            df = safe_read_excel(path, default_empty=True)
        if df is not None and not df.empty:
            _processed_file_cache = df
            _processed_file_cache_mtime = mtime
            return df.copy()
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        print(f"오류: bank_before.json 파일 로드 실패 - {e}", flush=True)
        return pd.DataFrame()

# bank_after 대용량 JSON 캐시 (파일 mtime 기준 갱신)
_category_file_cache = None
_category_file_cache_mtime = None

def load_category_file():
    """카테고리 적용 파일 로드 (MyBank/bank_after.json). 손상 시 빈 DataFrame 반환. 대용량 시 캐시 사용."""
    global _category_file_cache, _category_file_cache_mtime
    try:
        category_file = Path(BANK_AFTER_PATH)
        if not category_file.exists():
            _category_file_cache = None
            _category_file_cache_mtime = None
            return load_processed_file() if load_processed_file() is not None else pd.DataFrame()
        try:
            mtime = category_file.stat().st_mtime
        except OSError:
            mtime = None
        if _category_file_cache is not None and mtime is not None and _category_file_cache_mtime == mtime:
            return _category_file_cache.copy()
        if safe_read_data_json:
            df = safe_read_data_json(BANK_AFTER_PATH, default_empty=True)
        else:
            df = safe_read_excel(category_file, default_empty=True)
        if df is not None and not df.empty:
            df.columns = [str(c).strip().lstrip('\ufeff') for c in df.columns]
            if '구분' in df.columns and '취소' not in df.columns:
                df = df.rename(columns={'구분': '취소'})
            _category_file_cache = df
            _category_file_cache_mtime = mtime
            return df.copy()
        df = load_processed_file()
        if df is not None and not df.empty and '구분' in df.columns and '취소' not in df.columns:
            df = df.rename(columns={'구분': '취소'})
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        print(f"Error in load_category_file: {str(e)}", flush=True)
        return pd.DataFrame()

@app.route('/')
def index():
    workspace_path = str(SCRIPT_DIR)  # 전처리전 작업폴더(MyBank 경로)
    resp = make_response(render_template('index.html', workspace_path=workspace_path))
    # 전처리 페이지 캐시 방지: 네비게이션 갱신이 바로 반영되도록
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/source-files')
@ensure_working_directory
def get_source_files():
    """원본 파일 목록 반환. MyInfo/.source/Bank 의 .xls, .xlsx만 취급."""
    try:
        current_dir = os.getcwd()
        source_dir = Path(SOURCE_BANK_DIR)
        if not source_dir.exists():
            return jsonify({
                'error': f'.source/Bank 폴더를 찾을 수 없습니다.\n현재 작업 디렉토리: {current_dir}\n.source/Bank 경로: {source_dir}',
                'files': []
            }), 404
        
        files = load_source_files()
        response = jsonify({
            'files': files,
            'count': len(files)
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        current_dir = os.getcwd()
        return jsonify({
            'error': f'파일 목록 로드 중 오류가 발생했습니다: {str(e)}\n현재 작업 디렉토리: {current_dir}\n스크립트 디렉토리: {SCRIPT_DIR}',
            'files': []
        }), 500

def _create_empty_bank_before(path):
    """bank_before가 없을 때 빈 표준 컬럼 JSON 생성. 데이터 로딩 오류(Errno 2) 방지."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ['거래일', '거래시간', '은행명', '계좌번호', '입금액', '출금액', '잔액',
            '취소', '적요', '내용', '송금메모', '거래점']
    empty = pd.DataFrame(columns=cols)
    if safe_write_data_json:
        safe_write_data_json(str(path), empty)
    else:
        empty.to_excel(str(path), index=False, engine='openpyxl')


def _remove_bank_before_after_and_bak():
    """통합·전처리 다시 실행 전에 bank_before/bank_after 데이터 파일 삭제. 캐시 무효화."""
    global _processed_file_cache, _processed_file_cache_mtime, _category_file_cache, _category_file_cache_mtime
    _processed_file_cache = None
    _processed_file_cache_mtime = None
    _category_file_cache = None
    _category_file_cache_mtime = None
    for path_str in (BANK_BEFORE_PATH, BANK_AFTER_PATH):
        p = Path(path_str)
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass


@app.route('/api/reintegrate', methods=['POST'])
@ensure_working_directory
def reintegrate_bank():
    """bank_before를 .source/Bank 기준으로 다시 통합·전처리하여 덮어쓴다. before/after 삭제 후 통합·전처리만 수행(bank_after 미생성)."""
    try:
        _remove_bank_before_after_and_bak()
        _path_added = False
        try:
            _dir_str = str(SCRIPT_DIR)
            if _dir_str not in sys.path:
                sys.path.insert(0, _dir_str)
                _path_added = True
            import process_bank_data as _pbd
            _pbd.integrate_bank_transactions(output_file=str(Path(BANK_BEFORE_PATH)))
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500
        finally:
            if _path_added and str(SCRIPT_DIR) in sys.path:
                sys.path.remove(str(SCRIPT_DIR))
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/regenerate-prepost', methods=['POST'])
@ensure_working_directory
def regenerate_prepost():
    """bank_before·bank_after 삭제 후 source→전처리→before→카테고리분류→후처리→after 전체 재생성."""
    try:
        _remove_bank_before_after_and_bak()
        _path_added = False
        try:
            _dir_str = str(SCRIPT_DIR)
            if _dir_str not in sys.path:
                sys.path.insert(0, _dir_str)
                _path_added = True
            import process_bank_data as _pbd
            _pbd.integrate_bank_transactions(output_file=str(Path(BANK_BEFORE_PATH)))
            if not Path(BANK_BEFORE_PATH).exists() or Path(BANK_BEFORE_PATH).stat().st_size == 0:
                return jsonify({'ok': False, 'error': 'bank_before 생성 후에도 없거나 비어 있습니다. .source/Bank 원본을 확인하세요.'}), 500
            if not _pbd.classify_and_save():
                err = getattr(_pbd, 'LAST_CLASSIFY_ERROR', None) or '카테고리 분류·후처리 실패'
                return jsonify({'ok': False, 'error': str(err)}), 500
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500
        finally:
            if _path_added and str(SCRIPT_DIR) in sys.path:
                sys.path.remove(str(SCRIPT_DIR))
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/processed-data')
@ensure_working_directory
def get_processed_data():
    """전처리된 데이터 반환 (필터링 지원). 전체 JSON 반환, 클라이언트에서 테이블 렌더."""
    try:
        output_path = Path(BANK_BEFORE_PATH).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        bank_before_existed = output_path.exists()  # 요청 시작 시 존재 여부 (이번 요청에서 생성됐으면 에러 문구 구분)
        # bank_before, category_table만 준비 (bank_after 생성/카테고리분류는 하지 않음). 경로를 명시해 동일 경로에 생성 보장.
        _path_added = False
        try:
            _dir_str = str(SCRIPT_DIR)
            if _dir_str not in sys.path:
                sys.path.insert(0, _dir_str)
                _path_added = True
            import process_bank_data as _pbd
            _pbd.ensure_bank_before_and_category(bank_before_path=str(output_path))
        except Exception as e:
            error_msg = str(e)
            if 'No such file' in error_msg and 'bank_before' in error_msg:
                _create_empty_bank_before(output_path)
            else:
                hint = []
                if 'bank_after' in error_msg or 'PermissionError' in error_msg or '사용 중' in error_msg:
                    hint.append('bank_after.xlsx를 열어둔 프로그램(Excel 등)을 닫아주세요.')
                if 'xlrd' in error_msg or 'No module' in error_msg:
                    hint.append('.xls 파일 읽기에는 xlrd 패키지가 필요합니다: pip install xlrd')
                extra = '\n' + '\n'.join(hint) if hint else ''
                return jsonify({
                    'error': f'파일 생성 실패: {error_msg}{extra}',
                    'count': 0,
                    'deposit_amount': 0,
                    'withdraw_amount': 0,
                    'data': []
                }), 500
        finally:
            if _path_added and str(SCRIPT_DIR) in sys.path:
                sys.path.remove(str(SCRIPT_DIR))

        if not output_path.exists():
            try:
                _pbd.integrate_bank_transactions(output_file=str(output_path))
            except Exception:
                pass
        if not output_path.exists():
            _create_empty_bank_before(output_path)

        # 전처리후: bank_after 있으면 사용. 없으면 before 기준으로 계정과목분류·후처리 후 after 생성해 사용.
        category_file_exists = Path(BANK_AFTER_PATH).exists()
        if category_file_exists:
            try:
                df = load_category_file()
            except Exception:
                df = load_processed_file()
        else:
            df = load_processed_file()

        # after가 없고 before 데이터가 있으면 → 계정과목분류·후처리 실행해 after 생성 후 재로드
        if not category_file_exists and not df.empty:
            _path_added_2 = False
            try:
                if str(SCRIPT_DIR) not in sys.path:
                    sys.path.insert(0, str(SCRIPT_DIR))
                    _path_added_2 = True
                import process_bank_data as _pbd
                if _pbd.classify_and_save():
                    category_file_exists = True
                    try:
                        df = load_category_file()
                    except Exception:
                        pass
            except Exception as e:
                print(f"after 자동 생성 실패: {e}", flush=True)
            finally:
                if _path_added_2 and str(SCRIPT_DIR) in sys.path:
                    sys.path.remove(str(SCRIPT_DIR))

        if df.empty:
            # 데이터 없음 시 추출 실패 이유(LAST_INTEGRATE_ERROR)를 함께 반환해 화면에 표시
            integrate_reason = None
            try:
                import process_bank_data as _pbd_reason
                integrate_reason = getattr(_pbd_reason, 'LAST_INTEGRATE_ERROR', None) or None
                if integrate_reason and not isinstance(integrate_reason, str):
                    integrate_reason = None
            except Exception:
                pass
            response = jsonify({
                'total': 0,
                'count': 0,
                'deposit_amount': 0,
                'withdraw_amount': 0,
                'deposit_count': 0,
                'withdraw_count': 0,
                'data': [],
                'file_exists': category_file_exists,
                'integrate_reason': (integrate_reason.strip() if integrate_reason else None)
            })
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response

        # 카테고리 조회 테이블용: 키워드·카테고리·기타거래 없으면 빈 컬럼 추가 (bank_before fallback 또는 구버전 bank_after 시)
        for col in ['키워드', '카테고리', '기타거래']:
            if col not in df.columns:
                df[col] = ''

        # 필터 파라미터
        bank_filter = (request.args.get('bank') or '').strip()
        date_filter = request.args.get('date', '')
        account_filter = (request.args.get('account') or '').strip()
        
        # 전처리후 은행 필터: bank_before.xlsx(load_processed_file)의 '은행명' 컬럼에서 적용
        bank_col = next((c for c in df.columns if str(c).strip() == '은행명'), None)
        if bank_filter and bank_col is not None:
            allowed = set(BANK_FILTER_ALIASES.get(bank_filter, [bank_filter]))
            s = df[bank_col].fillna('').astype(str).str.strip()
            df = df[s.isin(allowed)].copy()
        
        if date_filter:
            df = df[df['거래일'].astype(str).str.startswith(date_filter)]
        
        if account_filter and '계좌번호' in df.columns:
            df = df[df['계좌번호'].fillna('').astype(str).str.strip() == account_filter]
        
        # 집계 계산 (전체 필터된 데이터 기준)
        count = len(df)
        deposit_amount = df['입금액'].sum() if not df.empty else 0
        withdraw_amount = df['출금액'].sum() if not df.empty else 0
        deposit_count = int((pd.to_numeric(df['입금액'], errors='coerce').fillna(0) > 0).sum()) if not df.empty and '입금액' in df.columns else 0
        withdraw_count = int((pd.to_numeric(df['출금액'], errors='coerce').fillna(0) > 0).sum()) if not df.empty and '출금액' in df.columns else 0

        # NaN 값을 None으로 변환
        df = df.where(pd.notna(df), None)

        # 전체 JSON 반환 (클라이언트에서 한 번에 테이블 렌더, 스크롤은 CSS)
        total = len(df)
        data = df.to_dict('records')
        data = _json_safe(data)
        resp_payload = {
            'total': total,
            'count': len(data),
            'deposit_amount': int(deposit_amount),
            'withdraw_amount': int(withdraw_amount),
            'deposit_count': deposit_count,
            'withdraw_count': withdraw_count,
            'data': data,
            'file_exists': category_file_exists
        }
        response = jsonify(resp_payload)
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        category_file_exists = Path(BANK_AFTER_PATH).exists()
        return jsonify({
            'error': str(e),
            'total': 0,
            'count': 0,
            'deposit_amount': 0,
            'withdraw_amount': 0,
            'deposit_count': 0,
            'withdraw_count': 0,
            'data': [],
            'file_exists': category_file_exists
        }), 500

@app.route('/api/simya-ranges')
@ensure_working_directory
def get_simya_ranges():
    """category_table.json에서 분류=심야구분인 행의 키워드(시작/종료 hh:mm:ss)를 파싱하여 반환."""
    try:
        df = load_category_table(CATEGORY_TABLE_PATH, default_empty=True)
        if df is None or df.empty or '분류' not in df.columns:
            return jsonify({'ranges': []})
        simya = df[df['분류'].fillna('').astype(str).str.strip() == '심야구분'].copy()
        ranges = []
        for _, row in simya.iterrows():
            kw = str(row.get('키워드', '') or '').strip()
            if not kw or '/' not in kw:
                continue
            parts = kw.split('/', 1)
            start_s, end_s = parts[0].strip(), parts[1].strip()
            # hh:mm:ss 또는 hhmmss 형식 파싱
            def to_seconds(s):
                s = str(s).strip()
                if ':' in s:
                    p = s.split(':')
                    h = int(p[0]) if len(p) > 0 else 0
                    m = int(p[1]) if len(p) > 1 else 0
                    sec = int(float(p[2])) if len(p) > 2 else 0
                else:
                    s = s.replace(' ', '')
                    if len(s) >= 6:
                        h, m, sec = int(s[0:2]), int(s[2:4]), int(s[4:6])
                    else:
                        return None
                return h * 3600 + m * 60 + sec
            start_sec = to_seconds(start_s)
            end_sec = to_seconds(end_s)
            if start_sec is not None and end_sec is not None:
                ranges.append({'start': start_s if ':' in start_s else f'{start_s[0:2]}:{start_s[2:4]}:{start_s[4:6]}', 'end': end_s if ':' in end_s else f'{end_s[0:2]}:{end_s[2:4]}:{end_s[4:6]}'})
        return jsonify({'ranges': ranges})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'ranges': [], 'error': str(e)})


@app.route('/api/category-applied-data')
@ensure_working_directory
def get_category_applied_data():
    """카테고리 적용된 데이터 반환 (필터링 지원). 전체 JSON 반환."""
    try:
        # bank_before, category_table만 준비 (테이블/출력 시 카테고리 분류 미수행)
        _path_added = False
        try:
            _dir_str = str(SCRIPT_DIR)
            if _dir_str not in sys.path:
                sys.path.insert(0, _dir_str)
                _path_added = True
            import process_bank_data as _pbd
            _pbd.ensure_bank_before_and_category()
        except Exception:
            pass  # ensure 실패 시 기존 파일로 진행
        finally:
            if _path_added and str(SCRIPT_DIR) in sys.path:
                sys.path.remove(str(SCRIPT_DIR))

        category_file_exists = Path(BANK_AFTER_PATH).exists()
        
        try:
            df = load_category_file()
        except Exception as e:
            print(f"Error loading category file: {str(e)}")
            traceback.print_exc()
            # 파일 로드 실패 시 빈 DataFrame 반환
            df = pd.DataFrame()
        
        if df.empty:
            response = jsonify({
                'count': 0,
                'total': 0,
                'deposit_amount': 0,
                'withdraw_amount': 0,
                'deposit_count': 0,
                'withdraw_count': 0,
                'data': [],
                'file_exists': category_file_exists
            })
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response
        
        # 필터 파라미터 (전처리후 은행/계좌에 따라 필터링)
        bank_filter = (request.args.get('bank') or '').strip()
        date_filter = request.args.get('date', '')
        account_filter = (request.args.get('account') or '').strip()
        
        # 필터 적용
        if bank_filter and '은행명' in df.columns:
            allowed = set(BANK_FILTER_ALIASES.get(bank_filter, [bank_filter]))
            s = df['은행명'].fillna('').astype(str).str.strip()
            df = df[s.isin(allowed)].copy()
        
        if account_filter and '계좌번호' in df.columns:
            df = df[df['계좌번호'].fillna('').astype(str).str.strip() == account_filter]
        
        if date_filter and '거래일' in df.columns:
            try:
                # 거래일 컬럼을 안전하게 문자열로 변환
                df['거래일_str'] = df['거래일'].astype(str)
                df = df[df['거래일_str'].str.startswith(date_filter, na=False)]
                df = df.drop('거래일_str', axis=1)
            except Exception as e:
                print(f"Error filtering by date: {str(e)}")
                # 날짜 필터링 실패 시 필터 없이 진행
                pass
        
        # 필수 컬럼 확인
        required_columns = ['입금액', '출금액']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns and not df.empty:
            print(f"Warning: Missing columns in data: {missing_columns}")
            for col in missing_columns:
                df[col] = 0
        # 카테고리 적용후 테이블용: 키워드·카테고리·기타거래 없으면 빈 컬럼 추가 (bank_before fallback 또는 구버전 bank_after 시)
        for col in ['키워드', '카테고리', '기타거래']:
            if col not in df.columns:
                df[col] = ''

        # 집계 계산 (필터 적용 후 전체 기준)
        count = len(df)
        deposit_amount = df['입금액'].sum() if not df.empty and '입금액' in df.columns else 0
        withdraw_amount = df['출금액'].sum() if not df.empty and '출금액' in df.columns else 0
        dep_series = pd.to_numeric(df['입금액'], errors='coerce').fillna(0) if not df.empty and '입금액' in df.columns else pd.Series(dtype=float)
        wit_series = pd.to_numeric(df['출금액'], errors='coerce').fillna(0) if not df.empty and '출금액' in df.columns else pd.Series(dtype=float)
        deposit_count = int((dep_series > 0).sum())
        withdraw_count = int((wit_series > 0).sum())
        
        df = df.where(pd.notna(df), None)
        # 카테고리 적용후 테이블: 거래일 → 거래시간 → 계좌번호 순 정렬
        sort_cols = []
        if '거래일' in df.columns:
            sort_cols.append('거래일')
        if '거래시간' in df.columns:
            sort_cols.append('거래시간')
        if '계좌번호' in df.columns:
            sort_cols.append('계좌번호')
        if sort_cols:
            df = df.sort_values(by=sort_cols, ascending=True, na_position='last').reset_index(drop=True)
        # 전체 JSON 반환 (클라이언트에서 한 번에 테이블 렌더)
        total = len(df)
        data = df.to_dict('records')
        data = _json_safe(data)
        response = jsonify({
            'total': total,
            'count': len(data),
            'deposit_amount': int(deposit_amount),
            'withdraw_amount': int(withdraw_amount),
            'deposit_count': deposit_count,
            'withdraw_count': withdraw_count,
            'data': data,
            'file_exists': category_file_exists
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        category_file_exists = Path(BANK_AFTER_PATH).exists()
        return jsonify({
            'error': str(e),
            'count': 0,
            'deposit_amount': 0,
            'withdraw_amount': 0,
            'data': [],
            'file_exists': category_file_exists
        }), 500

@app.route('/api/source-data')
@ensure_working_directory
def get_source_data():
    """원본 파일 데이터 반환 (필터링 지원). MyInfo/.source/Bank 의 .xls, .xlsx만 취급."""
    try:
        source_dir = Path(SOURCE_BANK_DIR)
        current_dir = os.getcwd()
        if not source_dir.exists():
            return jsonify({
                'error': f'.source/Bank 폴더를 찾을 수 없습니다.\n현재 작업 디렉토리: {current_dir}\n.source/Bank 경로: {source_dir}',
                'count': 0,
                'deposit_amount': 0,
                'withdraw_amount': 0,
                'files': []
            }), 404
        
        # 필터 파라미터
        bank_filter = request.args.get('bank', '')
        date_filter = request.args.get('date', '')
        
        all_data = []
        count = 0
        deposit_amount = 0
        withdraw_amount = 0
        
        # .source는 .xls, .xlsx만 취급
        xls_files = list(source_dir.glob('*.xls')) + list(source_dir.glob('*.xlsx'))
        xls_files = sorted(set(xls_files), key=lambda p: (p.name, str(p)))
        if not xls_files:
            return jsonify({
                'error': f'.source/Bank 폴더에 .xls, .xlsx 파일이 없습니다.\n현재 작업 디렉토리: {current_dir}\n.source/Bank 경로: {source_dir}',
                'count': 0,
                'deposit_amount': 0,
                'withdraw_amount': 0,
                'files': []
            }), 404
        
        for file_path in xls_files:
            # 은행명 추출
            filename = file_path.name
            bank_name = None
            if '국민은행' in filename:
                bank_name = '국민은행'
            elif '신한은행' in filename:
                bank_name = '신한은행'
            elif '하나은행' in filename:
                bank_name = '하나은행'
            
            # 은행 필터 적용
            if bank_filter and bank_name != bank_filter:
                continue
            
            try:
                # 엑셀 파일 읽기
                xls = pd.ExcelFile(file_path)
                for sheet_name in xls.sheet_names:
                    try:
                        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
                        
                        df = df.where(pd.notna(df), None)
                        data_dict = df.to_dict('records')
                        data_dict = _json_safe(data_dict)
                        sheet_data = {
                            'filename': filename,
                            'sheet_name': sheet_name,
                            'bank': bank_name,
                            'data': data_dict
                        }
                        all_data.append(sheet_data)
                        count += len(data_dict)
                    except Exception:
                        continue
            except Exception:
                # .source는 .xls, .xlsx만 취급. 읽기 실패 시 스킵
                continue
        
        response = jsonify({
            'count': count,
            'deposit_amount': int(deposit_amount),
            'withdraw_amount': int(withdraw_amount),
            'files': all_data
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        response = jsonify({
            'error': str(e),
            'count': 0,
            'deposit_amount': 0,
            'withdraw_amount': 0,
            'files': []
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500

# 카테고리 페이지 라우트
@app.route('/category')
def category():
    """카테고리 페이지"""
    return render_template('category.html')

# 카테고리: MyInfo/.source/category_table.json 단일 테이블(구분 없음, 은행/신용카드 공통)
@app.route('/api/bank_category')
@ensure_working_directory
def get_category_table():
    """category_table.json 전체 반환 (구분 없음). 없으면 생성 후 반환."""
    path = Path(CATEGORY_TABLE_PATH)
    try:
        _path_added = False
        try:
            _dir_str = str(SCRIPT_DIR)
            if _dir_str not in sys.path:
                sys.path.insert(0, _dir_str)
                _path_added = True
            import process_bank_data as _pbd
            _pbd.ensure_bank_before_and_category()
            if path.exists():
                _pbd.migrate_bank_category_file(str(path))
        except Exception as _e:
            if str(path).endswith('.json'):
                try:
                    if path.exists() and path.stat().st_size > 0:
                        path.unlink()
                    from category_table_io import create_empty_category_table
                    create_empty_category_table(str(path))
                except Exception:
                    pass
            else:
                raise
        finally:
            if _path_added and str(SCRIPT_DIR) in sys.path:
                sys.path.remove(str(SCRIPT_DIR))

        df, file_existed = _io_get_category_table(str(path))
        cols = CATEGORY_TABLE_COLUMNS
        if file_existed and (df is None or df.empty) and path.exists() and path.stat().st_size > 0:
            if str(path).endswith('.json'):
                try:
                    path.unlink()
                    from category_table_io import create_empty_category_table
                    create_empty_category_table(str(path))
                except Exception:
                    pass
            df = pd.DataFrame(columns=cols)
        if len(df) == 0 and path.exists():
            _orig_cwd = os.getcwd()
            try:
                if str(SCRIPT_DIR) not in sys.path:
                    sys.path.insert(0, str(SCRIPT_DIR))
                import process_bank_data as _pbd_fill
                os.chdir(SCRIPT_DIR)
                _pbd_fill.create_category_table(pd.DataFrame())
                df, _ = _io_get_category_table(str(path))
            except Exception:
                pass
            finally:
                os.chdir(_orig_cwd)
        if df is None or df.empty:
            df = pd.DataFrame(columns=cols)
        data = df.to_dict('records')
        response = jsonify({
            'data': data,
            'columns': ['분류', '키워드', '카테고리'],
            'count': len(df),
            'file_exists': True
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        err_msg = str(e).lower()
        if str(path).endswith('.json'):
            try:
                if path.exists() and path.stat().st_size > 0:
                    path.unlink()
                from category_table_io import create_empty_category_table
                create_empty_category_table(str(path))
            except Exception:
                pass
            df = pd.DataFrame(columns=['분류', '키워드', '카테고리'])
            response = jsonify({
                'data': df.to_dict('records'),
                'columns': ['분류', '키워드', '카테고리'],
                'count': 0,
                'file_exists': True
            })
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response
        file_exists = path.exists()
        response = jsonify({
            'error': str(e),
            'data': [],
            'file_exists': file_exists
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500

@app.route('/api/bank_category', methods=['POST'])
@ensure_working_directory
def save_category_table():
    """category_table.json 전체 갱신 (구분 없음)"""
    try:
        path = str(Path(CATEGORY_TABLE_PATH))
        data = request.json or {}
        action = data.get('action', 'add')
        success, error_msg, count = apply_category_action(path, action, data)
        if not success:
            return jsonify({'success': False, 'error': error_msg}), 400
        try:
            from category_table_defaults import sync_category_create_from_xlsx
            sync_category_create_from_xlsx(path)
        except Exception:
            pass
        response = jsonify({
            'success': True,
            'message': '카테고리 테이블이 업데이트되었습니다.',
            'count': count
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        response = jsonify({
            'success': False,
            'error': str(e)
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500

# 분석 페이지 라우트
@app.route('/analysis/basic')
def analysis_basic():
    """기본 기능 분석 페이지"""
    return render_template('analysis_basic.html')

@app.route('/analysis/print')
@ensure_working_directory
def print_analysis():
    """은행거래 기본분석 인쇄용 페이지 (bank_after.xlsx 사용, 신용카드 기본분석과 동일 양식)"""
    try:
        bank_filter = request.args.get('bank', '')
        category_filter = request.args.get('category', '')  # 선택한 카테고리 (출력 시 사용)

        df = load_category_file()
        if df.empty:
            return "데이터가 없습니다.", 400

        if bank_filter and '은행명' in df.columns:
            df = df[df['은행명'].astype(str).str.strip() == bank_filter]

        total_count = len(df)
        deposit_count = len(df[df['입금액'] > 0])
        withdraw_count = len(df[df['출금액'] > 0])
        total_deposit = int(df['입금액'].sum())
        total_withdraw = int(df['출금액'].sum())
        net_balance = total_deposit - total_withdraw

        # 카테고리별 입출금 내역 (bank_after의 카테고리 컬럼 기준)
        category_col = '카테고리' if '카테고리' in df.columns else '적요'
        if category_col not in df.columns:
            df[category_col] = '(빈값)'
        df[category_col] = df[category_col].fillna('').astype(str).str.strip().replace('', '(빈값)')
        category_stats = df.groupby(category_col).agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        category_stats = category_stats.rename(columns={category_col: '카테고리'})
        category_stats['차액'] = category_stats['입금액'] - category_stats['출금액']
        category_stats['차액_절대값'] = category_stats['차액'].abs()
        category_stats = category_stats.sort_values(['차액_절대값', '차액', '입금액'], ascending=[False, False, False])
        category_stats = category_stats.drop(columns=['차액_절대값'], errors='ignore')

        top_category = category_stats.iloc[0]['카테고리'] if not category_stats.empty else ''
        selected_category = category_filter if category_filter else top_category
        if selected_category:
            trans_all = df[df[category_col] == selected_category]
            transaction_total_count = len(trans_all)
            transactions = trans_all.head(15)
            transaction_deposit_total = int(trans_all['입금액'].sum())
            transaction_withdraw_total = int(trans_all['출금액'].sum())
        else:
            transaction_total_count = 0
            transactions = pd.DataFrame()
            transaction_deposit_total = 0
            transaction_withdraw_total = 0

        bank_col = '은행명'
        bank_stats = df.groupby(bank_col).agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()

        account_col = '계좌번호'
        if account_col in df.columns:
            account_stats = df.groupby([bank_col, account_col]).agg({
                '입금액': 'sum',
                '출금액': 'sum'
            }).reset_index()
            # 출력용: 계좌번호 뒤 6자리 (그래픽 레이블/범례와 동일)
            acc_ser = account_stats[account_col].astype(str).str.strip()
            account_stats['account_short'] = acc_ser.apply(lambda x: x[-6:] if len(x) > 6 else x)
        else:
            account_stats = pd.DataFrame()

        max_deposit = int(bank_stats['입금액'].max()) if not bank_stats.empty else 1
        max_withdraw = int(bank_stats['출금액'].max()) if not bank_stats.empty else 1
        max_account_deposit = int(account_stats['입금액'].max()) if not account_stats.empty and '입금액' in account_stats.columns else 1
        max_account_withdraw = int(account_stats['출금액'].max()) if not account_stats.empty and '출금액' in account_stats.columns else 1
        total_account_deposit = int(account_stats['입금액'].sum()) if not account_stats.empty and '입금액' in account_stats.columns else 0
        total_account_withdraw = int(account_stats['출금액'].sum()) if not account_stats.empty and '출금액' in account_stats.columns else 0
        total_account_deposit_10 = int(account_stats.head(10)['입금액'].sum()) if not account_stats.empty and '입금액' in account_stats.columns else 0
        total_account_withdraw_10 = int(account_stats.head(10)['출금액'].sum()) if not account_stats.empty and '출금액' in account_stats.columns else 0

        date_col = '거래일'
        if date_col in df.columns:
            df_print = df.copy()
            df_print['_dt'] = pd.to_datetime(df_print[date_col], errors='coerce')
            df_print = df_print[df_print['_dt'].notna()]
            df_print['월'] = df_print['_dt'].dt.to_period('M').astype(str)
            monthly_totals = df_print.groupby('월').agg({'입금액': 'sum', '출금액': 'sum'}).reset_index()
            monthly_totals = monthly_totals.sort_values('월')
            months_list = monthly_totals['월'].tolist()
            monthly_totals_list = monthly_totals.to_dict('records')
            max_monthly_withdraw = int(monthly_totals['출금액'].max()) if not monthly_totals.empty else 1
            max_monthly_both = int(max(monthly_totals['입금액'].max(), monthly_totals['출금액'].max())) if not monthly_totals.empty else 1
        else:
            months_list = []
            monthly_totals_list = []
            max_monthly_withdraw = 1
            max_monthly_both = 1

        return render_template('print_analysis.html',
                             report_date=datetime.now().strftime('%Y-%m-%d'),
                             bank_filter=bank_filter or '전체',
                             total_count=total_count,
                             deposit_count=deposit_count,
                             withdraw_count=withdraw_count,
                             total_deposit=total_deposit,
                             total_withdraw=total_withdraw,
                             net_balance=net_balance,
                             category_stats=category_stats.to_dict('records'),
                             transactions=transactions.to_dict('records'),
                             bank_stats=bank_stats.to_dict('records'),
                             account_stats=account_stats.to_dict('records'),
                             bank_col=bank_col,
                             account_col=account_col,
                             selected_category=selected_category,
                             max_deposit=max_deposit,
                             max_withdraw=max_withdraw,
                             max_account_deposit=max_account_deposit,
                             max_account_withdraw=max_account_withdraw,
                             total_account_deposit=total_account_deposit,
                             total_account_withdraw=total_account_withdraw,
                             total_account_deposit_10=total_account_deposit_10,
                             total_account_withdraw_10=total_account_withdraw_10,
                             transaction_total_count=transaction_total_count,
                             transaction_deposit_total=transaction_deposit_total,
                             transaction_withdraw_total=transaction_withdraw_total,
                             months_list=months_list,
                             monthly_totals_list=monthly_totals_list,
                             max_monthly_withdraw=max_monthly_withdraw,
                             max_monthly_both=max_monthly_both)
    except Exception as e:
        traceback.print_exc()
        return f"오류 발생: {str(e)}", 500

# 분석 API 라우트
@app.route('/api/analysis/summary')
@ensure_working_directory
def get_analysis_summary():
    """전체 통계 요약 (bank_after.xlsx 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({
                'total_deposit': 0,
                'total_withdraw': 0,
                'net_balance': 0,
                'total_count': 0,
                'deposit_count': 0,
                'withdraw_count': 0
            })
        
        # 은행 필터
        bank_filter = request.args.get('bank', '')
        if bank_filter:
            df = df[df['은행명'] == bank_filter]
        
        total_deposit = df['입금액'].sum()
        total_withdraw = df['출금액'].sum()
        net_balance = total_deposit - total_withdraw
        total_count = len(df)
        deposit_count = len(df[df['입금액'] > 0])
        withdraw_count = len(df[df['출금액'] > 0])
        
        response = jsonify({
            'total_deposit': int(total_deposit),
            'total_withdraw': int(total_withdraw),
            'net_balance': int(net_balance),
            'total_count': total_count,
            'deposit_count': deposit_count,
            'withdraw_count': withdraw_count
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/by-category')
@ensure_working_directory
def get_analysis_by_category():
    """카테고리별 분석 (bank_after 기준)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'data': []})
        
        # 은행 필터: 은행전체일 경우 전체 집계, 특정 은행 선택 시 해당 은행 집계
        bank_filter = request.args.get('bank', '')
        if bank_filter:
            df = df[df['은행명'] == bank_filter]
        
        # 카테고리분류를 입출금으로 매핑
        if '카테고리분류' in df.columns and '입출금' not in df.columns:
            df['입출금'] = df['카테고리분류']
        
        # 카테고리 필터 (여러 필터 지원)
        classification_filter = request.args.get('입출금', '')
        transaction_type_filter = request.args.get('거래유형', '')
        category_filter = request.args.get('카테고리', '')
        
        # 기존 방식 지원 (하위 호환성)
        category_type = request.args.get('category_type', '')
        category_value = request.args.get('category_value', '')
        if category_type and category_value:
            if category_type in df.columns:
                df = df[df[category_type] == category_value]
        
        # 새로운 방식 (여러 필터 동시 적용)
        if classification_filter and '입출금' in df.columns:
            df = df[df['입출금'] == classification_filter]
        if transaction_type_filter and '거래유형' in df.columns:
            df = df[df['거래유형'] == transaction_type_filter]
        if category_filter and '카테고리' in df.columns:
            df = df[df['카테고리'] == category_filter]
        
        # 카테고리별 입금/출금 집계 (입출금, 거래유형 등 대표값 포함)
        group_col = '카테고리' if '카테고리' in df.columns else '적요'
        if group_col not in df.columns:
            df[group_col] = '(빈값)'
        df[group_col] = df[group_col].fillna('').astype(str).str.strip().replace('', '(빈값)')
        agg_dict = {
            '입금액': 'sum',
            '출금액': 'sum'
        }
        # groupby 키와 같은 컬럼은 agg에 넣지 않음 (already exists 오류 방지)
        if '입출금' in df.columns and '입출금' != group_col:
            agg_dict['입출금'] = 'first'
        if '거래유형' in df.columns and '거래유형' != group_col:
            agg_dict['거래유형'] = 'first'
        if '카테고리' in df.columns and '카테고리' != group_col:
            agg_dict['카테고리'] = 'first'
        if '은행명' in df.columns and '은행명' != group_col:
            agg_dict['은행명'] = 'first'
        if '내용' in df.columns and '내용' != group_col:
            agg_dict['내용'] = 'first'
        if '거래점' in df.columns and '거래점' != group_col:
            agg_dict['거래점'] = 'first'
        category_stats = df.groupby(group_col).agg(agg_dict).reset_index()
        
        # 차액 계산
        category_stats['차액'] = category_stats['입금액'] - category_stats['출금액']
        
        # 정렬: 카테고리 올림차순
        category_stats = category_stats.sort_values(group_col, ascending=True)
        
        # 데이터 포맷팅
        data = []
        for _, row in category_stats.iterrows():
            cat_val = row[group_col] if pd.notna(row[group_col]) and str(row[group_col]).strip() != '' else '(빈값)'
            item = {
                'category': cat_val,
                'deposit': int(row['입금액']) if pd.notna(row['입금액']) else 0,
                'withdraw': int(row['출금액']) if pd.notna(row['출금액']) else 0,
                'balance': int(row['차액']) if pd.notna(row['차액']) else 0
            }
            # 입출금, 거래유형, 카테고리 정보 추가
            if '입출금' in row:
                item['classification'] = str(row['입출금']) if pd.notna(row['입출금']) and row['입출금'] != '' else '(빈값)'
            else:
                item['classification'] = '(빈값)'
            if '거래유형' in row:
                item['transactionType'] = str(row['거래유형']) if pd.notna(row['거래유형']) and row['거래유형'] != '' else '(빈값)'
            else:
                item['transactionType'] = '(빈값)'
            if '카테고리' in row:
                item['transactionTarget'] = str(row['카테고리']) if pd.notna(row['카테고리']) and row['카테고리'] != '' else '(빈값)'
            else:
                item['transactionTarget'] = '(빈값)'
            if '은행명' in row:
                item['bank'] = str(row['은행명']) if pd.notna(row['은행명']) and row['은행명'] != '' else '(빈값)'
            else:
                item['bank'] = '(빈값)'
            if '내용' in row:
                item['content'] = str(row['내용']) if pd.notna(row['내용']) and row['내용'] != '' else ''
            else:
                item['content'] = ''
            if '거래점' in row:
                item['transactionPoint'] = str(row['거래점']) if pd.notna(row['거래점']) and row['거래점'] != '' else ''
            else:
                item['transactionPoint'] = ''
            data.append(item)
        
        response = jsonify({'data': data})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/by-category-group')
@ensure_working_directory
def get_analysis_by_category_group():
    """카테고리 기준 분석 (입출금/거래유형/카테고리 기준 집계)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'data': []})
        
        # 카테고리분류를 입출금으로 매핑
        if '카테고리분류' in df.columns and '입출금' not in df.columns:
            df['입출금'] = df['카테고리분류']
        
        # 은행 필터
        bank_filter = request.args.get('bank', '')
        if bank_filter:
            df = df[df['은행명'] == bank_filter]
        
        # 카테고리 필터 (입출금/거래유형/카테고리)
        입출금_filter = request.args.get('입출금', '')
        거래유형_filter = request.args.get('거래유형', '')
        category_filter = request.args.get('카테고리', '')
        
        if 입출금_filter and '입출금' in df.columns:
            df = df[df['입출금'] == 입출금_filter]
        if 거래유형_filter and '거래유형' in df.columns:
            df = df[df['거래유형'] == 거래유형_filter]
        if category_filter and '카테고리' in df.columns:
            df = df[df['카테고리'] == category_filter]
        
        # 입출금/거래유형/카테고리 기준으로 집계
        groupby_columns = []
        if '입출금' in df.columns:
            groupby_columns.append('입출금')
        if '거래유형' in df.columns:
            groupby_columns.append('거래유형')
        if '카테고리' in df.columns:
            groupby_columns.append('카테고리')
        
        if not groupby_columns:
            return jsonify({'data': []})
        
        # 집계 (은행명도 포함하여 집계)
        category_stats = df.groupby(groupby_columns + ['은행명']).agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        
        # 차액 계산
        category_stats['차액'] = category_stats['입금액'] - category_stats['출금액']
        category_stats['총거래액'] = category_stats['입금액'] + category_stats['출금액']
        
        # 카테고리 그룹별로 다시 집계 (은행명은 가장 많은 거래가 있는 은행명 사용)
        category_final = []
        for category_group, group_df in category_stats.groupby(groupby_columns):
            # 가장 많은 거래액이 있는 은행명 선택
            main_bank_row = group_df.loc[group_df['총거래액'].idxmax()]
            main_bank = main_bank_row['은행명']
            
            # 카테고리 그룹별 합계
            total_deposit = group_df['입금액'].sum()
            total_withdraw = group_df['출금액'].sum()
            total_balance = total_deposit - total_withdraw
            
            item = {
                'deposit': int(total_deposit) if pd.notna(total_deposit) else 0,
                'withdraw': int(total_withdraw) if pd.notna(total_withdraw) else 0,
                'balance': int(total_balance) if pd.notna(total_balance) else 0,
                '은행명': str(main_bank) if pd.notna(main_bank) and main_bank != '' else '(빈값)'
            }
            
            # 각 카테고리 컬럼 추가
            if isinstance(category_group, tuple):
                for i, col in enumerate(groupby_columns):
                    value = category_group[i] if i < len(category_group) else None
                    if pd.notna(value) and value != '':
                        item[col] = str(value)
                    else:
                        item[col] = '(빈값)'
            else:
                if '입출금' in groupby_columns:
                    item['입출금'] = str(category_group) if pd.notna(category_group) and category_group != '' else '(빈값)'
                elif '거래유형' in groupby_columns:
                    item['거래유형'] = str(category_group) if pd.notna(category_group) and category_group != '' else '(빈값)'
                elif '카테고리' in groupby_columns:
                    item['카테고리'] = str(category_group) if pd.notna(category_group) and category_group != '' else '(빈값)'
            
            category_final.append(item)
        
        # 정렬: 차액 절대값 큰 순, 절대값 같으면 차액 큰 순, 차액 같으면 입금액 많은 순
        category_final_df = pd.DataFrame(category_final)
        category_final_df['차액_절대값'] = category_final_df['balance'].abs()
        category_final_df = category_final_df.sort_values(['차액_절대값', 'balance', 'deposit'], ascending=[False, False, False])
        category_final_df = category_final_df.drop('차액_절대값', axis=1)
        
        # 데이터 포맷팅
        data = category_final_df.to_dict('records')
        
        response = jsonify({'data': data})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/by-month')
@ensure_working_directory
def get_analysis_by_month():
    """월별 추이 분석 (카테고리 파일 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'months': [], 'deposit': [], 'withdraw': [], 'min_date': None, 'max_date': None})
        
        # 전체 데이터의 최소/최대 날짜 계산 (필터 적용 전)
        df_all = df.copy()
        df_all['거래일'] = pd.to_datetime(df_all['거래일'], errors='coerce')
        df_all = df_all[df_all['거래일'].notna()]
        min_date = df_all['거래일'].min()
        max_date = df_all['거래일'].max()
        
        # 은행 필터
        bank_filter = request.args.get('bank', '')
        if bank_filter:
            df = df[df['은행명'] == bank_filter]
        
        # 카테고리분류를 입출금으로 매핑
        if '카테고리분류' in df.columns and '입출금' not in df.columns:
            df['입출금'] = df['카테고리분류']
        
        # 카테고리 필터 (여러 필터 지원)
        classification_filter = request.args.get('입출금', '')
        transaction_type_filter = request.args.get('거래유형', '')
        category_filter = request.args.get('카테고리', '')
        
        # 기존 방식 지원 (하위 호환성)
        category_type = request.args.get('category_type', '')
        category_value = request.args.get('category_value', '')
        if category_type and category_value:
            if category_type in df.columns:
                df = df[df[category_type] == category_value]
        
        # 새로운 방식 (여러 필터 동시 적용)
        if classification_filter and '입출금' in df.columns:
            df = df[df['입출금'] == classification_filter]
        if transaction_type_filter and '거래유형' in df.columns:
            df = df[df['거래유형'] == transaction_type_filter]
        if category_filter and '카테고리' in df.columns:
            df = df[df['카테고리'] == category_filter]
        
        df['거래일'] = pd.to_datetime(df['거래일'], errors='coerce')
        df = df[df['거래일'].notna()]
        df['거래월'] = df['거래일'].dt.to_period('M').astype(str)
        
        # 전체 기간의 모든 월 생성 (최소일부터 최대일까지)
        if pd.notna(min_date) and pd.notna(max_date):
            date_range = pd.period_range(start=min_date.to_period('M'), end=max_date.to_period('M'), freq='M')
            all_months = [str(period) for period in date_range]
        else:
            all_months = sorted(df['거래월'].unique().tolist())
        
        # 월별 집계
        monthly_stats = df.groupby('거래월').agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        
        # 모든 월에 대해 데이터 생성 (없는 월은 0)
        deposit_dict = dict(zip(monthly_stats['거래월'], monthly_stats['입금액']))
        withdraw_dict = dict(zip(monthly_stats['거래월'], monthly_stats['출금액']))
        
        deposit = [int(deposit_dict.get(month, 0)) if pd.notna(deposit_dict.get(month, 0)) else 0 for month in all_months]
        withdraw = [int(withdraw_dict.get(month, 0)) if pd.notna(withdraw_dict.get(month, 0)) else 0 for month in all_months]
        
        response = jsonify({
            'months': all_months,
            'deposit': deposit,
            'withdraw': withdraw,
            'min_date': str(min_date) if pd.notna(min_date) else None,
            'max_date': str(max_date) if pd.notna(max_date) else None
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/by-category-monthly')
@ensure_working_directory
def get_analysis_by_category_monthly():
    """카테고리별 월별 입출금 추이 분석"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'months': [], 'categories': []})
        
        # 카테고리분류를 입출금으로 매핑
        if '카테고리분류' in df.columns and '입출금' not in df.columns:
            df['입출금'] = df['카테고리분류']
        
        # 은행 필터
        bank_filter = request.args.get('bank', '')
        if bank_filter:
            df = df[df['은행명'] == bank_filter]
        
        # 카테고리 필터 (입출금/거래유형/카테고리)
        입출금_filter = request.args.get('입출금', '')
        거래유형_filter = request.args.get('거래유형', '')
        category_filter = request.args.get('카테고리', '')
        
        if 입출금_filter and '입출금' in df.columns:
            df = df[df['입출금'] == 입출금_filter]
        if 거래유형_filter and '거래유형' in df.columns:
            df = df[df['거래유형'] == 거래유형_filter]
        if category_filter and '카테고리' in df.columns:
            df = df[df['카테고리'] == category_filter]
        
        # 날짜 처리
        df['거래일'] = pd.to_datetime(df['거래일'], errors='coerce')
        df = df[df['거래일'].notna()]
        df['거래월'] = df['거래일'].dt.to_period('M').astype(str)
        
        # 카테고리 그룹 컬럼 구성
        groupby_columns = []
        if '입출금' in df.columns:
            groupby_columns.append('입출금')
        if '거래유형' in df.columns:
            groupby_columns.append('거래유형')
        if '카테고리' in df.columns:
            groupby_columns.append('카테고리')
        
        if not groupby_columns:
            return jsonify({'months': [], 'categories': []})
        
        # 카테고리별 월별 집계
        monthly_by_category = df.groupby(groupby_columns + ['거래월']).agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        
        # 모든 월 목록 추출
        all_months = sorted(df['거래월'].unique().tolist())
        
        # 카테고리별 데이터 구성
        categories_data = []
        for category_group, group_df in monthly_by_category.groupby(groupby_columns):
            # 카테고리 라벨 생성 (거래유형/카테고리만 포함)
            category_label_parts = []
            if isinstance(category_group, tuple):
                # 튜플인 경우 (여러 컬럼으로 그룹화된 경우)
                for i, col in enumerate(groupby_columns):
                    if col in ['거래유형', '카테고리']:
                        value = category_group[i] if i < len(category_group) else None
                        if pd.notna(value) and value != '':
                            category_label_parts.append(str(value))
            else:
                if pd.notna(category_group) and category_group != '':
                    category_label_parts.append(str(category_group))
            
            category_label = '_'.join(category_label_parts) if category_label_parts else '(빈값)'
            
            # 월별 데이터 매핑
            monthly_deposit = {}
            monthly_withdraw = {}
            for _, row in group_df.iterrows():
                month = row['거래월']
                monthly_deposit[month] = int(row['입금액']) if pd.notna(row['입금액']) else 0
                monthly_withdraw[month] = int(row['출금액']) if pd.notna(row['출금액']) else 0
            
            # 모든 월에 대해 데이터 생성 (없는 월은 0)
            deposit_data = [monthly_deposit.get(month, 0) for month in all_months]
            withdraw_data = [monthly_withdraw.get(month, 0) for month in all_months]
            
            # 총 입금액, 출금액, 차액 계산 (차액 절대값 기준 정렬용)
            total_deposit = sum(deposit_data)
            total_withdraw = sum(withdraw_data)
            total_balance = total_deposit - total_withdraw
            abs_balance = abs(total_balance)
            
            categories_data.append({
                'label': category_label,
                'deposit': deposit_data,
                'withdraw': withdraw_data,
                'total_deposit': total_deposit,
                'total_withdraw': total_withdraw,
                'total_balance': total_balance,
                'abs_balance': abs_balance
            })
        
        # 차액(절대값) 기준으로 정렬하고 상위 10개만 선택
        categories_data.sort(key=lambda x: x['abs_balance'], reverse=True)
        categories_data = categories_data[:10]
        
        response = jsonify({
            'months': all_months,
            'categories': categories_data
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e), 'months': [], 'categories': []}), 500

@app.route('/api/analysis/by-content')
@ensure_working_directory
def get_analysis_by_content():
    """내용별 분석 (bank_after.xlsx 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'deposit': [], 'withdraw': []})
        
        # 내용별 입금 (모든 거래처, 제한 없음)
        deposit_by_content = df.groupby('내용')['입금액'].sum().sort_values(ascending=False)
        deposit_data = [{'content': idx if idx else '(빈값)', 'amount': int(val)} for idx, val in deposit_by_content.items() if val > 0]
        
        # 내용별 출금 (모든 거래처, 제한 없음)
        withdraw_by_content = df.groupby('내용')['출금액'].sum().sort_values(ascending=False)
        withdraw_data = [{'content': idx if idx else '(빈값)', 'amount': int(val)} for idx, val in withdraw_by_content.items() if val > 0]
        
        response = jsonify({
            'deposit': deposit_data,
            'withdraw': withdraw_data
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/by-division')
@ensure_working_directory
def get_analysis_by_division():
    """취소별 분석 (bank_after.xlsx 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'data': []})
        
        division_stats = df.groupby('취소').agg({
            '입금액': 'sum',
            '출금액': 'sum',
            '거래일': 'count'
        }).reset_index()
        division_stats.columns = ['division', 'deposit', 'withdraw', 'count']
        division_stats = division_stats.fillna('')
        division_stats['deposit'] = division_stats['deposit'].astype(int)
        division_stats['withdraw'] = division_stats['withdraw'].astype(int)
        
        data = division_stats.to_dict('records')
        response = jsonify({'data': data})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/by-bank')
@ensure_working_directory
def get_analysis_by_bank():
    """계좌별 분석 (카테고리 파일 사용). bank 필터 시 해당 은행 계좌만 반환."""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'bank': [], 'account': []})
        bank_filter = request.args.get('bank', '').strip()
        if bank_filter and '은행명' in df.columns:
            df = df[df['은행명'].astype(str).str.strip() == bank_filter]
        if '계좌번호' not in df.columns:
            df['계좌번호'] = ''
        # 은행별 통계 (필터 드롭다운용) + 건수
        bank_stats = df.groupby('은행명').agg({'입금액': 'sum', '출금액': 'sum'}).reset_index()
        bank_counts = df.groupby('은행명').size().reset_index(name='count')
        bank_stats = bank_stats.merge(bank_counts, on='은행명')
        bank_data = [{'bank': row['은행명'], 'count': int(row['count']), 'deposit': int(row['입금액']), 'withdraw': int(row['출금액'])} for _, row in bank_stats.iterrows()]
        # 계좌별 통계 (테이블·비율·집계 차트용) + 건수
        account_stats = df.groupby(['은행명', '계좌번호']).agg({'입금액': 'sum', '출금액': 'sum'}).reset_index()
        account_counts = df.groupby(['은행명', '계좌번호']).size().reset_index(name='count')
        account_stats = account_stats.merge(account_counts, on=['은행명', '계좌번호'])
        account_data = [{
            'bank': row['은행명'] if pd.notna(row['은행명']) else '',
            'account': str(row['계좌번호']).strip() if pd.notna(row['계좌번호']) else '',
            'count': int(row['count']),
            'deposit': int(row['입금액']),
            'withdraw': int(row['출금액'])
        } for _, row in account_stats.iterrows()]
        response = jsonify({
            'bank': bank_data,
            'account': account_data
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/transactions-by-content')
@ensure_working_directory
def get_transactions_by_content():
    """거래처(내용)별 거래 내역 (bank_after.xlsx 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'deposit': [], 'withdraw': []})
        
        type_filter = request.args.get('type', 'deposit')  # 'deposit' or 'withdraw'
        limit = int(request.args.get('limit', 10))  # 상위 N개 거래처
        
        if type_filter == 'deposit':
            # 입금 상위 거래처
            top_contents = df[df['입금액'] > 0].groupby('내용')['입금액'].sum().sort_values(ascending=False).head(limit)
            top_content_list = top_contents.index.tolist()
            
            # 해당 거래처들의 모든 입금 거래 내역
            transactions = df[(df['내용'].isin(top_content_list)) & (df['입금액'] > 0)].copy()
            transactions = transactions.sort_values('입금액', ascending=False)
            
            transactions = transactions.where(pd.notna(transactions), None)
            data = transactions[['거래일', '은행명', '입금액', '취소', '적요', '내용', '거래점']].to_dict('records')
            data = _json_safe(data)
        else:
            top_contents = df[df['출금액'] > 0].groupby('내용')['출금액'].sum().sort_values(ascending=False).head(limit)
            top_content_list = top_contents.index.tolist()
            transactions = df[(df['내용'].isin(top_content_list)) & (df['출금액'] > 0)].copy()
            transactions = transactions.sort_values('출금액', ascending=False)
            transactions = transactions.where(pd.notna(transactions), None)
            data = transactions[['거래일', '은행명', '출금액', '취소', '적요', '내용', '거래점']].to_dict('records')
            data = _json_safe(data)
        response = jsonify({'data': data})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/transactions')
@ensure_working_directory
def get_analysis_transactions():
    """카테고리별 상세 거래 내역 반환 (bank_after 기준)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'data': [], 'deposit_total': 0, 'withdraw_total': 0, 'balance': 0, 'deposit_count': 0, 'withdraw_count': 0})
        
        transaction_type = request.args.get('type', 'deposit')
        category_filter = request.args.get('category', '')  # 카테고리 필터
        content_filter = request.args.get('content', '')   # 거래처 필터 (하위 호환성)
        bank_filter = request.args.get('bank', '')
        
        # 카테고리 필터 우선, 없으면 거래처 필터 사용 (하위 호환성)
        if category_filter:
            filter_col = '카테고리' if '카테고리' in df.columns else '적요'
            filtered_df = df[df[filter_col].fillna('').astype(str).str.strip() == category_filter].copy()
        elif content_filter:
            filtered_df = df[df['내용'] == content_filter].copy()
        else:
            return jsonify({'data': [], 'deposit_total': 0, 'withdraw_total': 0, 'balance': 0, 'deposit_count': 0, 'withdraw_count': 0})
        
        # 은행 필터: 은행전체일 경우 전체 집계, 특정 은행 선택 시 해당 은행 집계
        if bank_filter:
            filtered_df = filtered_df[filtered_df['은행명'] == bank_filter].copy()
        
        # 카테고리 필터
        category_type = request.args.get('category_type', '')
        category_value = request.args.get('category_value', '')
        if category_type and category_value:
            if category_type in filtered_df.columns:
                filtered_df = filtered_df[filtered_df[category_type] == category_value].copy()
        
        # 카테고리별 입금/출금 합계 및 건수 계산
        deposit_total = filtered_df['입금액'].sum() if not filtered_df.empty else 0
        withdraw_total = filtered_df['출금액'].sum() if not filtered_df.empty else 0
        balance = deposit_total - withdraw_total
        deposit_count = len(filtered_df[filtered_df['입금액'] > 0]) if not filtered_df.empty else 0
        withdraw_count = len(filtered_df[filtered_df['출금액'] > 0]) if not filtered_df.empty else 0
        
        # 카테고리 거래내역 테이블: 내용 대신 기타거래 컬럼 사용 (기타거래 없으면 내용)
        extra_col = '기타거래' if '기타거래' in filtered_df.columns else '내용'
        
        if transaction_type == 'detail':
            # 상세 모드(기본분석 카테고리 거래내역): 전체 컬럼 반환 (행 클릭 시 말풍선에 전체 표시용)
            result_df = filtered_df.copy()
        elif transaction_type == 'deposit':
            filtered_df = filtered_df[filtered_df['입금액'] > 0]
            # 필요한 컬럼만 선택
            result_df = filtered_df[['거래일', '은행명', '입금액', '취소', '적요', extra_col, '거래점']].copy()
            result_df.rename(columns={'입금액': '금액'}, inplace=True)
        elif transaction_type == 'withdraw':
            filtered_df = filtered_df[filtered_df['출금액'] > 0]
            # 필요한 컬럼만 선택
            result_df = filtered_df[['거래일', '은행명', '출금액', '취소', '적요', extra_col, '거래점']].copy()
            result_df.rename(columns={'출금액': '금액'}, inplace=True)
        else: # balance - 차액 상위순일 때는 입금과 출금 모두 표시
            # 입금과 출금이 모두 있는 행만 필터링
            deposit_df = filtered_df[filtered_df['입금액'] > 0].copy()
            withdraw_df = filtered_df[filtered_df['출금액'] > 0].copy()
            
            # 입금 데이터
            deposit_result = deposit_df[['거래일', '은행명', '입금액', '취소', '적요', extra_col, '거래점']].copy()
            deposit_result.rename(columns={'입금액': '금액'}, inplace=True)
            deposit_result['거래유형'] = '입금'
            
            # 출금 데이터
            withdraw_result = withdraw_df[['거래일', '은행명', '출금액', '취소', '적요', extra_col, '거래점']].copy()
            withdraw_result.rename(columns={'출금액': '금액'}, inplace=True)
            withdraw_result['거래유형'] = '출금'
            
            # 두 데이터프레임 합치기
            result_df = pd.concat([deposit_result, withdraw_result], ignore_index=True)
        
        # 거래일 순으로 정렬
        result_df = result_df.sort_values('거래일')
        
        # 기타거래 컬럼: NaN/NaT를 빈 문자열로 통일해 JSON에서 null로 나가 빈 행으로 보이는 것 방지
        if extra_col in result_df.columns:
            result_df[extra_col] = result_df[extra_col].fillna('').astype(str).str.strip()
        result_df = result_df.where(pd.notna(result_df), None)
        # 기타거래만 다시 문자열 보장 (where가 None으로 바꾼 경우 대비)
        if extra_col in result_df.columns:
            result_df[extra_col] = result_df[extra_col].apply(lambda x: '' if x is None else str(x).strip())
        data = result_df.to_dict('records')
        data = _json_safe(data)
        response = jsonify({
            'data': data,
            'deposit_total': int(deposit_total),
            'withdraw_total': int(withdraw_total),
            'balance': int(balance),
            'deposit_count': int(deposit_count),
            'withdraw_count': int(withdraw_count)
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/content-by-category')
@ensure_working_directory
def get_content_by_category():
    """카테고리별 거래처 목록 반환 (bank_after.xlsx 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'data': []})
        
        category_filter = request.args.get('category', '')
        if not category_filter:
            return jsonify({'data': []})
        
        filter_col = '카테고리' if '카테고리' in df.columns else '적요'
        filtered_df = df[(df[filter_col].fillna('').astype(str).str.strip() == category_filter) & (df['입금액'] > 0)].copy()
        
        if filtered_df.empty:
            return jsonify({'data': []})
        
        # 거래처별 입금액 합계
        content_stats = filtered_df.groupby('내용')['입금액'].sum().sort_values(ascending=False).reset_index()
        
        data = []
        for _, row in content_stats.iterrows():
            data.append({
                'content': row['내용'] if pd.notna(row['내용']) and row['내용'] != '' else '(빈값)',
                'amount': int(row['입금액']) if pd.notna(row['입금액']) else 0
            })
        
        response = jsonify({'data': data})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/date-range')
@ensure_working_directory
def get_date_range():
    """bank_after.xlsx 데이터의 최소/최대 거래일 반환"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'min_date': None, 'max_date': None})
        
        # 거래일 컬럼 확인
        if '거래일' not in df.columns:
            return jsonify({'min_date': None, 'max_date': None})
        
        # 거래일을 날짜 형식으로 변환
        df['거래일'] = pd.to_datetime(df['거래일'], errors='coerce')
        df = df[df['거래일'].notna()]
        
        if df.empty:
            return jsonify({'min_date': None, 'max_date': None})
        
        min_date = df['거래일'].min()
        max_date = df['거래일'].max()
        
        response = jsonify({
            'min_date': min_date.strftime('%Y-%m-%d') if pd.notna(min_date) else None,
            'max_date': max_date.strftime('%Y-%m-%d') if pd.notna(max_date) else None
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e), 'min_date': None, 'max_date': None}), 500

def _json_500(obj):
    """500 응답도 JSON으로 통일 (Content-Type 설정)."""
    r = jsonify(obj)
    r.headers['Content-Type'] = 'application/json; charset=utf-8'
    return r, 500

@app.route('/api/generate-category', methods=['POST'])
@ensure_working_directory
def generate_category():
    """카테고리 자동 생성 실행. 항상 JSON 반환."""
    try:
        # process_bank_data.py 같은 프로세스에서 실행 (subprocess 시 debugpy/venv 오류 방지)
        script_path = Path(SCRIPT_DIR) / 'process_bank_data.py'
        if not script_path.exists():
            return _json_500({
                'success': False,
                'error': f'process_bank_data.py 파일을 찾을 수 없습니다. 경로: {script_path}'
            })
        
        _orig_cwd = os.getcwd()
        _path_added = False
        detail = None
        success = False
        try:
            os.chdir(SCRIPT_DIR)
            _dir_str = str(SCRIPT_DIR)
            if _dir_str not in sys.path:
                sys.path.insert(0, _dir_str)
                _path_added = True
            import process_bank_data as _pbd
            _pbd.ensure_bank_before_and_category()  # bank_before, category_table 준비 (생성 시에만 카테고리 분류)
            success = _pbd.classify_and_save()
            if not success:
                detail = getattr(_pbd, 'LAST_CLASSIFY_ERROR', None)
        except Exception as e:
            success = False
            detail = str(e)
            traceback.print_exc()
        finally:
            os.chdir(_orig_cwd)
            if _path_added and str(SCRIPT_DIR) in sys.path:
                sys.path.remove(str(SCRIPT_DIR))
        
        if not success:
            err_msg = '카테고리 분류 중 오류가 발생했습니다.'
            if detail:
                err_msg += '\n[원인] ' + detail
            return _json_500({'success': False, 'error': err_msg})
        
        # bank_after 파일 확인 (MyBank 아래)
        output_path = Path(BANK_AFTER_PATH)
        if output_path.exists():
            df = safe_read_data_json(output_path, default_empty=True) if safe_read_data_json else safe_read_excel(output_path, default_empty=True)
            count = len(df) if df is not None else 0
            resp = jsonify({
                'success': True,
                'message': f'카테고리 생성 완료: {count}건',
                'count': count
            })
            resp.headers['Content-Type'] = 'application/json; charset=utf-8'
            return resp
        return _json_500({
            'success': False,
            'error': f'bank_after 파일이 생성되지 않았습니다. 경로: {output_path}'
        })
    except FileNotFoundError as e:
        return _json_500({'success': False, 'error': f'파일을 찾을 수 없습니다: {str(e)}'})
    except Exception as e:
        error_trace = traceback.format_exc()
        return _json_500({
            'success': False,
            'error': f'{str(e)}\n상세 정보는 서버 로그를 확인하세요.'
        })

@app.route('/help')
def help():
    """은행거래 도움말 페이지"""
    return render_template('help.html')

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    # use_reloader=False: 프로젝트 루트에서 실행 시 리로더가 잘못된 경로로 재실행되어 실패하는 것 방지
    app.run(debug=True, port=5001, host='127.0.0.1', use_reloader=False)
