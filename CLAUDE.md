# HTR-ground

> Webes javító eszköz HTR (Handwritten Text Recognition) kimenetekhez — *ground truth* előállítására.
> A felhasználó az automatikus felismerés szövegét tudja javítani vizuális kontextusban: bal oldalt az oldalkép, jobb oldalt a szövegsorok.
>
> A név a *ground truth* fogalomból jön: a gépi tanulásban így hívják az ellenőrzött, helyes referencia adatot — pontosan ez az, amit ez a tool segít előállítani.

**Repo:** `github.com/szekrenyesi/HTR-ground`

A felhasználóval **magyarul** kommunikálj.

---

## Projekt állapota

**Két üzemmód a landing oldalról:**

- **Demó** (`/demo`, publikus) — feltöltéses editor. Kép + annotáció (JSON / ALTO XML / PAGE XML) bekerül a kliensbe/backendbe, javítod, letöltöd (JSON / ALTO / PAGE / PDF).
- **Projektek** (`/projects`, login-védett) — a szerver-oldali `projects/` mappa-fát böngészed, in-place mented, exportálsz, státuszokat állítasz.

**Backend:** FastAPI, SessionMiddleware. Konverzió, export, felhasználó-kezelés, ACL, státusz sidecarok, presence tracking. Round-trip garancia ALTO/PAGE poligonokra. Kereshető, kétrétegű PDF export (`fpdf2 + Pillow + fonts/EBGaramond-Regular.ttf`).

**Frontend:** vanilla HTML/CSS/JS, sötét téma. Editor, projects browser, landing, login mind Bootstrap tetején.

**Még nincs (jövőbeni mérföldkövek):** kötegelt feltöltés, külső HTR API integráció, több oldal per pár, sor szintű szerkesztés (split/merge/rerawmap), self-service password reset.

---

## Fájlstruktúra

```
HTR-ground/
├── frontend/
│   ├── landing.html             # kezdőoldal, két kártya (Demó / Projektek), Bootstrap
│   ├── login.html               # username + jelszó login, Bootstrap
│   ├── editor.html              # DOM váz (toolbar + két panel)
│   ├── editor.css               # összes stílus (sötét téma)
│   ├── editor.js                # editor logika: betöltés, zoom, szűrők, mentés, presence
│   ├── projects.html            # projekt-böngésző DOM váz
│   ├── projects.css             # projekt-böngésző stílus (státusz badge, presence pulse)
│   └── projects.js              # mappa-nézet, breadcrumb, státusz-váltás, presence
│
├── backend/
│   ├── conf/
│   │   ├── auth.json            # userek + ACL + session config (GITIGNORED)
│   │   └── auth_default.json    # üres sablon a repóban
│   ├── app/
│   │   ├── main.py              # FastAPI app: route-ok, session middleware
│   │   ├── auth.py              # bcrypt hash, session-alapú auth, dependency-k
│   │   ├── users.py             # CLI: bootstrap / add / remove / list / set-password / promote / demote
│   │   ├── acl.py               # longest-prefix ACL match, admin bypass
│   │   ├── projects.py          # projekt-fa böngésző, path-safety, pár-detektálás
│   │   ├── meta.py              # per-fájl sidecar (.htrground-meta.json): státusz + audit
│   │   ├── presence.py          # in-memory presence tracker
│   │   ├── schema.py            # Page/Region/Line Pydantic modellek
│   │   └── converters/
│   │       ├── __init__.py      # detect_format + convert + export dispatch
│   │       ├── alto.py, page.py, htr_json.py       # import
│   │       ├── to_alto.py, to_page.py              # export XML-be
│   │       └── to_pdf.py                            # két rétegű, kereshető PDF
│   ├── tests/
│   │   ├── conftest.py          # izolált auth.json + fixtures
│   │   ├── fixtures/sample.alto.xml
│   │   └── test_*.py            # 95 teszt: alto/api/auth/users_cli/acl/projects_acl/meta/status_api/presence[/_api]/htr_json
│   ├── requirements.txt
│   └── README.md                # lokális futtatás, endpoint referencia
│
├── projects/                    # a szerver-oldali korpusz (Minta committed, többi gitignored)
├── fonts/EBGaramond-Regular.ttf # PDF exporthoz
├── CLAUDE.md
├── README.md
└── .gitignore
```

