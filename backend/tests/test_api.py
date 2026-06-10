"""
FastAPI integrációs tesztek a /api/convert endpoint-ra.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root_serves_editor(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<!DOCTYPE html>" in r.text
    assert "HTR Editor" in r.text


def test_convert_alto(client):
    with open(EXAMPLES / "Bakonykuti_V1_049.alto.xml", "rb") as f:
        r = client.post(
            "/api/convert",
            files={"file": ("Bakonykuti_V1_049.alto.xml", f, "application/xml")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["format_detected"] == "alto-xml"
    page = body["page"]
    assert page["source_format"] == "alto-xml"
    assert page["image_width"] == 5496
    assert page["image_height"] == 3670
    assert len(page["regions"]) >= 1
    # az első sor szövege a Bakonykuti mintán "1756"
    assert page["regions"][0]["lines"][0]["text"] == "1756"


def test_convert_json_passthrough(client):
    with open(EXAMPLES / "Bakonykuti_V1_049.json", "rb") as f:
        r = client.post(
            "/api/convert",
            files={"file": ("Bakonykuti_V1_049.json", f, "application/json")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["format_detected"] == "json"


def test_convert_unknown_format(client):
    r = client.post(
        "/api/convert",
        files={"file": ("x.txt", b"hello world", "text/plain")},
    )
    assert r.status_code == 400


def test_convert_empty_file(client):
    r = client.post(
        "/api/convert",
        files={"file": ("x.json", b"", "application/json")},
    )
    assert r.status_code == 400
