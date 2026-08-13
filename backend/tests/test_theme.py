"""
Téma-váltás tesztek: theme.css/theme.js kiszolgálás, meta tag injection,
config-alapú default_theme.
"""
import importlib
import pytest

from app import auth


def test_theme_css_served(anon_client):
    r = anon_client.get("/theme.css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]
    # CSS változók léteznek
    assert "--bg-page" in r.text
    assert "--accent-success" in r.text
    # Light téma is definiálva
    assert '[data-theme="light"]' in r.text


def test_theme_js_served(anon_client):
    r = anon_client.get("/theme.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert "htrground-theme" in r.text  # localStorage kulcs
    assert "theme-toggle" in r.text


def test_default_theme_meta_dark(anon_client):
    """Config nélkül a default dark."""
    r = anon_client.get("/")
    assert r.status_code == 200
    assert 'name="default-theme" content="dark"' in r.text


def test_default_theme_meta_configurable(anon_client):
    """Az `auth.json.default_theme=light` átjön a HTML-be."""
    auth.AUTH_CONFIG["default_theme"] = "light"
    try:
        r = anon_client.get("/")
        assert 'name="default-theme" content="light"' in r.text

        # Login oldalon is
        r = anon_client.get("/login")
        assert 'name="default-theme" content="light"' in r.text
    finally:
        del auth.AUTH_CONFIG["default_theme"]


def test_default_theme_meta_invalid_falls_back_to_dark(anon_client):
    """Rossz érték → dark (biztonságos fallback)."""
    auth.AUTH_CONFIG["default_theme"] = "psychedelic"
    try:
        r = anon_client.get("/")
        assert 'name="default-theme" content="dark"' in r.text
    finally:
        del auth.AUTH_CONFIG["default_theme"]


def test_all_html_pages_have_theme_toggle(anon_client, logged_in_client):
    """Minden HTML oldal head-jében legyen theme.js és toggle gomb."""
    # Landing
    r = anon_client.get("/")
    assert 'theme-toggle' in r.text
    assert 'theme.js' in r.text
    # Login
    r = anon_client.get("/login")
    assert 'theme-toggle' in r.text
    # Demo (editor)
    r = anon_client.get("/demo")
    assert 'theme-toggle' in r.text
    # Projects
    r = logged_in_client.get("/projects", follow_redirects=False)
    # A projects requires_auth_or_redirect — belépve 200
    assert r.status_code == 200
    assert 'theme-toggle' in r.text
