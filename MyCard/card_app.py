# -*- coding: utf-8 -*-
from flask import Flask, render_template, jsonify, request
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

# 스크립트 디렉토리 = MyCard 폴더
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, '..'))
# category: MyInfo/info_category.xlsx 하나만 사용
INFO_CATEGORY_PATH = str(Path(PROJECT_ROOT) / 'info_category.xlsx')
# 원본 카드 파일: .source/Card. before/after: MyCard 폴더
SOURCE_CARD_DIR = os.path.join(PROJECT_ROOT, '.source', 'Card')
CARD_BEFORE_PATH = os.path.join(SCRIPT_DIR, 'card_before.xlsx')
CARD_AFTER_PATH = os.path.join(SCRIPT_DIR, 'card_after.xlsx')

def _load_process_card_data_module():
    """MyCard 내 process_card_data.py를 명시적으로 로드 (같은 프로세스·같은 환경 사용)"""
    import importlib.util
    module_path = os.path.join(SCRIPT_DIR, 'process_card_data.py')
    if not os.path.isfile(module_path):
        raise FileNotFoundError(f'process_card_data.py를 찾을 수 없습니다: {module_path}')
    spec = importlib.util.spec_from_file_location('process_card_data', module_path)
    mod = importlib.util.module_from_spec(spec)
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    spec.loader.exec_module(mod)
    return mod


def _ensure_card_category_file():
    """info_category.xlsx가 없으면 기본 규칙으로 생성 (구분 없음)."""
    path = Path(INFO_CATEGORY_PATH)
    if path.exists():
        return
    try:
        mod = _load_process_card_data_module()
        mod.create_category_table(None, category_filepath=INFO_CATEGORY_PATH)
    except Exception as e:
        print(f"[card_app] info_category.xlsx 생성 실패: {e}")


def _call_integrate_card():
    """card_before.xlsx 생성 (MyCard 폴더). info_category 있으면 카테고리 적용 후 저장."""
    mod = _load_process_card_data_module()
    card_before_path = Path(CARD_BEFORE_PATH)
    df = mod.integrate_card_excel(skip_write=True)
    # 가맹점명 비어있으면 카드사로 채움 (카드사·카드번호·이용일·이용금액 있는 행)
    if df is not None and not df.empty and all(c in df.columns for c in ['카드사', '카드번호', '이용일', '이용금액', '가맹점명']):
        has_card = (
            df['카드사'].notna() & (df['카드사'].astype(str).str.strip() != '') &
            df['카드번호'].notna() & (df['카드번호'].astype(str).str.strip() != '') &
            df['이용일'].notna() & (df['이용일'].astype(str).str.strip() != '') &
            df['이용금액'].notna() &
            (df['가맹점명'].fillna('').astype(str).str.strip() == '')
        )
        df.loc[has_card, '가맹점명'] = df.loc[has_card, '카드사']
    if df is not None and not df.empty:
        _apply_카드사_사업자번호_기본값(df)
    # 이용금액 마이너스 → 카테고리 현금처리 (우선 적용, 기타 카테고리 적용 무시)
    if df is not None and not df.empty:
        if '카테고리' not in df.columns:
            df['카테고리'] = ''
        _apply_이용금액_마이너스_현금처리(df)
    # info_category.xlsx가 있을 때만 카테고리 적용 (구분 없음)
    if df is not None and not df.empty and '가맹점명' in df.columns and Path(INFO_CATEGORY_PATH).exists():
        try:
            full = pd.read_excel(INFO_CATEGORY_PATH, engine='openpyxl').fillna('')
            if '구분' in full.columns:
                full = full.drop(columns=['구분'], errors='ignore')
            category_df = full[['분류', '키워드', '카테고리']].copy() if all(c in full.columns for c in ['분류', '키워드', '카테고리']) else full
            if not category_df.empty:
                df = mod.apply_category_from_merchant(df, category_df)
        except Exception:
            pass
    if df is not None:
        # 현금처리: 이용금액>0일 때만 * -1 (입금으로 저장)
        _apply_현금처리_이용금액_negate(df)
        # 할부: '일시불'/0 → 공백 (card_before.xlsx 저장 전 정규화)
        if not df.empty and '할부' in df.columns:
            df['할부'] = df['할부'].apply(
                lambda v: '' if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ('', '0', '일시불') else v
            )
        try:
            mod.safe_write_excel(df, str(card_before_path))
        except Exception as e:
            print(f"card_before.xlsx 저장 실패: {e}")

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

def _apply_카드사_사업자번호_기본값(df):
    """신한카드/하나카드 이면서 사업자번호 없으면 기본값 저장 (card_before, card_after)."""
    if df.empty or '카드사' not in df.columns or '사업자번호' not in df.columns:
        return
    empty_biz = (df['사업자번호'].fillna('').astype(str).str.strip() == '')
    shinhan = df['카드사'].fillna('').astype(str).str.strip().str.contains('신한', case=False, na=False)
    hana = df['카드사'].fillna('').astype(str).str.strip().str.contains('하나', case=False, na=False)
    if (empty_biz & shinhan).any():
        df.loc[empty_biz & shinhan, '사업자번호'] = '202-81-48079'
    if (empty_biz & hana).any():
        df.loc[empty_biz & hana, '사업자번호'] = '104-86-56659'


def _apply_이용금액_마이너스_현금처리(df):
    """이용금액이 마이너스인 행의 카테고리를 현금처리로 설정 (card_before, card_after 저장 전 적용)."""
    if df.empty or '이용금액' not in df.columns or '카테고리' not in df.columns:
        return
    amt = pd.to_numeric(df['이용금액'], errors='coerce')
    minus_mask = amt < 0
    if minus_mask.any():
        df.loc[minus_mask, '카테고리'] = '현금처리'


def _apply_현금처리_이용금액_negate(df):
    """현금처리 행: 이용금액>0일 때만 -1을 곱하여 입금으로 저장 (이미 음수면 그대로).
    card_before, card_after 저장 전 적용."""
    if df.empty or '이용금액' not in df.columns or '카테고리' not in df.columns:
        return
    현금처리 = df['카테고리'].fillna('').astype(str).str.strip() == '현금처리'
    amt = pd.to_numeric(df['이용금액'], errors='coerce')
    to_negate = 현금처리 & (amt > 0)  # 이용금액>0만 negate (음수=환급은 그대로)
    if to_negate.any():
        df.loc[to_negate, '이용금액'] = -df.loc[to_negate, '이용금액']


