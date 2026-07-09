"""
Unit tesztek az `app.auth` modulra.
"""
import pytest

from app import auth


def test_hash_and_verify_roundtrip():
    h = auth.hash_password("titok")
    assert h.startswith("$2b$")
    assert auth._verify_hash("titok", h)
    assert not auth._verify_hash("rossz", h)


def test_verify_credentials_success():
    assert auth.verify_credentials("anna", "annapass") is True


def test_verify_credentials_wrong_password():
    assert auth.verify_credentials("anna", "rossz") is False


def test_verify_credentials_unknown_user():
    assert auth.verify_credentials("nincsilyen", "akarmi") is False


def test_verify_credentials_empty():
    assert auth.verify_credentials("", "") is False
    assert auth.verify_credentials("anna", "") is False
    assert auth.verify_credentials("", "annapass") is False


def test_is_admin_flag():
    assert auth.is_admin_user("admin") is True
    assert auth.is_admin_user("anna") is False
    assert auth.is_admin_user("nincsilyen") is False
    assert auth.is_admin_user(None) is False


def test_get_user_shape():
    u = auth.get_user("anna")
    assert u is not None
    assert u["display_name"] == "Kovács Anna"
    assert "password_hash" in u


def test_get_user_missing():
    assert auth.get_user("nincsilyen") is None


def test_no_config_falls_back_to_empty(tmp_path):
    """Fresh install (üres conf mappa) esetén a szerver elindul, csak
    warning-ot ad — nem fatal error."""
    import warnings
    original_conf_dir = auth.CONF_DIR
    auth.CONF_DIR = tmp_path
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = auth.load_auth_config()
        assert cfg["users"] == {}
        assert cfg["projects"] == {}
        assert any("bootstrap" in str(warning.message) for warning in w)
    finally:
        auth.CONF_DIR = original_conf_dir


def test_legacy_shape_rejected(tmp_path):
    """A régi v1 (van `password`, nincs `users`) shape-et explicit hibaüzenettel utasítjuk el."""
    import json
    legacy = {"password": "secret", "session_secret": "x"}
    d = tmp_path / "conf"
    d.mkdir()
    (d / "auth.json").write_text(json.dumps(legacy), encoding="utf-8")

    original_conf_dir = auth.CONF_DIR
    auth.CONF_DIR = d
    try:
        with pytest.raises(auth.AuthConfigError) as ei:
            auth.load_auth_config()
        assert "bootstrap" in str(ei.value)
    finally:
        auth.CONF_DIR = original_conf_dir
