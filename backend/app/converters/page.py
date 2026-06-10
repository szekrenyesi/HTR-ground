"""
PAGE XML → belső Page séma.

Specifikáció: https://www.primaresearch.org/tools/PAGELibraries
Használja: Transkribus, eScriptorium, OCR-D, stb.

A PAGE XML mindig ad poligont (<Coords points="x1,y1 x2,y2 ..."/>),
nem kell szintetizálni.

A szöveg a <TextEquiv><Unicode> elemben van. Több TextEquiv (pl. különböző
indexű alternatívák) is lehet — az `index="0"`-t, vagy ha nincs index,
az elsőt preferáljuk.

Megjegyzés: ehhez a konverterhez egyelőre nincs valódi minta fájlunk a
projektben. A spec alapján íródott; az első PAGE XML beérkezésekor
érdemes ellenőrizni és kiegészíteni az `examples/`-be egy mintával.
"""
from __future__ import annotations

from typing import List, Optional
from lxml import etree

from ..schema import Page, Region, Line, Point


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _children_local(elem, local_name: str):
    return [c for c in elem if _strip_ns(c.tag) == local_name]


def _descendants_local(elem, local_name: str):
    return [e for e in elem.iter() if _strip_ns(e.tag) == local_name]


def _parse_points(s: str) -> List[Point]:
    """PAGE: 'x1,y1 x2,y2 ...' (egész számok jellemzően)."""
    if not s:
        return []
    pts: List[Point] = []
    for tok in s.split():
        if "," not in tok:
            continue
        x_str, y_str = tok.split(",", 1)
        pts.append([float(x_str), float(y_str)])
    return pts


def _coords_of(elem) -> List[Point]:
    """<Coords points="..."/> közvetlen gyerek."""
    for c in _children_local(elem, "Coords"):
        return _parse_points(c.get("points", ""))
    return []


def _baseline_of(elem) -> Optional[List[Point]]:
    for b in _children_local(elem, "Baseline"):
        pts = _parse_points(b.get("points", ""))
        return pts if pts else None
    return None


def _rect_from_polygon(poly: List[Point]) -> List[float]:
    if not poly:
        return [0.0, 0.0, 0.0, 0.0]
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, y0 = min(xs), min(ys)
    x1, y1 = max(xs), max(ys)
    return [x0, y0, x1 - x0, y1 - y0]


def _text_of_line(line_elem) -> str:
    """
    <TextEquiv><Unicode>...</Unicode></TextEquiv>
    Ha több TextEquiv van, az `index="0"`-t (vagy elsőt) választjuk.
    """
    equivs = _children_local(line_elem, "TextEquiv")
    if not equivs:
        return ""
    # Próbáljuk az index alapján rendezni
    def _idx(e):
        try:
            return int(e.get("index", "0"))
        except (TypeError, ValueError):
            return 0
    equivs_sorted = sorted(equivs, key=_idx)
    for eq in equivs_sorted:
        for uc in _children_local(eq, "Unicode"):
            return uc.text or ""
    return ""


def parse(data: bytes) -> Page:
    parser = etree.XMLParser(recover=True, remove_blank_text=False)
    root = etree.fromstring(data, parser=parser)

    # Page méret
    img_w: Optional[int] = None
    img_h: Optional[int] = None
    pages = _descendants_local(root, "Page")
    if pages:
        pe = pages[0]
        try:
            img_w = int(float(pe.get("imageWidth"))) if pe.get("imageWidth") else None
            img_h = int(float(pe.get("imageHeight"))) if pe.get("imageHeight") else None
        except (TypeError, ValueError):
            pass

    regions: List[Region] = []
    for tr in _descendants_local(root, "TextRegion"):
        r_coords = _coords_of(tr)
        r_rect = _rect_from_polygon(r_coords)
        lines: List[Line] = []

        for tl in _children_local(tr, "TextLine"):
            l_coords = _coords_of(tl)
            l_rect = _rect_from_polygon(l_coords)
            baseline = _baseline_of(tl)
            text = _text_of_line(tl)
            lines.append(Line(
                coords=l_coords,
                rect=l_rect,
                baseline=baseline,
                text=text,
            ))

        regions.append(Region(coords=r_coords, rect=r_rect, lines=lines))

    return Page(
        regions=regions,
        image_width=img_w,
        image_height=img_h,
    )
