"""
HTR-ground backend — FastAPI app.

Futtatás (a backend/ mappából):
    uvicorn app.main:app --reload --port 8000

Endpoint-ok:
    GET  /                  → editor.html kiszolgálása
    GET  /examples/...      → a példa fájlok (kép, JSON, ALTO) kiszolgálása
    POST /api/convert       → HTR fájl (JSON / ALTO XML / PAGE XML) → belső JSON
    GET  /api/health        → egyszerű health check
    GET  /docs              → auto Swagger UI
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .converters import convert, detect_format, UnknownFormatError


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
    version="0.1.0",
)


# ─── Static: a frontend és a példák ──────────────────────────────────────
# Az examples-t StaticFiles-szal mountoljuk, hogy a frontend hivatkozhasson rá.
if EXAMPLES_DIR.exists():
    app.mount("/examples", StaticFiles(directory=str(EXAMPLES_DIR)), name="examples")


@app.get("/", include_in_schema=False)
def serve_editor():
    """A frontend belépési pont — az editor.html."""
    index = FRONTEND_DIR / "editor.html"
    if not index.exists():
        raise HTTPException(status_code=500, detail=f"editor.html nem található: {index}")
    return FileResponse(str(index), media_type="text/html")


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
