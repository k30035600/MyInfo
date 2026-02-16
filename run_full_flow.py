# -*- coding: utf-8 -*-
"""전체 수행: 은행 ensure → 카드/캐시 로드 → 서버 기동. python run_full_flow.py [--no-server]"""
import os
import sys

os.environ.setdefault("MYINFO_ROOT", os.path.dirname(os.path.abspath(__file__)))
_root = os.environ["MYINFO_ROOT"]
if _root not in sys.path:
    sys.path.insert(0, _root)
os.chdir(_root)
_LOG_PATH = os.path.join(_root, "run_full_flow.log")


def _log(msg):
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass
    try:
        print(msg, flush=True)
    except (ValueError, OSError):
        pass


def main():
    _log("run_full_flow start")
    try:
        import MyBank.process_bank_data as pbd
        pbd.ensure_bank_before_and_category()
        _log("1. Bank OK")
        import MyCard.card_app
        import MyCash.cash_app
        _log("2. MyCard, MyCash OK")
        _log("3. Done.")
    except Exception as e:
        _log("ERROR: " + str(e))
        raise
    if "--no-server" not in sys.argv:
        _log("4. Starting server...")
        import subprocess
        subprocess.Popen(
            [sys.executable, os.path.join(_root, "app.py")],
            cwd=_root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _log("5. http://127.0.0.1:8080")
    else:
        _log("4. Server skipped (--no-server). Run: python app.py")


if __name__ == "__main__":
    main()
