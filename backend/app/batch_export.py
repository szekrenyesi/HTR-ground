"""
Kötegelt export egy projekt-mappa (vagy annak almappái) tartalmából.

Egy vagy több formátumban (ALTO / PAGE / JSON / PDF), opcionálisan a
képekkel és sidecar metaadatokkal együtt egy ZIP-be csomagolva.

Az algoritmus:
  - Bejárja a mappa (opcionálisan almappák) párját (kép + annotáció[k])
  - Minden párra minden kért annotációs formátumra:
      * Ha már létezik a párhoz ilyen formátumú fájl ÉS az a LEGFRISSEBB
        (mtime szerint) az annotációk között → beemelés AS-IS
      * Egyébként → konvertálás a legfrissebb annotációból
  - Kép: beemelés AS-IS, ha a felhasználó kérte
  - Sidecar (`.htrground-meta.json`): beemelés AS-IS, ha kérte
  - PDF: kép nélküli páron kihagyás, warning-ba téve
  - ACL: a `list_folder` szintjén már szűrtük; itt csak azt kapjuk, amit lát

A ZIP mappastruktúrája megegyezik a forrással: a `root_user_path`-hoz képest
relatív path-tal kerülnek be a fájlok.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import projects as proj_mod
from . import meta as pair_meta
from .converters import EXPORT_EXT, convert, export as export_page, to_pdf
from .schema import Page


# ─── Konstansok ──────────────────────────────────────────────────────────
# Egyszerre elérhető formátumok, felsorolás sorrendje = UI checkbox sorrend
ANNOTATION_FORMATS = ("alto-xml", "page-xml", "json")
PDF_FORMAT = "pdf"
ALL_FORMATS = ANNOTATION_FORMATS + (PDF_FORMAT,)


# ─── Segéd: párok bejárása ───────────────────────────────────────────────
def _iter_pairs(root: Path, recursive: bool):
    """A mappa (és opcionálisan almappák) párját visszaadja.

    Yield: (folder: Path, basename: str, image_path: Optional[Path],
            annotations: Dict[format, Path])
    """
    walker = root.rglob("*") if recursive else root.iterdir()
    # rglob mindent visszaad, iterdir csak a közvetlen gyerekeket.
    # Csoportosítás: (folder, basename) → {image, annotations}
    grouped: Dict[Tuple[Path, str], Dict] = {}
    for entry in walker:
        if not entry.is_file() or entry.name.startswith("."):
            continue
        classified = proj_mod._classify(entry.name)
        if classified is None:
            continue
        basename, kind, fmt = classified
        key = (entry.parent, basename)
        bucket = grouped.setdefault(key, {"image": None, "annotations": {}})
        if kind == "image":
            bucket["image"] = entry
        else:
            bucket["annotations"][fmt or "xml"] = entry

    # Determinisztikus rendezés: mappa path → basename
    for (folder, basename) in sorted(grouped.keys(), key=lambda k: (str(k[0]).lower(), k[1].lower())):
        b = grouped[(folder, basename)]
        if not b["image"] and not b["annotations"]:
            continue
        yield folder, basename, b["image"], b["annotations"]


# ─── Segéd: „legfrissebb" annotáció ──────────────────────────────────────
def _newest_annotation(annotations: Dict[str, Path]) -> Optional[Tuple[str, Path]]:
    """A legnagyobb mtime-mel bíró annotációt adja vissza (format, path).

    Ha üres a szótár → None. Egyenlő mtime-nál a formátum-prioritás dönt
    (JSON > ALTO XML > PAGE XML > xml) — determinisztikusság miatt.
    """
    if not annotations:
        return None
    priority = {fmt: i for i, fmt in enumerate(proj_mod.ANNOTATION_FORMAT_PRIORITY)}
    def key(item):
        fmt, path = item
        # Nagyobb mtime előre; egyezésnél a kisebb prioritás-index (JSON=0) előre
        return (-path.stat().st_mtime, priority.get(fmt, 99))
    return sorted(annotations.items(), key=key)[0]


def _load_page_from(source_path: Path) -> Page:
    """Egy annotáció-fájlból belső Page-t olvas be."""
    return convert(source_path.read_bytes(), filename=source_path.name)


# ─── ZIP entry-generálás egy párra ───────────────────────────────────────
def _annotation_bytes_for(
    fmt: str,
    annotations: Dict[str, Path],
    newest_page_cache: Dict[str, Page],
    image_filename: str = "",
) -> bytes:
    """A kért formátumhoz adja vissza a bájtokat.

    - Ha létezik ez a formátum ÉS ez a legfrissebb → AS-IS
    - Egyébként a legfrissebbből konvertálunk
    - A `newest_page_cache` egy dict, ami a párra egyszer konvertált Page-t
      tárolja, hogy több formátum egyszerre-generálásakor ne konvertáljunk
      többször ugyanabból a forrásból.
    """
    newest = _newest_annotation(annotations)
    if newest is None:
        raise ValueError("nincs annotáció a párhoz")
    newest_fmt, newest_path = newest

    existing_path = annotations.get(fmt)
    if existing_path is not None and existing_path == newest_path:
        # A kért formátum ÉS legfrissebb ugyanaz → AS-IS
        return existing_path.read_bytes()

    # Konvertálás a legfrissebbből
    if "page" not in newest_page_cache:
        newest_page_cache["page"] = _load_page_from(newest_path)
    return export_page(newest_page_cache["page"], fmt, image_filename=image_filename)


# ─── Fő belépési pont ────────────────────────────────────────────────────
def build_zip(
    user_path: str,
    formats: List[str],
    *,
    include_images: bool = False,
    include_sidecars: bool = False,
    recursive: bool = True,
) -> Tuple[bytes, Dict[str, list]]:
    """Egy mappa exportját ZIP-be csomagolja.

    Args:
      user_path:        a projekt-fa alatti path (pl. "Bakonykuti/1949"),
                        `""` = a projects/ gyökere. **ACL-t itt már NEM
                        ellenőrzünk** — a hívó (main.py endpoint) felelős.
      formats:          annotációs formátumok listája: "alto-xml", "page-xml",
                        "json", "pdf" közül. Üres lista is megengedett, ha
                        pl. csak képek/sidecarok kellenek.
      include_images:   képfájlokat is beemeljük a ZIP-be
      include_sidecars: `.htrground-meta.json` sidecarokat is beemeljük

    Returns:
      (zip_bytes, warnings) — a warnings egy dict kulcsonként listával:
        - "skipped_pdf":         PDF kihagyva (nincs kép a párhoz)
        - "no_annotation":       pár, aminek nincs egyetlen annotációja sem
        - "conversion_error":    konverziós hibák
    """
    for fmt in formats:
        if fmt not in ALL_FORMATS:
            raise ValueError(f"Ismeretlen formátum: {fmt!r}")

    root = proj_mod.resolve_safe(user_path)
    if not root.is_dir():
        raise NotADirectoryError(f"Nem mappa: {user_path!r}")

    warnings: Dict[str, list] = {
        "skipped_pdf":      [],
        "no_annotation":    [],
        "conversion_error": [],
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for folder, basename, image_path, annotations in _iter_pairs(root, recursive):
            rel_folder = folder.relative_to(root)
            rel_str = "" if str(rel_folder) == "." else str(rel_folder)

            # Kép beemelés
            if include_images and image_path is not None:
                arcname = _arcname(rel_str, image_path.name)
                zf.write(image_path, arcname)

            # Sidecar beemelés
            if include_sidecars:
                sidecar_path = pair_meta.sidecar_path(folder, basename)
                if sidecar_path.exists():
                    arcname = _arcname(rel_str, sidecar_path.name)
                    zf.write(sidecar_path, arcname)

            # Ha kell annotációs formátum, de nincs egyetlen annotáció sem
            annotation_formats_requested = [f for f in formats if f in ANNOTATION_FORMATS]
            has_any_annotation = bool(annotations)
            if annotation_formats_requested and not has_any_annotation:
                warnings["no_annotation"].append(f"{rel_str}/{basename}".lstrip("/"))
                # PDF kérés esetén is ki kell hagyni — nincs mit konvertálni

            # Annotációs formátumok generálása
            page_cache: Dict[str, Page] = {}
            for fmt in annotation_formats_requested:
                if not has_any_annotation:
                    continue
                try:
                    content = _annotation_bytes_for(
                        fmt, annotations, page_cache,
                        image_filename=image_path.name if image_path else "",
                    )
                except Exception as e:
                    warnings["conversion_error"].append(
                        f"{rel_str}/{basename} → {fmt}: {e}".lstrip("/")
                    )
                    continue
                arcname = _arcname(rel_str, basename + EXPORT_EXT[fmt])
                zf.writestr(arcname, content)

            # PDF generálás
            if PDF_FORMAT in formats:
                if image_path is None:
                    warnings["skipped_pdf"].append(f"{rel_str}/{basename}".lstrip("/"))
                elif not has_any_annotation:
                    # Ha nincs annotáció, a fenti no_annotation ág már felvette
                    pass
                else:
                    try:
                        if "page" not in page_cache:
                            newest = _newest_annotation(annotations)
                            page_cache["page"] = _load_page_from(newest[1])
                        pdf_bytes = to_pdf.export(page_cache["page"], image_path.read_bytes())
                        arcname = _arcname(rel_str, basename + ".pdf")
                        zf.writestr(arcname, pdf_bytes)
                    except Exception as e:
                        warnings["conversion_error"].append(
                            f"{rel_str}/{basename} → pdf: {e}".lstrip("/")
                        )

    # Üres warning-listák kihagyása
    warnings = {k: v for k, v in warnings.items() if v}
    return buffer.getvalue(), warnings


def _arcname(rel_folder: str, filename: str) -> str:
    """A ZIP-en belüli path. Windows-kompatibilitáshoz `/` elválasztó."""
    if not rel_folder or rel_folder == ".":
        return filename
    return f"{rel_folder.replace(chr(92), '/')}/{filename}"


def zip_filename_for(user_path: str) -> str:
    """A letölthető ZIP fájlneve: a path `/` → `-`, üres path esetén 'projects'."""
    p = (user_path or "").strip("/")
    if not p:
        return "projects.zip"
    return p.replace("/", "-") + ".zip"


def encode_warnings_header(warnings: Dict[str, list]) -> str:
    """A warning-eket egy header-be sűrítjük (JSON string)."""
    if not warnings:
        return ""
    return json.dumps(warnings, ensure_ascii=False)
