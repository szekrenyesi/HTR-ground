"""
ALTO konverter tesztek.

Az `examples/Bakonykuti_V1_049.alto.xml` és a hozzá tartozó belső JSON
ugyanabból a forrásból származik — a koordináták és sorszövegek
1:1 egyeznek (a poligonokat leszámítva, amiket az ALTO nem tárol).
"""
import json
from pathlib import Path

import pytest

from app.converters import alto, convert, detect_format
from app.schema import Page


EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples"
ALTO_FILE = EXAMPLES / "Bakonykuti_V1_049.alto.xml"
JSON_FILE = EXAMPLES / "Bakonykuti_V1_049.json"


@pytest.fixture(scope="module")
def alto_bytes() -> bytes:
    return ALTO_FILE.read_bytes()


@pytest.fixture(scope="module")
def reference_json() -> dict:
    return json.loads(JSON_FILE.read_text(encoding="utf-8"))


def test_detect_alto(alto_bytes):
    assert detect_format(alto_bytes, "x.xml") == "alto-xml"


def test_alto_parses(alto_bytes):
    page = alto.parse(alto_bytes)
    assert isinstance(page, Page)
    assert page.image_width == 5496
    assert page.image_height == 3670
    assert len(page.regions) >= 1


def test_alto_region_count_matches_reference(alto_bytes, reference_json):
    page = alto.parse(alto_bytes)
    assert len(page.regions) == len(reference_json["regions"])


def test_alto_line_count_matches_per_region(alto_bytes, reference_json):
    page = alto.parse(alto_bytes)
    for i, region in enumerate(page.regions):
        ref_lines = reference_json["regions"][i]["lines"]
        assert len(region.lines) == len(ref_lines), (
            f"Régió {i}: {len(region.lines)} sor a ALTO-ban, "
            f"{len(ref_lines)} a referencia JSON-ban"
        )


def test_alto_first_line_text_and_geometry(alto_bytes):
    page = alto.parse(alto_bytes)
    first = page.regions[0].lines[0]
    # Az ALTO-ban: CONTENT="1756", HPOS=3246, VPOS=409, WIDTH=301, HEIGHT=130
    assert first.text == "1756"
    assert first.rect == [3246.0, 409.0, 301.0, 130.0]
    # baseline="3246,538 3289,512"
    assert first.baseline == [[3246.0, 538.0], [3289.0, 512.0]]


def test_alto_line_rects_match_reference(alto_bytes, reference_json):
    """A téglalapoknak (rect) 1:1 egyezniük kell."""
    page = alto.parse(alto_bytes)
    for ri, region in enumerate(page.regions):
        for li, line in enumerate(region.lines):
            ref_rect = reference_json["regions"][ri]["lines"][li]["rect"]
            # Az ALTO float-ot ad (egész értékekkel); a JSON int-eket — összehasonlítás értékre
            assert [int(v) for v in line.rect] == ref_rect, (
                f"R{ri} L{li} rect eltér: ALTO {line.rect} vs ref {ref_rect}"
            )


def test_alto_polygon_synthesized_from_rect(alto_bytes):
    """Ha nincs <Shape><Polygon>, a poligon a téglalapból szintetizálódik (4 sarokpont)."""
    page = alto.parse(alto_bytes)
    line = page.regions[0].lines[0]
    assert len(line.coords) == 4  # 4 sarokpont
    x, y, w, h = line.rect
    # óramutató szerint: top-left, top-right, bottom-right, bottom-left
    assert line.coords == [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def test_convert_dispatch(alto_bytes):
    """A magas szintű convert() helyesen dispatchel."""
    page = convert(alto_bytes, filename="Bakonykuti_V1_049.alto.xml")
    assert page.source_format == "alto-xml"
    assert len(page.regions) >= 1
