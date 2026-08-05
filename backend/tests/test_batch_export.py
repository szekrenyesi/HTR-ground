"""
Batch export tesztek.

A `build_zip` legfontosabb viselkedéseit ellenőrzik:
  - AS-IS beemelés, ha a kért formátum a legfrissebb
  - Konverzió a legfrissebbből, ha a kért formátum régi vagy nem létezik
  - Kép + sidecar opcionális beemelése
  - PDF kihagyás kép nélküli páron (warning-gal)
  - Mappastruktúra megőrzése
  - ACL az endpoint szintjén
"""
import io
import json
import os
import zipfile
from pathlib import Path

import pytest

from app import auth, projects, batch_export, meta as pair_meta


SAMPLE_PAGE_JSON = json.dumps({
    "regions": [
        {
            "coords": [[0.0, 0.0], [100.0, 0.0], [100.0, 50.0], [0.0, 50.0]],
            "rect":   [0.0, 0.0, 100.0, 50.0],
            "lines": [
                {
                    "coords":   [[10.0, 10.0], [90.0, 10.0], [90.0, 40.0], [10.0, 40.0]],
                    "rect":     [10.0, 10.0, 80.0, 30.0],
                    "baseline": [[10.0, 40.0], [90.0, 40.0]],
                    "text":     "Példa szöveg"
                }
            ]
        }
    ],
    "image_width":  100,
    "image_height": 50
}, ensure_ascii=False)


@pytest.fixture
def tmp_projects(tmp_path, monkeypatch):
    """Egy egyszerű projekt-fa: Minta/1 és Minta/2."""
    tree = tmp_path / "projects"

    f1 = tree / "Minta" / "1"
    f1.mkdir(parents=True)
    (f1 / "sample.jpg").write_bytes(b"fake-jpg-1")
    (f1 / "sample.json").write_text(SAMPLE_PAGE_JSON, encoding="utf-8")

    f2 = tree / "Minta" / "2"
    f2.mkdir(parents=True)
    (f2 / "another.jpg").write_bytes(b"fake-jpg-2")
    (f2 / "another.json").write_text(SAMPLE_PAGE_JSON, encoding="utf-8")
    # sidecar is a másodikhoz
    pair_meta.set_status(f2, "another", "folyamatban", "anna")

    monkeypatch.setattr(projects, "PROJECTS_ROOT", tree)
    auth.AUTH_CONFIG["projects"] = {}
    return tree


