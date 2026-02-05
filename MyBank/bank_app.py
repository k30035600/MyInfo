# -*- coding: utf-8 -*-
from flask import Flask, render_template, jsonify, request, make_response, redirect
import traceback
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import io
import os
from functools import wraps
from datetime import datetime

# UTF-8 인코딩 설정 (Windows 콘솔용)
if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

app = Flask(__name__)

# JSON 인코딩 설정 (한글 지원)
app.json.ensure_ascii = False
app.config['JSON_AS_ASCII'] = False

# 스크립트 디렉토리 (모듈 로드 시 한 번만 계산)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# MyInfo/.source: before·after·category xlsx / Bank: 은행 source xls·xlsx
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, '..'))
SOURCE_DATA_DIR = os.path.join(PROJECT_ROOT, '.source')
SOURCE_BANK_DIR = os.path.join(PROJECT_ROOT, '.source', 'Bank')

# 전처리후 은행 필터: 드롭다운 값 → 실제 데이터에 있을 수 있는 은행명 별칭
# 적용 위치: get_processed_data()에서 load_processed_file()(bank_before.xlsx)로 읽은 DataFrame의 '은행명' 컬럼
BANK_FILTER_ALIASES = {
    '국민은행': ['국민은행', 'KB국민은행', '한국주택은행', '국민', '국민 은행'],
    '신한은행': ['신한은행', '신한'],
    '하나은행': ['하나은행', '하나'],
}

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

def load_processed_file():
    """전처리된 파일 로드 (MyInfo/.source/bank_before.xlsx)"""
    try:
        path = Path(SOURCE_DATA_DIR) / 'bank_before.xlsx'
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_excel(str(path), engine='openpyxl')
        return df
    except Exception as e:
        print(f"오류: bank_before.xlsx 파일 로드 실패 - {e}", flush=True)
        return pd.DataFrame()

def load_category_file():
    """카테고리 파일 로드 (MyInfo/.source/bank_after.xlsx)"""
    try:
        category_file = Path(SOURCE_DATA_DIR) / 'bank_after.xlsx'
        if category_file.exists():
            try:
                df = pd.read_excel(str(category_file), engine='openpyxl')
                return df
            except Exception as e:
                print(f"Error reading {category_file}: {str(e)}")
                return pd.DataFrame()
        return load_processed_file()
    except Exception as e:
        print(f"Error in load_category_file: {str(e)}")
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

