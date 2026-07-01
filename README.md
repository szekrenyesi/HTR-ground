# HTR-ground

Web-based correction tool for HTR (Handwritten Text Recognition) output — for
producing *ground truth* transcriptions of historical manuscripts.

The user sees the page image on the left, the recognised text lines on the
right, and edits the text in visual context. Save exports ALTO XML, PAGE XML,
or the internal JSON.

The name comes from *ground truth* — the verified reference data used in
machine learning, which is precisely what this tool helps produce.

---

## Two usage modes

- **Demo / playground** (`/demo`, public) — upload your own image + annotation
  pair from disk, correct, download the result in JSON / ALTO XML / PAGE XML.
  Works even from `file://` (client-side JSON only).
- **Projects** (`/projects`, login required) — browse a server-side `projects/`
  folder tree, open image+transcript pairs directly, save-in-place with export
  to other formats. Ideal when many people work on a shared corpus.

---

## Project layout

```
HTR-ground/
├── frontend/
│   ├── landing.html             # home: two cards (Demo / Projects), Bootstrap
│   ├── login.html               # shared-password login page, Bootstrap
│   ├── editor.html              # DOM skeleton (toolbar + two panels)
│   ├── editor.css               # all editor styles (dark theme)
│   ├── editor.js                # editor logic: load, zoom, filters, save
│   ├── projects.html            # Projects file browser skeleton, Bootstrap
│   ├── projects.css             # Projects dark-theme styles on top of Bootstrap
│   └── projects.js              # folder navigation, breadcrumb, listing
│
├── backend/
│   ├── conf/
│   │   └── auth_default.json    # shared password + session secret template
│   │                            #   (conf/auth.json is gitignored)
│   └── app/
│       ├── main.py              # FastAPI app: routes, session middleware
│       ├── auth.py              # verify_password, session guards
│       ├── projects.py          # safe path resolve, pair detection, load/save
│       ├── schema.py            # Page / Region / Line Pydantic models
│       └── converters/
│           ├── __init__.py      # detect_format + convert + export dispatch
│           ├── alto.py          # ALTO XML → Page  (import)
│           ├── page.py          # PAGE XML → Page  (import)
│           ├── htr_json.py      # native JSON      (import)
│           ├── to_alto.py       # Page → ALTO XML  (export)
│           └── to_page.py       # Page → PAGE XML  (export)
│
├── examples/                    # sample files (image, JSON, ALTO)
├── projects/                    # (user content) shared corpus tree
├── CLAUDE.md                    # context for AI assistants
└── README.md
```

---

## Setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Auth: generate a strong password + session secret and drop them into
# conf/auth.json (gitignored). Without this file, the app falls back to
# auth_default.json which contains a placeholder value — fine for a local
# first run, but replace it before exposing the service.
python3 -c "
import json, secrets
with open('conf/auth.json', 'w') as f:
    json.dump({
        'password':                secrets.token_urlsafe(24),
        'session_secret':          secrets.token_urlsafe(48),
        'session_cookie_name':     'htrground_session',
        'session_max_age_seconds': 604800,
    }, f, indent=4)
print('Password:', json.load(open('conf/auth.json'))['password'])
"

uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000>. The landing page has two cards:

- **Demo** — no login. Upload an image + annotation, edit, download.
- **Projects** — redirects to login on first visit. Then browse `projects/`.

Tests: `pytest -q` from the `backend/` folder.

---

## Data flow

### Internal `Page` model

Both frontend and backend speak the same JSON structure (Pydantic models in
[`backend/app/schema.py`](backend/app/schema.py)):

```json
{
  "regions": [
    {
      "coords": [[x, y], ...],
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
  "image_width": 5496,
  "image_height": 3670,
  "source_format": "alto-xml"
}
```

Coordinates are always in the source image's native pixel space.

### Import (`converters/`)

`POST /api/convert` autodetects the input format (`.json`, ALTO XML, PAGE XML)
and returns a `Page`. Format detection is done from the first few KB of the
byte stream, not the filename.

