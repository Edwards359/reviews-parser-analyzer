from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for path in (ROOT / "worker_ai-main",):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


_APP_DIR = ROOT / "app_test_2803-main"
if _APP_DIR.exists() and "app" not in sys.modules:
    pkg = types.ModuleType("app")
    pkg.__path__ = [str(_APP_DIR)]
    sys.modules["app"] = pkg
