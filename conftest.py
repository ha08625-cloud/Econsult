# conftest.py (at project root: /home/cxclaw/projects/Econsult/conftest.py)
import sys
import os

_root = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_root, "backend"))
sys.path.insert(0, os.path.join(_root, "backend", "contracts"))