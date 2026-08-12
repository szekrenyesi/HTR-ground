"""
A `python -m app.users` CLI tesztek. Nem futtatunk subprocess-t; közvetlenül
hívjuk a `main()`-t, mert egyszerűbb és gyorsabb.
"""
import io
from contextlib import redirect_stdout, redirect_stderr

import pytest

from app import auth, users as users_cli


def _run(argv, monkeypatch=None, prompt_password: str = None):
    """Segéd: CLI hívás stdout/stderr capture-rel."""
    out, err = io.StringIO(), io.StringIO()
    if prompt_password and monkeypatch:
        monkeypatch.setattr(users_cli, "_prompt_password_interactive", lambda: prompt_password)
    with redirect_stdout(out), redirect_stderr(err):
        rc = users_cli.main(argv)
    return rc, out.getvalue(), err.getvalue()


def test_list_shows_existing_users(reset_auth_config):
    rc, out, _ = _run(["list"])
    assert rc == 0
    assert "admin" in out
    assert "anna" in out
    # password hash SOHA nem jelenik meg
    assert "$2b$" not in out


def test_add_user_with_generated_password(reset_auth_config):
    rc, out, _ = _run(["add", "csaba", "Csaba", "--generate"])
    assert rc == 0
    assert "hozzáadva" in out
    assert "Egyszeri jelszó" in out
    # Az új user létezik és admin-flag nélkül jött létre
    assert auth.get_user("csaba") is not None
    assert auth.is_admin_user("csaba") is False


def test_add_user_with_prompt(reset_auth_config, monkeypatch):
    rc, out, _ = _run(
        ["add", "dora", "Dóra"],
        monkeypatch=monkeypatch,
        prompt_password="dorapass",
    )
    assert rc == 0
    assert auth.verify_credentials("dora", "dorapass") is True


def test_add_admin_user(reset_auth_config):
    rc, _, _ = _run(["add", "root", "Root", "--generate", "--admin"])
    assert rc == 0
    assert auth.is_admin_user("root") is True


def test_add_duplicate_fails(reset_auth_config):
    rc, _, err = _run(["add", "anna", "Anna", "--generate"])
    assert rc == 2
    assert "létezik" in err


def test_remove_user(reset_auth_config):
    assert auth.get_user("anna") is not None
    rc, out, _ = _run(["remove", "anna"])
    assert rc == 0
    assert "törölve" in out
    assert auth.get_user("anna") is None


def test_remove_missing_fails(reset_auth_config):
    rc, _, err = _run(["remove", "nincsilyen"])
    assert rc == 2
    assert "Nem létezik" in err


def test_set_password_generated(reset_auth_config):
    rc, out, _ = _run(["set-password", "anna", "--generate"])
    assert rc == 0
    assert "frissítve" in out
    # A régi jelszó már nem működik
    assert auth.verify_credentials("anna", "annapass") is False


def test_set_password_prompt(reset_auth_config, monkeypatch):
    rc, _, _ = _run(
        ["set-password", "anna"],
        monkeypatch=monkeypatch,
        prompt_password="uj-jelszo-123",
    )
    assert rc == 0
    assert auth.verify_credentials("anna", "uj-jelszo-123") is True
    assert auth.verify_credentials("anna", "annapass") is False


def test_promote_and_demote(reset_auth_config):
    assert auth.is_admin_user("anna") is False
    rc, _, _ = _run(["promote", "anna"])
    assert rc == 0
    assert auth.is_admin_user("anna") is True
    rc, _, _ = _run(["demote", "anna"])
    assert rc == 0
    assert auth.is_admin_user("anna") is False


def test_bootstrap_refuses_existing_without_force(reset_auth_config):
    rc, _, err = _run(["bootstrap"])
    assert rc == 2
    assert "létezik" in err


def test_bootstrap_with_force(reset_auth_config, monkeypatch):
    rc, out, _ = _run(
        ["bootstrap", "--force", "--generate"],
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    assert auth.is_admin_user("admin") is True
    # Alapból a régi userek eltűnnek — friss config
    assert auth.get_user("anna") is None


# ─── Csoport-parancsok ─────────────────────────────────────────────────
def test_groups_empty(reset_auth_config):
    """Alapban nincs csoport (a conftest üres groups-szal indít)."""
    rc, out, _ = _run(["groups"])
    assert rc == 0
    assert "Nincs" in out


def test_group_add(reset_auth_config):
    rc, out, _ = _run(["group-add", "anna", "import"])
    assert rc == 0
    assert "hozzáadva" in out
    assert auth.is_in_group("anna", "import") is True
    assert "import" in auth.user_groups("anna")


def test_group_add_creates_group(reset_auth_config):
    """Új csoport auto-létrejön, ha még nem létezik."""
    assert not (auth.AUTH_CONFIG.get("groups") or {}).get("reviewer")
    rc, _, _ = _run(["group-add", "anna", "reviewer"])
    assert rc == 0
    assert "anna" in auth.AUTH_CONFIG["groups"]["reviewer"]


def test_group_add_duplicate_is_noop(reset_auth_config):
    _run(["group-add", "anna", "import"])
    rc, out, _ = _run(["group-add", "anna", "import"])
    assert rc == 0
    assert "már tagja" in out


def test_group_add_unknown_user(reset_auth_config):
    rc, _, err = _run(["group-add", "nincsilyen", "import"])
    assert rc == 2
    assert "Nem létezik" in err


def test_group_remove(reset_auth_config):
    _run(["group-add", "anna", "import"])
    _run(["group-add", "bela", "import"])
    rc, out, _ = _run(["group-remove", "anna", "import"])
    assert rc == 0
    assert "eltávolítva" in out
    assert auth.is_in_group("anna", "import") is False
    assert auth.is_in_group("bela", "import") is True


def test_group_remove_deletes_empty_group(reset_auth_config):
    """Ha kivesszük az utolsó tagot, a csoport törlődik teljesen."""
    _run(["group-add", "anna", "import"])
    _run(["group-remove", "anna", "import"])
    groups = auth.AUTH_CONFIG.get("groups") or {}
    assert "import" not in groups


def test_group_remove_not_a_member(reset_auth_config):
    rc, _, err = _run(["group-remove", "anna", "import"])
    assert rc == 2
    assert "nem tagja" in err


def test_groups_lists_all(reset_auth_config):
    _run(["group-add", "anna", "import"])
    _run(["group-add", "bela", "reviewer"])
    rc, out, _ = _run(["groups"])
    assert rc == 0
    assert "import" in out
    assert "anna" in out
    assert "reviewer" in out
    assert "bela" in out


def test_list_shows_group_column(reset_auth_config):
    _run(["group-add", "anna", "import"])
    rc, out, _ = _run(["list"])
    assert rc == 0
    assert "GROUPS" in out
    # anna sorában szerepel az import
    for line in out.splitlines():
        if line.startswith("anna"):
            assert "import" in line
            break
    else:
        pytest.fail("Nincs anna sor a list outputban")
