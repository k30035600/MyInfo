# -*- coding: utf-8 -*-
"""
금융거래 통합정보(mybcinfo) 통합 서버
은행거래 통합정보(mybcbank)와 신용카드 통합정보(mybccard)를 통합 관리
하나의 서버에서 모든 기능을 제공합니다.
"""
from flask import Flask, render_template, render_template_string, redirect
import os
import sys
import subprocess
import traceback
import importlib.util
import io
import tempfile
import warnings

# 서브 앱 등록 설정: (폴더명, URL prefix, 앱 파일명, 표시 이름)
SUBAPP_CONFIG = (
    ('MyBank', '/bank', 'bank_app.py', '은행거래 통합정보'),
    ('MyCard', '/card', 'card_app.py', '신용카드 통합정보'),
)

# Windows 콘솔 한글 출력 (UTF-8)
if sys.platform == 'win32':
    try:
        # Python 3.7+ 에서는 reconfigure 사용 (더 안전)
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        else:
            # Python 3.6 이하에서는 기존 방식 사용 (buffer가 열려있는 경우만)
            if hasattr(sys.stdout, 'buffer') and not sys.stdout.buffer.closed:
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True, errors='replace')
            if hasattr(sys.stderr, 'buffer') and not sys.stderr.buffer.closed:
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True, errors='replace')
    except Exception:
        pass

# Excel 읽기 시 openpyxl/xlrd에서 나오는 OLE2 경고 억제 (무해한 메시지)
warnings.filterwarnings('ignore', message='.*OLE2 inconsistency.*')
warnings.filterwarnings('ignore', message='.*SSCS size is 0 but SSAT.*')
# openpyxl: 헤더/푸터 파싱 불가 시 무시 (데이터에는 영향 없음)
warnings.filterwarnings('ignore', message='.*Cannot parse header or footer.*')

app = Flask(__name__)

# JSON 인코딩 설정 (한글 지원)
app.json.ensure_ascii = False
app.config['JSON_AS_ASCII'] = False

