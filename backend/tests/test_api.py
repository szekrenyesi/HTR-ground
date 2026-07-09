"""
FastAPI integrációs tesztek. Az `anon_client` és `logged_in_client` a conftest-ből jön.
"""
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ─── Public endpointok ────────────────────────────────────────────────────
def test_health(anon_client):
    r = anon_client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root_serves_landing(anon_client):
    """A gyökér mostantól a landing.html — két kártya (Demó / Projektek)."""
    r = anon_client.get("/")
    assert r.status_code == 200
    assert "<!DOCTYPE html>" in r.text
    # A landing tartalmaz „Demó" szót — nem szigorú, csak sanity check
    assert "Demó" in r.text or "demo" in r.text.lower()


def test_demo_serves_editor(anon_client):
    r = anon_client.get("/demo")
    assert r.status_code == 200
    assert "HTR Editor" in r.text


def test_convert_alto(anon_client):
    with open(FIXTURES / "sample.alto.xml", "rb") as f:
        r = anon_client.post(
            "/api/convert",
            files={"file": ("sample.alto.xml", f, "application/xml")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["format_detected"] == "alto-xml"
    page = body["page"]
    assert page["source_format"] == "alto-xml"
    assert page["image_width"] == 3231
    assert page["image_height"] == 5038
    assert page["regions"][0]["lines"][0]["text"] == "Tekintetes Úr!"


def test_convert_unknown_format(anon_client):
    r = anon_client.post(
        "/api/convert",
        files={"file": ("x.txt", b"hello world", "text/plain")},
    )
    assert r.status_code == 400


def test_convert_empty_file(anon_client):
    r = anon_client.post(
        "/api/convert",
        files={"file": ("x.json", b"", "application/json")},
    )
    assert r.status_code == 400


# ─── Auth ─────────────────────────────────────────────────────────────────
def test_session_anon(anon_client):
    r = anon_client.get("/api/session")
    assert r.status_code == 200
    assert r.json() == {"authenticated": False}


def test_session_logged_in(logged_in_client):
    r = logged_in_client.get("/api/session")
    assert r.status_code == 200
    body = r.json()
    assert body["authenticated"] is True
    assert body["username"] == "anna"
    assert body["display_name"] == "Kovács Anna"
    assert body["is_admin"] is False


def test_session_admin(admin_client):
    r = admin_client.get("/api/session")
    body = r.json()
    assert body["authenticated"] is True
    assert body["username"] == "admin"
    assert body["is_admin"] is True


def test_login_wrong_password(anon_client):
    r = anon_client.post(
        "/login",
        data={"username": "anna", "password": "rossz-jelszo"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error=1" in r.headers["location"]


def test_login_unknown_user(anon_client):
    r = anon_client.post(
        "/login",
        data={"username": "nincsilyen", "password": "akarmi"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error=1" in r.headers["location"]


def test_logout_clears_session(logged_in_client):
    r = logged_in_client.post("/logout", follow_redirects=False)
    assert r.status_code == 303
    r2 = logged_in_client.get("/api/session")
    assert r2.json() == {"authenticated": False}


# ─── Auth-gated route-ok ─────────────────────────────────────────────────
def test_projects_api_requires_auth(anon_client):
    r = anon_client.get("/api/projects")
    assert r.status_code == 401


def test_projects_api_authorised(logged_in_client):
    r = logged_in_client.get("/api/projects")
    assert r.status_code == 200
    body = r.json()
    assert "subfolders" in body
    assert "pairs" in body


def test_projects_html_redirects_when_anon(anon_client):
    r = anon_client.get("/projects", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]
