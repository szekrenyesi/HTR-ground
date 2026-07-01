"""
Auth helper — közös jelszós belépés, session cookie-val.

- A jelszó és session titok a `backend/conf/auth.json`-ban van, ami a repóban .gitignore-olt.
  Ha nincs `auth.json`, az `auth_default.json`-ra esik vissza (fresh clone).
- Nincs 'user' fogalom: aki tudja a jelszót, be van léptetve. A session cookie
  jelöli be a belépést (starlette SessionMiddleware).
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse


CONF_DIR = Path(__file__).resolve().parent.parent / "conf"


def load_auth_config() -> dict:
    """Prefer conf/auth.json; fall back to conf/auth_default.json."""
    for name in ("auth.json", "auth_default.json"):
        p = CONF_DIR / name
        if p.exists():
            with p.open(encoding="utf-8") as fh:
                return json.load(fh)
    raise FileNotFoundError(
        f"Sem auth.json, sem auth_default.json nem található itt: {CONF_DIR}"
    )


AUTH_CONFIG = load_auth_config()


def verify_password(candidate: str) -> bool:
    """Constant-time password compare."""
    expected = AUTH_CONFIG.get("password", "")
    if not expected:
        return False
    return secrets.compare_digest(str(candidate), str(expected))


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("auth"))


def require_auth(request: Request):
    """FastAPI dependency: API kérésekhez.

    Nem-authozottnak 401-et dob JSON hibaüzenettel — a kliens (JS) így
    magától tud kezelni. HTML oldalakhoz külön (require_auth_or_redirect) van.
    """
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Nincs belépve")


def require_auth_or_redirect(request: Request):
    """HTML oldalakhoz: ha nincs belépve, redirect a login oldalra."""
    if not is_authenticated(request):
        # A `next` paraméterrel visszairányítjuk oda, ahonnan jött
        next_url = request.url.path
        return RedirectResponse(url=f"/login?next={next_url}", status_code=303)
    return None
