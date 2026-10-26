from __future__ import annotations
import logging
import os
import sys
from dotenv import load_dotenv
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
load_dotenv(os.path.join(_ROOT, '.env'))
logging.basicConfig(level=os.getenv('PYTHON_LOG_LEVEL', 'INFO'), format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

def main() -> None:
    py_ai = os.path.join(_ROOT, 'python-ai')
    if py_ai not in sys.path:
        sys.path.insert(0, py_ai)
    from app.mcp_server.server import run_server
    run_server()
if __name__ == '__main__':
    main()
