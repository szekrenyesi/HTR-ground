"""
API tesztek a presence endpointokra és a listázás presence-mezőjére.
"""
import pytest

from app import auth, projects
from app.presence import tracker


@pytest.fixture(autouse=True)
def clean_tracker():
    tracker.clear()
    yield
    tracker.clear()


@pytest.fixture
def tmp_projects_tree(tmp_path, monkeypatch):
    tree = tmp_path / "projects"
    folder = tree / "Minta" / "1"
    folder.mkdir(parents=True)
    (folder / "sample.jpg").write_bytes(b"fake-jpg")
    (folder / "sample.json").write_text(
        '{"regions":[],"image_width":100,"image_height":100}', encoding="utf-8"
    )
    monkeypatch.setattr(projects, "PROJECTS_ROOT", tree)
    auth.AUTH_CONFIG["projects"] = {}
    return tree


def test_heartbeat_requires_auth(anon_client, tmp_projects_tree):
    r = anon_client.post(
        "/api/presence/heartbeat",
        json={"path": "Minta/1", "basename": "sample"},
    )
    assert r.status_code == 401


def test_heartbeat_registers(logged_in_client, tmp_projects_tree):
    r = logged_in_client.post(
        "/api/presence/heartbeat",
        json={"path": "Minta/1", "basename": "sample"},
    )
    assert r.status_code == 200
    users = tracker.active_users("Minta/1", "sample")
    assert users[0][0] == "anna"


def test_get_presence_excludes_self(logged_in_client, tmp_projects_tree):
    # Anna heartbeat-el — de amikor lekéri, önmagát ne kapja vissza
    logged_in_client.post(
        "/api/presence/heartbeat",
        json={"path": "Minta/1", "basename": "sample"},
    )
    r = logged_in_client.get("/api/presence?path=Minta/1&basename=sample")
    body = r.json()
    assert body["others"] is None  # csak önmaga van jelen


def test_listing_includes_presence_of_others(
    logged_in_client, admin_client, tmp_projects_tree
):
    # Admin heartbeat-el a sample-en, aztán Anna listázza
    admin_client.post(
        "/api/presence/heartbeat",
        json={"path": "Minta/1", "basename": "sample"},
    )
    r = logged_in_client.get("/api/projects/Minta/1")
    body = r.json()
    pair = body["pairs"][0]
    assert "presence" in pair
    assert pair["presence"]["users"][0]["username"] == "admin"


def test_listing_no_presence_when_alone(logged_in_client, tmp_projects_tree):
    """Ha senki más nem heartbeat-el, ne legyen presence a válaszban."""
    r = logged_in_client.get("/api/projects/Minta/1")
    body = r.json()
    pair = body["pairs"][0]
    assert "presence" not in pair


def test_leave_removes_user(logged_in_client, admin_client, tmp_projects_tree):
    admin_client.post(
        "/api/presence/heartbeat",
        json={"path": "Minta/1", "basename": "sample"},
    )
    admin_client.post(
        "/api/presence/leave",
        json={"path": "Minta/1", "basename": "sample"},
    )
    r = logged_in_client.get("/api/presence?path=Minta/1&basename=sample")
    assert r.json()["others"] is None


def test_heartbeat_missing_basename(logged_in_client, tmp_projects_tree):
    r = logged_in_client.post(
        "/api/presence/heartbeat",
        json={"path": "Minta/1"},
    )
    assert r.status_code == 400
