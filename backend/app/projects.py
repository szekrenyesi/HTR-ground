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


def list_folder(user_path: str) -> dict:
    """Egy mappa tartalmának JSON-esítése a frontend számára."""
    p = resolve_safe(user_path)
    if not p.exists():
        raise FileNotFoundError(f"Nem létezik: {user_path!r}")
    if not p.is_dir():
        raise NotADirectoryError(f"Nem mappa: {user_path!r}")

    subfolders: List[dict] = []
    # basename → {'image': {...}, 'annotations': {'json': {...}, 'alto-xml': {...}, ...}}
    grouped: Dict[str, dict] = {}

    for entry in sorted(p.iterdir(), key=lambda e: e.name.lower()):
        if entry.name.startswith("."):
            continue
        rel_child = f"{user_path.rstrip('/')}/{entry.name}" if user_path else entry.name
        stat = entry.stat()

        if entry.is_dir():
            subfolders.append({
                "name": entry.name,
                "path": rel_child,
                "modified": stat.st_mtime,
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
def find_pair(user_path: str, basename: str) -> Dict[str, Optional[Path]]:
    """Adott mappában adott basename-hez keresi meg a képet és annotációkat.

    Visszatérés:
      {
        "folder":            <Path>,
        "image":             <Path or None>,
        "annotations":       {"json": Path, "alto-xml": Path, ...},
      }
    """
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


def load_pair(user_path: str, basename: str):
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
    found = find_pair(user_path, basename)
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
def save_pair(user_path: str, basename: str, content: bytes, save_format: str) -> Path:
    """A `content` bájtsort menti a megfelelő fájlnévre a mappában.

    Ha ugyanazon a basename-on ugyanabban a formátumban már van fájl, felülírjuk.
    Ha más formátumú testvérfájl van, azt békén hagyjuk (nem törlünk semmit).

    Visszatérés: a mentett fájl teljes path-a.
    """
    if save_format not in VALID_SAVE_FORMATS:
        raise ValueError(f"Ismeretlen save_format: {save_format!r}")

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
