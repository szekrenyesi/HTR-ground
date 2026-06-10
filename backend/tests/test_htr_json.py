"""
Belső JSON pass-through teszt: a referencia JSON-t betöltjük és visszakapjuk.
"""
import json
from pathlib import Path

import pytest

from app.converters import htr_json, convert, detect_format


EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples"
JSON_FILE = EXAMPLES / "Bakonykuti_V1_049.json"


@pytest.fixture(scope="module")
def json_bytes() -> bytes:
    return JSON_FILE.read_bytes()


def test_detect_json(json_bytes):
    assert detect_format(json_bytes, "x.json") == "json"


def test_json_parses(json_bytes):
    page = htr_json.parse(json_bytes)
    assert len(page.regions) >= 1
    assert page.regions[0].lines[0].text == "1756"


def test_convert_dispatch_json(json_bytes):
    page = convert(json_bytes, filename="x.json")
    assert page.source_format == "json"
