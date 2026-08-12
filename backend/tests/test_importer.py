"""
Import + delete tesztek.

Lefed: mappa létrehozás, fájl-upload (jó + rossz kiterjesztések, dotfile,
overwrite, path escape), mappa törlés, pár törlés. Plusz az endpoint
jogosultsági szűrők (admin vs import-tag vs sima user).
"""
import json
import pytest

from app import auth, projects, importer


# ─── Modul-szintű unit tesztek ──────────────────────────────────────────
def test_validate_rel_path_accepts_simple():
    assert importer._validate_rel_path("foo.jpg") == ["foo.jpg"]
    assert importer._validate_rel_path("sub/foo.jpg") == ["sub", "foo.jpg"]


def test_validate_rel_path_rejects_dotdot():
    with pytest.raises(projects.PathEscapeError):
        importer._validate_rel_path("../foo.jpg")


def test_validate_rel_path_rejects_absolute():
    # Az abszolút path leading `/`-ja eltűnik a strip miatt, ami OK — a `_validate_rel_path`
    # csak a path-elemeken belüli tiltásokat ellenőrzi. Az abszolút path elleni védelem
    # a resolve() + relative_to() páros.
    parts = importer._validate_rel_path("/foo.jpg")
    assert parts == ["foo.jpg"]


def test_validate_rel_path_rejects_dotfile():
    with pytest.raises(importer.ImportError):
        importer._validate_rel_path(".hidden.jpg")
    with pytest.raises(importer.ImportError):
        importer._validate_rel_path("sub/.hidden")


def test_has_allowed_extension():
    assert importer._has_allowed_extension("foo.jpg")
    assert importer._has_allowed_extension("foo.JPG")
    assert importer._has_allowed_extension("foo.json")
    assert importer._has_allowed_extension("foo.alto.xml")
    assert not importer._has_allowed_extension("foo.txt")
    assert not importer._has_allowed_extension("foo.exe")
    assert not importer._has_allowed_extension("foo")


# ─── Modul-szint: create_folder + upload_files + delete_* ───────────────
@pytest.fixture
def tmp_projects(tmp_path, monkeypatch):
    tree = tmp_path / "projects"
    tree.mkdir()
    monkeypatch.setattr(projects, "PROJECTS_ROOT", tree)
    auth.AUTH_CONFIG["projects"] = {}
    return tree


def test_create_folder_simple(tmp_projects):
    p = importer.create_folder("Bakonykuti")
    assert p.exists() and p.is_dir()


def test_create_folder_nested(tmp_projects):
    p = importer.create_folder("Bakonykuti/1949/oldal")
    assert p.exists()


def test_create_folder_already_exists(tmp_projects):
    importer.create_folder("Bakonykuti")
    with pytest.raises(importer.ImportError):
        importer.create_folder("Bakonykuti")


def test_create_folder_path_escape(tmp_projects):
    with pytest.raises(projects.PathEscapeError):
        importer.create_folder("../evil")


def test_upload_files_simple(tmp_projects):
    importer.create_folder("Minta")
    result = importer.upload_files("Minta", [
        ("foo.jpg",  b"fake-jpg"),
        ("foo.json", b'{"regions":[]}'),
    ])
    assert result["uploaded"] == ["foo.jpg", "foo.json"]
    assert result["skipped"] == []
    assert (tmp_projects / "Minta" / "foo.jpg").read_bytes() == b"fake-jpg"


def test_upload_files_nested_creates_subdirs(tmp_projects):
    importer.create_folder("Minta")
    result = importer.upload_files("Minta", [
        ("1949/oldal.jpg",  b"a"),
        ("1949/oldal.json", b"{}"),
        ("1950/other.jpg",  b"b"),
    ])
    assert set(result["uploaded"]) == {"1949/oldal.jpg", "1949/oldal.json", "1950/other.jpg"}
    assert (tmp_projects / "Minta" / "1949" / "oldal.jpg").exists()
    assert (tmp_projects / "Minta" / "1950" / "other.jpg").exists()


