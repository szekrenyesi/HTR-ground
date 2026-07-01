"""
Belső Page → ALTO XML v4.

Programmatically építjük, nem sablonnal — kevesebb függőség, tisztább kód.
A polygon a `<Shape><Polygon POINTS="..."/></Shape>` blokkban kerül ki
(nem csak a bounding box), így a HTR-ground által előállított ALTO
kompatibilis az importerekkel is (kör-oda-vissza).
"""
from __future__ import annotations

from typing import List

from lxml import etree

from ..schema import Page, Region, Line, Point


ALTO_NS = "http://www.loc.gov/standards/alto/ns-v4#"
XSI_NS  = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = (
    "http://www.loc.gov/standards/alto/ns-v4# "
    "https://www.loc.gov/standards/alto/v4/alto.xsd"
)


def _fmt_int(v) -> str:
    """Ha kerekítve egész, egészként; egyébként vessző nélkül float."""
    fv = float(v)
    iv = int(round(fv))
    return str(iv) if abs(fv - iv) < 1e-6 else f"{fv:g}"


def _points_attr(coords: List[Point]) -> str:
    return " ".join(f"{_fmt_int(x)},{_fmt_int(y)}" for x, y in coords)


def _add_shape(parent, coords: List[Point]) -> None:
    if not coords:
        return
    shape = etree.SubElement(parent, f"{{{ALTO_NS}}}Shape")
    poly = etree.SubElement(shape, f"{{{ALTO_NS}}}Polygon")
    poly.set("POINTS", _points_attr(coords))


def _rect_attrs(elem, rect) -> None:
    x, y, w, h = rect
    elem.set("HPOS",   _fmt_int(x))
    elem.set("VPOS",   _fmt_int(y))
    elem.set("WIDTH",  _fmt_int(w))
    elem.set("HEIGHT", _fmt_int(h))


def export(page: Page) -> bytes:
    """Page → ALTO v4 XML bájtfolyam (UTF-8, deklarációval)."""

    nsmap = {None: ALTO_NS, "xsi": XSI_NS}
    root = etree.Element(f"{{{ALTO_NS}}}alto", nsmap=nsmap)
    root.set(f"{{{XSI_NS}}}schemaLocation", SCHEMA_LOCATION)

    # <Description>
    desc = etree.SubElement(root, f"{{{ALTO_NS}}}Description")
    mu = etree.SubElement(desc, f"{{{ALTO_NS}}}MeasurementUnit")
    mu.text = "pixel"
    etree.SubElement(desc, f"{{{ALTO_NS}}}sourceImageInformation")
    etree.SubElement(desc, f"{{{ALTO_NS}}}Processing")

    # <Styles> — üresen, de a kliensek szeretik
    styles = etree.SubElement(root, f"{{{ALTO_NS}}}Styles")
    etree.SubElement(styles, f"{{{ALTO_NS}}}TextStyle")
    etree.SubElement(styles, f"{{{ALTO_NS}}}ParagraphStyle")

    # <Layout><Page><PrintSpace>...
    layout = etree.SubElement(root, f"{{{ALTO_NS}}}Layout")
    page_elem = etree.SubElement(layout, f"{{{ALTO_NS}}}Page")
    if page.image_width is not None:
        page_elem.set("WIDTH", str(int(page.image_width)))
    if page.image_height is not None:
        page_elem.set("HEIGHT", str(int(page.image_height)))
    page_elem.set("PHYSICAL_IMG_NR", "1")
    page_elem.set("ID", "p1")

    print_space = etree.SubElement(page_elem, f"{{{ALTO_NS}}}PrintSpace")
    if page.image_width is not None and page.image_height is not None:
        _rect_attrs(print_space, [0, 0, page.image_width, page.image_height])

    for ri, region in enumerate(page.regions):
        block = etree.SubElement(print_space, f"{{{ALTO_NS}}}TextBlock")
        block.set("ID", f"r{ri}")
        _rect_attrs(block, region.rect)
        _add_shape(block, region.coords)

        for li, line in enumerate(region.lines, start=1):
            tl = etree.SubElement(block, f"{{{ALTO_NS}}}TextLine")
            tl.set("ID", f"r{ri}l{li}")
            _rect_attrs(tl, line.rect)
            tl.set("BASEDIRECTION", "ltr")
            if line.baseline:
                tl.set("BASELINE", _points_attr(line.baseline))
            _add_shape(tl, line.coords)

            s = etree.SubElement(tl, f"{{{ALTO_NS}}}String")
            s.set("ID", f"r{ri}l{li}_s")
            _rect_attrs(s, line.rect)
            s.set("CONTENT", line.text or "")

    etree.indent(root, space="  ")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
