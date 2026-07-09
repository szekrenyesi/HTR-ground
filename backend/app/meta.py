"""
Per-fájl sidecar (`.htrground-meta.json`) írás/olvasás.

Egy sidecar egyetlen pár (basename) mellett él, a képével és annotációjával
azonos mappában:

    projects/<...>/<basename>.jpg
    projects/<...>/<basename>.alto.xml
    projects/<...>/<basename>.htrground-meta.json     ← ez

Tartalma:

    {
      "status":            "folyamatban",     # kötelező, enum
      "status_changed_by": "anna",             # ki állította a státuszt (opcionális)
      "status_changed_at": "2026-07-09T…Z",   # ISO 8601 UTC
      "edited_by":         "anna",             # ki mentett utoljára (opcionális)
      "edited_at":         "2026-07-09T…Z",
      "notes":             ""                  # szabad szöveg
    }

Az alapstátusz `"új"` — ez akkor is megjelenik a listázásban, ha egy fájlnak
még nincs sidecar-ja.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


META_EXT = ".htrground-meta.json"

VALID_STATUSES = ("új", "folyamatban", "ellenőrzésre vár", "kész")
DEFAULT_STATUS = "új"


def sidecar_path(folder: Path, basename: str) -> Path:
    return folder / f"{basename}{META_EXT}"


def default_meta() -> Dict[str, Any]:
    """Az alapállapot, ha nincs sidecar."""
    return {
        "status":            DEFAULT_STATUS,
        "status_changed_by": None,
        "status_changed_at": None,
        "edited_by":         None,
        "edited_at":         None,
        "notes":             "",
    }


def _validate_status(value: str) -> str:
    if value not in VALID_STATUSES:
        raise ValueError(
            f"Ismeretlen státusz: {value!r}. "
            f"Engedélyezett: {', '.join(VALID_STATUSES)}"
        )
    return value


def read(folder: Path, basename: str) -> Dict[str, Any]:
    """Betölti a sidecart, vagy visszaadja az alapértékeket, ha nincs."""
    p = sidecar_path(folder, basename)
    if not p.exists():
        return default_meta()
    try:
        with p.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return default_meta()
        # Merge-eljük az alapokkal, hogy hiányzó mezők ne szakítsanak meg semmit
        merged = default_meta()
        merged.update({k: v for k, v in data.items() if k in merged})
        # A státusz értékét validáljuk; ismeretlen → alap
        if merged["status"] not in VALID_STATUSES:
            merged["status"] = DEFAULT_STATUS
        return merged
    except (json.JSONDecodeError, OSError):
        return default_meta()


def _write_atomic(folder: Path, basename: str, data: Dict[str, Any]) -> Path:
    p = sidecar_path(folder, basename)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp.replace(p)
    return p


def _now_iso() -> str:
    """UTC ISO 8601 formátum, `Z` suffix-szel — a JS/böngésző jól érti."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def set_status(folder: Path, basename: str, status: str, username: Optional[str],
               notes: Optional[str] = None) -> Dict[str, Any]:
    """Új státusz állítása. Frissíti a `status_*` mezőket, `edited_*`-et NEM."""
    _validate_status(status)
    current = read(folder, basename)
    current["status"]            = status
    current["status_changed_by"] = username
    current["status_changed_at"] = _now_iso()
    if notes is not None:
        current["notes"] = notes
    _write_atomic(folder, basename, current)
    return current


def record_edit(folder: Path, basename: str, username: Optional[str]) -> Dict[str, Any]:
    """A tartalom-mentés utáni update: csak az `edited_*` mezőket írja.

    Ha a fájlnak még nincs sidecar-ja, létrehozzuk az alap státusszal.
    """
    current = read(folder, basename)
    current["edited_by"] = username
    current["edited_at"] = _now_iso()
    _write_atomic(folder, basename, current)
    return current