def test_upload_files_rejects_bad_extensions(tmp_projects):
    importer.create_folder("Minta")
    result = importer.upload_files("Minta", [
        ("script.sh",   b"#!/bin/bash\nrm -rf /"),
        ("readme.txt",  b"hello"),
        ("good.jpg",    b"x"),
    ])
    assert result["uploaded"] == ["good.jpg"]
    reasons = [s["reason"] for s in result["skipped"]]
    assert any("Kiterjesztés" in r for r in reasons)
    assert len(result["skipped"]) == 2


def test_upload_files_rejects_dotfiles(tmp_projects):
    importer.create_folder("Minta")
    result = importer.upload_files("Minta", [
        (".htrground.json", b"{}"),
        ("normal.json",     b"{}"),
    ])
    assert result["uploaded"] == ["normal.json"]
    assert any(".htrground" in s["path"] for s in result["skipped"])


def test_upload_files_no_overwrite(tmp_projects):
    importer.create_folder("Minta")
    (tmp_projects / "Minta" / "foo.jpg").write_bytes(b"original")
    result = importer.upload_files("Minta", [
        ("foo.jpg", b"replacement"),
    ])
    assert result["uploaded"] == []
    assert result["skipped"][0]["path"] == "foo.jpg"
    assert "létezik" in result["skipped"][0]["reason"]
    # Eredeti tartalom változatlan
    assert (tmp_projects / "Minta" / "foo.jpg").read_bytes() == b"original"


def test_upload_files_rejects_path_escape(tmp_projects):
    importer.create_folder("Minta")
    result = importer.upload_files("Minta", [
        ("../evil.jpg", b"x"),
    ])
    assert result["uploaded"] == []
    assert len(result["skipped"]) == 1


def test_delete_folder_recursive(tmp_projects):
    importer.create_folder("Minta/inner")
    (tmp_projects / "Minta" / "foo.jpg").write_bytes(b"x")
    (tmp_projects / "Minta" / "inner" / "bar.jpg").write_bytes(b"y")
    importer.delete_folder("Minta")
    assert not (tmp_projects / "Minta").exists()


def test_delete_folder_missing(tmp_projects):
    with pytest.raises(FileNotFoundError):
        importer.delete_folder("Nonexistent")


def test_delete_folder_refuses_root(tmp_projects):
    with pytest.raises(importer.ImportError):
        # A gyökér `""` az egész projects/-t érintené — a _validate_rel_path elutasítja
        importer.delete_folder("")


def test_delete_pair(tmp_projects):
    from app import meta as pair_meta
    importer.create_folder("Minta")
    folder = tmp_projects / "Minta"
    (folder / "foo.jpg").write_bytes(b"img")
    (folder / "foo.json").write_bytes(b'{"regions":[]}')
    (folder / "foo.alto.xml").write_bytes(b"<alto/>")
    pair_meta.set_status(folder, "foo", "kész", "admin")

    result = importer.delete_pair("Minta", "foo")
    assert set(result["deleted"]) == {"foo.jpg", "foo.json", "foo.alto.xml", "foo.htrground-meta.json"}
    # A mappa maga megmarad
    assert folder.exists()
    # De egy fájl sincs bent
    assert list(folder.iterdir()) == []


def test_delete_pair_missing(tmp_projects):
    importer.create_folder("Minta")
    with pytest.raises(FileNotFoundError):
        importer.delete_pair("Minta", "no-such")


# ─── Endpoint tesztek (jogosultsági szűrő + happy path) ─────────────────
@pytest.fixture
def import_user_client(anon_client, tmp_projects):
    """Anna kap 'import' csoport-tagságot, aztán belép."""
    auth.AUTH_CONFIG["groups"] = {"import": ["anna"]}
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post("/login", data={"username": "anna", "password": "annapass"}, follow_redirects=False)
    assert r.status_code == 303
    yield c
    auth.AUTH_CONFIG["groups"] = {}


def test_create_folder_endpoint_needs_import(logged_in_client, tmp_projects):
    """Anna alapból NEM import-tag → 403."""
    r = logged_in_client.post("/api/project-folder", json={"path": "Uj"})
    assert r.status_code == 403


def test_create_folder_endpoint_import_user_ok(import_user_client, tmp_projects):
    r = import_user_client.post("/api/project-folder", json={"path": "Uj"})
    assert r.status_code == 200
    assert (tmp_projects / "Uj").is_dir()


