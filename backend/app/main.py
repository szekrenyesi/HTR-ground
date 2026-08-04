"""
HTR-ground backend — FastAPI app.

Futtatás (a backend/ mappából):
    uvicorn app.main:app --reload --port 8000

Endpoint-ok:
    GET  /                  → landing.html (két kártya: Demó / Projektek)
    GET  /demo              → editor.html (nyilvános, feltöltéses editor)
    GET  /login             → login.html
    POST /login             → jelszó ellenőrzés + session cookie
    POST /logout            → session törlés
    GET  /examples/...      → a példa fájlok (kép, JSON, ALTO) kiszolgálása
    POST /api/convert       → HTR fájl (JSON / ALTO XML / PAGE XML) → belső JSON
    GET  /api/health        → egyszerű health check
    GET  /api/session       → belépési állapot lekérdezése (JS-nek)
    GET  /docs              → auto Swagger UI
"""
from __future__ import annotations

import json as _json
import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import (
    AUTH_CONFIG,
    is_authenticated,
    require_auth,
    require_auth_or_redirect,
    session_info,
    verify_credentials,
)
from .converters import (
    EXPORT_EXT,
    EXPORT_MIME,
    UnknownFormatError,
    convert,
    detect_format,
    export as export_page,
    to_pdf,
)
from .projects import (
    PROJECTS_ROOT,
    AccessDeniedError,
    PathEscapeError,
    find_pair,
    list_folder,
    load_pair,
    resolve_safe,
    save_pair,
)
from . import meta as pair_meta
from . import presence as presence_mod
from .schema import Page


# Projekt gyökér: backend/app/main.py → backend/app → backend → REPO_ROOT
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
EXAMPLES_DIR = REPO_ROOT / "examples"


# ─── Sub-path deployment support ─────────────────────────────────────────
# Ha a HTR-ground egy reverse proxy sub-path alatt fut (pl.
# https://altnyelv.unideb.hu/htr-ground/), akkor a HTR_GROUND_ROOT_PATH env
# var segít ezt kompenzálni:
#   - a FastAPI-nek megmondjuk a `root_path`-et (OpenAPI docs, redirect building)
#   - a HTML-be `<base>` tag + meta tag kerül, hogy a frontend tudja a prefixet
#   - a login/logout redirect-eket manuálisan prefix-eljük
#
# Alapérték: üres = root telepítés (a jelenlegi működés).
def _normalize_root_path(raw: str) -> str:
    """Ha van érték, `/`-vel kezdődjön és NE `/`-re végződjön."""
    p = (raw or "").strip()
    if not p:
        return ""
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/")


ROOT_PATH = _normalize_root_path(os.environ.get("HTR_GROUND_ROOT_PATH", ""))


app = FastAPI(
    title="HTR-ground",
    description=(
        "Backend a HTR-ground javító eszközhöz.\n\n"
        "Demo / playground: HTR kimenetek (ALTO XML, PAGE XML, natív JSON) "
        "konverziója a belső szerkesztő formátumra."
    ),
    version="0.3.0",
    root_path=ROOT_PATH,
)

# ─── Session ─────────────────────────────────────────────────────────────
# HTTPS mögé (reverse proxy elé) tett telepítéshez a session cookie-ra
# Secure flaget teszünk, hogy sose menjen ki plaintext HTTP-n. Bekapcsolás:
#   HTR_GROUND_HTTPS=1 environment variable
_https_only = os.environ.get("HTR_GROUND_HTTPS", "").lower() in ("1", "true", "yes", "on")

app.add_middleware(
    SessionMiddleware,
    secret_key=AUTH_CONFIG["session_secret"],
    session_cookie=AUTH_CONFIG.get("session_cookie_name", "htrground_session"),
    max_age=AUTH_CONFIG.get("session_max_age_seconds", 604800),
    same_site="lax",
    https_only=_https_only,
)


# ─── Static: a frontend és a példák ──────────────────────────────────────
# Az examples-t StaticFiles-szal mountoljuk, hogy a frontend hivatkozhasson rá.
if EXAMPLES_DIR.exists():
    app.mount("/examples", StaticFiles(directory=str(EXAMPLES_DIR)), name="examples")


