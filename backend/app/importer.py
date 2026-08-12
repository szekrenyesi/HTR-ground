"""
Import + törlés — webes felületről.

Négy operáció:
  - `create_folder(path, username)`     — új mappa létrehozása
  - `upload_files(path, files, ...)`    — fájlok feltöltése egy mappába
  - `delete_folder(path, username)`     — mappa törlése rekurzívan (admin)
  - `delete_pair(path, basename, ...)`  — egy pár összes fájlja (admin)

Jogosultság:
  - `create_folder` / `upload_files`: admin VAGY 'import' csoport tag.
    Nem-adminra érvényesül az ACL (a target mappának láthatónak kell lennie).
  - `delete_*`: csak admin.

Fájl-elfogadás (upload):
  - Kép: .jpg, .jpeg, .png, .tif, .tiff, .gif
  - Annotáció: .json, .xml (beleértve .alto.xml, .page.xml)
  - Minden más → skip warning-gal
  - Dotfile (nevben `.`-ral kezdődik) → skip warning-gal
  - Meglévő fájl → NEM írjuk felül, skip warning-gal
  - Path-safety: `..`, abszolút, üres komponens → PathEscapeError → HTTP 400
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import projects as proj_mod
from .projects import PathEscapeError, resolve_safe


# ─── Elfogadott kiterjesztések ───────────────────────────────────────────
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".gif"}
ALLOWED_ANNOTATION_EXTS = {".json", ".xml"}


class ImportError(Exception):
    """Import-oldali hiba (pl. már létező mappa, invalid név)."""


def _has_allowed_extension(filename: str) -> bool:
    """A filename kiterjesztése megengedett-e?

    A `.alto.xml` és `.page.xml` compound extensionokat is elfogadja, mert
    a `.xml`-t engedélyezzük."""
    low = filename.lower()
    for ext in ALLOWED_IMAGE_EXTS | ALLOWED_ANNOTATION_EXTS:
        if low.endswith(ext):
            return True
    return False


def _validate_rel_path(rel: str) -> List[str]:
    """Egy relatív path-ot validál és felbont path-elemekre.

    Elutasítja: abszolút path, `..`, üres komponens, dotfile-t bárhol.
    """
    if not rel:
        raise ImportError("Üres path.")
    # Normalizáljuk: `/`-ekre bontjuk, kivesszük az üreseket
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    if not parts:
        raise ImportError(f"Érvénytelen path: {rel!r}")
    for p in parts:
        if p in (".", ".."):
            raise PathEscapeError(f"Tiltott path-elem: {p!r}")
        if p.startswith("."):
            raise ImportError(f"Rejtett fájlok / mappák tiltva: {p!r}")
        if "/" in p or "\\" in p:
            raise ImportError(f"Érvénytelen karakter a névben: {p!r}")
    return parts


# ─── Mappa létrehozás ────────────────────────────────────────────────────
def create_folder(path: str) -> Path:
    """Létrehoz egy új mappát a projects-fa alatt.

    A hívó (main.py) felelős az auth + ACL ellenőrzésért — itt csak a
    path-safety-t validáljuk.

    Támogatja a mkdir -p szemantikát: közbenső mappákat is létrehozza.
    """
    parts = _validate_rel_path(path)
    target = resolve_safe("/".join(parts))
    if target.exists():
        raise ImportError(f"Már létezik: {path!r}")
    target.mkdir(parents=True, exist_ok=False)
    return target


# ─── Fájl-feltöltés ──────────────────────────────────────────────────────
def upload_files(
    parent_path: str,
    files: List[Tuple[str, bytes]],
) -> Dict[str, list]:
    """Fájlokat helyez el a `parent_path` alatti mappa-fába.

    `files` egy lista: [(relative_path, content_bytes), ...]

    A `relative_path` a `parent_path`-hoz képest relatív; támogat almappákat
    (pl. `1949/oldal_001.jpg`). Ha a mappa nem létezik, automatikusan
    létrehozzuk.

    Visszatérés:
      {
        "uploaded":  ["1949/oldal_001.jpg", ...],
        "skipped":   [{"path": "...", "reason": "..."}, ...],
      }
    """
    parent = resolve_safe(parent_path) if parent_path else resolve_safe("")
    if not parent.is_dir():
        raise ImportError(f"A cél mappa nem létezik: {parent_path!r}")

    uploaded: List[str] = []
    skipped:  List[dict] = []

    for rel, content in files:
        try:
            parts = _validate_rel_path(rel)
        except (PathEscapeError, ImportError) as e:
            skipped.append({"path": rel, "reason": str(e)})
            continue

        filename = parts[-1]
        if not _has_allowed_extension(filename):
            skipped.append({
                "path": rel,
                "reason": f"Kiterjesztés nem engedélyezett — csak .jpg/.jpeg/.png/.tif/.tiff/.gif/.xml/.json",
            })
            continue

        # A target mappa a parent-en belül van + a relatív komponensek (az utolsó a fájlnév)
        target_dir = parent.joinpath(*parts[:-1]) if len(parts) > 1 else parent
        target_file = target_dir / filename

        # Path escape final check — `resolve()` biztosítja hogy nem menekülünk
        try:
            parent_res = parent.resolve()
            resolved = target_file.resolve()
            resolved.relative_to(parent_res)  # raises ValueError ha kilépne
        except ValueError:
            skipped.append({"path": rel, "reason": "path kilép a target-ből"})
            continue

        # SOHA nem írjuk felül a meglévő fájlt
        if target_file.exists():
            skipped.append({"path": rel, "reason": "már létezik, nem írjuk felül"})
            continue

        # Létrehozzuk a közbenső mappákat, ha kell
        target_dir.mkdir(parents=True, exist_ok=True)

        # Írás — atomikusan (.tmp + rename)
        tmp = target_file.with_suffix(target_file.suffix + ".tmp")
        try:
            tmp.write_bytes(content)
            tmp.replace(target_file)
        except OSError as e:
            skipped.append({"path": rel, "reason": f"írási hiba: {e}"})
            if tmp.exists():
                try: tmp.unlink()
                except OSError: pass
            continue

        # Ki bejegyzés — a rel path-ot mutatjuk, a userre nézve az elárul mindent
        uploaded.append(rel)

    return {"uploaded": uploaded, "skipped": skipped}


# ─── Törlés — csak admin ─────────────────────────────────────────────────
def delete_folder(path: str) -> Dict:
    """Rekurzívan törli a mappát. A hívó felelős admin ellenőrzésért.

    Visszatérés:
      { "path": "...", "deleted": True }
    """
    parts = _validate_rel_path(path)
    target = resolve_safe("/".join(parts))
    if not target.exists():
        raise FileNotFoundError(f"Nem létezik: {path!r}")
    if not target.is_dir():
        raise NotADirectoryError(f"Nem mappa: {path!r}")
    # Extra biztonsági check: soha ne töröljük magát a projects/ gyökeret
    if target.resolve() == proj_mod.PROJECTS_ROOT.resolve():
        raise ImportError("A projects/ gyökeret nem lehet törölni.")
    shutil.rmtree(target)
    return {"path": path, "deleted": True}


def delete_pair(path: str, basename: str) -> Dict:
    """Egy pár összes fájljának törlése: kép + minden annotáció + sidecar.

    A hívó felelős admin ellenőrzésért.

    Visszatérés:
      { "deleted": ["foo.jpg", "foo.json", "foo.htrground-meta.json"] }
    """
    from . import meta as pair_meta  # circular import elkerülésre

    found = proj_mod.find_pair(path, basename)  # ACL bypass — a hívó admin
    folder = found["folder"]

    deleted: List[str] = []

    # Kép
    if found["image"] is not None:
        try:
            found["image"].unlink()
            deleted.append(found["image"].name)
        except OSError:
            pass

    # Minden annotáció
    for _fmt, ann_path in found["annotations"].items():
        try:
            ann_path.unlink()
            deleted.append(ann_path.name)
        except OSError:
            pass

    # Sidecar
    sidecar = pair_meta.sidecar_path(folder, basename)
    if sidecar.exists():
        try:
            sidecar.unlink()
            deleted.append(sidecar.name)
        except OSError:
            pass

    if not deleted:
        raise FileNotFoundError(f"Nincs mit törölni: {path}/{basename}")

    return {"deleted": deleted}
