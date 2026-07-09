"""
API tesztek a státusz-endpointokra és a listázás meta-mezőjére.
"""
import pytest

from app import auth, projects, meta


@pytest.fixture
def tmp_projects_tree(tmp_path, monkeypatch):
    """Egy egyszerű projekt-fa: `Minta/1/sample.jpg + sample.json`."""
    tree = tmp_path / "projects"
    folder = tree / "Minta" / "1"
    folder.mkdir(parents=True)
    (folder / "sample.jpg").write_bytes(b"fake-jpg")
    (folder / "sample.json").write_text(
        '{"regions":[],"image_width":100,"image_height":100}', encoding="utf-8"
    )
    monkeypatch.setattr(projects, "PROJECTS_ROOT", tree)
    # Nincs ACL korlát
    auth.AUTH_CONFIG["projects"] = {}
    return tree


def test_status_values_endpoint(anon_client):
    r = anon_client.get("/api/status-values")
    assert r.status_code == 200
    body = r.json()
    assert body["default"] == "új"
    assert "folyamatban" in body["values"]
    assert "kész" in body["values"]


def test_listing_includes_default_meta(logged_in_client, tmp_projects_tree):
    r = logged_in_client.get("/api/projects/Minta/1")
    assert r.status_code == 200, r.text
    body = r.json()
    pair = body["pairs"][0]
    assert pair["basename"] == "sample"
    assert pair["meta"]["status"] == "új"
    assert pair["meta"]["status_changed_by"] is None


def test_put_status_creates_sidecar(logged_in_client, tmp_projects_tree):
    r = logged_in_client.put(
        "/api/project-status?path=Minta/1&basename=sample",
        json={"status": "folyamatban"},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["status"] == "folyamatban"
    assert result["status_changed_by"] == "anna"
    # Sidecar tényleg létrejött
    sidecar = tmp_projects_tree / "Minta" / "1" / "sample.htrground-meta.json"
    assert sidecar.exists()


def test_put_status_invalid(logged_in_client, tmp_projects_tree):
    r = logged_in_client.put(
        "/api/project-status?path=Minta/1&basename=sample",
        json={"status": "kitalált"},
    )
    assert r.status_code == 400


def test_put_status_missing_pair(logged_in_client, tmp_projects_tree):
    r = logged_in_client.put(
        "/api/project-status?path=Minta/1&basename=nincs_ilyen",
        json={"status": "folyamatban"},
    )
    assert r.status_code == 404


def test_put_status_requires_auth(anon_client, tmp_projects_tree):
    r = anon_client.put(
        "/api/project-status?path=Minta/1&basename=sample",
        json={"status": "folyamatban"},
    )
    assert r.status_code == 401


def test_sidecar_not_listed_as_annotation(logged_in_client, tmp_projects_tree):
    """A sidecar fájl NE jelenjen meg a listázásban külön annotációként."""
    # Előbb rakjunk egy status-t, hogy létrejöjjön a sidecar
    logged_in_client.put(
        "/api/project-status?path=Minta/1&basename=sample",
        json={"status": "folyamatban"},
    )
    r = logged_in_client.get("/api/projects/Minta/1")
    body = r.json()
    # Csak `sample` legyen, nem `sample.htrground-meta`
    basenames = [p["basename"] for p in body["pairs"]]
    assert basenames == ["sample"]


def test_save_pair_records_edit(logged_in_client, tmp_projects_tree):
    """A tartalom-mentés utána a `meta.edited_by` frissüljön."""
    page_data = {
        "regions": [
            {
                "coords": [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]],
                "rect":   [0.0, 0.0, 10.0, 10.0],
                "lines": [],
            }
        ]
    }
    r = logged_in_client.put(
        "/api/project-file?path=Minta/1&basename=sample",
        json={"page": page_data},
    )
    assert r.status_code == 200, r.text
    # A listázásban megjelenjen az edited_by
    r2 = logged_in_client.get("/api/projects/Minta/1")
    pair = r2.json()["pairs"][0]
    assert pair["meta"]["edited_by"] == "anna"
    assert pair["meta"]["edited_at"] is not None