- ALTO XML — if `<Shape><Polygon POINTS="…"/></Shape>` is present it is used;
  otherwise the polygon is synthesised from `HPOS/VPOS/WIDTH/HEIGHT`.
- PAGE XML — polygons come from `<Coords points="…"/>` directly.
- Native JSON — passthrough, validated against the `Page` schema.

### Export (`converters/to_alto.py`, `to_page.py`)

Reverse direction, called by `POST /api/export` (demo mode) and `PUT
/api/project-file` (project mode). Both formats emit real polygons, not just
bounding boxes.

### Round-trip guarantee

`convert(export(page, format), format=…)` returns the same regions/lines/
polygons/text. Verified for `alto-xml` and `page-xml` against the Bakonykuti
sample (68 lines, exact polygon match).

---

## Projects

The **Projects** mode lets multiple users work against a shared corpus on the
server without uploading files through the browser. The tree can be
arbitrarily deep — folders that contain image + annotation pairs are the
leaves.

### Adding a project

Drop files into `projects/<project>/<subproject>/…`:

```
projects/
├── Minta/                       # committed as a demo (see .gitignore)
│   ├── 1949/
│   │   ├── Minta_V1_049.jpg
│   │   └── Minta_V1_049.json
│   └── 1950/
│       ├── Minta_V1_050.jpg
│       └── Minta_V1_050.alto.xml
└── …                            # your own projects, gitignored by default
```

By default `.gitignore` excludes everything under `projects/` except for the
`Minta/` sample folder, which is committed as a working demo. Your own
projects stay local unless you explicitly add them.

Pair detection groups files by basename, respecting compound extensions
(`.alto.xml` and `.page.xml`). Image extensions: `.jpg`, `.jpeg`, `.png`,
`.tif`, `.tiff`, `.gif`. Annotations: `.json`, `.xml`, `.alto.xml`, `.page.xml`.

If both an image and an annotation with the same basename exist, they show up
as a single pair in the browser. Missing halves show up with a `nincs kép`
("no image") or `nincs átirat` ("no transcript") tag.

### `.htrground.json` — save format per folder

Optional. Only looked at in leaf folders. Controls what format the **Save**
button writes when a file is edited in that folder:

```json
{
  "save_format": "alto-xml"
}
```

Valid values: `json`, `alto-xml`, `page-xml`. If the file is missing or
invalid, the original loaded format is used. The **Export** dropdown still
lets you download in any of the three formats regardless of this setting.

### Path safety

All path handling goes through
[`projects.resolve_safe`](backend/app/projects.py) which resolves the
user-provided path relative to `projects/` and refuses any escape (`../`,
absolute paths, symlink chains that leave the tree). Attempted escapes raise
`PathEscapeError` → HTTP 400.

---

## Authentication

Shared-password model — anyone with the password gets full access; no per-user
identity or per-project ACLs. Suits a small trusted team; for larger setups a
real identity layer is a future item.

- Password lives in `backend/conf/auth.json` (gitignored). Template is
  `backend/conf/auth_default.json`, which ships in the repo with a placeholder.
- Session is a signed cookie via `starlette.middleware.sessions.SessionMiddleware`,
  keyed with the `session_secret` from `auth.json`.
- Public routes: `/`, `/demo`, `/login`, `/editor.*`, `/api/convert`,
  `/api/export`, `/api/health`, `/api/session`.
- Auth-gated: `/projects*`, `/api/projects*`, `/api/project-*`.

Logout: `POST /logout` clears the session.

---

## API reference

Base URL: `http://<host>:<port>` (default 8000). All auth-gated endpoints
return HTTP 401 as JSON if the session cookie is missing.

### Public

