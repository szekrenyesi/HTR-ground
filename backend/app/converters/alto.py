"""
ALTO XML → belső Page séma.

Specifikáció: https://www.loc.gov/standards/alto/
Támogatott verziók: v2 / v3 / v4 (a használt elemkészlet közös).

Az ALTO általában csak TÉGLALAPOKAT ad (HPOS/VPOS/WIDTH/HEIGHT attribútumokkal).
A poligonokat ezekből szintetizáljuk (4 sarokpont).

Ha az ALTO tartalmaz <Shape><Polygon POINTS="..."/></Shape> elemet (v4),
azt használjuk a téglalap helyett.
"""
from __future__ import annotations

from typing import List, Optional, Tuple
from lxml import etree

from ..schema import Page, Region, Line, Point


def _strip_ns(tag: str) -> str:
    """`{http://...}TextLine` → `TextLine`"""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _findall_local(elem, local_name: str):
    """Mindegy milyen namespace-ben van, helyi név alapján keres."""
    return [e for e in elem.iter() if _strip_ns(e.tag) == local_name]


def _children_local(elem, local_name: str):
    """Csak közvetlen gyerekek."""
    return [c for c in elem if _strip_ns(c.tag) == local_name]


def _rect_from_attrs(elem) -> Optional[List[float]]:
    """[HPOS, VPOS, WIDTH, HEIGHT] attribútumokból [x, y, w, h]."""
    try:
        x = float(elem.get("HPOS"))
        y = float(elem.get("VPOS"))
        w = float(elem.get("WIDTH"))
        h = float(elem.get("HEIGHT"))
    except (TypeError, ValueError):
        return None
    return [x, y, w, h]


def _rect_to_polygon(rect: List[float]) -> List[Point]:
    """[x, y, w, h] → 4 sarokpontos poligon, óramutató járásával egyező."""
    x, y, w, h = rect
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _parse_points(s: str) -> List[Point]:
    """
    Ponttömb formátumok:
      - ALTO Polygon: "x1,y1 x2,y2 ..." VAGY "x1 y1 x2 y2 ..."
      - BASELINE attribútum: "x1,y1 x2,y2 ..."
    """
    if not s:
        return []
    tokens = s.replace(",", " ").split()
    nums = [float(t) for t in tokens]
    return [[nums[i], nums[i + 1]] for i in range(0, len(nums) - 1, 2)]


def _polygon_from_shape(elem) -> Optional[List[Point]]:
    """Ha van <Shape><Polygon POINTS="..."/></Shape>, abból szedjük ki."""
    for shape in _children_local(elem, "Shape"):
        for poly in _children_local(shape, "Polygon"):
            pts = poly.get("POINTS")
            if pts:
                return _parse_points(pts)
    return None


def _coords_for(elem) -> Tuple[List[float], List[Point]]:
    """
    Egy ALTO elemhez (TextBlock / TextLine) visszaad:
      - rect: [x, y, w, h]
      - coords: poligon (poligonból vagy szintetizálva a téglalapból)
    """
    rect = _rect_from_attrs(elem) or [0.0, 0.0, 0.0, 0.0]
    poly = _polygon_from_shape(elem)
    if poly is None:
        poly = _rect_to_polygon(rect)
    return rect, poly


def _text_of_line(line_elem) -> str:
    """
    Egy <TextLine> szöveges tartalma.
    Több <String CONTENT="..."/> elemet szóközzel köt össze.
    A SP (whitespace) elemet figyelembe vesszük.
    HYP-et (sortörési kötőjel) a végére fűzzük.
    """
    parts: List[str] = []
    for child in line_elem:
        name = _strip_ns(child.tag)
        if name == "String":
            content = child.get("CONTENT")
            if content is not None:
                parts.append(content)
        elif name == "SP":
            # explicit szóköz — csak akkor adjuk hozzá, ha még nincs a végén
            if parts and not parts[-1].endswith(" "):
                parts.append(" ")
        elif name == "HYP":
            content = child.get("CONTENT") or "-"
            parts.append(content)
    return "".join(parts)


def parse(data: bytes) -> Page:
    """ALTO XML bájtfolyam → Page."""
    # `recover=True`: legyünk megengedők kis hibákra
    parser = etree.XMLParser(recover=True, remove_blank_text=False)
    root = etree.fromstring(data, parser=parser)

    # Page méret
    img_w: Optional[int] = None
    img_h: Optional[int] = None
    page_elems = _findall_local(root, "Page")
    if page_elems:
        pe = page_elems[0]
        try:
            img_w = int(float(pe.get("WIDTH"))) if pe.get("WIDTH") else None
            img_h = int(float(pe.get("HEIGHT"))) if pe.get("HEIGHT") else None
        except (TypeError, ValueError):
            pass

    regions: List[Region] = []
    for block in _findall_local(root, "TextBlock"):
        rect, coords = _coords_for(block)
        lines: List[Line] = []

        for line_elem in _children_local(block, "TextLine"):
            line_rect, line_coords = _coords_for(line_elem)
            baseline_str = line_elem.get("BASELINE")
            baseline = _parse_points(baseline_str) if baseline_str else None
            text = _text_of_line(line_elem)
            lines.append(Line(
                coords=line_coords,
                rect=line_rect,
                baseline=baseline if baseline else None,
                text=text,
            ))

        regions.append(Region(coords=coords, rect=rect, lines=lines))

    return Page(
        regions=regions,
        image_width=img_w,
        image_height=img_h,
    )