def _card_deposit_withdraw_from_이용금액(df):
    """신용카드: 이용금액 → 입금액/출금액. 현금처리는 항상 입금.
    이용금액이 있는 행만 변환 (은행 데이터는 기존 입금액/출금액 유지)."""
    if df.empty or '이용금액' not in df.columns:
        return
    amt = pd.to_numeric(df['이용금액'], errors='coerce')
    has_amt = amt.notna() & (amt != 0)
    if not has_amt.any():
        return
    cat = df['카테고리'].fillna('').astype(str).str.strip() if '카테고리' in df.columns else pd.Series([''] * len(df), index=df.index)
    # 현금처리: 항상 입금 (이용금액 절대값을 입금액에)
    현금처리 = (cat == '현금처리')
    입금 = ((amt < 0) | 현금처리) & has_amt
    출금 = ((amt > 0) & ~현금처리) & has_amt
    if '입금액' not in df.columns:
        df['입금액'] = 0
    if '출금액' not in df.columns:
        df['출금액'] = 0
    df.loc[입금, '입금액'] = amt[입금].abs()
    df.loc[출금, '출금액'] = amt[출금].abs()


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
    """MyInfo/.source/Card 의 원본 파일 목록 가져오기. .xls, .xlsx만 취급."""
    source_dir = Path(SOURCE_CARD_DIR)
    files = []
    if not source_dir.exists():
        current_dir = os.getcwd()
        print(f"[WARNING] .source/Card 폴더를 찾을 수 없습니다. 현재 작업 디렉토리: {current_dir}, .source/Card 경로: {source_dir}", flush=True)
        return []
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
    """전처리된 카드 파일 로드 (card_after.xlsx만 사용).
    이용금액 → 입금액/출금액 변환 적용."""
    try:
        if not Path(CARD_AFTER_PATH).exists():
            return pd.DataFrame()
        df = pd.read_excel(CARD_AFTER_PATH, engine='openpyxl')
        if not df.empty and '이용금액' in df.columns:
            _card_deposit_withdraw_from_이용금액(df)
        return df
    except Exception as e:
        print(f"오류: card_after.xlsx 로드 실패 - {e}", flush=True)
        return pd.DataFrame()


def load_card_before_file():
    """전처리전 카드 통합 파일 card_before.xlsx 로드 (MyCard 폴더)"""
    try:
        path = Path(CARD_BEFORE_PATH)
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_excel(str(path), engine='openpyxl')
        return df
    except Exception as e:
        print(f"오류: card_before.xlsx 파일 로드 실패 - {e}", flush=True)
        return pd.DataFrame()

def load_category_file():
    """카테고리 적용 파일 로드 (MyCard/card_after.xlsx).
    카드 데이터(이용금액 있음)는 입금액/출금액 추가 (현금처리→입금)."""
    try:
        if Path(CARD_AFTER_PATH).exists():
            try:
                df = pd.read_excel(CARD_AFTER_PATH, engine='openpyxl')
                if not df.empty and '이용금액' in df.columns:
                    _card_deposit_withdraw_from_이용금액(df)
                return df
            except Exception as e:
                print(f"Error reading {CARD_AFTER_PATH}: {str(e)}")
                return pd.DataFrame()
        return pd.DataFrame()
    except Exception as e:
        print(f"Error in load_category_file: {str(e)}")
        return pd.DataFrame()

