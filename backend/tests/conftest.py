"""
Pytest konfiguráció: tegyük a `backend/` mappát az import útvonalra,
hogy a tesztek `from app.converters import ...` formában importálhassanak.
"""
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

REPO_ROOT = BACKEND_ROOT.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