# ─── Frontend asset helper ───────────────────────────────────────────────
from fastapi.responses import HTMLResponse

# HTML-be a `{{ROOT_PATH}}` placeholder-t behelyettesítjük a runtime prefix-re.
# Így ugyanaz a frontend fájl kiszolgál root-mód (üres) és sub-path módban is.
_HTML_TEMPLATE_MARKER = "{{ROOT_PATH}}"


def _serve_frontend_asset(name: str, media_type: str):
    path = FRONTEND_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{name} nem található: {path}")
    # HTML-t template-eljük, hogy a prefix mindig helyes legyen
    if media_type.startswith("text/html"):
        html = path.read_text(encoding="utf-8")
        html = html.replace(_HTML_TEMPLATE_MARKER, ROOT_PATH)
        return HTMLResponse(content=html)
    return FileResponse(str(path), media_type=media_type)


def _prefixed(url: str) -> str:
    """Egy belső URL prefix-elése — a redirect-ekhez.

    - Az abszolút HTTP(S) URL-eket változatlanul hagyjuk
    - A `/`-vel kezdődő path-hoz hozzáfűzzük a ROOT_PATH-ot (ha van)
    """
    if not url:
        return url
    if url.startswith(("http://", "https://", "//")):
        return url
    if not ROOT_PATH:
        return url
    # Elkerüljük, hogy már prefix-elt URL-re megint rárakjuk
    if url.startswith(ROOT_PATH + "/") or url == ROOT_PATH:
        return url
    if not url.startswith("/"):
        url = "/" + url
    return ROOT_PATH + url


# ─── HTML oldalak ────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def serve_landing():
    """Kezdőoldal — két kártya: Demó / Projektek."""
    return _serve_frontend_asset("landing.html", "text/html")


@app.get("/demo", include_in_schema=False)
def serve_demo():
    """A demó editor (feltöltéses, nyilvános)."""
    return _serve_frontend_asset("editor.html", "text/html")


@app.get("/login", include_in_schema=False)
def serve_login():
    return _serve_frontend_asset("login.html", "text/html")


# Static assets — ELŐBB, hogy a /projects/{...} path-catch-all ne kapja be őket
@app.get("/editor.css", include_in_schema=False)
def serve_editor_css():
    return _serve_frontend_asset("editor.css", "text/css")


@app.get("/editor.js", include_in_schema=False)
def serve_editor_js():
    return _serve_frontend_asset("editor.js", "application/javascript")


@app.get("/projects.js", include_in_schema=False)
def serve_projects_js():
    return _serve_frontend_asset("projects.js", "application/javascript")


@app.get("/projects.css", include_in_schema=False)
def serve_projects_css():
    return _serve_frontend_asset("projects.css", "text/css")


@app.get("/projects", include_in_schema=False)
def serve_projects_page(request: Request):
    """Projekt böngésző. Belépés szükséges."""
    redirect = require_auth_or_redirect(request)
    if redirect is not None:
        return redirect
    return _serve_frontend_asset("projects.html", "text/html")


@app.get("/projects/edit", include_in_schema=False)
def serve_project_editor(request: Request):
    """Projekt editor mód. Az editor.html-t szolgáljuk ki; a JS a query
    paraméterekből (`path`, `basename`) tudja mit kell betölteni."""
    redirect = require_auth_or_redirect(request)
    if redirect is not None:
        return redirect
    return _serve_frontend_asset("editor.html", "text/html")


@app.get("/projects/{deep_path:path}", include_in_schema=False)
def serve_projects_page_deep(request: Request, deep_path: str):
    """Ugyanazt a HTML-t szolgáljuk ki tetszőleges /projects/… al-path-ra;
    a projects.js olvassa a location.pathname-t és aszerint jelenít meg."""
    redirect = require_auth_or_redirect(request)
    if redirect is not None:
        return redirect
    return _serve_frontend_asset("projects.html", "text/html")


