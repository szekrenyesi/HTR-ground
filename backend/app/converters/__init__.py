"""
Format detection + dispatch a megfelelő konverterre.

Használat:
    page = convert(file_bytes, filename="x.xml")
    # vagy explicit:
    page = convert(file_bytes, format="alto-xml")
"""
from __future__ import annotations

from typing import Optional
from ..schema import Page
from . import alto, page as page_xml, htr_json


class UnknownFormatError(ValueError):
    pass


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