| Method | Path                                         | Purpose                                    |
|--------|----------------------------------------------|--------------------------------------------|
| GET    | `/`                                          | Landing page                               |
| GET    | `/demo`                                      | Demo editor (upload-based)                 |
| GET    | `/login`                                     | Login form                                 |
| POST   | `/login`                                     | Password check, sets session cookie        |
| POST   | `/logout`                                    | Clears session                             |
| GET    | `/api/session`                               | `{authenticated: bool}`                    |
| GET    | `/api/health`                                | `{status: "ok"}`                           |
| POST   | `/api/convert`                               | HTR file → internal `Page` JSON            |
| POST   | `/api/export`                                | `Page` JSON → JSON / ALTO / PAGE download  |

### Auth-gated

| Method | Path                                         | Purpose                                    |
|--------|----------------------------------------------|--------------------------------------------|
| GET    | `/projects`                                  | Projects browser (HTML)                    |
| GET    | `/projects/{path}`                           | Same browser, deep-linked to a folder      |
| GET    | `/projects/edit?path=…&basename=…`           | Editor in project mode (HTML)              |
| GET    | `/api/projects`                              | Root folder listing (JSON)                 |
| GET    | `/api/projects/{path}`                       | Folder listing (JSON)                      |
| GET    | `/api/project-file?path=…&basename=…`        | Load one pair → `{page, image_url, save_format, …}` |
| PUT    | `/api/project-file?path=…&basename=…`        | Save one pair in-place (overwrite)         |
| GET    | `/api/project-image?path=…&basename=…`       | Serve the pair's image file                |

### Example: convert + export

```bash
# Upload an ALTO XML, get internal JSON back
curl -F "file=@examples/Bakonykuti_V1_049.alto.xml" \
     http://localhost:8000/api/convert

# Export a Page as PAGE XML
curl -X POST http://localhost:8000/api/export \
     -H "Content-Type: application/json" \
     -d '{"page": {...}, "format": "page-xml", "basename": "Bakonykuti_V1_049"}' \
     -o out.page.xml
```

---

## Frontend architecture

Three-file split, no build step:

- **`editor.html`** — DOM skeleton with a `<base href="/">` injected via
  inline script when served over HTTP. This makes relative `editor.css` /
  `editor.js` resolve to the server root regardless of the current URL
  (needed because `/projects/edit?…` would otherwise resolve them to
  `/projects/editor.css`, which falls into the folder-browser catch-all and
  returns HTML). In `file://` mode the base tag is skipped and relative
  paths resolve normally.
- **`editor.css`** — dark theme, all layout and component styles.
- **`editor.js`** — one top-level module: state, DOM refs, image filters,
  file loading, zoom logic, text-panel rendering, SVG overlay, detail view
  (canvas crop with contrast-aware highlighting), save + export.

`editor.js` detects the mode at startup by looking at
`window.location.pathname` — anything under `/projects/edit` puts it in
project mode. Project mode:

- Hides upload buttons, shows a project-info label (`path / basename / fmt`).
- Auto-loads the pair via `GET /api/project-file`.
- Save button = in-place `PUT /api/project-file`.
- Separate **Export ▾** button opens the format dropdown for downloads.
- Back button in the toolbar returns to the parent folder in the browser.

The Bootstrap-based pages (landing, login, projects) share a minimal dark
theme layered on Bootstrap 5.3 from CDN.

---

## Development notes

- **Two configs**, both with `_default.json` templates:
  - `backend/conf/auth.json` — password + session secret
- **Adding a new format** (e.g. hOCR): add a `parse()` in
  `converters/x.py`, extend `detect_format()` and the dispatch table in
  `converters/__init__.py`. For export, add `to_x.py` and register it in
  `EXPORT_MIME` / `EXPORT_EXT`.
- **Route ordering**: static asset routes (`/editor.css`, `/projects.css`,
  etc.) are declared *before* the `/projects/{deep_path:path}` catch-all so
  they win the match.
- **ALTO polygons**: the exporter always writes `<Shape><Polygon POINTS>` —
  no bare bounding-box output. This means round-tripping through HTR-ground
  never loses polygon information, even if the input source (e.g. some
  legacy ALTO producers) only had rectangles.
- **Atomic writes**: `save_pair()` writes to `<name>.tmp` first, then
  `Path.replace()` renames — safe against partial writes if the process is
  killed mid-save.
