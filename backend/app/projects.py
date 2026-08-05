"""
Projekt-mappa böngésző.

A repo gyökerében lévő `projects/` mappa alatt lévő struktúrát tesz elérhetővé.
Minden mappa lehet:
  - konténer mappa (subprojektek almappái)
  - terminális mappa (kép + annotáció párokat tartalmaz)

Egy mappa akkor is lehet vegyes: subfolder és pár is együtt.

Pár = azonos basename-ű kép + annotáció (JSON / ALTO XML / PAGE XML / generikus XML).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Optional

from . import acl, meta
from .auth import AUTH_CONFIG, is_admin_user


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROJECTS_ROOT = REPO_ROOT / "projects"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".gif"}

# Prioritási sorrend: ha egy basenamn-hez több annotáció van, ez alapján választunk
ANNOTATION_FORMAT_PRIORITY = ("json", "alto-xml", "page-xml", "xml")

# Per-folder config
DIR_CONFIG_FILENAME = ".htrground.json"
VALID_SAVE_FORMATS = {"json", "alto-xml", "page-xml"}
ANNOTATION_EXT = {
    "json":     ".json",
    "alto-xml": ".alto.xml",
    "page-xml": ".page.xml",
    "xml":      ".xml",
}


class PathEscapeError(ValueError):
    """A kért path kilépne a projects/ alól."""


def resolve_safe(user_path: str) -> Path:
    """A user path-ot feloldjuk a PROJECTS_ROOT-ra vetítve, escape-ellenőrzéssel."""
    if not user_path:
        return PROJECTS_ROOT
    # Slashes-tal normalizálva
    user_path = user_path.strip("/")
    p = (PROJECTS_ROOT / user_path).resolve()
    root_resolved = PROJECTS_ROOT.resolve()
    try:
        p.relative_to(root_resolved)
    except ValueError:
        raise PathEscapeError(f"A path kilép a projects/ alól: {user_path!r}")
    return p


def _detect_annotation(filename_lower: str) -> Optional[tuple[str, str]]:
    """Ha ez egy annotáció-fájl, add vissza (basename_lower_len, format).

    Compound-először (foo.alto.xml → format='alto-xml').
    """
    # Compound
    if filename_lower.endswith(".alto.xml"):
        return (len(filename_lower) - len(".alto.xml"), "alto-xml")
    if filename_lower.endswith(".page.xml"):
        return (len(filename_lower) - len(".page.xml"), "page-xml")
    # Egyszerű
    if filename_lower.endswith(".json"):
        return (len(filename_lower) - len(".json"), "json")
    if filename_lower.endswith(".xml"):
        return (len(filename_lower) - len(".xml"), "xml")
    return None


def _detect_image(filename_lower: str) -> Optional[int]:
    """Ha ez egy kép, add vissza a basename hosszát; egyébként None."""
    for ext in IMAGE_EXTS:
        if filename_lower.endswith(ext):
            return len(filename_lower) - len(ext)
    return None


def _classify(filename: str) -> Optional[tuple[str, str, Optional[str]]]:
    """(basename, kind, format) — kind: 'image' vagy 'annotation'; format csak annotációnál."""
    low = filename.lower()
    # A sidecart NE tekintsük annotációnak — a listázó külön kezeli
    if low.endswith(meta.META_EXT):
        return None
    ann = _detect_annotation(low)
    if ann is not None:
        base_len, fmt = ann
        return filename[:base_len], "annotation", fmt
    img_len = _detect_image(low)
    if img_len is not None:
        return filename[:img_len], "image", None
    return None


def _build_breadcrumb(user_path: str) -> List[Dict[str, str]]:
    crumbs = [{"name": "projects", "path": ""}]
    if user_path:
        parts = [p for p in user_path.split("/") if p]
        accum: List[str] = []
        for part in parts:
            accum.append(part)
            crumbs.append({"name": part, "path": "/".join(accum)})
    return crumbs


def _pick_best_annotation(annotations: Dict[str, dict]) -> Optional[dict]:
    """A priori sorrendben (JSON > ALTO > PAGE > XML) az elsőt választja."""
    for fmt in ANNOTATION_FORMAT_PRIORITY:
        if fmt in annotations:
            entry = annotations[fmt]
            entry["format"] = fmt
            return entry
    return None


class AccessDeniedError(PermissionError):
    """Az adott user nem látja a kért path-ot."""


def _projects_cfg() -> dict:
    return AUTH_CONFIG.get("projects") or {}


def _user_can_see(user_path: str, username: Optional[str]) -> bool:
    return acl.is_visible(
        user_path,
        username,
        is_admin=is_admin_user(username),
        projects_cfg=_projects_cfg(),
    )


def count_statuses(user_path: str, username: Optional[str] = None) -> dict:
    """Rekurzívan végigmegy a `user_path` alatti fán, minden pár státuszát
    aggregálja. ACL-tudatos: a rejtett almappák nem számítanak bele.

    Visszatérés:
      {
        "counts": {"új": N, "folyamatban": N, ...},  # csak nem-nulla értékek
        "total":  N,
      }
    """
    from collections import OrderedDict
    # Kezdetben minden érvényes státusz 0
    counts = OrderedDict((s, 0) for s in meta.VALID_STATUSES)

    if not _user_can_see(user_path, username):
        return {"counts": {}, "total": 0}

    root = resolve_safe(user_path)
    if not root.is_dir():
        return {"counts": {}, "total": 0}

    admin = is_admin_user(username)
    cfg = _projects_cfg()

    def _walk(folder: Path, rel: str):
        # Az aktuális mappa párainak státuszgyűjtése
        grouped: Dict[str, dict] = {}
        for entry in folder.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                # Almappa ACL check
                child_rel = f"{rel}/{entry.name}" if rel else entry.name
                if not acl.is_visible(child_rel, username, is_admin=admin, projects_cfg=cfg):
                    continue
                _walk(entry, child_rel)
                continue
            if not entry.is_file():
                continue
            classified = _classify(entry.name)
            if classified is None:
                continue
            basename, kind, _fmt = classified
            grouped.setdefault(basename, {"image": False, "has_annotation": False})
            if kind == "image":
                grouped[basename]["image"] = True
            else:
                grouped[basename]["has_annotation"] = True

        for basename, b in grouped.items():
            # Csak akkor számít, ha van kép VAGY annotáció
            if not (b["image"] or b["has_annotation"]):
                continue
            m = meta.read(folder, basename)
            status = m.get("status", meta.DEFAULT_STATUS)
            if status in counts:
                counts[status] += 1

    _walk(root, user_path.strip("/"))

    # Csak azokat a státuszokat adjuk vissza, ahol > 0 — a UI ezekből épít badge-eket
    # de meghagyjuk a rendezést (VALID_STATUSES sorrend)
    nonzero = OrderedDict((s, n) for s, n in counts.items() if n > 0)
    return {
        "counts": dict(nonzero),
        "total":  sum(nonzero.values()),
    }


def list_folder(user_path: str, username: Optional[str] = None) -> dict:
    """Egy mappa tartalmának JSON-esítése a frontend számára.

    ACL:
      - Ha a `user_path` maga rejtve van a `username` elől → AccessDeniedError.
      - Almappák szűrve: csak azok, amiket a user lát.
      - Fájlpárokra az ACL a szülő path szerint dönt (ha a mappát látod, a
        párokat is).
    """
    if not _user_can_see(user_path, username):
        raise AccessDeniedError(f"Nincs jogosultság a mappához: {user_path!r}")

    p = resolve_safe(user_path)
    if not p.exists():
        raise FileNotFoundError(f"Nem létezik: {user_path!r}")
    if not p.is_dir():
        raise NotADirectoryError(f"Nem mappa: {user_path!r}")

    subfolders: List[dict] = []
    # basename → {'image': {...}, 'annotations': {'json': {...}, 'alto-xml': {...}, ...}}
    grouped: Dict[str, dict] = {}

    admin = is_admin_user(username)
    cfg = _projects_cfg()

    for entry in sorted(p.iterdir(), key=lambda e: e.name.lower()):
        if entry.name.startswith("."):
            continue
        rel_child = f"{user_path.rstrip('/')}/{entry.name}" if user_path else entry.name
        stat = entry.stat()

        if entry.is_dir():
            # ACL szűrő: csak azok az almappák látszanak, amiket a user láthat
            if not acl.is_visible(rel_child, username, is_admin=admin, projects_cfg=cfg):
                continue
            subfolders.append({
                "name":     entry.name,
                "path":     rel_child,
                "modified": stat.st_mtime,
                # Az almappa rekurzív statisztikája — a UI kis dot-sávokra bontja
                "stats":    count_statuses(rel_child, username),
            })
            continue

        classified = _classify(entry.name)
        if classified is None:
            continue
        basename, kind, fmt = classified

        bucket = grouped.setdefault(basename, {"image": None, "annotations": {}})
        entry_info = {
            "filename": entry.name,
            "modified": stat.st_mtime,
            "size":     stat.st_size,
        }
        if kind == "image":
            bucket["image"] = entry_info
        else:
            bucket["annotations"][fmt or "xml"] = entry_info

    # Párok felépítése — csak azok jelennek meg, akiknek van vagy képük vagy annotációjuk
    pairs: List[dict] = []
    for basename in sorted(grouped.keys(), key=str.lower):
        b = grouped[basename]
        image = b["image"]
        annotation = _pick_best_annotation(b["annotations"])
        if not image and not annotation:
            continue
        # Módosítási idő: a késöbbi kettő közül
        mtimes = [x["modified"] for x in (image, annotation) if x]
        pairs.append({
            "basename":   basename,
            "image":      image,
            "annotation": annotation,
            "modified":   max(mtimes) if mtimes else None,
            "meta":       meta.read(p, basename),
            # Ha több annotáció is van, a többiről is tudjon a kliens
            "other_annotations": [
                {"format": fmt, **info}
                for fmt, info in b["annotations"].items()
                if annotation is None or fmt != annotation.get("format")
            ],
        })

    return {
        "path":       user_path,
        "breadcrumb": _build_breadcrumb(user_path),
        "subfolders": subfolders,
        "pairs":      pairs,
        "stats":      count_statuses(user_path, username),
    }


# ─── Per-folder config ──────────────────────────────────────────────────
def load_dir_config(folder: Path) -> dict:
    """Ha van `.htrground.json` a mappában, betöltjük; egyébként üres dict."""
    cfg_path = folder / DIR_CONFIG_FILENAME
    if not cfg_path.exists():
        return {}
    try:
        with cfg_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


# ─── Egy pár betöltése ──────────────────────────────────────────────────
def find_pair(user_path: str, basename: str, username: Optional[str] = None) -> Dict[str, Optional[Path]]:
    """Adott mappában adott basename-hez keresi meg a képet és annotációkat.

    ACL: ha `username` át van adva, ellenőrizzük, hogy látja-e a mappát.

    Visszatérés:
      {
        "folder":            <Path>,
        "image":             <Path or None>,
        "annotations":       {"json": Path, "alto-xml": Path, ...},
      }
    """
    if username is not None and not _user_can_see(user_path, username):
        raise AccessDeniedError(f"Nincs jogosultság a mappához: {user_path!r}")
    folder = resolve_safe(user_path)
    if not folder.is_dir():
        raise NotADirectoryError(f"Nem mappa: {user_path!r}")

    result: Dict = {"folder": folder, "image": None, "annotations": {}}
    basename_lower = basename.lower()

    for entry in folder.iterdir():
        if not entry.is_file() or entry.name.startswith("."):
            continue
        classified = _classify(entry.name)
        if classified is None:
            continue
        base, kind, fmt = classified
        if base.lower() != basename_lower:
            continue
        if kind == "image":
            result["image"] = entry
        else:
            result["annotations"][fmt or "xml"] = entry

    return result


def _pick_best_annotation_path(annotations: Dict[str, Path]) -> Optional[tuple[str, Path]]:
    for fmt in ANNOTATION_FORMAT_PRIORITY:
        if fmt in annotations:
            return fmt, annotations[fmt]
    return None


def load_pair(user_path: str, basename: str, username: Optional[str] = None):
    """Egy pár betöltése.

    Visszatérés:
      {
        "path":                user_path,
        "basename":            basename,
        "annotation_bytes":    <bytes> (a legjobb annotáció tartalma),
        "annotation_format":   "json" | "alto-xml" | "page-xml" | "xml",
        "annotation_filename": "foo.json",
        "image_filename":      "foo.jpg" or None,
        "save_format":         "json" | "alto-xml" | "page-xml"  (dir config vagy annotation_format),
      }
    """
    found = find_pair(user_path, basename, username=username)
    ann = _pick_best_annotation_path(found["annotations"])
    if ann is None:
        raise FileNotFoundError(f"Nincs annotáció a párhoz: {user_path}/{basename}")
    ann_format, ann_path = ann

    image = found["image"]
    dir_cfg = load_dir_config(found["folder"])
    save_format = dir_cfg.get("save_format", ann_format)
    if save_format not in VALID_SAVE_FORMATS:
        # Ha a config érvénytelen vagy 'xml' (nem tudjuk milyen), az annotation_format-ra esünk vissza
        save_format = ann_format if ann_format in VALID_SAVE_FORMATS else "json"

    return {
        "path":                user_path,
        "basename":            basename,
        "annotation_bytes":    ann_path.read_bytes(),
        "annotation_format":   ann_format,
        "annotation_filename": ann_path.name,
        "image_filename":      image.name if image else None,
        "save_format":         save_format,
    }


# ─── Mentés / felülírás ─────────────────────────────────────────────────
def save_pair(user_path: str, basename: str, content: bytes, save_format: str,
              username: Optional[str] = None) -> Path:
    """A `content` bájtsort menti a megfelelő fájlnévre a mappában.

    Ha ugyanazon a basename-on ugyanabban a formátumban már van fájl, felülírjuk.
    Ha más formátumú testvérfájl van, azt békén hagyjuk (nem törlünk semmit).

    ACL: ha `username` át van adva, ellenőrizzük a láthatóságot.

    Visszatérés: a mentett fájl teljes path-a.
    """
    if save_format not in VALID_SAVE_FORMATS:
        raise ValueError(f"Ismeretlen save_format: {save_format!r}")

    if username is not None and not _user_can_see(user_path, username):
        raise AccessDeniedError(f"Nincs jogosultság a mappához: {user_path!r}")

    folder = resolve_safe(user_path)
    if not folder.is_dir():
        raise NotADirectoryError(f"Nem mappa: {user_path!r}")

    ext = ANNOTATION_EXT[save_format]
    target = folder / (basename + ext)
    # Atomikus írás: átmeneti .tmp fájlba, aztán rename
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(content)
    tmp.replace(target)
    return target
