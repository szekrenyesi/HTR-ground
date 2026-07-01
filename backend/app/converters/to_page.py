"""
Belső Page → PAGE XML (PRImA / PAGE Content 2019-07-15).

Specifikáció: https://www.primaresearch.org/tools/PAGELibraries
Használja: Transkribus, eScriptorium, OCR-D, stb.

A PAGE-ben natívan a poligon a `<Coords points="x1,y1 x2,y2 ..."/>`-ban van;
a bounding box-ot nem kell külön attribútumként megadni.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from lxml import etree

from ..schema import Page, Region, Line, Point


PAGE_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
XSI_NS  = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = (
    "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15 "
    "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15/pagecontent.xsd"
)


def _fmt_int(v) -> str:
    fv = float(v)
    iv = int(round(fv))
    return str(iv) if abs(fv - iv) < 1e-6 else f"{fv:g}"


def _points_attr(coords: List[Point]) -> str:
    return " ".join(f"{_fmt_int(x)},{_fmt_int(y)}" for x, y in coords)


def _add_coords(parent, coords: List[Point]) -> None:
    if not coords:
        # A PAGE séma megköveteli a Coords elemet — üres poligonnal is
        etree.SubElement(parent, f"{{{PAGE_NS}}}Coords").set("points", "")
        return
    el = etree.SubElement(parent, f"{{{PAGE_NS}}}Coords")
    el.set("points", _points_attr(coords))


def _add_text_equiv(parent, text: str) -> None:
    eq = etree.SubElement(parent, f"{{{PAGE_NS}}}TextEquiv")
    uc = etree.SubElement(eq, f"{{{PAGE_NS}}}Unicode")
    uc.text = text or ""


def export(page: Page, image_filename: str = "") -> bytes:
    """Page → PAGE XML bájtfolyam (UTF-8, deklarációval).

    `image_filename` a Page elem `imageFilename` attribútumába kerül; a spec
    kötelezővé teszi, viszont a Page nem tárolja — a hívó tudja megadni.
    """
    nsmap = {None: PAGE_NS, "xsi": XSI_NS}
    root = etree.Element(f"{{{PAGE_NS}}}PcGts", nsmap=nsmap)
    root.set(f"{{{XSI_NS}}}schemaLocation", SCHEMA_LOCATION)

    # <Metadata>
    meta = etree.SubElement(root, f"{{{PAGE_NS}}}Metadata")
    creator = etree.SubElement(meta, f"{{{PAGE_NS}}}Creator")
    creator.text = "HTR-ground"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    etree.SubElement(meta, f"{{{PAGE_NS}}}Created").text = now
    etree.SubElement(meta, f"{{{PAGE_NS}}}LastChange").text = now

    # <Page>
    page_elem = etree.SubElement(root, f"{{{PAGE_NS}}}Page")
    page_elem.set("imageFilename", image_filename)
    if page.image_width is not None:
        page_elem.set("imageWidth",  str(int(page.image_width)))
    if page.image_height is not None:
        page_elem.set("imageHeight", str(int(page.image_height)))

    for ri, region in enumerate(page.regions):
        tr = etree.SubElement(page_elem, f"{{{PAGE_NS}}}TextRegion")
        tr.set("id", f"r{ri}")
        tr.set("type", "paragraph")
        _add_coords(tr, region.coords)

        for li, line in enumerate(region.lines, start=1):
            tl = etree.SubElement(tr, f"{{{PAGE_NS}}}TextLine")
            tl.set("id", f"r{ri}l{li}")
            _add_coords(tl, line.coords)
            if line.baseline:
                bl = etree.SubElement(tl, f"{{{PAGE_NS}}}Baseline")
                bl.set("points", _points_attr(line.baseline))
            _add_text_equiv(tl, line.text)

    etree.indent(root, space="  ")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