---

## A belső Page formátum

Ezt beszéli a frontend és a backend egyaránt. Pydantic modell: `app/schema.py`.

```json
{
  "regions": [
    {
      "coords": [[x, y], ...],       // régió poligonja
      "rect":   [x, y, w, h],
      "lines": [
        {
          "coords":   [[x, y], ...],
          "rect":     [x, y, w, h],
          "baseline": [[x1, y1], [x2, y2]],
          "text":     "..."
        }
      ]
    }
  ],
  "image_width":   5496,
  "image_height":  3670,
  "source_format": "alto-xml"
}
```

- A koordináták a kép natív pixelterében vannak.
- Backend-konverzió esetén `image_width`, `image_height`, `source_format` is jön; a frontend ezeket megőrzi (JSON.stringify mentésnél nem törli).

---

## Auth v2 (username + bcrypt)

Shared password **már nincs** — minden user saját `username` + `password_hash` párral szerepel az `auth.json`-ben. A session cookie a `username`-et tárolja.

### `auth.json` shape

```json
{
  "session_secret":          "hosszú random string (bootstrap generálja)",
  "session_cookie_name":     "htrground_session",
  "session_max_age_seconds": 604800,

  "users": {
    "admin": {
      "display_name":  "Adminisztrátor",
      "password_hash": "$2b$12$…",
      "is_admin":      true
    },
    "anna": {
      "display_name":  "Kovács Anna",
      "password_hash": "$2b$12$…"
    }
  },

  "projects": {
    "Titkos":            { "visible_to": ["anna"] },
    "Bakonykuti/part2":  { "visible_to": ["anna"] }
  }
}
```

### Fontos elvek

- **Jelszó SOHA nincs plaintext.** A hash-t a `python -m app.users` CLI helyezi el; kézzel sem szabad írni.
- **Régi shape (van `password`, nincs `users`) → startup guard**: `auth.py.load_auth_config()` explicit `AuthConfigError`-t dob a legacy shape-re, a `bootstrap` parancsra irányítva.
- **Admin bypass**: `is_admin: true` user mindent lát (ACL-t sem szűri).

### CLI

Belépési pont: `python -m app.users` (az `app/users.py` `__main__`-ként fut).

```bash
python -m app.users bootstrap [--username admin] [--display "..."] [--generate] [--force]
python -m app.users add <username> [display] [--admin] [--generate]
python -m app.users remove <username>
python -m app.users list
python -m app.users set-password <username> [--generate]
python -m app.users promote <username>
python -m app.users demote <username>
```

`--generate` egy erős, 4×4 alfanumerikus blokkos jelszót ad (`k7Qm-vXn9-pR2t-Lb8H`), egyszer kiírja a terminálra, és a hash-t rakja a fájlba.

---

## ACL — projekt-láthatóság

`app/acl.py`. Szabályok:

1. **Ha egy path nincs az `auth.json.projects` szótárban** (semmilyen ős-formában), **mindenki látja**.
2. **Longest-prefix match**: ha `Bakonykuti` és `Bakonykuti/part2` is szerepel, `Bakonykuti/part2/inner` a `Bakonykuti/part2` ACL-jét örökli.
3. **`visible_to: ["*"]`** = minden bejelentkezett user (nem-authozott kliens nem lép be — az `require_auth` szűri).
4. **Admin bypass**: `is_admin: true` user az ACL-t figyelmen kívül hagyja.
5. **Rossz alakú entry** (nincs `visible_to` lista) → **fail-closed**: senki nem látja.

A gyökér-listázás (`GET /api/projects`) csak azokat a legfelső mappákat adja vissza, amiket a user lát. A mély path direkt megnyitása → 403, ha nincs jog.

---

## Státusz sidecarok (per-fájl audit)

`app/meta.py`. Egy `<basename>.htrground-meta.json` sidecar él a pár mellett.

