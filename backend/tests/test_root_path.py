"""
Sub-path deployment tesztek: HTR_GROUND_ROOT_PATH támogatás.

A `main.py` a modul-load-kor olvassa az env var-t, ezért ehhez a teszthez
egy külön processt kell indítani, vagy külön importálást szimulálni.
Mi az utóbbit csináljuk: importlib.reload után új appot kapunk.
"""
import importlib
import os

import pytest


@pytest.fixture
def app_with_root_path(monkeypatch):
    """Új FastAPI app példány, `HTR_GROUND_ROOT_PATH=/htr-ground` env var-ral."""
    monkeypatch.setenv("HTR_GROUND_ROOT_PATH", "/htr-ground")
    # Az `app.main` module-ot újratöltjük, hogy a friss env var érvényesüljön
    from app import main as main_mod
    reloaded = importlib.reload(main_mod)
    yield reloaded
    # Cleanup: állítsuk vissza az eredetit
    monkeypatch.delenv("HTR_GROUND_ROOT_PATH", raising=False)
    importlib.reload(main_mod)


@pytest.fixture
def client_subpath(app_with_root_path):
    from fastapi.testclient import TestClient
    return TestClient(app_with_root_path.app)


def test_root_path_is_read_from_env(app_with_root_path):
    assert app_with_root_path.ROOT_PATH == "/htr-ground"


def test_root_path_normalization_adds_leading_slash(monkeypatch):
    from app.main import _normalize_root_path
    assert _normalize_root_path("htr") == "/htr"
    assert _normalize_root_path("/htr") == "/htr"
    assert _normalize_root_path("/htr/") == "/htr"
    assert _normalize_root_path("") == ""
    assert _normalize_root_path("  ") == ""


def test_html_template_injects_root_path(client_subpath):
    """A HTML-be a {{ROOT_PATH}} placeholder helyett a valós prefix kerül."""
    r = client_subpath.get("/")
    assert r.status_code == 200
    assert '<base href="/htr-ground/">' in r.text
    assert 'content="/htr-ground"' in r.text
    assert "{{ROOT_PATH}}" not in r.text  # placeholder tényleg kicserélve


def test_login_html_has_prefixed_form_action(client_subpath):
    r = client_subpath.get("/login")
    assert 'action="/htr-ground/login"' in r.text


def test_login_redirect_prefixed(client_subpath):
    """Sikertelen login → redirect a prefixelt /login-ra."""
    r = client_subpath.post(
        "/login",
        data={"username": "anna", "password": "rossz"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].startswith("/htr-ground/login")


def test_login_success_redirect_prefixed(client_subpath):
    """Sikeres login → redirect a prefixelt /projects-re."""
    r = client_subpath.post(
        "/login",
        data={"username": "anna", "password": "annapass"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/htr-ground/projects"


def test_logout_redirect_prefixed(client_subpath):
    # Előbb belépünk
    client_subpath.post("/login", data={"username": "anna", "password": "annapass"})
    r = client_subpath.post("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/htr-ground/"


def test_require_auth_redirect_uses_prefix(client_subpath):
    """Nem-belépett user a /projects-re megy → login redirect prefixelt URL-re."""
    r = client_subpath.get("/projects", follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers["location"]
    assert loc.startswith("/htr-ground/login")
    # A `next` paraméterben is prefix legyen
    assert "next=/htr-ground/projects" in loc


def test_project_image_url_is_prefixed(client_subpath, tmp_path, monkeypatch):
    """A /api/project-file válaszban lévő image_url is prefixet kap."""
    from app import projects, auth
    tree = tmp_path / "projects"
    folder = tree / "Minta"
    folder.mkdir(parents=True)
    (folder / "sample.jpg").write_bytes(b"fake")
    (folder / "sample.json").write_text(
        '{"regions":[],"image_width":100,"image_height":100}', encoding="utf-8"
    )
    monkeypatch.setattr(projects, "PROJECTS_ROOT", tree)
    auth.AUTH_CONFIG["projects"] = {}

    # Login
    client_subpath.post("/login", data={"username": "anna", "password": "annapass"})
    r = client_subpath.get("/api/project-file?path=Minta&basename=sample")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["image_url"].startswith("/htr-ground/api/")


def test_root_mode_has_empty_prefix_in_html(anon_client):
    """Alapállapotban (nincs env var) a HTML `<base href="/">` kell hogy legyen."""
    r = anon_client.get("/")
    assert r.status_code == 200
    assert '<base href="/">' in r.text
    assert "{{ROOT_PATH}}" not in r.text
