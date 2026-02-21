# -*- coding: utf-8 -*-
"""
MyInfo 통합 서버 (app.py)

목적:
  - MyBank(은행거래), MyCard(신용카드), MyCash(금융정보) 서브앱을 하나의 Flask 앱으로 제공.
  - 템플릿은 프로젝트 루트의 templates/ 사용 (index.html, help.html, 404.html 등).

실행 흐름 (유지보수 시 참고):
  1. 환경 변수·UTF-8 설정 → Flask 앱 생성 → after_request( charset, gzip )
  2. SUBAPP_CONFIG 기준으로 MyBank, MyCard, MyCash 순서로 load_subapp_routes() 호출
     → 각 서브앱 소스 읽기 → UTF-8 블록 패치 → 메모리에서 모듈 로드 → 라우트를 prefix 붙여 등록
  3. /, /help, /bank, /card, /cash, /shutdown, /health 등 메인 라우트 등록
  4. __main__ 시: waitress 서버 기동

서브앱 라우트 예: /bank/ → bank_app, /card/ → card_app, /cash/ → cash_app.
각 요청 시 create_proxy_view()가 해당 앱의 작업 디렉토리로 chdir 후 뷰 실행.
"""
import os
import sys
import io
import tempfile
import traceback
import subprocess
import importlib.util
import warnings

# ----- 1. 환경·인코딩 (Railway·로컬 공통) -----
os.environ.setdefault("LANG", "en_US.UTF-8")
os.environ.setdefault("LC_ALL", "en_US.UTF-8")
os.environ.setdefault("PYTHONUTF8", "1")

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass

from datetime import datetime
from flask import Flask, render_template, render_template_string, redirect, make_response, request

SERVER_START_TIME = None


def _get_version():
    """VERSION 파일에서 버전 문자열 반환 (서버 재시작 없이 반영)."""
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, 'VERSION')
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read().strip() or '26/02/05'
    except Exception:
        pass
    return '26/02/05'


# ----- 2. 서브앱 설정 (폴더명, URL prefix, 진입 스크립트, 표시명) -----
SUBAPP_CONFIG = (
    ('MyBank', '/bank', 'bank_app.py', '은행거래 통합정보'),
    ('MyCard', '/card', 'card_app.py', '신용카드 통합정보'),
    ('MyCash', '/cash', 'cash_app.py', '금융정보 종합분석'),
)


try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    elif sys.platform == 'win32' and hasattr(sys.stdout, 'buffer') and not getattr(sys.stdout.buffer, 'closed', True):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True, errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True, errors='replace')
except Exception:
    pass

warnings.filterwarnings('ignore', message='.*OLE2 inconsistency.*')
warnings.filterwarnings('ignore', message='.*SSCS size is 0 but SSAT.*')
warnings.filterwarnings('ignore', message='.*Cannot parse header or footer.*')

# ----- 3. Flask 앱 초기화 -----
app = Flask(__name__)
SERVER_START_TIME = datetime.now()

# Flask 2.2+: orjson으로 JSON 응답 직렬화 가속 (선택)
try:
    from flask.json.provider import DefaultJSONProvider
    import orjson as _orjson
    class _ORJSONProvider(DefaultJSONProvider):
        def dumps(self, obj, **kwargs):
            return _orjson.dumps(obj).decode('utf-8')
        def loads(self, s, **kwargs):
            if isinstance(s, bytes):
                return _orjson.loads(s)
            return _orjson.loads(s.encode('utf-8'))
    app.json_provider_class = _ORJSONProvider
except Exception:
    pass

app.json.ensure_ascii = False
app.config['JSON_AS_ASCII'] = False
_root = os.path.dirname(os.path.abspath(__file__))
CATEGORY_TABLE_PATH = os.path.join(_root, '.source', 'category_table.json')
os.environ['MYINFO_ROOT'] = _root
# 필수 디렉터리 생성 (.source, .source/Bank, .source/Card, .source/Cash)
try:
    for _d in (os.path.join(_root, '.source'), os.path.join(_root, '.source', 'Bank'), os.path.join(_root, '.source', 'Card'), os.path.join(_root, '.source', 'Cash')):
        os.makedirs(_d, exist_ok=True)
except Exception:
    pass