@app.route('/')
def index():
    workspace_path = str(SCRIPT_DIR)
    return render_template('index.html', workspace_path=workspace_path, category_filename='info_category.xlsx')

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/api/source-files')
@ensure_working_directory
def get_source_files():
    """원본 파일 목록 반환. MyInfo/.source/Card 의 .xls, .xlsx만 취급."""
    try:
        current_dir = os.getcwd()
        source_dir = Path(SOURCE_CARD_DIR)
        if not source_dir.exists():
            return jsonify({
                'error': f'.source/Card 폴더를 찾을 수 없습니다.\n현재 작업 디렉토리: {current_dir}\n.source/Card 경로: {source_dir}',
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

@app.route('/api/card-before-data')
@ensure_working_directory
def get_card_before_data():
    """전처리전 테이블용: card_before.xlsx 반환 (없으면 .source/Card Excel 통합 후 생성)"""
    try:
        card_before_path = Path(CARD_BEFORE_PATH)
        if not card_before_path.exists() or card_before_path.stat().st_size == 0:
            try:
                _call_integrate_card()
                if not card_before_path.exists():
                    return jsonify({
                        'error': 'card_before.xlsx가 생성되지 않았습니다. MyInfo/.source/Card에 .xls/.xlsx 파일이 있는지 확인하세요.',
                        'columns': [],
                        'data': [],
                        'count': 0
                    }), 500
            except Exception as e:
                return jsonify({
                    'error': f'card_before.xlsx 생성 오류: {str(e)}',
                    'columns': [],
                    'data': [],
                    'count': 0
                }), 500

        df = load_card_before_file()
        if df.empty:
            return jsonify({
                'columns': [],
                'data': [],
                'count': 0
            })
        df = df.where(pd.notna(df), None)
        columns = list(df.columns)
        data = _json_safe(df.to_dict('records'))
        return jsonify({
            'columns': columns,
            'data': data,
            'count': len(data)
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'columns': [],
            'data': [],
            'count': 0
        }), 500


@app.route('/api/run-card-preprocess', methods=['POST'])
@ensure_working_directory
def run_card_preprocess():
    """Source 루트 Excel 통합하여 card_before.xlsx 생성/갱신 (동일 프로세스에서 실행)"""
    try:
        _call_integrate_card()
        return jsonify({'success': True, 'message': 'card_before.xlsx가 생성되었습니다.'})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/processed-data')
@ensure_working_directory
def get_processed_data():
    """전처리된 데이터 반환 (카드: card_before.xlsx 기준, 필터링 지원).
    전처리후: card_before 있으면 기존 파일 읽어 사용, 없으면 통합 생성 후 사용."""
    try:
        output_path = Path(CARD_BEFORE_PATH)
        if not output_path.exists() or output_path.stat().st_size == 0:
            try:
                _call_integrate_card()
                if not output_path.exists():
                    return jsonify({
                        'error': '통합 파일이 생성되지 않았습니다. MyInfo/.source/Card에 .xls, .xlsx 파일이 있는지 확인하세요.',
                        'count': 0,
                        'deposit_amount': 0,
                        'withdraw_amount': 0,
                        'data': []
                    }), 500
            except Exception as e:
                return jsonify({
                    'error': f'통합 파일 생성 오류: {str(e)}',
                    'count': 0,
                    'deposit_amount': 0,
                    'withdraw_amount': 0,
                    'data': []
                }), 500
        
        df = load_card_before_file()
        category_file_exists = Path(INFO_CATEGORY_PATH).exists()
        # info_category.xlsx(신용카드) 없으면 기본 규칙으로 생성 후 카테고리 적용
        if not category_file_exists and not df.empty:
            try:
                mod = _load_process_card_data_module()
                mod.create_category_table(None, category_filepath=INFO_CATEGORY_PATH)
                category_file_exists = Path(INFO_CATEGORY_PATH).exists()
            except Exception:
                pass
        # 가맹점명 기반 카테고리 적용 (info_category.xlsx 신용카드 규칙)
        if not df.empty and category_file_exists:
            try:
                full = pd.read_excel(INFO_CATEGORY_PATH, engine='openpyxl').fillna('')
                if '구분' in full.columns: full = full.drop(columns=['구분'], errors='ignore')
                category_df = full[['분류', '키워드', '카테고리']].copy() if all(c in full.columns for c in ['분류', '키워드', '카테고리']) else full
                mod = _load_process_card_data_module()
                df = mod.apply_category_from_merchant(df, category_df)
            except Exception:
                pass
        
        if df.empty:
            response = jsonify({
                'count': 0,
                'deposit_amount': 0,
                'withdraw_amount': 0,
                'data': [],
                'file_exists': category_file_exists
            })
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response
        
        # 필터 파라미터 (card_before: 카드사, 카드번호, 이용일 등)
        date_filter = request.args.get('date', '')
        bank_filter = request.args.get('bank', '')  # 카드사 필터
        cardno_filter = request.args.get('cardno', '')  # 카드번호 필터
        
        # 카드사 필터 (카드사 컬럼)
        if bank_filter and not df.empty and '카드사' in df.columns:
            df = df[df['카드사'].astype(str).str.strip() == bank_filter]
        # 카드번호 필터
        if cardno_filter and not df.empty and '카드번호' in df.columns:
            df = df[df['카드번호'].astype(str).str.strip() == cardno_filter]
        # 이용일 필터 (yy/mm 또는 yyyy-mm 등)
        if date_filter and not df.empty and '이용일' in df.columns:
            d = date_filter.replace('-', '').replace('/', '').replace('.', '')[:6]
            df = df[df['이용일'].astype(str).str.replace(r'[\s\-/.]', '', regex=True).str.startswith(d)]
        elif date_filter and not df.empty:
            date_col = next((c for c in df.columns if '일' in str(c) or '날짜' in str(c)), None)
            if date_col:
                df = df[df[date_col].astype(str).str.replace(r'[\s\-/.]', '', regex=True).str.startswith(date_filter.replace('-', '').replace('/', ''))]
        
        # 카드번호 16자 이하 행 제외 (전처리후 표시용)
        if not df.empty and '카드번호' in df.columns:
            df = df[df['카드번호'].astype(str).str.strip().str.len() > 16]
        
        # 집계 계산 (card_before: 이용금액<0 → 입금, 이용금액>0 → 출금, 현금처리 → 항상 입금 / 은행: 입금액·출금액)
        count = len(df)
        if not df.empty and '이용금액' in df.columns:
            _card_deposit_withdraw_from_이용금액(df)
            deposit_amount = int(df['입금액'].sum())
            withdraw_amount = int(df['출금액'].sum())
        else:
            deposit_amount = int(df['입금액'].sum()) if not df.empty and '입금액' in df.columns else 0
            withdraw_amount = int(df['출금액'].sum()) if not df.empty and '출금액' in df.columns else 0
        
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
        category_file_exists = Path(CARD_BEFORE_PATH).exists()
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
    """카테고리 적용된 데이터 반환 (card_after.xlsx, 필터링 지원).
    카테고리 조회: card_after 있으면 기존 파일 읽어 사용. 생성은 'card_after.xlsx 생성' 버튼에서만."""
    try:
        category_file_exists = Path(CARD_AFTER_PATH).exists()
        
        # 카테고리 파일 로드
        try:
            df = load_category_file()
        except Exception as e:
            print(f"Error loading category file: {str(e)}")
            traceback.print_exc()
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
        
        # 필터 파라미터 (카드: 카드사, 은행: 은행명)
        bank_filter = request.args.get('bank', '')
        date_filter = request.args.get('date', '')
        bank_col = '카드사' if not df.empty and '카드사' in df.columns else '은행명'
        if bank_filter and bank_col in df.columns:
            df = df[df[bank_col].astype(str).str.strip() == bank_filter]
        
        if date_filter:
            date_col = '이용일' if '이용일' in df.columns else ('거래일' if '거래일' in df.columns else None)
            if date_col:
                try:
                    d = date_filter.replace('-', '').replace('/', '').replace('.', '')[:6]
                    df['_date_str'] = df[date_col].astype(str).str.replace(r'[\s\-/.]', '', regex=True)
                    df = df[df['_date_str'].str.startswith(d, na=False)]
                    df = df.drop('_date_str', axis=1)
                except Exception as e:
                    print(f"Error filtering by date: {str(e)}")
                    pass
        
        # 집계 계산: 카드(card_after)는 이용금액 기준(현금처리→입금), 은행은 입금액/출금액
        count = len(df)
        if not df.empty and '이용금액' in df.columns:
            _card_deposit_withdraw_from_이용금액(df)
            deposit_amount = int(df['입금액'].sum())
            withdraw_amount = int(df['출금액'].sum())
        else:
            for c in ['입금액', '출금액']:
                if c not in df.columns:
                    df[c] = 0
            deposit_amount = int(df['입금액'].sum()) if not df.empty else 0
            withdraw_amount = int(df['출금액'].sum()) if not df.empty else 0
        
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
        return jsonify({
            'error': str(e),
            'count': 0,
            'deposit_amount': 0,
            'withdraw_amount': 0,
            'data': [],
            'file_exists': Path(CARD_AFTER_PATH).exists()
        }), 500

@app.route('/api/source-data')
@ensure_working_directory
def get_source_data():
    """전처리전 테이블용: MyInfo/.source/Card 의 .xls/.xlsx를 직접 읽어 원본 데이터를 JSON으로 반환."""
    try:
        source_dir = Path(SOURCE_CARD_DIR)
        current_dir = os.getcwd()
        if not source_dir.exists():
            return jsonify({
                'error': f'.source/Card 폴더를 찾을 수 없습니다.\n현재 작업 디렉토리: {current_dir}\n.source/Card 경로: {source_dir}',
                'count': 0,
                'files': []
            }), 404

        card_filter = request.args.get('card', '')
        all_data = []
        count = 0
        excel_files = sorted(
            list(source_dir.glob('*.xls')) + list(source_dir.glob('*.xlsx')),
            key=lambda p: (p.name, str(p))
        )
        for file_path in excel_files:
            filename = file_path.name
            card_name = None
            if '국민' in filename:
                card_name = '국민카드'
            elif '신한' in filename:
                card_name = '신한카드'
            elif '하나' in filename:
                card_name = '하나카드'
            elif '현대' in filename:
                card_name = '현대카드'
            elif '농협' in filename:
                card_name = '농협카드'

            if card_filter and card_name != card_filter:
                continue

            try:
                suf = file_path.suffix.lower()
                engine = 'xlrd' if suf == '.xls' else 'openpyxl'
                xls = pd.ExcelFile(file_path, engine=engine)
                for sheet_name in xls.sheet_names:
                    try:
                        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None, engine=engine)
                        df = df.where(pd.notna(df), None)
                        data_dict = df.to_dict('records')
                        data_dict = _json_safe(data_dict)
                        sheet_data = {
                            'filename': filename,
                            'sheet_name': sheet_name,
                            'card': card_name,
                            'data': data_dict
                        }
                        all_data.append(sheet_data)
                        count += len(data_dict)
                    except Exception:
                        continue
            except Exception:
                continue

        response = jsonify({
            'count': count,
            'files': all_data
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        response = jsonify({
            'error': str(e),
            'count': 0,
            'files': []
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500

# 카테고리 페이지 라우트
@app.route('/category')
def category():
    """카테고리 페이지"""
    return render_template('category.html', category_filename='info_category.xlsx')

@app.route('/api/card_category')
def get_category_table():
    """info_category.xlsx 전체 반환 (구분 없음)."""
    path = Path(INFO_CATEGORY_PATH)
    try:
        file_exists = path.exists()
        cols = ['분류', '키워드', '카테고리']
        if not file_exists:
            df = pd.DataFrame(columns=cols)
        else:
            full = pd.read_excel(str(path), engine='openpyxl').fillna('')
            if '구분' in full.columns:
                full = full.drop(columns=['구분'], errors='ignore')
            df = full[cols].copy() if all(c in full.columns for c in cols) else pd.DataFrame(columns=cols)
        for col in cols:
            if col not in df.columns:
                df[col] = ''
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
        response = jsonify({
            'error': str(e),
            'data': [],
            'file_exists': path.exists()
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response, 500

@app.route('/api/card_category', methods=['POST'])
def save_category_table():
    """info_category.xlsx 전체 갱신 (구분 없음)"""
    path = Path(INFO_CATEGORY_PATH)
    file_columns = ['분류', '키워드', '카테고리']
    try:
        data = request.json
        action = data.get('action', 'add')
        if path.exists():
            full_df = pd.read_excel(str(path), engine='openpyxl').fillna('')
            if '구분' in full_df.columns:
                full_df = full_df.drop(columns=['구분'], errors='ignore')
            df = full_df[file_columns].copy() if all(c in full_df.columns for c in file_columns) else pd.DataFrame(columns=file_columns)
        else:
            df = pd.DataFrame(columns=file_columns)
        for col in file_columns:
            if col not in df.columns:
                df[col] = ''
        df = df.fillna('')
        if action == 'add':
            new_row = {'분류': data.get('분류', ''), '키워드': data.get('키워드', ''), '카테고리': data.get('카테고리', '')}
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        elif action == 'update':
            original_분류 = data.get('original_분류', '')
            original_keyword = data.get('original_키워드', '')
            original_category = data.get('original_카테고리', '')
            new_분류 = data.get('분류', '')
            new_keyword = data.get('키워드', '')
            new_category = data.get('카테고리', '')
            mask = ((df['분류'] == original_분류) & (df['키워드'] == original_keyword) & (df['카테고리'] == original_category))
            if mask.any():
                df.loc[mask, '분류'] = new_분류
                df.loc[mask, '키워드'] = new_keyword
                df.loc[mask, '카테고리'] = new_category
            else:
                return jsonify({'success': False, 'error': '수정할 데이터를 찾을 수 없습니다.'}), 400
        elif action == 'delete':
            분류값 = data.get('original_분류', data.get('분류', ''))
            keyword = data.get('original_키워드', data.get('키워드', ''))
            category = data.get('original_카테고리', data.get('카테고리', ''))
            df = df[~((df['분류'] == 분류값) & (df['키워드'] == keyword) & (df['카테고리'] == category))]
        df.to_excel(str(path), index=False, engine='openpyxl')
        response = jsonify({
            'success': True,
            'message': '카테고리 테이블이 업데이트되었습니다.',
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

# 분석 API 라우트
@app.route('/api/analysis/summary')
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
        
        # 카드사/은행명 필터
        bank_filter = request.args.get('bank', '')
        bank_col = '카드사' if not df.empty and '카드사' in df.columns else '은행명'
        if bank_filter and bank_col in df.columns:
            df = df[df[bank_col].astype(str).str.strip() == bank_filter]
        
        if '입금액' not in df.columns:
            df['입금액'] = 0
        if '출금액' not in df.columns:
            df['출금액'] = 0
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
def get_analysis_by_category():
    """적요별 분석 (카테고리 파일 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'data': []})
        
        # 카드사/은행명 필터
        bank_filter = request.args.get('bank', '')
        bank_col = '카드사' if not df.empty and '카드사' in df.columns else '은행명'
        if bank_filter and bank_col in df.columns:
            df = df[df[bank_col].astype(str).str.strip() == bank_filter]
        
        # 카테고리분류를 입출금으로 매핑
        if '카테고리분류' in df.columns and '입출금' not in df.columns:
            df['입출금'] = df['카테고리분류']
        
        # 카테고리 필터 (여러 필터 지원)
        classification_filter = request.args.get('입출금', '')
        transaction_type_filter = request.args.get('거래유형', '')
        transaction_target_filter = ''
        
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
        
        # 카드: 카테고리별, 은행: 적요별 입금/출금 집계
        group_col = '카테고리' if '카테고리' in df.columns else '적요'
        agg_dict = {
            '입금액': 'sum',
            '출금액': 'sum'
        }
        
        # 입출금, 거래유형, 거래방법, 카드사/은행명, 내용, 거래점이 있으면 첫 번째 값 사용 (대표값)
        if '입출금' in df.columns:
            agg_dict['입출금'] = 'first'
        if '거래유형' in df.columns:
            agg_dict['거래유형'] = 'first'
        if '카드사' in df.columns:
            agg_dict['카드사'] = 'first'
        elif '은행명' in df.columns:
            agg_dict['은행명'] = 'first'
        if '내용' in df.columns:
            agg_dict['내용'] = 'first'
        if '거래점' in df.columns:
            agg_dict['거래점'] = 'first'
        
        category_stats = df.groupby(group_col).agg(agg_dict).reset_index()
        
        # 차액 계산
        category_stats['차액'] = category_stats['입금액'] - category_stats['출금액']
        
        # 정렬: 차액 절대값 큰 순, 절대값 같으면 차액 큰 순, 차액 같으면 입금액 많은 순
        category_stats['차액_절대값'] = category_stats['차액'].abs()
        category_stats = category_stats.sort_values(['차액_절대값', '차액', '입금액'], ascending=[False, False, False])
        category_stats = category_stats.drop('차액_절대값', axis=1)
        
        # 데이터 포맷팅
        data = []
        for _, row in category_stats.iterrows():
            cat_val = row[group_col] if pd.notna(row[group_col]) and row[group_col] != '' else '(빈값)'
            item = {
                'category': cat_val,
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
            item['transactionTarget'] = '(빈값)'
            if '카드사' in row:
                item['bank'] = str(row['카드사']) if pd.notna(row['카드사']) and row['카드사'] != '' else '(빈값)'
            elif '은행명' in row:
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
def get_analysis_by_category_group():
    """카테고리 기준 분석 (입출금/거래유형 기준 집계, 거래방법/거래지점 미사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'data': []})
        
        # 카테고리분류를 입출금으로 매핑
        if '카테고리분류' in df.columns and '입출금' not in df.columns:
            df['입출금'] = df['카테고리분류']
        
        # 카드사/은행명 필터
        bank_filter = request.args.get('bank', '')
        bank_col = '카드사' if not df.empty and '카드사' in df.columns else '은행명'
        if bank_filter and bank_col in df.columns:
            df = df[df[bank_col].astype(str).str.strip() == bank_filter]
        
        # 카테고리 필터 (입출금/거래유형만, 거래방법/거래지점 미사용)
        입출금_filter = request.args.get('입출금', '')
        거래유형_filter = request.args.get('거래유형', '')
        if 입출금_filter and '입출금' in df.columns:
            df = df[df['입출금'] == 입출금_filter]
        if 거래유형_filter and '거래유형' in df.columns:
            df = df[df['거래유형'] == 거래유형_filter]
        groupby_columns = []
        if '입출금' in df.columns:
            groupby_columns.append('입출금')
        if '거래유형' in df.columns:
            groupby_columns.append('거래유형')
        
        if not groupby_columns:
            return jsonify({'data': []})
        
        bank_col = '카드사' if '카드사' in df.columns else '은행명'
        if bank_col not in df.columns:
            return jsonify({'data': []})
        
        # 집계 (카드사/은행명 포함)
        category_stats = df.groupby(groupby_columns + [bank_col]).agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        
        # 차액 계산
        category_stats['차액'] = category_stats['입금액'] - category_stats['출금액']
        category_stats['총거래액'] = category_stats['입금액'] + category_stats['출금액']
        
        # 카테고리 그룹별로 다시 집계 (카드사/은행명은 가장 많은 거래가 있는 값 사용)
        category_final = []
        for category_group, group_df in category_stats.groupby(groupby_columns):
            main_bank_row = group_df.loc[group_df['총거래액'].idxmax()]
            main_bank = main_bank_row[bank_col]
            
            total_deposit = group_df['입금액'].sum()
            total_withdraw = group_df['출금액'].sum()
            total_balance = total_deposit - total_withdraw
            
            item = {
                'deposit': int(total_deposit) if pd.notna(total_deposit) else 0,
                'withdraw': int(total_withdraw) if pd.notna(total_withdraw) else 0,
                'balance': int(total_balance) if pd.notna(total_balance) else 0,
                'bank': str(main_bank) if pd.notna(main_bank) and main_bank != '' else '(빈값)'
            }
            if bank_col == '카드사':
                item['카드사'] = item['bank']
            else:
                item['은행명'] = item['bank']
            
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
        
        # 카드사/은행명 필터
        bank_filter = request.args.get('bank', '')
        bank_col = '카드사' if not df.empty and '카드사' in df.columns else '은행명'
        if bank_filter and bank_col in df.columns:
            df = df[df[bank_col].astype(str).str.strip() == bank_filter]
        
        # 카테고리분류를 입출금으로 매핑
        if '카테고리분류' in df.columns and '입출금' not in df.columns:
            df['입출금'] = df['카테고리분류']
        
        # 카테고리 필터 (여러 필터 지원)
        classification_filter = request.args.get('입출금', '')
        transaction_type_filter = request.args.get('거래유형', '')
        transaction_target_filter = ''
        
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
def get_analysis_by_category_monthly():
    """카테고리별 월별 입출금 추이 분석"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'months': [], 'categories': []})
        
        # 카테고리분류를 입출금으로 매핑
        if '카테고리분류' in df.columns and '입출금' not in df.columns:
            df['입출금'] = df['카테고리분류']
        
        # 카드사/은행명 필터
        bank_filter = request.args.get('bank', '')
        bank_col = '카드사' if not df.empty and '카드사' in df.columns else '은행명'
        if bank_filter and bank_col in df.columns:
            df = df[df[bank_col].astype(str).str.strip() == bank_filter]
        
        # 카테고리 필터 (입출금/거래유형만)
        입출금_filter = request.args.get('입출금', '')
        거래유형_filter = request.args.get('거래유형', '')
        if 입출금_filter and '입출금' in df.columns:
            df = df[df['입출금'] == 입출금_filter]
        if 거래유형_filter and '거래유형' in df.columns:
            df = df[df['거래유형'] == 거래유형_filter]
        df['거래일'] = pd.to_datetime(df['거래일'], errors='coerce')
        df = df[df['거래일'].notna()]
        df['거래월'] = df['거래일'].dt.to_period('M').astype(str)
        groupby_columns = []
        if '입출금' in df.columns:
            groupby_columns.append('입출금')
        if '거래유형' in df.columns:
            groupby_columns.append('거래유형')
        
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
                    # 입출금은 제외하고 거래유형만 포함 (거래방법/거래지점 미사용)
                    if col in ['거래유형']:
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
def get_analysis_by_bank():
    """카드사/은행별 분석 (카테고리 파일 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'bank': [], 'account': []})
        
        bank_col = '카드사' if '카드사' in df.columns else '은행명'
        if bank_col not in df.columns:
            return jsonify({'bank': [], 'account': []})
        
        # 카드사/은행별 통계
        bank_stats = df.groupby(bank_col).agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        bank_data = [{
            'bank': row[bank_col],
            'deposit': int(row['입금액']),
            'withdraw': int(row['출금액'])
        } for _, row in bank_stats.iterrows()]
        
        # 계좌별 통계 (카드: 카드번호, 은행: 계좌번호)
        account_col = '카드번호' if '카드번호' in df.columns else '계좌번호'
        if account_col in df.columns:
            account_stats = df.groupby([bank_col, account_col]).agg({
                '입금액': 'sum',
                '출금액': 'sum'
            }).reset_index()
            account_data = [{
                'bank': row[bank_col],
                'account': row[account_col],
                'deposit': int(row['입금액']),
                'withdraw': int(row['출금액'])
            } for _, row in account_stats.iterrows()]
        else:
            account_data = []
        
        response = jsonify({
            'bank': bank_data,
            'account': account_data
        })
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/transactions-by-content')
def get_transactions_by_content():
    """거래처(내용)별 거래 내역"""
    try:
        df = load_processed_file()
        if df.empty:
            return jsonify({'deposit': [], 'withdraw': []})
        
        type_filter = request.args.get('type', 'deposit')  # 'deposit' or 'withdraw'
        limit = int(request.args.get('limit', 10))  # 상위 N개 거래처
        
        bank_col = '카드사' if '카드사' in df.columns else '은행명'
        content_col = '가맹점명' if '가맹점명' in df.columns and '내용' not in df.columns else '내용'
        if content_col not in df.columns:
            content_col = '가맹점명' if '가맹점명' in df.columns else '내용'
        if type_filter == 'deposit':
            amt_col = '입금액' if '입금액' in df.columns else '이용금액'
            if amt_col not in df.columns:
                return jsonify({'data': []})
            top_contents = df[df[amt_col] > 0].groupby(content_col)[amt_col].sum().sort_values(ascending=False).head(limit)
            top_content_list = top_contents.index.tolist()
            transactions = df[(df[content_col].isin(top_content_list)) & (df[amt_col] > 0)].copy()
            transactions = transactions.sort_values(amt_col, ascending=False)
            transactions = transactions.where(pd.notna(transactions), None)
            cols = [c for c in ['거래일', '이용일', bank_col, amt_col, '구분', '적요', content_col, '거래점', '카테고리'] if c in transactions.columns]
            data = transactions[cols].to_dict('records') if cols else []
            data = _json_safe(data)
        else:
            amt_col = '출금액' if '출금액' in df.columns else '이용금액'
            if amt_col not in df.columns:
                return jsonify({'data': []})
            top_contents = df[df[amt_col] > 0].groupby(content_col)[amt_col].sum().sort_values(ascending=False).head(limit)
            top_content_list = top_contents.index.tolist()
            transactions = df[(df[content_col].isin(top_content_list)) & (df[amt_col] > 0)].copy()
            transactions = transactions.sort_values(amt_col, ascending=False)
            transactions = transactions.where(pd.notna(transactions), None)
            cols = [c for c in ['거래일', '이용일', bank_col, amt_col, '구분', '적요', content_col, '거래점', '카테고리'] if c in transactions.columns]
            data = transactions[cols].to_dict('records') if cols else []
            data = _json_safe(data)
        response = jsonify({'data': data})
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/transactions')
def get_analysis_transactions():
    """적요별 상세 거래 내역 반환 (카테고리 파일 사용)"""
    try:
        df = load_category_file()
        if df.empty:
            return jsonify({'data': [], 'deposit_total': 0, 'withdraw_total': 0, 'balance': 0, 'deposit_count': 0, 'withdraw_count': 0})
        
        transaction_type = request.args.get('type', 'deposit') # 'deposit' or 'withdraw'
        category_filter = request.args.get('category', '')  # 카테고리/적요 필터
        content_filter = request.args.get('content', '')  # 거래처 필터 (하위 호환성)
        bank_filter = request.args.get('bank', '')
        
        filter_col = '카테고리' if '카테고리' in df.columns else '적요'
        if category_filter:
            filtered_df = df[df[filter_col] == category_filter].copy()
        elif content_filter:
            filtered_df = df[df['내용'] == content_filter].copy()
        else:
            return jsonify({'data': [], 'deposit_total': 0, 'withdraw_total': 0, 'balance': 0, 'deposit_count': 0, 'withdraw_count': 0})
        
        # 카드사/은행명 필터
        bank_col = '카드사' if not filtered_df.empty and '카드사' in filtered_df.columns else '은행명'
        if bank_filter and bank_col in filtered_df.columns:
            filtered_df = filtered_df[filtered_df[bank_col].astype(str).str.strip() == bank_filter].copy()
        
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
        
        # 결과 컬럼: 카드 데이터는 카드사/이용일 등, 은행은 은행명/거래일 등
        date_col = '이용일' if '이용일' in filtered_df.columns else '거래일'
        amt_col_d = '입금액'
        amt_col_w = '출금액'
        select_cols = [c for c in [date_col, bank_col, amt_col_d, '구분', '적요', '내용', '거래점'] if c in filtered_df.columns]
        if not select_cols:
            select_cols = [c for c in [date_col, bank_col, '이용금액', '가맹점명', '카테고리'] if c in filtered_df.columns]
        
        cat_col = '카테고리' if '카테고리' in filtered_df.columns else '적요'
        merch_col = '가맹점명' if '가맹점명' in filtered_df.columns else '거래점'
        if transaction_type == 'detail':
            # 상세 모드: 카드사, 이용일, 입금액, 출금액, 거래점명 (전체 행 반환)
            cols = [c for c in [bank_col, date_col, '입금액', '출금액', merch_col] if c in filtered_df.columns]
            result_df = filtered_df[cols].copy() if cols else filtered_df.copy()
        elif transaction_type == 'deposit':
            filtered_df = filtered_df[filtered_df['입금액'] > 0]
            cols = [c for c in [cat_col, date_col, bank_col, '입금액'] if c in filtered_df.columns]
            result_df = filtered_df[cols].copy() if cols else filtered_df.copy()
            if '입금액' in result_df.columns:
                result_df.rename(columns={'입금액': '금액'}, inplace=True)
        elif transaction_type == 'withdraw':
            filtered_df = filtered_df[filtered_df['출금액'] > 0]
            cols = [c for c in [cat_col, date_col, bank_col, '출금액'] if c in filtered_df.columns]
            result_df = filtered_df[cols].copy() if cols else filtered_df.copy()
            if '출금액' in result_df.columns:
                result_df.rename(columns={'출금액': '금액'}, inplace=True)
        else: # balance - 차액 상위순일 때는 입금과 출금 모두 표시
            deposit_df = filtered_df[filtered_df['입금액'] > 0].copy()
            withdraw_df = filtered_df[filtered_df['출금액'] > 0].copy()
            cols_d = [c for c in [cat_col, date_col, bank_col, '입금액'] if c in deposit_df.columns]
            cols_w = [c for c in [cat_col, date_col, bank_col, '출금액'] if c in withdraw_df.columns]
            deposit_result = deposit_df[cols_d].copy() if cols_d else deposit_df.copy()
            if '입금액' in deposit_result.columns:
                deposit_result.rename(columns={'입금액': '금액'}, inplace=True)
            deposit_result['거래유형'] = '입금'
            withdraw_result = withdraw_df[cols_w].copy() if cols_w else withdraw_df.copy()
            if '출금액' in withdraw_result.columns:
                withdraw_result.rename(columns={'출금액': '금액'}, inplace=True)
            withdraw_result['거래유형'] = '출금'
            
            # 두 데이터프레임 합치기
            result_df = pd.concat([deposit_result, withdraw_result], ignore_index=True)
        
        # 거래일/이용일 순으로 정렬
        sort_col = date_col if date_col in result_df.columns else '거래일'
        if sort_col in result_df.columns:
            result_df = result_df.sort_values(sort_col)
        
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
    """card_before → card_after 생성. info_category(신용카드) 규칙으로 카테고리(계정과목/업종분류) 적용 후 저장."""
    try:
        mod = _load_process_card_data_module()
        card_before_path = Path(CARD_BEFORE_PATH)
        if not card_before_path.exists() or card_before_path.stat().st_size == 0:
            return jsonify({
                'success': False,
                'error': 'card_after.xlsx를 만들 수 없습니다. card_before.xlsx가 없거나 비어 있습니다. '
                         'MyInfo/.source/Card에 .xls/.xlsx 파일을 넣은 뒤 전처리를 먼저 실행하세요.'
            }), 400

        df_card = pd.read_excel(card_before_path, engine='openpyxl')
        Path(CARD_AFTER_PATH).parent.mkdir(parents=True, exist_ok=True)
        had_category_file = Path(INFO_CATEGORY_PATH).exists()

        # 카드사/카드번호/이용금액이 있으면서 가맹점명이 공란이면 가맹점명에 카드사 저장 (카테고리 매칭 전에 수행 → 신한카드 등 카드사명 매칭 가능)
        if not df_card.empty and all(c in df_card.columns for c in ['카드사', '카드번호', '이용금액', '가맹점명']):
            has_card = (
                (df_card['카드사'].fillna('').astype(str).str.strip() != '') &
                (df_card['카드번호'].fillna('').astype(str).str.strip() != '') &
                (df_card['이용금액'].notna()) &
                (df_card['가맹점명'].fillna('').astype(str).str.strip() == '')
            )
            df_card.loc[has_card, '가맹점명'] = df_card.loc[has_card, '카드사']

        # 신한카드/하나카드 + 사업자번호 없음 → 기본값 저장
        _apply_카드사_사업자번호_기본값(df_card)

        # 이용금액 마이너스 → 카테고리 현금처리 (우선 적용, 기타 카테고리 적용 무시)
        if '카테고리' not in df_card.columns:
            df_card['카테고리'] = ''
        _apply_이용금액_마이너스_현금처리(df_card)

        if had_category_file:
            try:
                full = pd.read_excel(INFO_CATEGORY_PATH, engine='openpyxl').fillna('')
                if '구분' in full.columns:
                    full = full.drop(columns=['구분'], errors='ignore')
                df_cat = full[['분류', '키워드', '카테고리']].copy() if all(c in full.columns for c in ['분류', '키워드', '카테고리']) else full
                df_card = mod.apply_category_from_merchant(df_card, df_cat)
            except Exception:
                pass
        # 카테고리 컬럼 없으면 추가, 비어 있거나 공백이면 '미분류' (card_before에 카테고리 없을 수 있음)
        if '카테고리' not in df_card.columns:
            df_card['카테고리'] = '미분류'
        else:
            empty_cat = df_card['카테고리'].fillna('').astype(str).str.strip() == ''
            df_card.loc[empty_cat, '카테고리'] = '미분류'
        # 카드번호 16자 이하 행 제외 후 card_after.xlsx 저장
        if not df_card.empty and '카드번호' in df_card.columns:
            df_card = df_card[df_card['카드번호'].astype(str).str.strip().str.len() > 16]
        # 시간 제외: '시간' 포함 컬럼 삭제, 이용일 등 날짜 컬럼은 날짜만 저장(시간 제거)
        if not df_card.empty:
            time_cols = [c for c in df_card.columns if '시간' in str(c)]
            if time_cols:
                df_card = df_card.drop(columns=time_cols, errors='ignore')
            for col in ['이용일', '거래일']:
                if col not in df_card.columns:
                    continue
                ser = pd.to_datetime(df_card[col], errors='coerce')
                df_card[col] = ser.dt.strftime('%Y-%m-%d').where(ser.notna(), df_card[col])
        # 카테고리 뒤 분류코드/업종분류 컬럼 추가 (카테고리 조회용)
        # 분류코드: 카테고리테이블 업종분류 해당 키워드 6자리 숫자를 문자로 저장. 나중에 코드 추가 예정.
        #   → 사업자번호를 기초로 국세청 홈페이지에서 업종분류 코드를 취득하여 저장할 예정.
        if '분류코드' not in df_card.columns:
            df_card['분류코드'] = ''
        else:
            df_card['분류코드'] = df_card['분류코드'].fillna('').astype(str).str.strip()
        # 업종분류: 나중에 코드 추가 예정.
        #   → 카테고리테이블 "업종분류"에 해당하는 6자리 코드를 매칭하고, 매칭 결과가 있을 경우 해당 카테고리를 업종분류에 저장할 예정.
        if '업종분류' not in df_card.columns:
            df_card['업종분류'] = ''
        else:
            df_card['업종분류'] = df_card['업종분류'].fillna('').astype(str).str.strip()
        # 현금처리: 이용금액>0일 때만 * -1 (입금으로 저장)
        _apply_현금처리_이용금액_negate(df_card)
        # 할부 컬럼: '일시불' 등 → 공백으로 저장 (card_after.xlsx에는 일시불 텍스트 미저장)
        if not df_card.empty and '할부' in df_card.columns:
            df_card['할부'] = df_card['할부'].apply(
                lambda v: '' if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ('', '0', '일시불') else v
            )
        # 컬럼 순서: ... 카테고리, 분류코드, 업종분류
        card_after_cols = ['카드사', '카드번호', '이용일', '이용금액', '가맹점명', '사업자번호', '할부', '카테고리', '분류코드', '업종분류']
        existing = [c for c in card_after_cols if c in df_card.columns]
        extra = [c for c in df_card.columns if c not in card_after_cols]
        df_card = df_card.reindex(columns=existing + extra)
        df_card.to_excel(str(CARD_AFTER_PATH), index=False, engine='openpyxl')

        if not had_category_file:
            try:
                mod.create_category_table(df_card, category_filepath=INFO_CATEGORY_PATH)
            except Exception as e:
                print(f"info_category.xlsx 신용카드 섹션 생성 실패: {e}")

        return jsonify({
            'success': True,
            'message': f'card_after.xlsx 생성 완료: {len(df_card)}건' + (
                ' (카테고리 적용 없이 미분류로 저장 후 info_category 신용카드 섹션 생성)' if not had_category_file else ' (info_category 적용)'
            ),
            'count': len(df_card),
            'folder': str(Path(CARD_AFTER_PATH).parent),
            'filename': Path(CARD_AFTER_PATH).name
        })
            
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
    """신용카드 도움말 페이지"""
    return render_template('help.html')

@app.route('/analysis/print')
@ensure_working_directory
def print_analysis():
    """신용카드 기본분석 인쇄용 페이지"""
    try:
        bank_filter = request.args.get('bank', '')
        category_filter = request.args.get('category', '')  # 선택한 카테고리 (출력 시 사용)
        
        # 데이터 로드
        df = load_category_file()
        if df.empty:
            return "데이터가 없습니다.", 400
        
        # 카드사 필터 적용
        bank_col = '카드사' if '카드사' in df.columns else '은행명'
        if bank_filter and bank_col in df.columns:
            df = df[df[bank_col].astype(str).str.strip() == bank_filter]
        
        # 통계 계산
        total_count = len(df)
        deposit_count = len(df[df['입금액'] > 0])
        withdraw_count = len(df[df['출금액'] > 0])
        total_deposit = int(df['입금액'].sum())
        total_withdraw = int(df['출금액'].sum())
        net_balance = total_deposit - total_withdraw
        
        # 카테고리별 입출금 내역
        category_stats = df.groupby('카테고리').agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        category_stats = category_stats.sort_values('출금액', ascending=False)
        
        # 카테고리별 거래내역: 선택한 카테고리가 있으면 해당 카테고리, 없으면 출금액 상위 카테고리
        top_category = category_stats.iloc[0]['카테고리'] if not category_stats.empty else ''
        selected_category = category_filter if category_filter else top_category
        if selected_category:
            trans_all = df[df['카테고리'] == selected_category]
            transaction_total_count = len(trans_all)
            transactions = trans_all.head(20)
            transaction_deposit_total = int(trans_all['입금액'].sum())
            transaction_withdraw_total = int(trans_all['출금액'].sum())
        else:
            transaction_total_count = 0
            transactions = pd.DataFrame()
            transaction_deposit_total = 0
            transaction_withdraw_total = 0
        
        # 카드사별 통계
        bank_stats = df.groupby(bank_col).agg({
            '입금액': 'sum',
            '출금액': 'sum'
        }).reset_index()
        
        # 카드별 통계
        account_col = '카드번호' if '카드번호' in df.columns else '계좌번호'
        if account_col in df.columns:
            account_stats = df.groupby([bank_col, account_col]).agg({
                '입금액': 'sum',
                '출금액': 'sum'
            }).reset_index()
        else:
            account_stats = pd.DataFrame()
        
        # 카드사별 통계 막대그래프용 최대값 (세로 막대 높이 비율)
        max_deposit = int(bank_stats['입금액'].max()) if not bank_stats.empty else 1
        max_withdraw = int(bank_stats['출금액'].max()) if not bank_stats.empty else 1
        
        # 카테고리별 월그래프 테이블용: 월별 입금/출금 집계
        date_col = '이용일' if '이용일' in df.columns else '거래일'
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

# info_category(신용카드) 섹션 없으면 기본 규칙으로 생성 (모듈 로드 시 한 번)
_ensure_card_category_file()

if __name__ == '__main__':
    # 현재 디렉토리를 스크립트 위치로 변경
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    print("=" * 50)
    print("신용카드 통합정보(mybccard) 서버를 시작합니다...")
    print("브라우저에서 http://localhost:5002 으로 접속하세요.")
    print("서버를 중지하려면 Ctrl+C를 누르세요.")
    print("=" * 50)
    app.run(debug=True, port=5002, host='127.0.0.1')
