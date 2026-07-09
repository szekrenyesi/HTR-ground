"""
Auth v2 — per-user belépés, bcrypt jelszavakkal, session cookie-val.

Az `auth.json` séma (részletek):

    {
      "session_secret":          "hosszú random string (bootstrap generálja)",
      "session_cookie_name":     "htrground_session",
      "session_max_age_seconds": 604800,
      "users": {
        "anna": {
          "display_name":  "Kovács Anna",
          "password_hash": "$2b$12$…",
          "is_admin":      false           # opcionális, default: false
        }
      },
      "projects": {
        "Titkos": { "visible_to": ["anna"] }   # opcionális, ACL modul olvassa
      }
    }

Elvek:
- Jelszó SOHA nincs plaintext. A hasheket a `users.py` CLI helyezi el.
- Session most `{"username": "..."}`-t tárol, `{"auth": True}` helyett.
- Régi shape (van `password`, nincs `users`) → startup guard hibaüzenettel leáll.
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any, Dict, Optional

import bcrypt
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse


CONF_DIR = Path(__file__).resolve().parent.parent / "conf"
AUTH_FILENAME         = "auth.json"
DEFAULT_FILENAME      = "auth_default.json"

# Bcrypt limit: max 72 byte a jelszó (a bcrypt algoritmus miatt). Ha ennél
# hosszabb jönne, egyszerűen levágjuk — nem hiba, csak konvenció.
_BCRYPT_MAX_BYTES = 72


class AuthConfigError(RuntimeError):
    """Rossz alakú vagy hiányzó auth config."""


# ─── Load / save ─────────────────────────────────────────────────────────
def _config_paths() -> tuple[Path, Path]:
    return CONF_DIR / AUTH_FILENAME, CONF_DIR / DEFAULT_FILENAME


def _empty_default_config() -> dict:
    """Fresh install fallback — a server elindul, csak nem lehet belépni,
    amíg `python -m app.users bootstrap` le nem fut."""
    return {
        "session_cookie_name":     "htrground_session",
        "session_max_age_seconds": 604800,
        "users":                   {},
        "projects":                {},
    }


def load_auth_config() -> dict:
    """Preferálja az `auth.json`-t, fallback: `auth_default.json`, végső
    esetben üres in-memory config.

    A régi (v1) shape-et (van `password`, nincs `users`) explicit hibaüzenettel
    utasítja el — ezzel elkerülhető, hogy egy elavult telepítés csendben úgy
    induljon, hogy senki nem tud belépni.

    Ha egyik fájl sem található, üres alapokat adunk vissza egy warning
    kíséretében. Ez engedi, hogy a Docker fresh mount / új telepítés
    esetén a szerver egyáltalán fel tudjon indulni, hogy a bootstrap CLI
    lefuthasson.
    """
    auth_path, default_path = _config_paths()

    if auth_path.exists():
        with auth_path.open(encoding="utf-8") as fh:
            cfg = json.load(fh)
        if _is_legacy_shape(cfg):
            raise AuthConfigError(
                f"A {auth_path} régi (shared password) formátumban van, "
                "amit már nem támogatunk. Töröld ki és futtasd újra a "
                "`python -m app.users bootstrap` parancsot."
            )
        return cfg

    if default_path.exists():
        with default_path.open(encoding="utf-8") as fh:
            return json.load(fh)

    # Fresh install / üres mounted conf — csak warning, nem fatal.
    import warnings
    warnings.warn(
        f"Nem található config a {CONF_DIR} alatt. A szerver elindul, "
        "de belépés nem lesz lehetséges, amíg le nem futtatod: "
        "python -m app.users bootstrap",
        RuntimeWarning,
        stacklevel=2,
    )
    return _empty_default_config()


def save_auth_config(cfg: dict) -> None:
    """Atomikus mentés: `.tmp`-be írás, majd rename."""
    auth_path, _ = _config_paths()
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = auth_path.with_suffix(auth_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=4, ensure_ascii=False)
    tmp.replace(auth_path)


def _is_legacy_shape(cfg: dict) -> bool:
    """Az M1 shared password shape: van `password`, nincs `users`."""
    return "password" in cfg and "users" not in cfg


# ─── Session-independent helpers ─────────────────────────────────────────
def _to_bytes(s: str) -> bytes:
    b = s.encode("utf-8")
    return b[:_BCRYPT_MAX_BYTES]


def hash_password(plaintext: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(_to_bytes(plaintext), salt).decode("ascii")


def _verify_hash(plaintext: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_to_bytes(plaintext), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def generate_session_secret() -> str:
    return secrets.token_urlsafe(48)


# ─── Runtime config: a folyamat első inicializálásakor egyszer ────────────
def _ensure_session_secret(cfg: dict) -> dict:
    """Ha nincs `session_secret`, generálunk egyet és visszaírjuk. Így egy fresh
    telepítés az `auth_default.json`-nal is elindul (a bootstrap CLI később
    kitölt egy erős, perzisztens értéket)."""
    if not cfg.get("session_secret"):
        cfg["session_secret"] = generate_session_secret()
    return cfg


AUTH_CONFIG: Dict[str, Any] = _ensure_session_secret(load_auth_config())


def reload_config() -> None:
    """Tesztek / bootstrap után újratöltés. Az `AUTH_CONFIG` in-place frissül."""
    fresh = _ensure_session_secret(load_auth_config())
    AUTH_CONFIG.clear()
    AUTH_CONFIG.update(fresh)


# ─── User lookups ────────────────────────────────────────────────────────
def get_user(username: str) -> Optional[Dict[str, Any]]:
    users = AUTH_CONFIG.get("users") or {}
    return users.get(username)


def verify_credentials(username: str, password: str) -> bool:
    """Constant-time-ish username lookup + bcrypt verify."""
    if not username or not password:
        return False
    user = get_user(username)
    if not user:
        # Nem-létező usernévnél is végzünk egy hash-verify-t egy dummy hash-en,
        # hogy timing-info-t ne szolgáltassunk. (Enyhe védekezés.)
        _verify_hash(password, "$2b$12$" + "x" * 53)
        return False
    return _verify_hash(password, user.get("password_hash", ""))


def is_admin_user(username: Optional[str]) -> bool:
    if not username:
        return False
    user = get_user(username)
    if not user:
        return False
    return bool(user.get("is_admin", False))


# ─── Session-based helpers (FastAPI request-tel) ─────────────────────────
def current_username(request: Request) -> Optional[str]:
    return request.session.get("username")


def current_user(request: Request) -> Optional[Dict[str, Any]]:
    name = current_username(request)
    if not name:
        return None
    return get_user(name)


def is_authenticated(request: Request) -> bool:
    return current_username(request) is not None


def is_admin(request: Request) -> bool:
    return is_admin_user(current_username(request))


# ─── FastAPI dependency-k ────────────────────────────────────────────────
def require_auth(request: Request) -> str:
    """API kérésekhez. Nem-authozottnak 401 + JSON.

    A visszatérési érték a username, hogy a route ne kelljen újra
    kikérnie: `def foo(user: str = Depends(require_auth))`.
    """
    name = current_username(request)
    if not name:
        raise HTTPException(status_code=401, detail="Nincs belépve")
    return name


def require_admin(request: Request) -> str:
    """Csak admin userekhez. Auth hiánynál 401, nem-adminnál 403."""
    name = require_auth(request)
    if not is_admin_user(name):
        raise HTTPException(status_code=403, detail="Nincs admin jog")
    return name


def require_auth_or_redirect(request: Request):
    """HTML oldalakhoz: ha nincs belépve, redirect a login oldalra."""
    if not is_authenticated(request):
        next_url = request.url.path
        if request.url.query:
            next_url = f"{next_url}?{request.url.query}"
        return RedirectResponse(url=f"/login?next={next_url}", status_code=303)
    return None


# ─── Session-payload builder a /api/session-höz ──────────────────────────
def session_info(request: Request) -> Dict[str, Any]:
    name = current_username(request)
    if not name:
        return {"authenticated": False}
    user = get_user(name) or {}
    return {
        "authenticated": True,
        "username":      name,
        "display_name":  user.get("display_name") or name,
        "is_admin":      bool(user.get("is_admin", False)),
    }