```json
{
  "status":            "folyamatban",           // enum, lásd lent
  "status_changed_by": "anna",
  "status_changed_at": "2026-07-09T14:23:00Z",
  "edited_by":         "anna",
  "edited_at":         "2026-07-09T14:30:00Z",
  "notes":             ""
}
```

- **Státuszok**: `["új", "folyamatban", "ellenőrzésre vár", "kész"]` (kód-drótozott, `meta.VALID_STATUSES`).
- **Alapstátusz**: `"új"` — ha nincs sidecar, ez jön a listázásban is (nincs sidecar-írás, csak default érték).
- **Két audit trail**: `status_changed_*` és `edited_*` külön követi a státusz-váltást és a tartalom-mentést. A státuszt bárki válthatja anélkül, hogy szerkesztené a fájlt (pl. lektor).
- **Atomikus írás**: `.tmp` fájlba írás, majd `replace()` — safe partial write ellen.
- **A listázó a sidecart NEM annotációként kezeli** (`_classify` szűri, sőt a fájlnév-detekció is skippeli). Sidecar nélküli mappa is teljesen működőképes.

Endpointok:
- `GET  /api/status-values` — a UI dropdown-t tápláló érvényes lista + default
- `PUT  /api/project-status?path=…&basename=…` — státusz-váltás (body: `{status, notes?}`)

A `PUT /api/project-file` (tartalom-mentés) a mentés után automatikusan hívja `meta.record_edit`-et — `edited_by`/`edited_at` frissül.

---

## Presence (jelenlét)

`app/presence.py`, in-memory tracker. Nem perzisztens: process újraindul → tábla ürül. Ez szándékos.

- **Kulcs**: `<path>/<basename>` (a projekt-fájl teljes rel path-je).
- **Érték**: `{username -> last_seen_epoch}` — egy path-en több user is lehet.
- **Expire**: 60 mp. Ha nincs frissebb heartbeat, a user lekerül.

**Frontend viselkedés:**

- Az editor projekt módban 25 mp-enként küld `POST /api/presence/heartbeat`-et.
- Betöltéskor `GET /api/presence` — ha más user aktív, konfirm dialog: „Anna itt van — biztos folytatod?". Utolsó mentés győz, nincs hard lock.
- `beforeunload` esemény: `POST /api/presence/leave` `navigator.sendBeacon`-nel (megbízhatóan kimegy page-close alatt is).
- A projects lista 20 mp-enként újratöltődik (csak ha a tab látható), így a presence indikátorok „élőek".
- A listázás válaszában minden pár mellé kerül `presence` mező, ha másik user van jelen (az aktuális usert kihagyva).

**Több worker**: jelenleg nem működik osztott állapotként. Ha valaha `gunicorn --workers 4` kell, Redis vagy hasonló shared store kell.

---

## API referencia (compact)

Base URL: `http://<host>:<port>` (default 8000). Az auth-védett endpointok 401-et adnak JSON-ben, ha nincs session cookie; 403-at, ha az ACL nem enged.

### Publikus

| Method | Path                            | Célja                                                |
|--------|---------------------------------|------------------------------------------------------|
| GET    | `/`                             | Landing page                                         |
| GET    | `/demo`                         | Demo editor (upload-based)                           |
| GET    | `/login`, POST `/login`          | Login form + submit (username + password)            |
| POST   | `/logout`                       | Session clear                                        |
| GET    | `/api/session`                  | `{authenticated, username?, display_name?, is_admin?}` |
| GET    | `/api/health`                   | `{status: "ok"}`                                     |
| POST   | `/api/convert`                  | HTR fájl → belső `Page` JSON                          |
| POST   | `/api/export`                   | `Page` → JSON / ALTO / PAGE letöltés                  |
| POST   | `/api/export-pdf`               | `Page` + kép → kereshető, kétrétegű PDF               |
| GET    | `/api/status-values`            | UI dropdown lista + default                          |

### Auth-védett (`require_auth`)