# 루트 템플릿 (파일 없이 코드 내장)
TEMPLATES = {
    'index': '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>금융거래 통합정보 (MyInfo)</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { height: 100%; margin: 0; padding: 0; }
        body { font-family: 'Malgun Gothic', '맑은 고딕', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; }
        .container { max-width: 1920px; width: 100%; background: white; border-radius: 20px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); padding: 40px; text-align: center; }
        .header { margin-bottom: 6px; }
        .header h1 { font-size: 2.5em; color: #333; margin-bottom: 4px; font-weight: bold; }
        .header p { font-size: 1.2em; color: #666; margin-top: 4px; }
        .services { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 30px; margin-top: 40px; }
        .service-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; padding: 40px; text-decoration: none; color: white; transition: transform 0.3s ease, box-shadow 0.3s ease; box-shadow: 0 5px 15px rgba(0,0,0,0.2); display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 250px; }
        .service-card:hover { transform: translateY(-10px); box-shadow: 0 10px 30px rgba(0,0,0,0.3); }
        .service-card.bank { background: linear-gradient(135deg, #2196F3 0%, #1976D2 100%); }
        .service-card.card { background: linear-gradient(135deg, #FF9800 0%, #F57C00 100%); }
        .service-card h2 { font-size: 2em; margin-bottom: 20px; font-weight: bold; }
        .service-card p { font-size: 1.1em; line-height: 1.6; opacity: 0.95; }
        .service-card .icon { font-size: 4em; margin-bottom: 20px; }
        .features { margin-top: 50px; padding-top: 40px; border-top: 2px solid #eee; }
        .features h3 { font-size: 1.5em; color: #333; margin-bottom: 30px; }
        .features-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-top: 20px; }
        .feature-item { padding: 20px; background: #f8f9fa; border-radius: 10px; border-left: 4px solid #667eea; }
        .feature-item h4 { color: #333; margin-bottom: 10px; font-size: 1.1em; }
        .feature-item p { color: #666; font-size: 0.9em; }
        @media (max-width: 768px) { .container { padding: 20px; } .header h1 { font-size: 2em; } .header p { font-size: 1em; } .services { grid-template-columns: 1fr; gap: 20px; } .service-card { padding: 30px; min-height: 200px; } .service-card h2 { font-size: 1.5em; } .service-card .icon { font-size: 3em; } .features-grid { grid-template-columns: 1fr; } }
        @media (max-width: 480px) { .header h1 { font-size: 1.5em; } .service-card { padding: 20px; min-height: 180px; } .service-card h2 { font-size: 1.3em; } .service-card p { font-size: 0.9em; } }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>💰 금융거래 통합정보</h1>
            <p>MyInfo - Financial Information System</p>
            <p style="font-size: 0.9em; color: #999; margin-top: 5px;">은행 거래와 신용카드 거래를 통합 관리하는 시스템 · <a href="/help" style="color: #667eea;">도움말</a></p>
        </div>
        <div class="services">
            <a href="/bank/" class="service-card bank"><div class="icon">🏦</div><h2>은행거래 통합정보</h2><p>MyBank</p><p style="margin-top: 15px; font-size: 0.95em;">은행 거래 내역을 전처리, 카테고리 분류,<br>기본 분석, 고급 분석을 통해 관리합니다.</p></a>
            <a href="/card/" class="service-card card"><div class="icon">💳</div><h2>신용카드 통합정보</h2><p>MyCard</p><p style="margin-top: 15px; font-size: 0.95em;">신용카드 거래 내역을 전처리, 카테고리 분류,<br>기본 분석, 고급 분석을 통해 관리합니다.</p></a>
        </div>
        <div class="features">
            <h3>주요 기능</h3>
            <div class="features-grid">
                <div class="feature-item"><h4>📊 전처리</h4><p>원본 데이터를 정제하고 표준화된 형식으로 변환</p></div>
                <div class="feature-item"><h4>🏷️ 카테고리</h4><p>거래 내역을 카테고리별로 자동 분류 및 관리</p></div>
                <div class="feature-item"><h4>📈 기본분석</h4><p>거래 통계, 월별 추이 등 기본적인 분석 제공</p></div>
            </div>
        </div>
    </div>
</body>
</html>''',
    'help': '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>도움말 - 금융거래 통합정보</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Malgun Gothic', '맑은 고딕', sans-serif; background-color: #f5f5f5; padding: 20px; }
        .container { max-width: 1920px; margin: 0 auto; background: white; border-radius: 10px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; margin-bottom: 30px; font-size: 2em; }
        h2 { color: #667eea; margin-top: 30px; margin-bottom: 15px; font-size: 1.5em; border-bottom: 2px solid #667eea; padding-bottom: 10px; }
        h3 { color: #555; margin-top: 20px; margin-bottom: 10px; font-size: 1.2em; }
        .help-section { margin-bottom: 30px; }
        .help-section p { line-height: 1.8; color: #666; margin-bottom: 10px; }
        .help-section ul { margin-left: 20px; margin-bottom: 15px; }
        .help-section li { line-height: 1.8; color: #666; margin-bottom: 5px; }
        .code-block { background: #f8f9fa; border-left: 4px solid #667eea; padding: 15px; margin: 15px 0; border-radius: 4px; font-family: 'Courier New', monospace; overflow-x: auto; }
        .feature-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }
        .feature-card { background: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 4px solid #667eea; }
        .feature-card h4 { color: #667eea; margin-bottom: 10px; }
        .main-nav { display: flex; flex-wrap: wrap; gap: 5px; padding: 10px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); max-width: 1920px; margin-left: auto; margin-right: auto; }
        .nav-item { padding: 10px 15px; background: rgba(255,255,255,0.9); color: #333; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 14px; transition: all 0.3s ease; flex: 1; min-width: 120px; text-align: center; white-space: nowrap; }
        .nav-item:hover { background: rgba(255,255,255,1); transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
        .nav-item.active { background: #FF9800; color: white; }
        @media (max-width: 768px) { .container { padding: 20px; } h1 { font-size: 1.5em; } h2 { font-size: 1.3em; } .feature-list { grid-template-columns: 1fr; } .main-nav { gap: 3px; padding: 8px; } .nav-item { font-size: 11px; padding: 6px 8px; min-width: 80px; flex: 1 1 calc(50% - 3px); } }
    </style>
</head>
<body>
    <nav class="main-nav">
        <a href="/" class="nav-item">🏠 홈</a>
        <a href="/bank/" class="nav-item">🏦 은행거래 전처리</a>
        <a href="/bank/category" class="nav-item">🏷️ 은행거래 카테고리</a>
        <a href="/bank/analysis/basic" class="nav-item">📊 은행거래 기본분석</a>
        <a href="/card/" class="nav-item">💳 신용카드 전처리</a>
        <a href="/card/category" class="nav-item">🏷️ 신용카드 카테고리</a>
        <a href="/card/analysis/basic" class="nav-item">📊 신용카드 기본분석</a>
        <a href="/help" class="nav-item active">❓ 도움말</a>
    </nav>
    <div class="container">
        <h1>❓ 도움말 - 금융거래 통합정보</h1>
        <div class="help-section"><h2>시작하기</h2><p>금융거래 통합정보(MyInfo)는 <strong>은행 거래</strong>와 <strong>신용카드 거래</strong>를 한곳에서 관리하는 웹 기반 시스템입니다. 은행거래 통합정보(MyBank)와 신용카드 통합정보(MyCard) 두 서비스를 통합하여 제공하며, <strong>전처리 → 카테고리 분류 → 분석</strong> 순으로 사용합니다.</p>
        <h3>시스템 구성</h3><ul><li><strong>통합 서버(app.py)</strong>: 홈페이지(/)와 이 도움말(/help)을 제공하며, /bank/*, /card/* 요청을 각각 MyBank·MyCard 서브 앱으로 전달합니다.</li><li><strong>은행거래 통합정보(MyBank)</strong>: /bank/ 전처리, /bank/category 카테고리, /bank/analysis/basic 기본분석, /bank/help 은행 도움말.</li><li><strong>신용카드 통합정보(MyCard)</strong>: /card/ 전처리, /card/category 카테고리, /card/analysis/basic 기본분석, /card/help 신용카드 도움말.</li></ul>
        <h3>서버 실행 방법</h3><div class="code-block">cd MyInfo 프로젝트 경로
python app.py</div><p>또는 <code>start-server.bat</code>을 더블클릭하여 실행하세요. 최초 실행 시 필요한 패키지(pip install)가 설치될 수 있으며, Waitress WSGI 서버가 기동됩니다. 기본 주소는 <strong>http://localhost:5000</strong>입니다.</p>
        <h3>프로젝트 폴더 구조</h3><ul><li><strong>MyInfo(루트)</strong>: app.py(통합 서버), start-server.bat, Lib 등.</li><li><strong>MyBank</strong>: 은행 전처리·카테고리·분석 로직, Source(원본 파일), bank_before.xlsx, bank_category.xlsx, bank_after.xlsx.</li><li><strong>MyCard</strong>: 신용카드 전처리·카테고리·분석 로직, Source(원본 파일), card_before.xlsx, card_category.xlsx, card_after.xlsx.</li></ul>
        <h3>권장 사용 흐름</h3><ul><li><strong>1단계 전처리</strong>: MyBank/Source 또는 MyCard/Source에 각 금융기관에서 내려받은 원본 파일(.xls, .xlsx)을 넣습니다. 파일명에 은행명 또는 카드사명이 포함되어야 합니다. 해당 메뉴에서 "전처리 실행"을 클릭하면 *_before.xlsx가 생성·갱신됩니다.</li><li><strong>2단계 카테고리</strong>: 카테고리 페이지에서 "카테고리 생성"으로 *_category.xlsx 규칙을 만든 뒤, 필요 시 키워드·카테고리를 수정합니다. "카테고리 적용"을 실행하면 *_after.xlsx가 생성·갱신됩니다.</li><li><strong>3단계 분석</strong>: 기본분석 페이지에서 전체 통계, 적요/가맹점별·월별·은행/카드사별 집계, 차트를 확인합니다. 상단 "은행명" 또는 "카드사" 필터와 "📄 출력" 버튼으로 인쇄용 뷰를 만들 수 있습니다.</li></ul></div>
        <div class="help-section"><h2>주요 기능</h2><div class="feature-list">
            <div class="feature-card"><h4>📊 전처리</h4><p>여러 은행·카드사의 거래 내역을 하나의 표준 형식으로 통합합니다. Source 폴더의 .xls/.xlsx를 읽어 bank_before.xlsx(은행) 또는 card_before.xlsx(카드)로 저장합니다. 은행은 거래일·적요·입출금·은행명·계좌 등, 카드는 이용일·가맹점명·이용금액·카드사 등으로 통일됩니다.</p></div>
            <div class="feature-card"><h4>🏷️ 카테고리</h4><p>키워드 기반 자동 분류로 거래를 카테고리별로 정리합니다. 은행은 전처리/후처리/거래방법/거래지점/기타거래, 신용카드는 계정과목/업종분류 등 분류와 키워드→카테고리 매핑을 관리하고, "카테고리 적용" 시 *_after.xlsx를 생성합니다.</p></div>
            <div class="feature-card"><h4>📈 기본분석</h4><p>전체 통계, 입출금 추이, 적요/가맹점별·월별·은행/계좌별 또는 카드사/카드별 집계, 막대·파이 차트를 통해 거래 패턴을 한눈에 파악합니다. 페이지 상단 필터와 "📄 출력" 버튼으로 범위 지정 및 인쇄가 가능합니다.</p></div>
        </div></div>
        <div class="help-section"><h2>은행거래 요약</h2><p>지원 은행: <strong>국민은행, 신한은행, 하나은행</strong>. 파일명에 은행명이 포함되어야 인식합니다. 전처리 결과는 <strong>bank_before.xlsx</strong>, 카테고리 규칙은 <strong>bank_category.xlsx</strong>, 카테고리 적용 후 최종 데이터는 <strong>bank_after.xlsx</strong>입니다. 기본분석은 bank_after.xlsx를 사용합니다. 상세 사용법·카테고리 체계·문제 해결은 <a href="/bank/help">은행거래 도움말</a>을 참고하세요.</p></div>
        <div class="help-section"><h2>신용카드 요약</h2><p>지원 카드사: <strong>국민카드, 신한카드, 현대카드, 하나카드</strong>. 파일명 형식은 <code>카드사_기타.xlsx</code>(예: 신한카드_김찬식_2024.xlsx)이며, 첫 번째 밑줄 앞이 카드사명으로 사용됩니다. 전처리 결과는 <strong>card_before.xlsx</strong>, 카테고리 규칙은 <strong>card_category.xlsx</strong>, 카테고리 적용 후 최종 데이터는 <strong>card_after.xlsx</strong>입니다. 상세 내용은 <a href="/card/help">신용카드 도움말</a>을 참고하세요.</p></div>
        <div class="help-section"><h2>페이지별 기능</h2><h3>은행거래 전처리 (/bank/)</h3><ul><li>MyBank/Source에 .xls/.xlsx를 넣고 "전처리 실행"을 클릭합니다.</li><li>전처리 전·후 데이터를 테이블로 비교할 수 있으며, <strong>은행</strong>, <strong>년·월</strong> 필터로 범위를 줄일 수 있습니다.</li></ul>
        <h3>은행거래 카테고리 (/bank/category)</h3><ul><li>카테고리 테이블(분류, 키워드, 카테고리)을 추가·수정·삭제로 관리합니다.</li><li>"카테고리 생성"으로 bank_before 기준 규칙을 자동 생성하고, "카테고리 적용"으로 bank_after.xlsx를 갱신합니다. 페이지 헤더의 "은행명" 필터와 "📄 출력" 버튼으로 특정 은행만 보거나 인쇄할 수 있습니다.</li></ul>
        <h3>은행거래 기본분석 (/bank/analysis/basic)</h3><ul><li>전체 통계, 적요별·월별·은행/계좌별 분석, 차트를 제공합니다. 헤더의 "은행명" 필터와 "📄 출력" 버튼으로 필터링 및 인쇄가 가능합니다.</li></ul>
        <h3>신용카드 전처리 (/card/)</h3><ul><li>MyCard/Source에 .xls/.xlsx를 넣고 "전처리 실행"을 클릭합니다.</li><li>전처리 전·후 데이터 비교, <strong>카드사</strong>, <strong>년·월</strong> 필터를 사용할 수 있습니다.</li></ul>
        <h3>신용카드 카테고리 (/card/category)</h3><ul><li>카테고리 테이블(계정과목, 업종분류)을 관리하고, "카테고리 생성" → "카테고리 적용"으로 card_after.xlsx를 갱신합니다. 헤더의 "카드사" 필터와 "📄 출력" 버튼을 사용할 수 있습니다.</li></ul>
        <h3>신용카드 기본분석 (/card/analysis/basic)</h3><ul><li>전체 통계, 가맹점별·월별·카드사별 분석, 차트를 제공합니다. "카드사" 필터와 "📄 출력" 버튼으로 범위 지정 및 인쇄가 가능합니다.</li></ul></div>
        <div class="help-section"><h2>문제 해결</h2><h3>404 또는 페이지를 찾을 수 없음</h3><ul><li>서버를 방금 시작했다면 은행/신용카드 서브 앱이 로드될 때까지 잠시 후 새로고침해 보세요.</li><li>프로젝트가 OneDrive 등 동기화 폴더에 있으면 파일 읽기 오류로 일부 경로가 404가 될 수 있습니다. 오류 페이지에 표시되는 안내를 참고하고, 필요 시 프로젝트를 동기화가 완료된 로컬 경로로 옮겨 보세요.</li></ul>
        <h3>서버 연결 오류</h3><ul><li>서버가 실행 중인지, 포트 5000이 다른 프로그램에서 사용 중이지 않은지 확인하세요.</li><li>방화벽에서 localhost:5000 접속이 허용되는지 확인하세요.</li></ul>
        <h3>데이터가 표시되지 않음</h3><ul><li>Source 폴더에 .xls/.xlsx가 있고, 파일명에 은행명/카드사명이 포함되는지 확인하세요.</li><li>전처리 후 bank_before.xlsx 또는 card_before.xlsx가 해당 폴더(MyBank/MyCard)에 생성되었는지 확인하세요. 파일이 Excel 등에서 열려 있으면 읽기 실패할 수 있습니다.</li><li>브라우저 F12 → Console에서 오류 메시지를 확인하세요.</li></ul>
        <h3>카테고리가 적용되지 않음</h3><ul><li>bank_category.xlsx 또는 card_category.xlsx가 있는지, "카테고리 생성"을 먼저 실행했는지 확인하세요.</li><li>*_after.xlsx를 Excel에서 열어둔 상태면 쓰기 오류가 날 수 있으니 파일을 닫고 다시 "카테고리 적용"을 실행하세요.</li></ul></div>
        <div class="help-section"><h2>접속 주소</h2><ul><li><strong>홈페이지:</strong> http://localhost:5000</li><li><strong>금융거래 도움말:</strong> http://localhost:5000/help</li><li><strong>은행거래 전처리:</strong> http://localhost:5000/bank/</li><li><strong>은행거래 카테고리:</strong> http://localhost:5000/bank/category</li><li><strong>은행거래 기본분석:</strong> http://localhost:5000/bank/analysis/basic</li><li><strong>은행거래 도움말:</strong> http://localhost:5000/bank/help</li><li><strong>신용카드 전처리:</strong> http://localhost:5000/card/</li><li><strong>신용카드 카테고리:</strong> http://localhost:5000/card/category</li><li><strong>신용카드 기본분석:</strong> http://localhost:5000/card/analysis/basic</li><li><strong>신용카드 도움말:</strong> http://localhost:5000/card/help</li></ul></div>
    </div>
</body>
</html>'''
}

def _patch_utf8_in_source(code):
    """서브 앱 소스에서 UTF-8 설정 블록(win32)을 주석 처리하여 통합 서버에서 중복 실행 방지"""
    lines = code.split('\n')
    modified_lines = []
    in_utf8_block = False
    indent_level = 0
    for i, line in enumerate(lines):
        if 'if sys.platform' in line and "'win32'" in line:
            in_utf8_block = True
            indent_level = len(line) - len(line.lstrip())
            modified_lines.append('# UTF-8 설정 코드 비활성화 (통합 서버에서 처리)')
            continue
        if in_utf8_block:
            current_indent = len(line) - len(line.lstrip()) if line.strip() else indent_level + 1
            if line.strip() == '':
                modified_lines.append('')
                continue
            if current_indent <= indent_level and line.strip() and not line.strip().startswith('#'):
                in_utf8_block = False
                modified_lines.append(line)
            elif 'sys.stdout = io.TextIOWrapper' in line or 'sys.stderr = io.TextIOWrapper' in line:
                modified_lines.append('# ' + line)
            elif line.strip() == 'pass' and i > 0 and 'except:' in lines[i - 1]:
                modified_lines.append('# ' + line)
                in_utf8_block = False
            else:
                modified_lines.append('# ' + line)
        else:
            modified_lines.append(line)
    return '\n'.join(modified_lines)


def _read_app_file(app_file):
    """서브 앱 소스 파일 읽기. OneDrive/Errno 22 대응: open → pathlib → 서브프로세스 순으로 시도."""
    app_file = os.path.normpath(os.path.abspath(app_file))
    subapp_dir = os.path.dirname(app_file)
    base_name = os.path.basename(app_file)
    # 1) 일반 open
    try:
        with open(app_file, 'r', encoding='utf-8') as f:
            return f.read()
    except OSError as e:
        if getattr(e, 'errno', None) != 22:
            raise
        # 2) pathlib
        try:
            from pathlib import Path
            return Path(app_file).read_text(encoding='utf-8')
        except Exception:
            pass
        # 3) 서브프로세스에서 읽고 임시 파일로 출력 (OneDrive 클라우드 전용 파일 대응)
        tmp_dir = tempfile.gettempdir()
        tmp_out = os.path.join(tmp_dir, 'myinfo_subapp_%s_%s.txt' % (os.getpid(), base_name))
        try:
            script = (
                "import sys; p=sys.argv[1]; t=sys.argv[2];\n"
                "f=open(p, encoding='utf-8'); c=f.read(); f.close();\n"
                "o=open(t, 'w', encoding='utf-8'); o.write(c); o.close()"
            )
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32' else 0
            r = subprocess.run(
                [sys.executable, '-c', script, base_name, tmp_out],
                cwd=subapp_dir,
                capture_output=True,
                timeout=30,
                creationflags=creationflags,
            )
            if r.returncode != 0:
                raise OSError(22, 'Invalid argument (subprocess read failed)')
            with open(tmp_out, 'r', encoding='utf-8') as f:
                return f.read()
        finally:
            try:
                if os.path.isfile(tmp_out):
                    os.unlink(tmp_out)
            except OSError:
                pass
        raise OSError(22, 'Invalid argument (OneDrive: 파일을 "항상 이 디바이스에 유지"로 설정 후 재시도)')


class _SubappLoader:
    """메모리에서 수정된 소스를 실행하는 로더 (임시 파일 미사용 → Errno 22 방지)"""
    def __init__(self, source_code, origin_path):
        self.source_code = source_code
        self.origin_path = origin_path

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        # card_app.py 등에서 __file__ 참조하므로 exec 전에 설정
        module.__file__ = self.origin_path
        code = compile(self.source_code, self.origin_path, 'exec')
        exec(code, module.__dict__)


def load_subapp_routes(subapp_path, url_prefix, app_filename):
    """서브 앱의 라우트를 메인 앱에 등록"""
    base_dir = os.path.dirname(__file__)
    # 폴더명 변경 호환: MyBank/MyCard 없으면 MYBCBANK/MYBCCARD 사용
    legacy_folders = {'MyBank': 'MYBCBANK', 'MyCard': 'MYBCCARD'}
    actual_path = subapp_path
    if not os.path.isdir(os.path.join(base_dir, subapp_path)) and subapp_path in legacy_folders:
        alt = legacy_folders[subapp_path]
        if os.path.isdir(os.path.join(base_dir, alt)):
            actual_path = alt
    subapp_dir = os.path.join(base_dir, actual_path)
    original_cwd = os.getcwd()
    
    try:
        os.chdir(subapp_dir)
        sys.path.insert(0, subapp_dir)
        
        app_file = os.path.join(subapp_dir, app_filename)
        app_file = os.path.normpath(os.path.abspath(app_file))
        
        code = _read_app_file(app_file)
        modified_code = _patch_utf8_in_source(code)
        
        # 임시 파일 없이 메모리에서 모듈 로드 (OneDrive/Errno 22 방지)
        loader = _SubappLoader(modified_code, app_file)
        spec = importlib.util.spec_from_loader("subapp", loader, origin=app_file)
        subapp_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(subapp_module)
        
        subapp_module.__file__ = app_file
        if hasattr(subapp_module, 'SCRIPT_DIR'):
            subapp_module.SCRIPT_DIR = subapp_dir
        if subapp_path == 'MyCard':
            from pathlib import Path
            mycard_path = Path(subapp_dir)
            if hasattr(subapp_module, 'CATEGORY_PATH'):
                subapp_module.CATEGORY_PATH = mycard_path / 'card_category.xlsx'
            if hasattr(subapp_module, 'CARD_AFTER_PATH'):
                subapp_module.CARD_AFTER_PATH = mycard_path / 'card_after.xlsx'
            if hasattr(subapp_module, '_ensure_card_category_file'):
                try:
                    subapp_module._ensure_card_category_file()
                except Exception as e:
                    print(f"[app] card_category.xlsx 자동 생성 실패: {e}")
        
        # 서브 앱 로드 후 즉시 stdout/stderr를 sys.__stdout__/__stderr__로 복원
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        
        # 서브 앱의 Flask 앱 인스턴스 가져오기
        subapp = subapp_module.app
        
        # 서브 앱의 모든 라우트를 메인 앱에 등록
        for rule in subapp.url_map.iter_rules():
            if rule.endpoint != 'static':
                # 원본 뷰 함수 가져오기
                view_func = subapp.view_functions[rule.endpoint]
                
                # URL prefix 추가하여 새 라우트 등록
                new_rule = str(rule.rule)
                if new_rule == '/':
                    new_rule = url_prefix + '/'
                else:
                    new_rule = url_prefix + new_rule
                
                # 메인 앱에 라우트 등록 (strict_slashes=False: /card 와 /card/ 둘 다 허용)
                proxy_func = create_proxy_view(view_func, subapp_dir, subapp)
                app.add_url_rule(
                    new_rule,
                    endpoint=f"{url_prefix.replace('/', '').replace('_', '')}_{rule.endpoint}",
                    view_func=proxy_func,
                    methods=rule.methods,
                    strict_slashes=False
                )
        
        return subapp
    finally:
        os.chdir(original_cwd)
        if subapp_dir in sys.path:
            sys.path.remove(subapp_dir)
        # 최종적으로 stdout/stderr를 sys.__stdout__/__stderr__로 복원
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

def create_proxy_view(view_func, app_dir, subapp_instance):
    """뷰 함수를 프록시하는 래퍼 함수 생성"""
    def proxy_view(*args, **kwargs):
        original_cwd = os.getcwd()
        try:
            # 서브 앱의 작업 폴더로 변경
            # 은행거래 통합정보: .\MyBank
            # 신용카드 통합정보: .\MyCard
            os.chdir(app_dir)
            
            # 서브 앱의 Flask 앱 컨텍스트에서 실행
            # 이렇게 하면 서브 앱의 템플릿 폴더를 사용할 수 있음
            with subapp_instance.app_context():
                # render_template을 서브 앱의 것으로 교체
                import flask
                
                # 서브 앱의 render_template 사용
                # 서브 앱의 템플릿 폴더를 사용하도록 설정
                original_flask_render = flask.render_template
                
                def subapp_render_template(template_name_or_list, **context):
                    """서브 앱의 템플릿 폴더를 사용하는 render_template"""
                    return subapp_instance.render_template(template_name_or_list, **context)
                
                # 임시로 render_template 교체
                flask.render_template = subapp_render_template
                
                try:
                    result = view_func(*args, **kwargs)
                    return result
                finally:
                    # 원본 복원
                    flask.render_template = original_flask_render
        finally:
            os.chdir(original_cwd)
    return proxy_view

def _subapp_error_page(prefix_name, detail, app_folder, app_filename):
    """서브 앱 로드 실패 시 표시할 HTML"""
    return render_template_string('''<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>라우트 등록 실패</title>
<style>
body { font-family: 'Malgun Gothic', sans-serif; background: #f5f5f5; padding: 40px; margin: 0; }
.container { max-width: 640px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
h1 { color: #c62828; margin-bottom: 16px; font-size: 1.4em; }
p { color: #444; line-height: 1.7; }
pre { background: #f5f5f5; padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 0.9em; }
.nav { margin-top: 24px; }
a { color: #1976d2; text-decoration: none; }
a:hover { text-decoration: underline; }
.tip { background: #fff8e1; border-left: 4px solid #ff9800; padding: 12px; margin-top: 16px; }
</style>
</head>
<body>
<div class="container">
<h1>''' + prefix_name + ''' 라우트를 불러올 수 없습니다</h1>
<p>서버 시작 시 해당 모듈 등록에 실패했습니다. 아래 오류를 확인한 뒤 조치하세요.</p>
<pre>{{ detail }}</pre>
<div class="tip">
<strong>OneDrive 사용 시:</strong> 프로젝트가 OneDrive 폴더에 있으면 <code>''' + app_folder + '/' + app_filename + '''</code> 파일이 클라우드 전용 상태일 수 있습니다. 
파일 탐색기에서 해당 파일 우클릭 → <strong>항상 이 디바이스에 유지</strong>로 설정한 뒤 서버를 다시 시작하세요.
</div>
<div class="nav"><a href="/">홈으로</a> · <a href="/help">도움말</a></div>
</div>
</body>
</html>''', detail=detail)

# 서브 앱 라우트 등록 (SUBAPP_CONFIG 기반)
_subapp_errors = {}  # prefix -> (표시이름, 오류메시지)

for _path, _prefix, _app_file, _name in SUBAPP_CONFIG:
    try:
        print(f"{_name} 라우트 등록 중...", flush=True)
        load_subapp_routes(_path, _prefix, _app_file)
        print(f"[OK] {_name} 라우트 등록 완료", flush=True)
        _subapp_errors.pop(_prefix, None)
    except Exception as e:
        err_msg = str(e)
        print(f"[ERROR] {_name} 라우트 등록 실패: {err_msg}", flush=True)
        traceback.print_exc()
        _subapp_errors[_prefix] = (_name, err_msg)
        # 실패한 prefix에 대한 폴백 라우트 등록 (404 대신 오류 안내 표시)
        def _make_fallback(prefix, name, msg, folder, app_filename):
            def fallback_view():
                return _subapp_error_page(name, msg, folder, app_filename)
            return fallback_view
        _view = _make_fallback(_prefix, _name, err_msg, _path, _app_file)
        app.add_url_rule(_prefix + '/', endpoint='fallback_' + _prefix.strip('/'), view_func=_view, strict_slashes=False)
        app.add_url_rule(_prefix, endpoint='fallback_' + _prefix.strip('/') + '_root', view_func=lambda: redirect(_prefix + '/'), methods=('GET',))

@app.route('/bank')
def redirect_bank():
    """은행 전처리: 끝 슬래시 없이 접속 시 /bank/ 로 리다이렉트"""
    return redirect('/bank/', code=302)


@app.route('/card')
def redirect_card():
    """신용카드 전처리: 끝 슬래시 없이 접속 시 /card/ 로 리다이렉트"""
    return redirect('/card/', code=302)


@app.route('/')
def index():
    """메인 홈페이지"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    original_cwd = os.getcwd()
    try:
        os.chdir(script_dir)
        return render_template_string(TEMPLATES['index'])
    finally:
        os.chdir(original_cwd)

@app.route('/help')
def help_page():
    """도움말"""
    return render_template_string(TEMPLATES['help'])

@app.route('/favicon.ico')
def favicon():
    return '', 204


@app.errorhandler(404)
def page_not_found(e):
    """404 시 한글 안내 페이지 및 접속 가능한 URL 목록 표시"""
    html = '''<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>페이지를 찾을 수 없습니다</title>
<style>
body { font-family: 'Malgun Gothic', sans-serif; background: #f5f5f5; padding: 40px; margin: 0; }
.container { max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
h1 { color: #333; margin-bottom: 20px; font-size: 1.5em; }
p { color: #666; line-height: 1.6; }
ul { margin: 20px 0; padding-left: 24px; }
li { margin: 8px 0; }
a { color: #2196F3; text-decoration: none; }
a:hover { text-decoration: underline; }
</style>
</head>
<body>
<div class="container">
<h1>찾을 수 없음</h1>
<p>요청하신 URL을 서버에서 찾을 수 없습니다. URL을 직접 입력하셨다면 철자를 확인하고, 아래 링크로 이동하시거나 잠시 후 다시 시도해 주세요.</p>
<p><strong>현재 접속 가능한 주소:</strong></p>
<ul>
<li><a href="/">홈페이지</a></li>
<li><a href="/bank/">은행거래 통합정보 (전처리)</a></li>
<li><a href="/card/">신용카드 통합정보 (전처리)</a></li>
<li><a href="/help">도움말</a></li>
</ul>
<p>서버를 방금 시작했다면, 은행/신용카드 라우트가 등록될 때까지 잠시 후 다시 시도해 보세요.</p>
</div>
</body>
</html>'''
    return html, 404


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    host = '127.0.0.1'
    port = 5000
    try:
        print("=" * 50, flush=True)
        print("금융거래 통합정보(mybcinfo) 통합 서버를 시작합니다...", flush=True)
        print("브라우저에서 http://localhost:5000 으로 접속하세요.", flush=True)
        print("", flush=True)
        print("접속 주소:", flush=True)
        print(f"- 홈페이지: http://localhost:{port}  또는  http://{host}:{port}", flush=True)
        print(f"- 은행거래 통합정보: http://localhost:{port}/bank", flush=True)
        print(f"- 신용카드 통합정보: http://localhost:{port}/card", flush=True)
        print("", flush=True)
        print(f"[INFO] 연결이 거부되면 http://{host}:{port} 으로 접속해 보세요.", flush=True)
        print("[INFO] 모든 서버가 하나로 통합되었습니다!", flush=True)
        print("[INFO] 프로덕션 WSGI 서버(Waitress)로 실행 중.", flush=True)
        print("", flush=True)
        print("서버를 중지하려면 Ctrl+C를 누르세요.", flush=True)
        print("=" * 50, flush=True)
        from waitress import serve
        # threads 늘려서 요청 대기 시 queue depth 경고 완화
        serve(app, host=host, port=port, threads=8)
    except Exception as e:
        print(f"서버 시작 오류: {e}", flush=True)
        traceback.print_exc()