# ----- 4. 기동 시 캐시·임시파일 정리 (다음 실행 시 깨끗한 상태) -----
def _clear_startup_caches():
    """기동 시 모듈 캐시·임시파일 초기화."""
    for _mod_name in list(sys.modules):
        try:
            _mod = sys.modules.get(_mod_name)
            if _mod is not None and hasattr(_mod, '_HEADER_LIKE_STRINGS'):
                setattr(_mod, '_HEADER_LIKE_STRINGS', None)
        except Exception:
            pass
    try:
        _tmp_dir = tempfile.gettempdir()
        for _f in os.listdir(_tmp_dir):
            if _f.startswith('myinfo_subapp_') and _f.endswith('.txt'):
                try:
                    os.unlink(os.path.join(_tmp_dir, _f))
                except OSError:
                    pass
    except Exception:
        pass
    try:
        _root = os.path.dirname(os.path.abspath(__file__))
        for _d in (_root, os.path.join(_root, '.source'), os.path.join(_root, 'MyBank'), os.path.join(_root, 'MyCard'), os.path.join(_root, 'MyCash')):
            if os.path.isdir(_d):
                for _f in os.listdir(_d):
                    if _f.startswith('.cat_tbl_') and (_f.endswith('.json') or _f.endswith('.xlsx')):
                        try:
                            os.unlink(os.path.join(_d, _f))
                        except OSError:
                            pass
    except Exception:
        pass


def _cleanup_and_exit():
    try:
        _clear_startup_caches()
    except Exception as e:
        print(f"[WARN] {e}", flush=True)
    try:
        os._exit(0)
    except Exception:
        sys.exit(0)


_GZIP_MIN_SIZE = 1024  # 이 크기 이상일 때만 gzip 적용
_SUBAPP_READ_TIMEOUT = 30  # 서브앱 소스 읽기 서브프로세스 타임아웃(초)

@app.after_request
def _ensure_utf8_charset(response):
    """응답 Content-Type에 charset=utf-8 보장."""
    ct = response.content_type or ""
    if ct.startswith("text/") or ct.startswith("application/json"):
        if "charset=" not in ct:
            response.content_type = f"{ct}; charset=utf-8"
    return response


@app.after_request
def _compress_response(response):
    """JSON/텍스트 응답이 일정 크기 이상이면 gzip 압축 (로딩 시간 단축)."""
    accept = request.headers.get("Accept-Encoding") or ""
    if "gzip" not in accept.lower():
        return response
    if response.direct_passthrough or response.status_code not in (200, 201):
        return response
    ct = (response.content_type or "").split(";")[0].strip()
    if ct not in ("application/json", "text/html", "text/plain", "text/css"):
        return response
    data = response.get_data(as_text=False)
    if not data or len(data) < _GZIP_MIN_SIZE:
        return response
    try:
        import gzip
        compressed = gzip.compress(data, compresslevel=6)
        response.set_data(compressed)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = len(compressed)
    except Exception:
        pass
    return response


# ----- 5. 서브앱 소스 로드 시 UTF-8 블록 비활성화 (통합 서버에서 중복 설정 방지) -----
def _patch_utf8_in_source(code):
    """서브앱 소스 내 win32 UTF-8 블록 주석 처리(통합 서버에서 중복 방지)."""
    lines = code.split('\n')
    modified_lines = []
    in_utf8_block = False
    indent_level = 0
    for i, line in enumerate(lines):
        if 'if sys.platform' in line and "'win32'" in line:
            in_utf8_block = True
            indent_level = len(line) - len(line.lstrip())
            modified_lines.append('# UTF-8 블록 비활성화')
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
        # 인자: argv[1]=읽을 파일명(base_name), argv[2]=임시 출력 경로. cwd=subapp_dir 이므로 subapp_dir/base_name 경로로 열림.
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
                timeout=_SUBAPP_READ_TIMEOUT,
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


# ----- 6. 서브앱 라우트 등록 (소스 읽기 → 패치 → 메모리 로드 → prefix 붙여 등록) -----
def load_subapp_routes(subapp_path, url_prefix, app_filename):
    """서브 앱의 라우트를 메인 앱에 등록. 실패 시 _subapp_errors에 저장 후 폴백 뷰 등록."""
    base_dir = os.path.dirname(__file__)
    # 폴더명 변경 호환: MyBank/MyCard 없으면 MYBCBANK/MYBCCARD 사용 (MyCash는 fallback 없이 오류)
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
        if hasattr(subapp_module, 'CATEGORY_TABLE_PATH'):
            subapp_module.CATEGORY_TABLE_PATH = CATEGORY_TABLE_PATH
        if subapp_path == 'MyBank':
            import os as _os
            subapp_module.BANK_BEFORE_PATH = _os.path.join(subapp_dir, 'bank_before.json')
            subapp_module.BANK_AFTER_PATH = _os.path.join(subapp_dir, 'bank_after.json')
        if subapp_path == 'MyCard':
            from pathlib import Path
            mycard_path = Path(subapp_dir)
            if hasattr(subapp_module, 'CARD_AFTER_PATH'):
                subapp_module.CARD_AFTER_PATH = str(mycard_path / 'card_after.json')
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        subapp = subapp_module.app
        for rule in subapp.url_map.iter_rules():
            if rule.endpoint != 'static':
                view_func = subapp.view_functions[rule.endpoint]
                new_rule = str(rule.rule)
                if new_rule == '/':
                    new_rule = url_prefix + '/'
                else:
                    new_rule = url_prefix + new_rule
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
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

