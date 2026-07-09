"""
Presence (jelenlét) tracker — memóriában.

Cél: „Anna épp X-et szerkeszti" jelzés a projekt-listában és az editor-ban,
lock nélkül. A frontend időnként heartbeat-tel jelzi a jelenlétét; a szerver
lejárt bejegyzéseket automatikusan takarítja.

- Kulcs: `path/basename` (a projekt-fájl teljes rel path-je).
- Érték: `(username, last_seen_epoch)`.
- Egy user egyszerre több fájlon is lehet (pl. két böngésző tab), de mindig
  ez a modul a hivatkozott igazság — mostani session ID-t nem tárolunk.
- Nem perzisztens: process újraindul → tábla ürül.

Több worker esetén ez a modul NEM osztott állapotot vezet. Kezdetben egy
uvicorn workerrel megyünk; ha később kell több worker, Redis vagy hasonló
megosztott store-ra kell váltani.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional, Tuple


# Lejárati idő: 60 mp után „gone"-nak tekintünk egy heartbeat-et
EXPIRE_SECONDS = 60


class PresenceTracker:
    def __init__(self, *, expire_seconds: int = EXPIRE_SECONDS,
                 clock=time.time):
        self._expire = expire_seconds
        self._clock  = clock
        self._lock   = threading.Lock()
        # key -> {username -> last_seen_epoch}
        # (Egy path-en több user is lehet egyszerre)
        self._table: Dict[str, Dict[str, float]] = {}

    def _key(self, path: str, basename: str) -> str:
        p = (path or "").strip("/")
        return f"{p}/{basename}" if p else basename

    def _expire_stale_locked(self, entries: Dict[str, float]) -> Dict[str, float]:
        now = self._clock()
        return {u: ts for u, ts in entries.items() if now - ts <= self._expire}

    def heartbeat(self, path: str, basename: str, username: str) -> None:
        """Jelezzük, hogy `username` most is dolgozik ezen a fájlon."""
        if not username:
            return
        key = self._key(path, basename)
        with self._lock:
            entries = self._table.setdefault(key, {})
            entries[username] = self._clock()
            # Gyors, opportunista takarítás
            self._table[key] = self._expire_stale_locked(entries)
            if not self._table[key]:
                del self._table[key]

    def leave(self, path: str, basename: str, username: str) -> None:
        """Explicit kilépés (pl. `beforeunload`)."""
        key = self._key(path, basename)
        with self._lock:
            entries = self._table.get(key)
            if not entries:
                return
            entries.pop(username, None)
            if not entries:
                del self._table[key]

    def active_users(self, path: str, basename: str) -> List[Tuple[str, float]]:
        """Egy fájlra: (username, last_seen_epoch) párok, lejárt eltávolítva."""
        key = self._key(path, basename)
        with self._lock:
            entries = self._table.get(key)
            if not entries:
                return []
            fresh = self._expire_stale_locked(entries)
            if fresh:
                self._table[key] = fresh
            else:
                self._table.pop(key, None)
            return [(u, ts) for u, ts in fresh.items()]

    def snapshot(self) -> Dict[str, List[Tuple[str, float]]]:
        """Az összes friss bejegyzés — pl. a listázó endpoint egyszerre kéri."""
        with self._lock:
            result: Dict[str, List[Tuple[str, float]]] = {}
            expired_keys: List[str] = []
            for key, entries in self._table.items():
                fresh = self._expire_stale_locked(entries)
                if fresh:
                    self._table[key] = fresh
                    result[key] = [(u, ts) for u, ts in fresh.items()]
                else:
                    expired_keys.append(key)
            for k in expired_keys:
                self._table.pop(k, None)
            return result

    def clear(self) -> None:
        """Tesztekhez."""
        with self._lock:
            self._table.clear()


# Modul-szintű, singleton példány. Tesztek `clear()`-elik és cserélik a clock-ot
# (ha kellene) — de mi mostani UI-nak elég egy publikus tracker.
tracker = PresenceTracker()


# ─── Kényelmi helper-ek ─────────────────────────────────────────────────
def format_for_pair(path: str, basename: str, *, exclude: Optional[str] = None
                    ) -> Optional[dict]:
    """A listázó/editor számára: melyik user van jelen (az `exclude`-t kihagyva)."""
    users = tracker.active_users(path, basename)
    if exclude:
        users = [(u, ts) for u, ts in users if u != exclude]
    if not users:
        return None
    # Ha több user van, mind visszaadjuk; a UI választhat, hogyan jeleníti meg.
    users.sort(key=lambda t: t[1], reverse=True)  # legfrissebb elöl
    return {
        "users": [{"username": u, "last_seen_epoch": ts} for u, ts in users],
    }
