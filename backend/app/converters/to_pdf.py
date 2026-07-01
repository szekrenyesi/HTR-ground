"""
Belső Page + képbájtok → kétrétegű PDF (image + invisible searchable text).

- A kép alatti szöveg pozicionálva van (sorok baseline-jára), így a PDF
  szövegkeresés/másolás pontos.
- A szöveg TextMode.INVISIBLE-lel van kirajzolva → láthatatlan, de a PDF
  szöveg-extrakciós motorja (pl. pdftotext) megtalálja.

Font: `HTR_GROUND_FONT` env változó vagy `<repo>/fonts/EBGaramond-Regular.ttf`.
Ha nem elérhető, `RuntimeError` — a fő endpoint 500-zal válaszol egyértelmű
üzenettel.
"""
from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from fpdf import FPDF
from fpdf.enums import TextMode
from PIL import Image

from ..schema import Page, Line


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_FONT_PATH = REPO_ROOT / "fonts" / "EBGaramond-Regular.ttf"

# A képet ekkora szélességre méretezzük a PDF-hez, hogy a fájlméret kezelhető
# maradjon. A koordináták a PDF-ben az EREDETI kép pixelein alapulnak
# (a page méret is), az embedded kép csak vizuálisan méretezve van kisebbre.
IMAGE_TARGET_WIDTH = 1500
JPEG_QUALITY = 78


def _resolve_font(font_path: Optional[str] = None) -> Path:
    """A használt fontot adja vissza; hiba, ha egyik sincs meg."""
    if font_path:
        p = Path(font_path)
        if p.is_file():
            return p
    env = os.environ.get("HTR_GROUND_FONT")
    if env:
        p = Path(env)
        if p.is_file():
            return p
    if DEFAULT_FONT_PATH.is_file():
        return DEFAULT_FONT_PATH
    raise RuntimeError(
        "PDF exporthoz nem található Unicode font. "
        f"Vagy tedd ide: {DEFAULT_FONT_PATH}, "
        "vagy állítsd be a HTR_GROUND_FONT env változót egy .ttf fájlra."
    )


def _prepare_image(image_bytes: bytes, target_width: int) -> tuple[bytes, int, int]:
    """A képet downscale-eli és JPEG-be tömöríti. Visszatérés: (bytes, w, h)."""
    img = Image.open(BytesIO(image_bytes))
    orig_w, orig_h = img.size
    if orig_w > target_width:
        ratio  = target_width / orig_w
        new_w  = target_width
        new_h  = int(orig_h * ratio)
        img    = img.resize((new_w, new_h), Image.LANCZOS)
    else:
        new_w, new_h = orig_w, orig_h

    # PDF-hez konzisztens RGB kell
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue(), orig_w, orig_h


def _line_baseline_and_size(line: Line) -> tuple[float, float, float]:
    """(x, baseline_y, font_size) becslés a sor rect-jéből (és baseline-jából, ha van)."""
    x, y, w, h = line.rect
    # Alapból a rect alsó ~75%-ára tesszük a baseline-t
    if line.baseline and len(line.baseline) >= 1:
        # A baseline első pontja adja az x-et, átlagos y-t számolunk
        bx = float(line.baseline[0][0])
        by = sum(float(p[1]) for p in line.baseline) / len(line.baseline)
    else:
        bx = float(x)
        by = float(y) + float(h) * 0.75
    # Fontméret a sor magasságából (kb. 40%-a jó heurisztika)
    fsize = max(8.0, float(h) * 0.4)
    return bx, by, fsize


def export(
    page: Page,
    image_bytes: bytes,
    *,
    font_path: Optional[str] = None,
) -> bytes:
    """Page + képbájtok → PDF bájtok (invisible text overlay)."""
    if not image_bytes:
        raise ValueError("PDF exporthoz kell a képfájl bájtjai.")

    font = _resolve_font(font_path)
    jpeg_bytes, page_w, page_h = _prepare_image(image_bytes, IMAGE_TARGET_WIDTH)

    # Ha a Page-nek van image_width/image_height, azt preferáljuk (koordináták
    # ehhez vannak kalibrálva). Egyébként a kép natív méretét használjuk.
    if page.image_width  and page.image_height:
        page_w = int(page.image_width)
        page_h = int(page.image_height)

    pdf = FPDF(orientation="P", unit="pt", format=(page_w, page_h))
    pdf.set_auto_page_break(auto=False)
    pdf.add_font("body", "", str(font), uni=True)
    pdf.add_page()

    # 1. Kép (a PDF page-t kitölti; JPEG lekicsinyítve a fájlméret miatt)
    pdf.image(BytesIO(jpeg_bytes), x=0, y=0, w=page_w, h=page_h)

    # 2. Láthatatlan szövegek a sorok pozícióiban
    pdf.text_mode = TextMode.FILL

    for region in page.regions:
        for line in region.lines:
            text = (line.text or "").strip()
            if not text:
                continue
            bx, by, fsize = _line_baseline_and_size(line)
            pdf.set_font("body", "", fsize)
            # A pdf.text a baseline-hez rajzol — pontosan amit szeretnénk
            try:
                with pdf.local_context(fill_opacity=0.01):
                    pdf.text(x=bx, y=by, text=text)
            except Exception:
                # Ha karakter nem kódolható, egy soronyi hiba ne állítsa le
                # az egészet — egyszerűen kihagyjuk azt a sort.
                continue

    out = BytesIO()
    pdf.output(out)
    return out.getvalue()
