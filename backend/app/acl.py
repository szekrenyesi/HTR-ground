"""
Projekt-láthatóság (ACL).

Szabályok:
- Ha egy path nincs az `auth.json.projects` szótárban (semmilyen ős-formában),
  **mindenki** látja.
- Ha van bejegyzés, a `visible_to` lista dönt: `"*"` = bárki bejelentkezett,
  egyébként a felsorolt usernevek.
- Több egyezés esetén a **leghosszabb prefix nyer** (legspecifikusabb bejegyzés).
- Az `is_admin: true` user minden path-ot lát (ACL bypass).

A path szintaxis: slash-elválasztott, leading/trailing slash nélkül, pl.
`"Bakonykuti"`, `"Bakonykuti/part2"`.
"""
from __future__ import annotations

from typing import Iterable, List, Optional


def _normalize(path: str) -> str:
    return (path or "").strip("/")


def _split(path: str) -> List[str]:
    p = _normalize(path)
    return p.split("/") if p else []


def _find_matching_entry(path: str, projects_cfg: dict) -> Optional[dict]:
    """A leghosszabb ős-prefix bejegyzést adja vissza, vagy None-t.

    Pl. `projects_cfg = {"A": {...}, "A/b": {...}}`:
      - `"A/b/c"` → `"A/b"` bejegyzés
      - `"A/x"`   → `"A"` bejegyzés
      - `"Z"`     → None
    """
    parts = _split(path)
    # Legspecifikusabb prefix-től a gyökér felé
    for i in range(len(parts), -1, -1):
        candidate = "/".join(parts[:i])
        if candidate in projects_cfg:
            entry = projects_cfg[candidate]
            if isinstance(entry, dict):
                return entry
    return None


def is_visible(path: str, username: Optional[str], *, is_admin: bool = False,
               projects_cfg: Optional[dict] = None) -> bool:
    """Visszaadja, hogy `username` látja-e a `path`-ot.

    Semmi bejegyzés + bárki (akár nem-belépett user) → nem: legalább be kell lépni,
    de az ACL nem gátol. Itt feltételezzük, hogy a hívó már ellenőrizte a
    belépést (require_auth). Ha `username` None, akkor csak akkor True,
    ha a path publikus.
    """
    if is_admin:
        return True
    cfg = projects_cfg or {}
    entry = _find_matching_entry(path, cfg)
    if entry is None:
        return True  # nincs korlátozás → mindenki látja
    visible_to = entry.get("visible_to")
    if not isinstance(visible_to, list):
        # Rossz alakú config: fail-closed
        return False
    if "*" in visible_to:
        return True
    if not username:
        return False
    return username in visible_to


def filter_folder_names(names: Iterable[str], username: Optional[str], *,
                        parent_path: str = "", is_admin: bool = False,
                        projects_cfg: Optional[dict] = None) -> List[str]:
    """Egy szülő-path (pl. gyökér `""`) alatti mappaneveket szűri az ACL szerint.

    Pl. gyökér listázás:
        filter_folder_names(["Bakonykuti", "Titkos", "Nyilvanos"], "anna", …)
    """
    kept: List[str] = []
    for name in names:
        child_path = f"{parent_path}/{name}".strip("/") if parent_path else name
        if is_visible(child_path, username, is_admin=is_admin, projects_cfg=projects_cfg):
            kept.append(name)
    return kept