def create_proxy_view(view_func, app_dir, subapp_instance):
    def proxy_view(*args, **kwargs):
        original_cwd = os.getcwd()
        try:
            os.chdir(app_dir)
            with subapp_instance.app_context():
                import flask
                original_flask_render = flask.render_template
                def subapp_render_template(template_name_or_list, **context):
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
        load_subapp_routes(_path, _prefix, _app_file)
        _subapp_errors.pop(_prefix, None)
    except Exception as e:
        err_msg = str(e)
        print(f"[ERROR] {_name} ({_prefix}, {_path}/{_app_file}) 라우트 등록 실패: {err_msg}", flush=True)
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

# 서버 기동 시 캐시·임시파일 초기화 (이전 실행 상태 제거)
_clear_startup_caches()

# ----- 7. 메인 라우트 (리다이렉트, 홈, 도움말, 종료, 헬스, 404) -----
@app.route('/bank')
def redirect_bank():
    """은행거래 전처리: 끝 슬래시 없이 접속 시 /bank/ 로 리다이렉트"""
    return redirect('/bank/', code=302)


@app.route('/cash')
def redirect_cash():
    """금융정보 병합작업: 끝 슬래시 없이 접속 시 /cash/ 로 리다이렉트"""
    return redirect('/cash/', code=302)


@app.route('/card')
def redirect_card():
    """신용카드 전처리: 끝 슬래시 없이 접속 시 /card/ 로 리다이렉트"""
    return redirect('/card/', code=302)


def _no_cache_headers():
    """브라우저 캐시 방지 헤더 (수정 사항 즉시 반영용)"""
    return {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
    }

@app.route('/')
def index():
    """메인 홈페이지"""
    start_time_str = SERVER_START_TIME.strftime('%H:%M:%S') if SERVER_START_TIME else ''
    resp = make_response(render_template('index.html', version=_get_version(), server_start_time=start_time_str))
    resp.headers.update(_no_cache_headers())
    if start_time_str:
        resp.headers['X-Server-Start'] = start_time_str  # 새 서버 응답 여부 확인용 (F12 → Network → 응답 헤더)
    return resp


@app.route('/help')
def help_page():
    """도움말 (금융정보 보고서)"""
    resp = make_response(render_template('help.html'))
    resp.headers.update(_no_cache_headers())
    return resp


@app.route('/shutdown')
def shutdown():
    """서버 종료 요청. 로컬호스트에서만 허용. 캐시·임시파일 초기화 후 프로세스를 종료한다."""
    remote = request.remote_addr or ''
    if remote not in ('127.0.0.1', '::1', 'localhost'):
        return 'Forbidden', 403, {'Content-Type': 'text/plain; charset=utf-8'}
    import threading
    def _do_shutdown():
        import time
        time.sleep(0.5)  # 응답 전송 대기
        _cleanup_and_exit()
    threading.Thread(target=_do_shutdown, daemon=True).start()
    resp = make_response('''<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>서버 종료</title><style>body{font-family:'Malgun Gothic',sans-serif;background:#f5f5f5;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}
.container{text-align:center;padding:40px;background:white;border-radius:12px;box-shadow:0 2px 10px rgba(0,0,0,0.1);}
h1{color:#333;margin-bottom:16px;}p{color:#666;}</style></head>
<body><div class="container"><h1>서버를 종료합니다</h1><p>캐시·임시파일을 초기화했습니다.</p><p>다음에 서버를 시작하면 처음부터 실행됩니다.</p><p id="msg" style="margin-top:20px;color:#999;">창을 닫는 중...</p></div>
<script>
setTimeout(function(){ try{ window.close(); setTimeout(function(){ document.getElementById("msg").innerHTML="자동으로 닫히지 않으면 이 창을 직접 닫아 주세요."; }, 500); }catch(e){} }, 800);
</script></body></html>''')
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    resp.headers.update(_no_cache_headers())
    return resp


@app.route('/health')
def health():
    """Railway 등에서 서비스 생존 확인용 (템플릿 없이 200 반환)"""
    return 'OK', 200, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/favicon.ico')
def favicon():
    return '', 204


@app.errorhandler(404)
def page_not_found(e):
    """404 시 한글 안내 페이지 및 접속 가능한 URL 목록 표시"""
    return render_template('404.html'), 404


# ----- 8. 진입점: 작업 디렉터리 설정 → waitress 서버 기동 -----
if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    # Railway/Heroku 등에서는 PORT가 주입되며 0.0.0.0으로 바인딩 필요
    port = int(os.environ.get('PORT', 8080))
    # 0.0.0.0으로 listen 시 localhost(IPv4/IPv6) 접속 가능
    host = '0.0.0.0'
    try:
        from waitress import serve
        # threads 늘려서 요청 대기 시 queue depth 경고 완화
        serve(app, host=host, port=port, threads=8)
    except Exception as e:
        print(f"서버 시작 오류: {e}", flush=True)
        traceback.print_exc()