# ─── Alap tesztek ────────────────────────────────────────────────────────
def test_export_single_annotation_format(tmp_projects):
    """JSON → JSON: már létezik, mtime szerint legfrissebb → AS-IS."""
    zip_bytes, warnings = batch_export.build_zip(
        "Minta/1", ["json"], recursive=True
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
    assert "sample.json" in names
    assert not warnings


def test_export_converts_to_missing_format(tmp_projects):
    """JSON csak → ALTO XML export → konverzió."""
    zip_bytes, _ = batch_export.build_zip(
        "Minta/1", ["alto-xml"], recursive=True
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        alto_content = zf.read("sample.alto.xml").decode()
    assert "sample.alto.xml" in names
    assert "<alto" in alto_content.lower()
    # A szöveg át kell hogy kerüljön
    assert "Példa szöveg" in alto_content


def test_export_multiple_formats(tmp_projects):
    """Egyszerre több formátum — mind bekerül."""
    zip_bytes, _ = batch_export.build_zip(
        "Minta/1", ["json", "alto-xml", "page-xml"], recursive=True
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    assert "sample.json"     in names
    assert "sample.alto.xml" in names
    assert "sample.page.xml" in names


def test_existing_format_used_as_is_when_newest(tmp_projects):
    """Ha az ALTO XML újabb, mint a JSON, kapja meg AS-IS."""
    # Alto fájlt írunk, ami újabb mtime-mel jön létre (mint a JSON)
    f1 = tmp_projects / "Minta" / "1"
    alto_original = "<?xml version='1.0'?><alto><Layout><Page HEIGHT='50' WIDTH='100'><PrintSpace><TextBlock ID='r0' HPOS='0' VPOS='0' WIDTH='100' HEIGHT='50'><TextLine HPOS='10' VPOS='10' WIDTH='80' HEIGHT='30' BASELINE='10,40 90,40'><String CONTENT='LEGREGIBB ALTO' HPOS='10' VPOS='10' WIDTH='80' HEIGHT='30'/></TextLine></TextBlock></PrintSpace></Page></Layout></alto>"
    (f1 / "sample.alto.xml").write_text(alto_original, encoding="utf-8")
    # Bizonytalan, hogy a JSON vagy az ALTO lesz újabb — biztosítsuk hogy ALTO
    older = os.path.getmtime(f1 / "sample.json") - 100
    os.utime(f1 / "sample.json", (older, older))

    zip_bytes, _ = batch_export.build_zip("Minta/1", ["alto-xml"], recursive=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        content = zf.read("sample.alto.xml").decode()
    # AS-IS beemelés → az „LEGREGIBB ALTO" szónak benne kell lennie
    assert "LEGREGIBB ALTO" in content


def test_older_format_gets_reconverted_from_newest(tmp_projects):
    """A JSON újabb, mint az ALTO → ALTO exportkor konvertálódik a JSON-ből."""
    f1 = tmp_projects / "Minta" / "1"
    (f1 / "sample.alto.xml").write_text(
        "<?xml version='1.0'?><alto><Layout><Page HEIGHT='50' WIDTH='100'><PrintSpace><TextBlock ID='r0'><TextLine><String CONTENT='REGI ALTO'/></TextLine></TextBlock></PrintSpace></Page></Layout></alto>",
        encoding="utf-8"
    )
    # A JSON legyen újabb
    newer = os.path.getmtime(f1 / "sample.alto.xml") + 100
    os.utime(f1 / "sample.json", (newer, newer))

    zip_bytes, _ = batch_export.build_zip("Minta/1", ["alto-xml"], recursive=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        content = zf.read("sample.alto.xml").decode()
    # A JSON tartalma („Példa szöveg") kell átjönnie, nem a „REGI ALTO"
    assert "Példa szöveg" in content
    assert "REGI ALTO" not in content


# ─── Kép + sidecar ───────────────────────────────────────────────────────
def test_include_images(tmp_projects):
    zip_bytes, _ = batch_export.build_zip(
        "Minta/1", ["json"], include_images=True, recursive=True
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        img_bytes = zf.read("sample.jpg")
    assert "sample.jpg" in names
    assert img_bytes == b"fake-jpg-1"


def test_include_sidecars(tmp_projects):
    """A sidecar (`.htrground-meta.json`) beemelése — csak, ha kérted."""
    # `Minta/2/another`-hoz van sidecar (fixture felvette)
    zip_bytes, _ = batch_export.build_zip(
        "Minta/2", ["json"], include_sidecars=True, recursive=True
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    assert "another.htrground-meta.json" in names


def test_no_sidecar_when_not_requested(tmp_projects):
    zip_bytes, _ = batch_export.build_zip(
        "Minta/2", ["json"], include_sidecars=False, recursive=True
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    assert "another.htrground-meta.json" not in names


def test_only_images_no_annotations(tmp_projects):
    """Ha csak képet kérsz — a ZIP csak képeket tartalmaz."""
    zip_bytes, warnings = batch_export.build_zip(
        "Minta/1", [], include_images=True, recursive=True
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    assert "sample.jpg" in names
    assert "sample.json" not in names
    assert "sample.alto.xml" not in names
    assert not warnings


# ─── Mappastruktúra ───────────────────────────────────────────────────────
def test_preserves_folder_structure(tmp_projects):
    """A Minta gyökeréből export → az almappák nevei megőrződnek."""
    zip_bytes, _ = batch_export.build_zip(
        "Minta", ["json"], recursive=True
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    assert "1/sample.json" in names
    assert "2/another.json" in names


def test_non_recursive_stays_in_folder(tmp_projects):
    """Nem-rekurzív módban az almappák tartalma NE jelenjen meg."""
    # A Minta gyökere önmagában nem tartalmaz párt (csak subdir-eket)
    zip_bytes, _ = batch_export.build_zip(
        "Minta", ["json"], recursive=False
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    # Semmi almappa-tartalom nem lehet
    assert "1/sample.json"    not in names
    assert "2/another.json"   not in names


# ─── PDF ─────────────────────────────────────────────────────────────────
def test_pdf_skipped_when_no_image(tmp_projects):
    """Egy pár kép nélkül, PDF-kérés → warning-ba kerül."""
    # Adjunk hozzá egy kép nélküli párt
    f3 = tmp_projects / "Minta" / "3"
    f3.mkdir(parents=True)
    (f3 / "textonly.json").write_text(SAMPLE_PAGE_JSON, encoding="utf-8")

    zip_bytes, warnings = batch_export.build_zip(
        "Minta/3", ["pdf"], recursive=True
    )
    assert "skipped_pdf" in warnings
    assert any("textonly" in w for w in warnings["skipped_pdf"])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    assert "textonly.pdf" not in names


# ─── ZIP fájlnév + warning header ────────────────────────────────────────
def test_zip_filename_root_folder():
    assert batch_export.zip_filename_for("") == "projects.zip"
    assert batch_export.zip_filename_for("Bakonykuti") == "Bakonykuti.zip"
    assert batch_export.zip_filename_for("Bakonykuti/1949") == "Bakonykuti-1949.zip"
    assert batch_export.zip_filename_for("/Bakonykuti/1949/") == "Bakonykuti-1949.zip"


def test_encode_warnings_header():
    assert batch_export.encode_warnings_header({}) == ""
    header = batch_export.encode_warnings_header({"skipped_pdf": ["a/b"]})
    parsed = json.loads(header)
    assert parsed["skipped_pdf"] == ["a/b"]


# ─── Endpoint tesztek ────────────────────────────────────────────────────
def test_endpoint_needs_auth(anon_client, tmp_projects):
    r = anon_client.get("/api/project-export?path=Minta&formats=json")
    assert r.status_code == 401


def test_endpoint_returns_zip(logged_in_client, tmp_projects):
    r = logged_in_client.get(
        "/api/project-export?path=Minta&formats=json,alto-xml&include_images=1&recursive=1"
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    assert 'filename="Minta.zip"' in r.headers["content-disposition"]

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(zf.namelist())
    assert "1/sample.json"     in names
    assert "1/sample.alto.xml" in names
    assert "1/sample.jpg"      in names


def test_endpoint_empty_selection_400(logged_in_client, tmp_projects):
    r = logged_in_client.get("/api/project-export?path=Minta")
    assert r.status_code == 400


def test_endpoint_bad_format_400(logged_in_client, tmp_projects):
    r = logged_in_client.get("/api/project-export?path=Minta&formats=hocr")
    assert r.status_code == 400


def test_endpoint_acl_blocks(logged_in_client, tmp_projects):
    """Ha az ACL rejt egy mappát, a user nem tudja exportálni."""
    auth.AUTH_CONFIG["projects"] = {"Minta": {"visible_to": ["admin"]}}
    try:
        r = logged_in_client.get("/api/project-export?path=Minta&formats=json")
        assert r.status_code == 403
    finally:
        auth.AUTH_CONFIG["projects"] = {}


def test_endpoint_admin_bypasses_acl(admin_client, tmp_projects):
    auth.AUTH_CONFIG["projects"] = {"Minta": {"visible_to": ["anna"]}}  # admin nincs benne
    try:
        r = admin_client.get("/api/project-export?path=Minta&formats=json")
        assert r.status_code == 200
    finally:
        auth.AUTH_CONFIG["projects"] = {}


def test_endpoint_warning_header(logged_in_client, tmp_projects):
    """PDF kérés kép nélküli párra → warning header."""
    f3 = tmp_projects / "Minta" / "3"
    f3.mkdir(parents=True)
    (f3 / "textonly.json").write_text(SAMPLE_PAGE_JSON, encoding="utf-8")

    r = logged_in_client.get("/api/project-export?path=Minta/3&formats=pdf")
    assert r.status_code == 200
    assert "x-htr-export-warnings" in {k.lower() for k in r.headers.keys()}
    warnings = json.loads(r.headers["X-HTR-Export-Warnings"])
    assert "skipped_pdf" in warnings