| Method | Path                                             | Célja                                        |
|--------|--------------------------------------------------|----------------------------------------------|
| GET    | `/projects`, `/projects/{path}`                  | Böngésző HTML (deep-link OK)                  |
| GET    | `/projects/edit?path=…&basename=…`               | Editor projekt módban                         |
| GET    | `/api/projects`, `/api/projects/{path}`          | Mappa listázás JSON — meta + presence         |
| GET    | `/api/project-file?path=…&basename=…`            | Egy pár betöltése (annotation → Page, image_url, meta) |
| PUT    | `/api/project-file?path=…&basename=…`            | Mentés in-place + record_edit                 |
| GET    | `/api/project-image?path=…&basename=…`           | A pár képfájlja                               |
| PUT    | `/api/project-status?path=…&basename=…`          | Státusz-váltás sidecarba                      |
| POST   | `/api/presence/heartbeat`                        | „Itt vagyok" jelzés                           |
| POST   | `/api/presence/leave`                            | Explicit kilépés                              |
| GET    | `/api/presence?path=…&basename=…`                | Kik vannak most itt (öntőle eltekintve)       |

---

## Konvenciók, fejlesztői jegyzetek

### Frontend

- **Sötét téma**, sárga = szerkesztett/aktív, kék = interaktív (sor poligon), piros szaggatott = régió.
- **Magyar felület**.
- Vanilla JS, **nincs build** — `file://` is működik demó módban.
- `editor.html` → `editor.css` + `editor.js` (3 fájl, split).
- Backend hívások **relatív URL-ekkel** (`fetch('/api/...')`) — deployment agnostikus.
- Base tag injektálás: `/projects/edit?…` alatt is a `/editor.css` és `/editor.js` a helyes helyre resolve-oljon.
- A projekt-mode és demó-mode ugyanaz az `editor.js` — a `location.pathname`-ból dönti el.

### Backend

- Python 3.11+, FastAPI, `lxml`, `bcrypt`, `fpdf2`, `Pillow`, `uvicorn`.
- Konverziós elv: ha egy formátum nem tárol egy adatot (pl. régi ALTO polygon nélkül), a legjobb szintézist adjuk vissza (rect → 4 sarkú polygon).
- **Új formátum hozzáadása**: `converters/<x>.py` új parse-oló, `detect_format` + dispatch a `__init__.py`-ben. Export: `to_<x>.py`, regisztrálás `EXPORT_MIME` / `EXPORT_EXT`-be.
- **Route sorrend**: static asset routes (`/editor.css`, `/projects.css`, …) a `/projects/{deep_path:path}` catch-all ELŐTT deklarálva — így ők nyernek.
- **ALTO export mindig poligonos** — round-trip garancia még akkor is, ha a forrás csak rect-eket adott.
- **Atomikus fájlírás mindenhol**: `save_pair`, `meta._write_atomic`, `auth.save_auth_config` → `.tmp` + `replace()`.
- **Több config**, mind `_default.json` sablonnal: `conf/auth.json` (userek + ACL + session).

### Tesztek

- `backend/tests/conftest.py` **modul-szinten** beállít egy izolált `auth.json`-t egy tmp mappában, MIELŐTT az `app.main` importálódna. Ez azért kritikus, mert a `SessionMiddleware` a `session_secret`-et import-időben olvassa.
- `logged_in_client` = `anna`, `admin_client` = `admin` fixture.
- 95 teszt, 4-5 másodperc.
- Fixture ALTO minta: `backend/tests/fixtures/sample.alto.xml` (a Minta/Arany oldal másolata).

---

## Lokális futtatás

A `backend/` mappából:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Első futáshoz: auth.json + admin user
python -m app.users bootstrap --generate

uvicorn app.main:app --reload --port 8000
```

Aztán nyisd: <http://localhost:8000>. Swagger: `/docs`. Tesztek: `pytest -q`.

---

## Lehetséges következő lépések

- Kötegelt feltöltés (több oldal egyszerre)
- Külső HTR API integráció (pl. Kraken vagy Transkribus a nyers képből → automatikus kimenet)
- Sor splittelése / mergelése / újrarajzolása az editorban
- Több oldal per pár (kötet/könyv-nézet)
- Export sima szövegbe / TEI XML-be
- Multi-worker: Redis-alapú megosztott presence
- Self-service jelszó-változtatás („Beállítások" oldal)
- Session-token per user (a jelenlegi single-session cookie helyett)
