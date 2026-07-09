"""
Belső JSON pass-through tesztek.

Nem külső fájlból dolgozunk — a Page sémából egyenest generálunk egy minimál
struktúrát, hogy ne függjünk fixture-ektől.
"""
import json

from app.converters import htr_json, convert, detect_format


SAMPLE_PAGE = {
    "regions": [
        {
            "coords": [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]],
            "rect":   [0.0, 0.0, 100.0, 100.0],
            "lines": [
                {
                    "coords": [[10.0, 10.0], [50.0, 10.0], [50.0, 30.0], [10.0, 30.0]],
                    "rect":   [10.0, 10.0, 40.0, 20.0],
                    "baseline": [[10.0, 30.0], [50.0, 30.0]],
                    "text": "Példa szöveg",
                }
            ],
        }
    ],
    "image_width":  200,
    "image_height": 300,
}


def test_detect_json():
    data = json.dumps(SAMPLE_PAGE).encode("utf-8")
    assert detect_format(data, "x.json") == "json"


def test_json_parses():
    data = json.dumps(SAMPLE_PAGE).encode("utf-8")
    page = htr_json.parse(data)
    assert len(page.regions) == 1
    assert page.regions[0].lines[0].text == "Példa szöveg"


def test_convert_dispatch_json():
    data = json.dumps(SAMPLE_PAGE).encode("utf-8")
    page = convert(data, filename="x.json")
    assert page.source_format == "json"
