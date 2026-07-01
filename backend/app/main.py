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
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import AUTH_CONFIG, is_authenticated, require_auth, require_auth_or_redirect, verify_password
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
    PathEscapeError,
    find_pair,
    list_folder,
    load_pair,
    save_pair,
)
from .schema import Page


# Projekt gyökér: backend/app/main.py → backend/app → backend → REPO_ROOT
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
EXAMPLES_DIR = REPO_ROOT / "examples"


app = FastAPI(
    title="HTR-ground",
    description=(
        "Backend a HTR-ground javító eszközhöz.\n\n"
        "Demo / playground: HTR kimenetek (ALTO XML, PAGE XML, natív JSON) "
        "konverziója a belső szerkesztő formátumra."
    ),
    version="0.2.0",
)

# ─── Session ─────────────────────────────────────────────────────────────
app.add_middleware(
    SessionMiddleware,
    secret_key=AUTH_CONFIG["session_secret"],
    session_cookie=AUTH_CONFIG.get("session_cookie_name", "htrground_session"),
    max_age=AUTH_CONFIG.get("session_max_age_seconds", 604800),
    same_site="lax",
)


# ─── Static: a frontend és a példák ──────────────────────────────────────
# Az examples-t StaticFiles-szal mountoljuk, hogy a frontend hivatkozhasson rá.
if EXAMPLES_DIR.exists():
    app.mount("/examples", StaticFiles(directory=str(EXAMPLES_DIR)), name="examples")


# ─── Frontend asset helper ───────────────────────────────────────────────
def _serve_frontend_asset(name: str, media_type: str) -> FileResponse:
    path = FRONTEND_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{name} nem található: {path}")
    return FileResponse(str(path), media_type=media_type)


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
    password: str = Form(...),
    next: Optional[str] = Form(None),
):
    if not verify_password(password):
        # Hibás jelszó — vissza a login oldalra
        target = f"/login?error=1"
        if next:
            target += f"&next={next}"
        return RedirectResponse(url=target, status_code=303)
    request.session["auth"] = True
    return RedirectResponse(url=next or "/projects", status_code=303)


@app.post("/logout", include_in_schema=False)
async def do_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/session")
def api_session(request: Request):
    """A frontend lekérdezheti, hogy be van-e lépve — pl. a landing-en."""
    return {"authenticated": is_authenticated(request)}


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
@app.get("/api/projects", dependencies=[Depends(require_auth)])
def api_projects_root():
    return list_folder("")


@app.get("/api/projects/{path:path}", dependencies=[Depends(require_auth)])
def api_projects_path(path: str):
    try:
        return list_folder(path)
    except PathEscapeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Nem létező mappa: {path!r}")
    except NotADirectoryError:
        raise HTTPException(status_code=400, detail=f"Nem mappa: {path!r}")


# ─── Egy projekt-pár betöltése / mentése ─────────────────────────────────
@app.get("/api/project-file", dependencies=[Depends(require_auth)])
def api_project_file_get(path: str, basename: str):
    """Egy pár annotáció + metaadatok betöltése editálásra.

    A képet külön endpoint szolgálja ki (`/api/project-image`).
    """
    try:
        loaded = load_pair(path, basename)
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
        f"/api/project-image?path={path}&basename={basename}"
        if loaded["image_filename"] else None
    )
    return {
        "path":                loaded["path"],
        "basename":            loaded["basename"],
        "annotation_filename": loaded["annotation_filename"],
        "annotation_format":   loaded["annotation_format"],
        "image_filename":      loaded["image_filename"],
        "image_url":           image_url,
        "save_format":         loaded["save_format"],
        "page":                page.model_dump(exclude_none=True),
    }


@app.get("/api/project-image", dependencies=[Depends(require_auth)])
def api_project_image(path: str, basename: str):
    """A pár képfájljának kiszolgálása."""
    try:
        found = find_pair(path, basename)
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


@app.put("/api/project-file", dependencies=[Depends(require_auth)])
async def api_project_file_put(
    request: Request,
    path: str,
    basename: str,
    format: Optional[str] = None,
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
            loaded = load_pair(path, basename)
            fmt = loaded["save_format"]
        except (FileNotFoundError, NotADirectoryError) as e:
            raise HTTPException(status_code=404, detail=str(e))
        except PathEscapeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    try:
        content = export_page(page, fmt, image_filename=body.get("image_filename") or "")
        target  = save_pair(path, basename, content, fmt)
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