@app.route('/api/processed-data')
@ensure_working_directory
def get_processed_data():
    """전처리된 데이터 반환 (필터링 지원). bank_before/category/after 없으면 생성."""
    try:
        # bank_before, bank_category, bank_after 없으면 생성
        _path_added = False
        try:
            _dir_str = str(SCRIPT_DIR)
            if _dir_str not in sys.path:
                sys.path.insert(0, _dir_str)
                _path_added = True
            import process_bank_data as _pbd
            _pbd.ensure_all_bank_files()
        except Exception as e:
            error_msg = str(e)
            hint = []
            if 'bank_after' in error_msg or 'PermissionError' in error_msg or '사용 중' in error_msg:
                hint.append('bank_after.xlsx를 열어둔 프로그램(Excel 등)을 닫아주세요.')
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

        output_path = Path(SOURCE_DATA_DIR) / 'bank_before.xlsx'
        if not output_path.exists():
            return jsonify({
                'error': 'bank_before.xlsx 생성 실패. .source/Bank 폴더와 process_bank_data.py를 확인하세요.',
                'count': 0,
                'deposit_amount': 0,
                'withdraw_amount': 0,
                'data': []
            }), 500

        df = load_processed_file()
        
        category_file_exists = (Path(SOURCE_DATA_DIR) / 'bank_after.xlsx').exists()
        
        if df.empty:
            source_dir = Path(SOURCE_BANK_DIR)
            source_files = []
            if source_dir.exists():
                source_files = list(source_dir.glob('*.xls')) + list(source_dir.glob('*.xlsx'))
            error_msg = '전처리된 데이터가 없습니다.'
            if output_path.exists() and output_path.stat().st_size > 0:
                error_msg += '\nbank_before.xlsx는 존재하지만 읽은 데이터가 비어있습니다.'
                error_msg += '\n파일이 Excel 등에서 열려 있으면 닫고, 내용·시트 구조를 확인해주세요.'
            elif not source_dir.exists():
                error_msg += '\n.source/Bank 폴더가 존재하지 않습니다.'
            elif len(source_files) == 0:
                error_msg += '\n.source/Bank 폴더에 .xls, .xlsx 파일이 없습니다.'
            else:
                error_msg += f'\n.source/Bank 폴더에 {len(source_files)}개의 .xls, .xlsx 파일이 있지만 데이터를 추출할 수 없었습니다.'
                error_msg += '\n파일 형식이나 내용을 확인해주세요.'
            
            response = jsonify({
                'error': error_msg,
                'count': 0,
                'deposit_amount': 0,
                'withdraw_amount': 0,
                'data': [],
                'file_exists': category_file_exists
            })
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response
        
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
        
        # 집계 계산
        count = len(df)
        deposit_amount = df['입금액'].sum() if not df.empty else 0
        withdraw_amount = df['출금액'].sum() if not df.empty else 0
        
        # NaN 값을 None으로 변환
        df = df.where(pd.notna(df), None)
        
        data = df.to_dict('records')
        data = _json_safe(data)
        response = jsonify({
            'count': count,
            'deposit_amount': int(deposit_amount),
            'withdraw_amount': int(withdraw_amount),
            'data': data,
            'file_exists': category_file_exists
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        category_file_exists = (Path(SOURCE_DATA_DIR) / 'bank_after.xlsx').exists()
        return jsonify({
            'error': str(e),
            'count': 0,
            'deposit_amount': 0,
            'withdraw_amount': 0,
            'data': [],
            'file_exists': category_file_exists
        }), 500

@app.route('/api/category-applied-data')
@ensure_working_directory
def get_category_applied_data():
    """카테고리 적용된 데이터 반환 (필터링 지원). bank_after 없으면 생성."""
    try:
        # bank_before, bank_category, bank_after 없으면 생성
        _path_added = False
        try:
            _dir_str = str(SCRIPT_DIR)
            if _dir_str not in sys.path:
                sys.path.insert(0, _dir_str)
                _path_added = True
            import process_bank_data as _pbd
            _pbd.ensure_all_bank_files()
        except Exception:
            pass  # ensure 실패 시 기존 파일로 진행
        finally:
            if _path_added and str(SCRIPT_DIR) in sys.path:
                sys.path.remove(str(SCRIPT_DIR))

        category_file_exists = (Path(SOURCE_DATA_DIR) / 'bank_after.xlsx').exists()
        
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
                'deposit_amount': 0,
                'withdraw_amount': 0,
                'data': [],
                'file_exists': category_file_exists  # 파일 존재 여부 추가
            })
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response
        
        # 필터 파라미터
        bank_filter = request.args.get('bank', '')
        date_filter = request.args.get('date', '')
        
        # 필터 적용
        if bank_filter and '은행명' in df.columns:
            df = df[df['은행명'] == bank_filter]
        
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
            # 누락된 컬럼 추가 (기본값 0)
            for col in missing_columns:
                df[col] = 0
        
        # 집계 계산
        count = len(df)
        deposit_amount = df['입금액'].sum() if not df.empty and '입금액' in df.columns else 0
        withdraw_amount = df['출금액'].sum() if not df.empty and '출금액' in df.columns else 0
        
        df = df.where(pd.notna(df), None)
        data = df.to_dict('records')
        data = _json_safe(data)
        response = jsonify({
            'count': count,
            'deposit_amount': int(deposit_amount),
            'withdraw_amount': int(withdraw_amount),
            'data': data,
            'file_exists': category_file_exists
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        category_file_exists = (Path(SOURCE_DATA_DIR) / 'bank_after.xlsx').exists()
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

# 은행거래 카테고리 테이블(bank_category.xlsx): 분류 = 전처리, 후처리, 거래방법, 거래지점
@app.route('/api/bank_category')
@ensure_working_directory
def get_category_table():
    """bank_category.xlsx 파일 데이터 반환 (MyInfo/.source). 없으면 생성 후 반환."""
    try:
        _path_added = False
        try:
            _dir_str = str(SCRIPT_DIR)
            if _dir_str not in sys.path:
                sys.path.insert(0, _dir_str)
                _path_added = True
            import process_bank_data as _pbd
            _pbd.ensure_all_bank_files()
        except Exception:
            pass
        finally:
            if _path_added and str(SCRIPT_DIR) in sys.path:
                sys.path.remove(str(SCRIPT_DIR))

        path = Path(SOURCE_DATA_DIR) / 'bank_category.xlsx'
        file_exists = path.exists()
        
        if not file_exists:
            df_empty = pd.DataFrame(columns=['분류', '키워드', '카테고리'])
            df_empty.to_excel(str(path), index=False, engine='openpyxl')
            file_exists = True
            df = df_empty
        else:
            df = pd.read_excel(str(path), engine='openpyxl')
        
        # NaN 값을 빈 문자열로 변환
        df = df.fillna('')
        
        # 파일 컬럼 순서: 분류, 키워드, 카테고리
        # 화면 표시 순서: 분류, 키워드, 카테고리
        # 존재하지 않는 컬럼 추가 (빈 값으로)
        for col in ['분류', '키워드', '카테고리']:
            if col not in df.columns:
                df[col] = ''
        
        # 데이터를 딕셔너리 리스트로 변환
        data = df.to_dict('records')
        
        response = jsonify({
            'data': data,
            'columns': ['분류', '키워드', '카테고리'],  # 화면 표시 순서
            'count': len(df),
            'file_exists': True
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        file_exists = (Path(SOURCE_DATA_DIR) / 'bank_category.xlsx').exists()
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
    """bank_category.xlsx 파일에 데이터 추가/삭제 (MyInfo/.source)"""
    try:
        path = Path(SOURCE_DATA_DIR) / 'bank_category.xlsx'
        data = request.json
        action = data.get('action', 'add')  # 'add' or 'delete'
        
        # 기존 파일 읽기
        if path.exists():
            df = pd.read_excel(str(path), engine='openpyxl')
        else:
            df = pd.DataFrame(columns=['분류', '키워드', '카테고리'])
        
        df = df.fillna('')
        
        # 파일 저장용 컬럼 순서: 분류, 키워드, 카테고리
        file_columns = ['분류', '키워드', '카테고리']
        # 존재하지 않는 컬럼 추가 (빈 값으로)
        for col in file_columns:
            if col not in df.columns:
                df[col] = ''
        # 컬럼 순서 재정렬 (파일 저장 순서)
        df = df[file_columns]
        
        if action == 'add':
            # 데이터 추가
            new_row = {
                '분류': data.get('분류', ''),
                '키워드': data.get('키워드', ''),
                '카테고리': data.get('카테고리', '')
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        elif action == 'update':
            # 데이터 수정 (원본 데이터를 찾아서 수정)
            original_분류 = data.get('original_분류', '')
            original_keyword = data.get('original_키워드', '')
            original_category = data.get('original_카테고리', '')
            
            new_분류 = data.get('분류', '')
            new_keyword = data.get('키워드', '')
            new_category = data.get('카테고리', '')
            
            # 원본 데이터 찾기
            mask = ((df['분류'] == original_분류) & 
                   (df['키워드'] == original_keyword) & 
                   (df['카테고리'] == original_category))
            
            if mask.any():
                # 해당 행 수정
                df.loc[mask, '분류'] = new_분류
                df.loc[mask, '키워드'] = new_keyword
                df.loc[mask, '카테고리'] = new_category
            else:
                return jsonify({
                    'success': False,
                    'error': '수정할 데이터를 찾을 수 없습니다.'
                }), 400
        elif action == 'delete':
            # 데이터 삭제 (분류, 키워드, 카테고리로 정확히 매칭)
            # 삭제 시 원본 데이터 사용 (입력 필드의 값이 아닌 선택된 행의 원본 값)
            분류값 = data.get('original_분류', data.get('분류', ''))
            keyword = data.get('original_키워드', data.get('키워드', ''))
            category = data.get('original_카테고리', data.get('카테고리', ''))
            df = df[~((df['분류'] == 분류값) & (df['키워드'] == keyword) & (df['카테고리'] == category))]
        
        # 파일 저장 (컬럼 순서: 분류, 키워드, 카테고리)
        df[file_columns].to_excel(str(path), index=False, engine='openpyxl')
        
        response = jsonify({
            'success': True,
            'message': f'카테고리 테이블이 업데이트되었습니다.',
            'count': len(df)
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
def print_analysis_redirect():
    """구 URL 호환: /analysis/print → /analysis/basic 리다이렉트"""
    return redirect('/bank/analysis/basic', code=302)

# 분석 API 라우트
@app.route('/api/analysis/summary')
@ensure_working_directory
def get_analysis_summary():
    """전체 통계 요약"""
    try:
        df = load_processed_file()
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
    """적요별 분석 (카테고리 파일 사용)"""
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
        transaction_target_filter = request.args.get('거래방법', '')
        
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
        if transaction_target_filter and '거래방법' in df.columns:
            df = df[df['거래방법'] == transaction_target_filter]
        
        # 적요별 입금/출금 집계 (입출금, 거래유형, 거래방법 정보도 포함)
        agg_dict = {
            '입금액': 'sum',
            '출금액': 'sum'
        }
        
        # 입출금, 거래유형, 거래방법, 은행명, 내용, 거래점이 있으면 첫 번째 값 사용 (대표값)
        if '입출금' in df.columns:
            agg_dict['입출금'] = 'first'
        if '거래유형' in df.columns:
            agg_dict['거래유형'] = 'first'
        if '거래방법' in df.columns:
            agg_dict['거래방법'] = 'first'
        if '은행명' in df.columns:
            agg_dict['은행명'] = 'first'
        if '내용' in df.columns:
            agg_dict['내용'] = 'first'
        if '거래점' in df.columns:
            agg_dict['거래점'] = 'first'
        
        category_stats = df.groupby('적요').agg(agg_dict).reset_index()
        
        # 차액 계산
        category_stats['차액'] = category_stats['입금액'] - category_stats['출금액']
        
        # 정렬: 차액 절대값 큰 순, 절대값 같으면 차액 큰 순, 차액 같으면 입금액 많은 순
        category_stats['차액_절대값'] = category_stats['차액'].abs()
        category_stats = category_stats.sort_values(['차액_절대값', '차액', '입금액'], ascending=[False, False, False])
        category_stats = category_stats.drop('차액_절대값', axis=1)
        
        # 데이터 포맷팅
        data = []
        for _, row in category_stats.iterrows():
            item = {
                'category': row['적요'] if pd.notna(row['적요']) and row['적요'] != '' else '(빈값)',
                'deposit': int(row['입금액']) if pd.notna(row['입금액']) else 0,
                'withdraw': int(row['출금액']) if pd.notna(row['출금액']) else 0,
                'balance': int(row['차액']) if pd.notna(row['차액']) else 0
            }
            # 입출금, 거래유형, 거래방법 정보 추가
            if '입출금' in row:
                item['classification'] = str(row['입출금']) if pd.notna(row['입출금']) and row['입출금'] != '' else '(빈값)'
            else:
                item['classification'] = '(빈값)'
            if '거래유형' in row:
                item['transactionType'] = str(row['거래유형']) if pd.notna(row['거래유형']) and row['거래유형'] != '' else '(빈값)'
            else:
                item['transactionType'] = '(빈값)'
            if '거래방법' in row:
                item['transactionTarget'] = str(row['거래방법']) if pd.notna(row['거래방법']) and row['거래방법'] != '' else '(빈값)'
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
    """카테고리 기준 분석 (입출금/거래유형/거래방법/거래지점 기준 집계)"""
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
        
        # 카테고리 필터 (입출금/거래유형/거래방법/거래지점)
        입출금_filter = request.args.get('입출금', '')
        거래유형_filter = request.args.get('거래유형', '')
        거래방법_filter = request.args.get('거래방법', '')
        거래지점_filter = request.args.get('거래지점', '')
        
        if 입출금_filter and '입출금' in df.columns:
            df = df[df['입출금'] == 입출금_filter]
        if 거래유형_filter and '거래유형' in df.columns:
            df = df[df['거래유형'] == 거래유형_filter]
        if 거래방법_filter and '거래방법' in df.columns:
            df = df[df['거래방법'] == 거래방법_filter]
        if 거래지점_filter and '거래지점' in df.columns:
            df = df[df['거래지점'] == 거래지점_filter]
        
        # 입출금/거래유형/거래방법/거래지점 기준으로 집계
        groupby_columns = []
        if '입출금' in df.columns:
            groupby_columns.append('입출금')
        if '거래유형' in df.columns:
            groupby_columns.append('거래유형')
        if '거래방법' in df.columns:
            groupby_columns.append('거래방법')
        if '거래지점' in df.columns:
            groupby_columns.append('거래지점')
        
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
                elif '거래방법' in groupby_columns:
                    item['거래방법'] = str(category_group) if pd.notna(category_group) and category_group != '' else '(빈값)'
                elif '거래지점' in groupby_columns:
                    item['거래지점'] = str(category_group) if pd.notna(category_group) and category_group != '' else '(빈값)'
            
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
        transaction_target_filter = request.args.get('거래방법', '')
        
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
        if transaction_target_filter and '거래방법' in df.columns:
            df = df[df['거래방법'] == transaction_target_filter]
        
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
        
        # 카테고리 필터 (입출금/거래유형/거래방법/거래지점)
        입출금_filter = request.args.get('입출금', '')
        거래유형_filter = request.args.get('거래유형', '')
        거래방법_filter = request.args.get('거래방법', '')
        거래지점_filter = request.args.get('거래지점', '')
        
        if 입출금_filter and '입출금' in df.columns:
            df = df[df['입출금'] == 입출금_filter]
        if 거래유형_filter and '거래유형' in df.columns:
            df = df[df['거래유형'] == 거래유형_filter]
        if 거래방법_filter and '거래방법' in df.columns:
            df = df[df['거래방법'] == 거래방법_filter]
        if 거래지점_filter and '거래지점' in df.columns:
            df = df[df['거래지점'] == 거래지점_filter]
        
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
        if '거래방법' in df.columns:
            groupby_columns.append('거래방법')
        if '거래지점' in df.columns:
            groupby_columns.append('거래지점')
        
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
            # 카테고리 라벨 생성 (거래유형_거래방법_거래지점만 포함)
            category_label_parts = []
            if isinstance(category_group, tuple):
                # 튜플인 경우 (여러 컬럼으로 그룹화된 경우)
                for i, col in enumerate(groupby_columns):
                    # 입출금은 제외하고 거래유형, 거래방법, 거래지점만 포함
                    if col in ['거래유형', '거래방법', '거래지점']:
                        value = category_group[i] if i < len(category_group) else None
                        if pd.notna(value) and value != '':
                            category_label_parts.append(str(value))
            else:
                # 단일 값인 경우 (거래유형/거래방법/거래지점 중 하나)
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
    """내용별 분석"""
    try:
        df = load_processed_file()
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
    """구분별 분석"""
    try:
        df = load_processed_file()
        if df.empty:
            return jsonify({'data': []})
        
        division_stats = df.groupby('구분').agg({
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
    """은행/계좌별 분석 (카테고리 파일 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'bank': [], 'account': []})
        
        # 은행별 통계
        bank_stats = df.groupby('은행명').agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        bank_data = [{
            'bank': row['은행명'],
            'deposit': int(row['입금액']),
            'withdraw': int(row['출금액'])
        } for _, row in bank_stats.iterrows()]
        
        # 계좌별 통계
        account_stats = df.groupby(['은행명', '계좌번호']).agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        account_data = [{
            'bank': row['은행명'],
            'account': row['계좌번호'],
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
    """거래처(내용)별 거래 내역"""
    try:
        df = load_processed_file()
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
            data = transactions[['거래일', '은행명', '입금액', '구분', '적요', '내용', '거래점']].to_dict('records')
            data = _json_safe(data)
        else:
            top_contents = df[df['출금액'] > 0].groupby('내용')['출금액'].sum().sort_values(ascending=False).head(limit)
            top_content_list = top_contents.index.tolist()
            transactions = df[(df['내용'].isin(top_content_list)) & (df['출금액'] > 0)].copy()
            transactions = transactions.sort_values('출금액', ascending=False)
            transactions = transactions.where(pd.notna(transactions), None)
            data = transactions[['거래일', '은행명', '출금액', '구분', '적요', '내용', '거래점']].to_dict('records')
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
    """적요별 상세 거래 내역 반환 (카테고리 파일 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'data': [], 'deposit_total': 0, 'withdraw_total': 0, 'balance': 0, 'deposit_count': 0, 'withdraw_count': 0})
        
        transaction_type = request.args.get('type', 'deposit') # 'deposit' or 'withdraw'
        category_filter = request.args.get('category', '')  # 적요 필터
        content_filter = request.args.get('content', '')  # 거래처 필터 (하위 호환성)
        bank_filter = request.args.get('bank', '')
        
        # 적요 필터 우선, 없으면 거래처 필터 사용 (하위 호환성)
        if category_filter:
            filtered_df = df[df['적요'] == category_filter].copy()
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
        
        # 적요별 입금/출금 합계 및 건수 계산
        deposit_total = filtered_df['입금액'].sum() if not filtered_df.empty else 0
        withdraw_total = filtered_df['출금액'].sum() if not filtered_df.empty else 0
        balance = deposit_total - withdraw_total
        deposit_count = len(filtered_df[filtered_df['입금액'] > 0]) if not filtered_df.empty else 0
        withdraw_count = len(filtered_df[filtered_df['출금액'] > 0]) if not filtered_df.empty else 0
        
        if transaction_type == 'detail':
            # 상세 모드: 거래일, 은행명, 입금액, 출금액, 내용
            detail_cols = ['거래일', '은행명', '입금액', '출금액']
            if '내용' in filtered_df.columns:
                detail_cols.append('내용')
            available_cols = [c for c in detail_cols if c in filtered_df.columns]
            result_df = filtered_df[available_cols].copy() if available_cols else filtered_df.copy()
        elif transaction_type == 'deposit':
            filtered_df = filtered_df[filtered_df['입금액'] > 0]
            # 필요한 컬럼만 선택
            result_df = filtered_df[['거래일', '은행명', '입금액', '구분', '적요', '내용', '거래점']].copy()
            result_df.rename(columns={'입금액': '금액'}, inplace=True)
        elif transaction_type == 'withdraw':
            filtered_df = filtered_df[filtered_df['출금액'] > 0]
            # 필요한 컬럼만 선택
            result_df = filtered_df[['거래일', '은행명', '출금액', '구분', '적요', '내용', '거래점']].copy()
            result_df.rename(columns={'출금액': '금액'}, inplace=True)
        else: # balance - 차액 상위순일 때는 입금과 출금 모두 표시
            # 입금과 출금이 모두 있는 행만 필터링
            deposit_df = filtered_df[filtered_df['입금액'] > 0].copy()
            withdraw_df = filtered_df[filtered_df['출금액'] > 0].copy()
            
            # 입금 데이터
            deposit_result = deposit_df[['거래일', '은행명', '입금액', '구분', '적요', '내용', '거래점']].copy()
            deposit_result.rename(columns={'입금액': '금액'}, inplace=True)
            deposit_result['거래유형'] = '입금'
            
            # 출금 데이터
            withdraw_result = withdraw_df[['거래일', '은행명', '출금액', '구분', '적요', '내용', '거래점']].copy()
            withdraw_result.rename(columns={'출금액': '금액'}, inplace=True)
            withdraw_result['거래유형'] = '출금'
            
            # 두 데이터프레임 합치기
            result_df = pd.concat([deposit_result, withdraw_result], ignore_index=True)
        
        # 거래일 순으로 정렬
        result_df = result_df.sort_values('거래일')
        
        result_df = result_df.where(pd.notna(result_df), None)
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
    """적요별 거래처 목록 반환"""
    try:
        df = load_processed_file()
        if df.empty:
            return jsonify({'data': []})
        
        category_filter = request.args.get('category', '')
        
        if not category_filter:
            return jsonify({'data': []})
        
        # 적요별 입금 거래처 집계
        filtered_df = df[(df['적요'] == category_filter) & (df['입금액'] > 0)].copy()
        
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
    """전처리후 데이터의 최소/최대 거래일 반환"""
    try:
        df = load_processed_file()
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

@app.route('/api/generate-category', methods=['POST'])
@ensure_working_directory
def generate_category():
    """카테고리 자동 생성 실행"""
    try:
        # process_bank_data.py 같은 프로세스에서 실행 (subprocess 시 debugpy/venv 오류 방지)
        script_path = Path(SCRIPT_DIR) / 'process_bank_data.py'
        if not script_path.exists():
            return jsonify({
                'success': False,
                'error': f'process_bank_data.py 파일을 찾을 수 없습니다. 경로: {script_path}'
            }), 500
        
        print("process_bank_data.py (classify) 실행 시작...")
        _orig_cwd = os.getcwd()
        _path_added = False
        try:
            os.chdir(SCRIPT_DIR)
            _dir_str = str(SCRIPT_DIR)
            if _dir_str not in sys.path:
                sys.path.insert(0, _dir_str)
                _path_added = True
            import process_bank_data as _pbd
            success = _pbd.classify_and_save()
        finally:
            os.chdir(_orig_cwd)
            if _path_added and str(SCRIPT_DIR) in sys.path:
                sys.path.remove(str(SCRIPT_DIR))
        
        if not success:
            return jsonify({
                'success': False,
                'error': '카테고리 분류 중 오류가 발생했습니다.'
            }), 500
        
        # bank_after.xlsx 파일 확인 (MyInfo/.source)
        output_path = Path(SOURCE_DATA_DIR) / 'bank_after.xlsx'
        if output_path.exists():
            try:
                df = pd.read_excel(str(output_path), engine='openpyxl')
                return jsonify({
                    'success': True,
                    'message': f'카테고리 생성 완료: {len(df)}건',
                    'count': len(df)
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'bank_after.xlsx 파일을 읽을 수 없습니다: {str(e)}'
                }), 500
        else:
            return jsonify({
                'success': False,
                'error': f'bank_after.xlsx 파일이 생성되지 않았습니다. 경로: {output_path}'
            }), 500
            
    except FileNotFoundError as e:
        return jsonify({
            'success': False,
            'error': f'파일을 찾을 수 없습니다: {str(e)}'
        }), 500
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"카테고리 생성 오류: {error_trace}")
        return jsonify({
            'success': False,
            'error': f'{str(e)}\n상세 정보는 서버 로그를 확인하세요.'
        }), 500

@app.route('/help')
def help():
    """은행거래 도움말 페이지"""
    return render_template('help.html')

if __name__ == '__main__':
    # 현재 디렉토리를 스크립트 위치로 변경
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    print("=" * 50)
    print("은행거래 통합정보(mybcbank) 서버를 시작합니다...")
    print("브라우저에서 http://localhost:5001 으로 접속하세요.")
    print("서버를 중지하려면 Ctrl+C를 누르세요.")
    print("=" * 50)
    app.run(debug=True, port=5001, host='127.0.0.1')
