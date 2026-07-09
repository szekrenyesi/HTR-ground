"""
Pytest konfiguráció.

Fontos: a beállítás **modul-szinten** történik (nem fixture-ben), mert az
`app.main` importáláskor olvassa a `AUTH_CONFIG["session_secret"]`-et a
SessionMiddleware-hez. Ha a fixture később futna, a middleware már a valódi
`backend/conf/auth.json`-nal (vagy a default-tal) lenne inicializálva.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest


# ─── 1. Backend importok ──────────────────────────────────────────────────
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

REPO_ROOT    = BACKEND_ROOT.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ─── 2. Auth izolált konfiguráció (modul-szinten) ─────────────────────────
_TMP_CONF = Path(tempfile.mkdtemp(prefix="htrground-test-conf-"))

# Az `app.auth` importja itt megnyitja az AKTUÁLIS CONF_DIR-t; ezért gyorsan
# átirányítjuk mielőtt bármilyen route/middleware inicializálódna.
from app import auth as _auth_mod  # noqa: E402

_TEST_CFG = {
    "session_secret":          "test-secret-do-not-use-in-prod",
    "session_cookie_name":     "htrground_session_test",
    "session_max_age_seconds": 3600,
    "users": {
        "admin": {
            "display_name":  "Test Admin",
            "password_hash": _auth_mod.hash_password("adminpass"),
            "is_admin":      True,
        },
        "anna": {
            "display_name":  "Kovács Anna",
            "password_hash": _auth_mod.hash_password("annapass"),
        },
        "bela": {
            "display_name":  "Nagy Béla",
            "password_hash": _auth_mod.hash_password("belapass"),
        },
    },
    "projects": {},
}
(_TMP_CONF / "auth.json").write_text(json.dumps(_TEST_CFG, indent=2), encoding="utf-8")

_auth_mod.CONF_DIR = _TMP_CONF
_auth_mod.reload_config()


def pytest_sessionfinish(session, exitstatus):
    """Töröljük a tmp konfigot a tesztfutás végén."""
    shutil.rmtree(_TMP_CONF, ignore_errors=True)


# ─── 3. Kliens fixture-ök ─────────────────────────────────────────────────
@pytest.fixture
def anon_client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture
def logged_in_client():
    """Bejelentkezett kliens `anna` néven (nem admin)."""
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post(
        "/login",
        data={"username": "anna", "password": "annapass"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    return c


@pytest.fixture
def admin_client():
    """Bejelentkezett kliens `admin` néven."""
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post(
        "/login",
        data={"username": "admin", "password": "adminpass"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    return c


# ─── 4. Reset a config-hoz módosítás után (CLI tesztek használják) ──────
@pytest.fixture
def reset_auth_config():
    """Egy teszt módosíthatja a config-ot; a végén állítsuk vissza az alapot."""
    yield _TEST_CFG
    (_TMP_CONF / "auth.json").write_text(
        json.dumps(_TEST_CFG, indent=2), encoding="utf-8"
    )
    _auth_mod.reload_config()
