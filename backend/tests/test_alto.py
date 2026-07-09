"""
ALTO konverter tesztek.

Fixture: `tests/fixtures/sample.alto.xml` — egy valós, polygonos ALTO v4 fájl
(a Minta/Arany oldalról). A tesztek konkrét számokat várnak el ebből a fájlból;
ha valaha lecseréled a fixture-t, ezeket is frissítsd.
"""
from pathlib import Path

import pytest

from app.converters import alto, convert, detect_format
from app.schema import Page


FIXTURES = Path(__file__).resolve().parent / "fixtures"
ALTO_FILE = FIXTURES / "sample.alto.xml"


@pytest.fixture(scope="module")
def alto_bytes() -> bytes:
    return ALTO_FILE.read_bytes()


def test_detect_alto(alto_bytes):
    assert detect_format(alto_bytes, "x.xml") == "alto-xml"


def test_alto_parses(alto_bytes):
    page = alto.parse(alto_bytes)
    assert isinstance(page, Page)
    assert page.image_width == 3231
    assert page.image_height == 5038
    assert len(page.regions) >= 1


def test_alto_first_line_text_and_geometry(alto_bytes):
    page = alto.parse(alto_bytes)
    first = page.regions[0].lines[0]
    assert first.text == "Tekintetes Úr!"
    assert first.rect == [1788.0, 834.0, 686.0, 182.0]
    assert first.baseline == [[1788.0, 983.0], [2300.0, 968.0]]


def test_alto_polygon_from_shape_element(alto_bytes):
    """Az ALTO v4 mintában van <Shape><Polygon> — azt kell használnunk, nem a rect-et."""
    page = alto.parse(alto_bytes)
    first = page.regions[0].lines[0]
    # A polygon 42 pontos ebben a fixture-ben; nem 4 (azaz nem a rect-ből szintetizáltuk)
    assert len(first.coords) > 4
    # És nem egyezik a téglalap 4 sarkával
    x, y, w, h = first.rect
    rect_corners = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    assert first.coords != rect_corners


def test_convert_dispatch(alto_bytes):
    """A magas szintű convert() helyesen dispatchel."""
    page = convert(alto_bytes, filename="sample.alto.xml")
    assert page.source_format == "alto-xml"
    assert len(page.regions) >= 1