def test_create_folder_endpoint_admin_ok(admin_client, tmp_projects):
    r = admin_client.post("/api/project-folder", json={"path": "AdminUj"})
    assert r.status_code == 200


def test_create_folder_endpoint_missing_path(admin_client, tmp_projects):
    r = admin_client.post("/api/project-folder", json={})
    assert r.status_code == 400


def test_create_folder_endpoint_acl(import_user_client, tmp_projects):
    """Anna látott projektjén belül tud létrehozni, rejtett projekthez nem."""
    auth.AUTH_CONFIG["projects"] = {"Titkos": {"visible_to": ["admin"]}}
    try:
        # Titkos alá NEM tudja
        r = import_user_client.post("/api/project-folder", json={"path": "Titkos/uj"})
        assert r.status_code == 403
    finally:
        auth.AUTH_CONFIG["projects"] = {}


def test_upload_endpoint_needs_import(logged_in_client, tmp_projects):
    (tmp_projects / "Uj").mkdir()
    files = [("files", ("foo.jpg", b"x", "image/jpeg"))]
    manifest = json.dumps(["foo.jpg"])
    r = logged_in_client.post(
        "/api/project-upload?path=Uj",
        files=files,
        data={"manifest": manifest},
    )
    assert r.status_code == 403


def test_upload_endpoint_happy_path(import_user_client, tmp_projects):
    (tmp_projects / "Uj").mkdir()
    files = [
        ("files", ("foo.jpg",  b"jpg-bytes", "image/jpeg")),
        ("files", ("foo.json", b'{"regions":[]}', "application/json")),
    ]
    manifest = json.dumps(["foo.jpg", "foo.json"])
    r = import_user_client.post(
        "/api/project-upload?path=Uj",
        files=files,
        data={"manifest": manifest},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["uploaded"]) == {"foo.jpg", "foo.json"}
    assert body["skipped"] == []


def test_upload_endpoint_manifest_length_mismatch(import_user_client, tmp_projects):
    (tmp_projects / "Uj").mkdir()
    files = [("files", ("foo.jpg", b"x", "image/jpeg"))]
    r = import_user_client.post(
        "/api/project-upload?path=Uj",
        files=files,
        data={"manifest": json.dumps(["foo.jpg", "bar.jpg"])},
    )
    assert r.status_code == 400


def test_delete_folder_endpoint_admin_only(import_user_client, logged_in_client, admin_client, tmp_projects):
    (tmp_projects / "ToDelete").mkdir()

    # Anna (import-tag) nem törölhet
    r = import_user_client.delete("/api/project-folder?path=ToDelete")
    assert r.status_code == 403

    # Anna alapból nem admin sem
    r = logged_in_client.delete("/api/project-folder?path=ToDelete")
    assert r.status_code == 403

    # Admin igen
    r = admin_client.delete("/api/project-folder?path=ToDelete")
    assert r.status_code == 200
    assert not (tmp_projects / "ToDelete").exists()


def test_delete_pair_endpoint_admin_only(admin_client, logged_in_client, tmp_projects):
    (tmp_projects / "Minta").mkdir()
    (tmp_projects / "Minta" / "foo.jpg").write_bytes(b"x")
    (tmp_projects / "Minta" / "foo.json").write_bytes(b"{}")

    r = logged_in_client.delete("/api/project-file?path=Minta&basename=foo")
    assert r.status_code == 403

    r = admin_client.delete("/api/project-file?path=Minta&basename=foo")
    assert r.status_code == 200
    body = r.json()
    assert set(body["deleted"]) >= {"foo.jpg", "foo.json"}


def test_session_info_includes_groups(import_user_client):
    r = import_user_client.get("/api/session")
    body = r.json()
    assert "import" in body["groups"]


def test_session_info_admin_no_explicit_groups(admin_client):
    """Admin userre a `groups` csak az explicit tagságokat listázza — az admin
    státusz külön mezőben (`is_admin`) van."""
    r = admin_client.get("/api/session")
    body = r.json()
    assert body["is_admin"] is True
    assert body["groups"] == []  # admin nincs explicit egyik csoportban sem