# ─── Auth endpointok ─────────────────────────────────────────────────────
@app.post("/login", include_in_schema=False)
async def do_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form(None),
):
    if not verify_credentials(username, password):
        # Hibás usernév vagy jelszó — vissza a login oldalra
        target = f"/login?error=1"
        if next:
            target += f"&next={next}"
        return RedirectResponse(url=_prefixed(target), status_code=303)
    request.session["username"] = username
    # Régi mezőt (v1) töröljük, ha valamiért ottragadt volna
    request.session.pop("auth", None)
    return RedirectResponse(url=_prefixed(next or "/projects"), status_code=303)


@app.post("/logout", include_in_schema=False)
async def do_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url=_prefixed("/"), status_code=303)


@app.get("/api/session")
def api_session(request: Request):
    """A frontend lekérdezheti a belépési állapotot.

    Válasz:
        - nem-authozott: {"authenticated": false}
        - authozott:     {"authenticated": true, "username": "...",
                          "display_name": "...", "is_admin": bool}
    """
    return session_info(request)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ─── Konverzió ────────────────────────────────────────────────────────────
@app.post("/api/convert")
async def api_convert(
    file: UploadFile = File(..., description="HTR fájl: ALTO XML, PAGE XML vagy natív JSON"),
    format: Optional[str] = Form(
        None,
        description='Opcionális: "alto-xml" | "page-xml" | "json". Ha üres, autodetekció.',
    ),
):
    """
    Bemenet:
        - `file`: multipart fájl
        - `format` (opcionális): kényszerített formátum, különben autodetekció

    Válasz:
        {
          "format_detected": "alto-xml",
          "page": { regions: [...], image_width, image_height, source_format }
        }
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="A feltöltött fájl üres.")

    try:
        if format:
            page = convert(data, filename=file.filename, format=format)
            detected = format
        else:
            detected = detect_format(data, file.filename)
            page = convert(data, filename=file.filename, format=detected)
    except UnknownFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # XML / JSON parsing hiba, séma validation, stb.
        raise HTTPException(
            status_code=422,
            detail=f"Konverziós hiba ({format or 'autodetekció'}): {e}",
        )

    return JSONResponse({
        "format_detected": detected,
        "page": page.model_dump(exclude_none=True),
    })


# ─── Export ──────────────────────────────────────────────────────────────
from fastapi import Body
from fastapi.responses import Response


@app.post("/api/export")
async def api_export(payload: dict = Body(...)):
    """
    Bemenet:
        {
          "page":   { regions: [...], image_width?, image_height? },
          "format": "json" | "alto-xml" | "page-xml",
          "basename":       "opcionális, a letöltési fájlnév alapja",
          "image_filename": "opcionális, PAGE XML imageFilename attribútuma"
        }

    Válasz: a szerializált tartalom mint attachment.
    """
    fmt = payload.get("format")
    if fmt not in EXPORT_MIME:
        raise HTTPException(status_code=400, detail=f"Ismeretlen format: {fmt!r}")

    raw_page = payload.get("page")
    if not isinstance(raw_page, dict):
        raise HTTPException(status_code=400, detail="Hiányzó vagy hibás `page` mező.")

    try:
        page = Page.model_validate(raw_page)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Érvénytelen Page: {e}")

    image_filename = payload.get("image_filename") or ""
    try:
        content = export_page(page, fmt, image_filename=image_filename)
    except UnknownFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export hiba: {e}")

    basename = payload.get("basename") or "corrected"
    filename = f"{basename}{EXPORT_EXT[fmt]}"
    return Response(
        content=content,
        media_type=EXPORT_MIME[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── Kétrétegű PDF export ────────────────────────────────────────────────
@app.post("/api/export-pdf")
async def api_export_pdf(
    page: str = Form(..., description="Page JSON string"),
    image: UploadFile = File(..., description="Az oldal képfájlja"),
    basename: Optional[str] = Form(None),
):
    """
    Kétrétegű, kereshető PDF export.

    Bemenet multipart:
      - `page`:     Page objektum JSON stringként
      - `image`:    az oldal képfájlja (jpg/png/…)
      - `basename`: opcionális, a letöltési fájlnév alapja
    """
    try:
        page_data = _json.loads(page)
    except _json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Hibás page JSON: {e}")
    try:
        page_obj = Page.model_validate(page_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Érvénytelen Page: {e}")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Üres képfájl.")

    try:
        pdf_bytes = to_pdf.export(page_obj, image_bytes)
    except RuntimeError as e:
        # Hiányzó font vagy hasonló infrastruktúra-hiba
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF export hiba: {e}")

    filename = f"{basename or 'corrected'}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── Projektek: mappa-tallózó API ────────────────────────────────────────
def _augment_with_presence(body: dict, current_user: str) -> dict:
    """A listázó válaszába beleírjuk a presence-t a párokhoz.

    A saját usernévet ki hagyjuk a jelzésekből — csak akkor van értelme
    „X van itt", ha valaki más az.
    """
    path = body.get("path", "")
    for pair in body.get("pairs", []):
        presence = presence_mod.format_for_pair(path, pair["basename"], exclude=current_user)
        if presence:
            pair["presence"] = presence
    return body


@app.get("/api/projects")
def api_projects_root(user: str = Depends(require_auth)):
    body = list_folder("", username=user)
    return _augment_with_presence(body, user)


@app.get("/api/projects/{path:path}")
def api_projects_path(path: str, user: str = Depends(require_auth)):
    try:
        body = list_folder(path, username=user)
    except AccessDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except PathEscapeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Nem létező mappa: {path!r}")
    except NotADirectoryError:
        raise HTTPException(status_code=400, detail=f"Nem mappa: {path!r}")
    return _augment_with_presence(body, user)


# ─── Egy projekt-pár betöltése / mentése ─────────────────────────────────
@app.get("/api/project-file")
def api_project_file_get(path: str, basename: str, user: str = Depends(require_auth)):
    """Egy pár annotáció + metaadatok betöltése editálásra.

    A képet külön endpoint szolgálja ki (`/api/project-image`).
    """
    try:
        loaded = load_pair(path, basename, username=user)
    except AccessDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except PathEscapeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (FileNotFoundError, NotADirectoryError) as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Az annotációt átkonvertáljuk a belső Page-re
    try:
        page = convert(loaded["annotation_bytes"], filename=loaded["annotation_filename"])
    except UnknownFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Konverziós hiba: {e}")

    image_url = (
        _prefixed(f"/api/project-image?path={path}&basename={basename}")
        if loaded["image_filename"] else None
    )
    # Meta (státusz + audit) — mindig hozzáadjuk a válaszhoz
    folder = resolve_safe(path)
    meta_info = pair_meta.read(folder, basename)
    return {
        "path":                loaded["path"],
        "basename":            loaded["basename"],
        "annotation_filename": loaded["annotation_filename"],
        "annotation_format":   loaded["annotation_format"],
        "image_filename":      loaded["image_filename"],
        "image_url":           image_url,
        "meta":                meta_info,
        "save_format":         loaded["save_format"],
        "page":                page.model_dump(exclude_none=True),
    }


@app.get("/api/project-image")
def api_project_image(path: str, basename: str, user: str = Depends(require_auth)):
    """A pár képfájljának kiszolgálása."""
    try:
        found = find_pair(path, basename, username=user)
    except AccessDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except PathEscapeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (FileNotFoundError, NotADirectoryError) as e:
        raise HTTPException(status_code=404, detail=str(e))

    image = found["image"]
    if image is None:
        raise HTTPException(status_code=404, detail="Nincs képfájl ehhez a párhoz.")
    ext = image.suffix.lower()
    media = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".tif": "image/tiff", ".tiff": "image/tiff",
        ".gif": "image/gif",
    }.get(ext, "application/octet-stream")
    return FileResponse(str(image), media_type=media)


@app.put("/api/project-file")
async def api_project_file_put(
    request: Request,
    path: str,
    basename: str,
    format: Optional[str] = None,
    user: str = Depends(require_auth),
):
    """Projekt-fájl mentése (felülírás).

    Body:  { "page": { ... } }
    Query: `format` opcionális; ha nincs, a `.htrground.json` `save_format`
           vagy az eredeti annotation_format lesz használva.
    """
    body = await request.json()
    raw_page = body.get("page")
    if not isinstance(raw_page, dict):
        raise HTTPException(status_code=400, detail="Hiányzó vagy hibás `page` mező.")

    try:
        page = Page.model_validate(raw_page)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Érvénytelen Page: {e}")

    # Format eldöntése: query > directory config > loaded format
    fmt = format
    if not fmt:
        try:
            loaded = load_pair(path, basename, username=user)
            fmt = loaded["save_format"]
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except (FileNotFoundError, NotADirectoryError) as e:
            raise HTTPException(status_code=404, detail=str(e))
        except PathEscapeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    try:
        content = export_page(page, fmt, image_filename=body.get("image_filename") or "")
        target  = save_pair(path, basename, content, fmt, username=user)
        # Audit: kinek a nevére / mikor rögzítjük az utolsó mentést
        pair_meta.record_edit(target.parent, basename, user)
    except AccessDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except UnknownFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PathEscapeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (FileNotFoundError, NotADirectoryError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Mentési hiba: {e}")

    return {
        "saved_filename": target.name,
        "save_format":    fmt,
    }


# ─── Státusz (per-fájl sidecar) ──────────────────────────────────────────
@app.get("/api/status-values")
def api_status_values():
    """A frontend dropdown-ját tápláló érvényes státusz-lista."""
    return {
        "values":  list(pair_meta.VALID_STATUSES),
        "default": pair_meta.DEFAULT_STATUS,
    }


@app.put("/api/project-status")
async def api_project_status_put(
    request: Request,
    path: str,
    basename: str,
    user: str = Depends(require_auth),
):
    """Egy pár státuszának állítása.

    Body:
        { "status": "folyamatban", "notes": "..." (opcionális) }
    """
    body = await request.json()
    status = body.get("status")
    if not isinstance(status, str):
        raise HTTPException(status_code=400, detail="Hiányzó `status` mező.")
    notes = body.get("notes")

    try:
        found = find_pair(path, basename, username=user)
    except AccessDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except PathEscapeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (FileNotFoundError, NotADirectoryError) as e:
        raise HTTPException(status_code=404, detail=str(e))

    folder = found["folder"]
    # A pár tényleg létezik-e?
    if found["image"] is None and not found["annotations"]:
        raise HTTPException(
            status_code=404,
            detail=f"Nincs ilyen pár: {path}/{basename}",
        )

    try:
        result = pair_meta.set_status(folder, basename, status, user, notes=notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


# ─── Presence (jelenlét) ─────────────────────────────────────────────────
@app.post("/api/presence/heartbeat")
async def api_presence_heartbeat(
    request: Request,
    user: str = Depends(require_auth),
):
    """A frontend időnként (kb. 25 mp-enként) jelzi, hogy még itt van.

    Body:
        { "path": "Bakonykuti/1949", "basename": "sample" }

    Válasz: kik vannak még a fájlon (az aktuális usert kihagyva).
    """
    body = await request.json()
    path     = body.get("path", "")
    basename = body.get("basename", "")
    if not basename:
        raise HTTPException(status_code=400, detail="Hiányzó `basename`.")
    presence_mod.tracker.heartbeat(path, basename, user)
    others = presence_mod.format_for_pair(path, basename, exclude=user)
    return {"ok": True, "others": others}


@app.post("/api/presence/leave")
async def api_presence_leave(
    request: Request,
    user: str = Depends(require_auth),
):
    """Explicit kilépés — `beforeunload` esetén hívja a kliens."""
    body = await request.json()
    path     = body.get("path", "")
    basename = body.get("basename", "")
    if basename:
        presence_mod.tracker.leave(path, basename, user)
    return {"ok": True}


@app.get("/api/presence")
def api_presence_get(
    path: str,
    basename: str,
    user: str = Depends(require_auth),
):
    """Aktuális presence egy párra — használhatja az editor beérkezéskor."""
    others = presence_mod.format_for_pair(path, basename, exclude=user)
    return {"others": others}
