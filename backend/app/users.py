"""
User admin CLI. Használat:

    python -m app.users bootstrap                # első futáskor: auth.json + admin user
    python -m app.users list
    python -m app.users add <username> [display]  # jelszó interaktív, vagy --generate
    python -m app.users remove <username>
    python -m app.users set-password <username>   # jelszó interaktív, vagy --generate
    python -m app.users promote <username>        # admin flag beállítása
    python -m app.users demote <username>         # admin flag levétele

A jelszót SOHA nem tároljuk plaintext-ként — bcrypt hash-t rakunk az
`auth.json`-be. A generált jelszó egyszer jelenik meg a terminálon.
"""
from __future__ import annotations

import argparse
import getpass
import secrets
import sys
from typing import Optional

from . import auth


# ─── Segédek ─────────────────────────────────────────────────────────────
def _generate_password(length_words: int = 2) -> str:
    """Rövid, olvashatóan elválasztott, magas entrópiájú jelszó.

    Formátum: 4 blokk × 4 alfanumerikus, kötőjellel — pl. `k7Qm-vXn9-pR2t-Lb8H`.
    Entrópia: ~95 bit — bőven elég, kezelhető is manuálisan átgépeléshez.
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    blocks = []
    for _ in range(length_words):
        blocks.append("".join(secrets.choice(alphabet) for _ in range(4)))
    return "-".join(blocks)


def _prompt_password_interactive() -> str:
    while True:
        p1 = getpass.getpass("Új jelszó: ")
        if not p1:
            print("Üres jelszó nem megengedett.", file=sys.stderr)
            continue
        p2 = getpass.getpass("Jelszó ismét: ")
        if p1 != p2:
            print("A két jelszó nem egyezik. Próbáld újra.", file=sys.stderr)
            continue
        return p1


def _resolve_password(generate: bool) -> tuple[str, bool]:
    """Visszaadja: (jelszó, generált-e).

    Ha `generate=True`, generálunk egyet. Egyébként interaktív prompt.
    """
    if generate:
        return _generate_password(), True
    return _prompt_password_interactive(), False


def _load_or_fresh_config() -> dict:
    """Ha nincs még auth.json, egy friss config-ot indítunk el belőle."""
    try:
        return auth.load_auth_config()
    except auth.AuthConfigError:
        # Ha maga a fájl olvasáskor is elhasal, tényleg friss telepítés — de
        # az `AuthConfigError` a régi (v1) shape-re is jön; ezt itt továbbdobjuk.
        raise


def _fresh_config() -> dict:
    return {
        "session_secret":          auth.generate_session_secret(),
        "session_cookie_name":     "htrground_session",
        "session_max_age_seconds": 604800,
        "users":                   {},
        "projects":                {},
    }


def _print_password_banner(username: str, password: str) -> None:
    print()
    print(f"  Egyszeri jelszó ({username}): {password}")
    print()
    print("  Ez az egyetlen alkalom, hogy ez a jelszó megjelenik.")
    print("  Ha elveszik: python -m app.users set-password " + username)
    print()


# ─── Parancsok ───────────────────────────────────────────────────────────
def cmd_bootstrap(args: argparse.Namespace) -> int:
    """Első futáshoz: hoz létre auth.json-t egy admin userrel."""
    auth_path, _ = auth._config_paths()
    if auth_path.exists() and not args.force:
        print(
            f"Már létezik: {auth_path}\n"
            "Ha újra akarod inicializálni: --force (figyelem: felülír).",
            file=sys.stderr,
        )
        return 2

    cfg = _fresh_config()
    admin_username = args.username or "admin"
    password, was_generated = _resolve_password(args.generate)

    cfg["users"][admin_username] = {
        "display_name":  args.display or "Adminisztrátor",
        "password_hash": auth.hash_password(password),
        "is_admin":      True,
    }
    auth.save_auth_config(cfg)
    auth.reload_config()

    print(f"✓ {auth_path.name} létrehozva.")
    print(f"✓ Admin user létrehozva: {admin_username} (is_admin: true)")
    if was_generated:
        _print_password_banner(admin_username, password)
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    cfg = _load_or_fresh_config()
    users = cfg.setdefault("users", {})
    if args.username in users:
        print(f"Már létezik ilyen user: {args.username}", file=sys.stderr)
        return 2

    password, was_generated = _resolve_password(args.generate)
    users[args.username] = {
        "display_name":  args.display or args.username,
        "password_hash": auth.hash_password(password),
        "is_admin":      bool(args.admin),
    }
    auth.save_auth_config(cfg)
    auth.reload_config()
    print(f"✓ {args.username} hozzáadva{' (admin)' if args.admin else ''}.")
    if was_generated:
        _print_password_banner(args.username, password)
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    cfg = _load_or_fresh_config()
    users = cfg.get("users") or {}
    if args.username not in users:
        print(f"Nem létezik: {args.username}", file=sys.stderr)
        return 2
    del users[args.username]
    auth.save_auth_config(cfg)
    auth.reload_config()
    print(f"✓ {args.username} törölve.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    cfg = _load_or_fresh_config()
    users = cfg.get("users") or {}
    if not users:
        print("Nincs egy user sem. Használd: python -m app.users bootstrap")
        return 0
    # Igazítás: leghosszabb usernév kiterjedésére
    max_name = max(len(u) for u in users)
    max_disp = max((len(u.get("display_name") or "") for u in users.values()), default=0)
    print(f"{'USER'.ljust(max_name)}  {'DISPLAY NAME'.ljust(max_disp)}  ADMIN")
    for name in sorted(users.keys(), key=str.lower):
        u = users[name]
        disp  = u.get("display_name") or ""
        admin = "✓" if u.get("is_admin") else ""
        print(f"{name.ljust(max_name)}  {disp.ljust(max_disp)}  {admin}")
    return 0


def cmd_set_password(args: argparse.Namespace) -> int:
    cfg = _load_or_fresh_config()
    users = cfg.get("users") or {}
    if args.username not in users:
        print(f"Nem létezik: {args.username}", file=sys.stderr)
        return 2

    password, was_generated = _resolve_password(args.generate)
    users[args.username]["password_hash"] = auth.hash_password(password)
    auth.save_auth_config(cfg)
    auth.reload_config()
    print(f"✓ {args.username} jelszava frissítve.")
    if was_generated:
        _print_password_banner(args.username, password)
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    return _set_admin_flag(args.username, True)


def cmd_demote(args: argparse.Namespace) -> int:
    return _set_admin_flag(args.username, False)


def _set_admin_flag(username: str, value: bool) -> int:
    cfg = _load_or_fresh_config()
    users = cfg.get("users") or {}
    if username not in users:
        print(f"Nem létezik: {username}", file=sys.stderr)
        return 2
    users[username]["is_admin"] = value
    auth.save_auth_config(cfg)
    auth.reload_config()
    verb = "promotálva (admin)" if value else "demotálva (nem admin)"
    print(f"✓ {username} {verb}.")
    return 0


# ─── Argparse ────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m app.users",
        description="HTR-ground user adminisztráció",
    )
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("bootstrap", help="Első futáshoz: auth.json + admin user")
    b.add_argument("--username", default=None, help="Admin usernév (default: 'admin')")
    b.add_argument("--display",  default=None, help="Megjelenített név")
    b.add_argument("--generate", action="store_true", help="Erős jelszó generálása")
    b.add_argument("--force",    action="store_true", help="Meglévő auth.json felülírása")
    b.set_defaults(func=cmd_bootstrap)

    a = sub.add_parser("add", help="Új user hozzáadása")
    a.add_argument("username")
    a.add_argument("display", nargs="?", default=None)
    a.add_argument("--admin",    action="store_true")
    a.add_argument("--generate", action="store_true")
    a.set_defaults(func=cmd_add)

    r = sub.add_parser("remove", help="User törlése")
    r.add_argument("username")
    r.set_defaults(func=cmd_remove)

    ls = sub.add_parser("list", help="Userek listázása")
    ls.set_defaults(func=cmd_list)

    sp = sub.add_parser("set-password", help="Jelszó frissítés")
    sp.add_argument("username")
    sp.add_argument("--generate", action="store_true")
    sp.set_defaults(func=cmd_set_password)

    pr = sub.add_parser("promote", help="Admin jog megadása")
    pr.add_argument("username")
    pr.set_defaults(func=cmd_promote)

    dm = sub.add_parser("demote", help="Admin jog levétele")
    dm.add_argument("username")
    dm.set_defaults(func=cmd_demote)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except auth.AuthConfigError as e:
        print(f"Config hiba: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
