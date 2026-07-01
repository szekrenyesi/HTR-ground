"""
Format detection + dispatch a megfelelő konverterre.

Használat:
    page = convert(file_bytes, filename="x.xml")
    # vagy explicit:
    page = convert(file_bytes, format="alto-xml")
"""
from __future__ import annotations

import json as _json
from typing import Optional
from ..schema import Page
from . import alto, page as page_xml, htr_json, to_alto, to_page


class UnknownFormatError(ValueError):
    pass


# ─── Export dispatch ─────────────────────────────────────────────────────
# format: "json" | "alto-xml" | "page-xml"
def export(page: Page, format: str, *, image_filename: str = "") -> bytes:
    if format == "json":
        return _json.dumps(
            page.model_dump(exclude_none=True), ensure_ascii=False, indent=2
        ).encode("utf-8")
    if format == "alto-xml":
        return to_alto.export(page)
    if format == "page-xml":
        return to_page.export(page, image_filename=image_filename)
    raise UnknownFormatError(f"Ismeretlen export formátum: {format!r}")


EXPORT_MIME = {
    "json":     "application/json; charset=utf-8",
    "alto-xml": "application/xml; charset=utf-8",
    "page-xml": "application/xml; charset=utf-8",
}

EXPORT_EXT = {
    "json":     ".json",
    "alto-xml": ".alto.xml",
    "page-xml": ".page.xml",
}


def detect_format(data: bytes, filename: Optional[str] = None) -> str:
    """
    Visszaadja: "alto-xml" | "page-xml" | "json"
    A tartalom alapján döntünk; a fájlnév csak gyenge hint.
    """
    head = data[:2048].lstrip()

    # JSON?
    if head.startswith(b"{") or head.startswith(b"["):
        return "json"

    # XML — nézzük meg melyik dialektus
    if head.startswith(b"<?xml") or head.startswith(b"<"):
        # Az első ~2KB-ban szinte biztosan megtaláljuk a gyökér elemet vagy a namespace-t
        sample = data[:4096].lower()
        if b"<alto" in sample or b"loc.gov/standards/alto" in sample:
            return "alto-xml"
        if b"<pcgts" in sample or b"primaresearch.org/page" in sample or b"schema/pagecontent" in sample:
            return "page-xml"
        raise UnknownFormatError(
            "Nem ismert XML dialektus (sem ALTO, sem PAGE). "
            "Ellenőrizd a gyökér elemet."
        )

    raise UnknownFormatError(
        "A fájl nem tűnik sem JSON-nak, sem XML-nek."
    )


def convert(data: bytes, *, filename: Optional[str] = None, format: Optional[str] = None) -> Page:
    fmt = format or detect_format(data, filename)
    if fmt == "alto-xml":
        page = alto.parse(data)
    elif fmt == "page-xml":
        page = page_xml.parse(data)
    elif fmt == "json":
        page = htr_json.parse(data)
    else:
        raise UnknownFormatError(f"Ismeretlen formátum: {fmt!r}")
    page.source_format = fmt
    return page
