# HTR-ground

> Webes javító eszköz HTR (Handwritten Text Recognition) kimenetekhez — *ground truth* előállítására.
> A felhasználó az automatikus felismerés szövegét tudja javítani vizuális kontextusban: bal oldalt az oldalkép, jobb oldalt a szövegsorok.
>
> A név a *ground truth* fogalomból jön: a gépi tanulásban így hívják az ellenőrzött, helyes referencia adatot — pontosan ez az, amit ez a tool segít előállítani.

**Repo:** `github.com/szekrenyesi/HTR-ground`

A felhasználóval **magyarul** kommunikálj.

---

## Projekt állapota

- **Frontend (`frontend/editor.html`):** önálló, build-mentes vanilla HTML/CSS/JS felület. Megnyitható `file://`-ből is.
- **Backend (`backend/`, M1 — demo / playground):** FastAPI app. Feladata:
  - kiszolgálja a frontendet a `/`-en
  - `POST /api/convert` — HTR fájlt (ALTO XML / PAGE XML / belső JSON) konvertál a belső JSON formátumra, amit az `editor.html` natívan ért
  - példa fájlokat szolgál `/examples/...` alatt
- **Még nincs:** felhasználói regisztráció, batch feltöltés, perzisztens tárolás, meglévő HTR API integráció (a nyers képből automatikus kimenet). Ezek külön mérföldkövek lesznek.

A demó / playground a végleges verzióban is benne marad — egy belépési pont arra, hogy XML kimenetekkel játszani lehessen backend nélkül is (kliens-oldali JSON betöltés) vagy backenddel (XML konverzió + példák).

---

## Fájlstruktúra

```
HTR-ground/
├── frontend/
│   ├── landing.html             # kezdőoldal, két kártya (Demó / Projektek), Bootstrap
│   ├── login.html               # közös jelszós belépőoldal, Bootstrap
│   ├── editor.html              # DOM váz (toolbar + két panel), CSS/JS betöltés
│   ├── editor.css               # összes stílus (sötét téma, layout, komponensek)
│   └── editor.js                # összes logika (állapot, betöltés, zoom, szűrők, mentés)
├── backend/
│   ├── conf/
│   │   └── auth_default.json    # közös jelszó + session titok templát; auth.json .gitignore
│   ├── app/
│   │   ├── main.py              # FastAPI app, route-ok, session middleware, landing/demo/login
│   │   ├── auth.py              # közös jelszó betöltés, verify_password, session helper
│   │   ├── schema.py            # Page / Region / Line Pydantic modell
│   │   └── converters/
│   │       ├── __init__.py      # detect_format + dispatch
│   │       ├── alto.py          # ALTO XML → Page
│   │       ├── page.py          # PAGE XML → Page
│   │       └── htr_json.py      # natív JSON passthrough
│   ├── tests/                   # pytest (17 teszt, 17 zöld)
│   ├── requirements.txt
│   └── README.md
├── examples/
│   ├── Bakonykuti_V1_049.jpg
│   ├── Bakonykuti_V1_049.json   # belső JSON példa
│   └── Bakonykuti_V1_049.alto.xml  # az ugyanezen oldal ALTO kimenete
├── CLAUDE.md
└── .gitignore
```

---

## JSON formátum (a HTR kimenet)

A bemenő JSON szerkezete:

```json
{
  "regions": [
    {
      "coords": [[x, y], ...],     // a régió poligonja (sokszög)
      "rect":   [x, y, w, h],       // a régió befoglaló téglalapja
      "lines": [
        {
          "coords":   [[x, y], ...], // a sor poligonja
          "rect":     [x, y, w, h],  // a sor befoglaló téglalapja
          "baseline": [[x1, y1], [x2, y2]],
          "text":     "..."          // a felismert (javítható) szöveg
        }
      ]
    }
  ]
}
```

- A koordináták az eredeti kép pixelterében vannak (a Bakonykuti példa: 5496×3670 px szkennelt oldal).
- A `text` a szerkesztendő mező. Minden más metaadat változatlan marad mentéskor.
- A mentett `corrected.json` ugyanezt a struktúrát adja vissza, csak a `text` mezők frissültek.
- Backend-konverzió esetén a `Page` opcionális meta-mezőket is adhat (`image_width`, `image_height`, `source_format`); a frontend ezeket egyelőre ignorálja, de a `JSON.stringify` mentésnél bennmaradnak.

---

## Az editor felépítése (`editor.html`)

### Felület

- **Toolbar (felül):** HTR fájl betöltés (`.json` / `.xml` / `.alto` / `.page`), kép betöltés, zoom kontroll, kontraszt léptetés, kiemelés ki/be, mentés gomb, státusz.
- **Bal panel (~56% szélesség):** kép panel.
- **Jobb panel:** szövegsorok régiónként csoportosítva, soronként egy input mező.

### HTR fájl betöltése

A „HTR betöltése" gomb a kiterjesztés alapján dönt:
- `.json` → kliens-oldali parse (`FileReader`), nem kell backend
- `.xml` / `.alto` / `.page` → `POST /api/convert` a backendre

Ha a backend nem elérhető (pl. `file://` mód), XML feltöltéskor a felhasználó értesítést kap, hogyan indítsa el a `uvicorn`-t.

### Két nézet a bal oldalon

1. **Oldal nézet (`page`)** — alapértelmezett. A teljes oldalkép zoomolhatóan, SVG overlay-jel:
   - piros szaggatott: régió poligonok
   - kék: sor poligonok (hover/select állapotban kiemelve sárgával)
2. **Részlet nézet (`detail`)** — canvasre rajzolva. Csak a kiválasztott sor körüli kivágás látszik:
   - a környező kontextus sötétített/szűrt
   - az aktuális sor poligonján belül az eredeti fényerő + kontraszt
   - külön zoom (`detailZoom`), külön scroll logika

A két nézet közt a jobb felső `Részlet nézet` / `Oldal nézet` gomb vált.

### Kép szűrők

- **Kontraszt léptető** (`Kont.` gomb): `1.0×` → `1.5×` → `2.0×` → `3.0×` → vissza. A `buildLineFilter()` CSS filter-t generál (`brightness * contrast`), amit aktuális sorra alkalmaz.
- **Kiemelés gomb** (`outline-btn` / `dimContext`): részlet nézetben dönti el, hogy a kontextus sötétebb-e mint a sor (fókusz) vagy uniform.

### Interakció

- Sor kiválasztása: kattintás a szövegsorra **vagy** az overlay poligonra → mindkettő szinkronban kiemelődik, és a kép odascrollol.
- Szerkesztés: input mezőbe írás. Ha eltér az eredetitől, a sor `edited` állapotba kerül (sárga pont + sárga aláhúzás).
- Navigáció a szövegben:
  - `Enter` / `ArrowDown` → következő sor
  - `ArrowUp` → előző sor
  - `Escape` → blur
- Zoom:
  - `+` / `−` gombok
  - `Ctrl+scroll` a képpanelben
  - `Illesztés` kattintás → fit-to-panel visszaállítás

### Állapot változók (a `<script>` blokk tetején)

- `data` — aktuális (szerkesztett) JSON
- `origData` — eredeti, az `edited` halmaz számításához
- `edited` — `Set<"ri-li">` a módosított sorokról
- `selected` — `{ri, li}` vagy `null`
- `viewMode` — `'page' | 'detail'`
- `zoomFit`, `zoomStep`, `detailZoom`, `imgContrast`, `dimContext` — UI állapot

---

## Konvenciók

### Frontend (`frontend/editor.html`)

- **Sötét téma**, sárga az „aktív/szerkesztett" jelzés, kék az „interaktív elem" (sor poligon), piros szaggatott a régió.
- A felület **magyar nyelvű**.
- Vanilla JS, **nincs build lépés** — közvetlenül megnyitható böngészőben (`file://` is működik kliens-oldali JSON-hoz).
- **Három fájl:** `editor.html` (DOM), `editor.css` (stílus), `editor.js` (logika). Relatív hivatkozás a HTML-ből (`href="editor.css"`, `src="editor.js"`), így `file://` módban a fájlrendszerről tölt, backenddel pedig a `/editor.css` és `/editor.js` route-ok (`app/main.py`) szolgálják ki.
- A koordináták és poligonok **a kép natív pixelterében** vannak; minden képernyő-skálázás a `currentEffectiveZoom()` / `scale` faktorokkal történik.
- A backend hívás **relatív URL**-ekkel megy (`fetch('/api/convert')`), így mindegy melyik domainen fut.

### Backend (`backend/`)

- **Python 3.11+, FastAPI, lxml, uvicorn.**
- `app/converters/` — egy fájl egy formátum (`alto.py`, `page.py`, `htr_json.py`). A közös belépési pont a `convert()` az `__init__.py`-ben.
- **Konverziós tervezési elv:** ha egy formátum nem tárol egy információt (pl. ALTO + poligon), akkor a legjobb szintézist adjuk vissza, ne dobjunk el adatot. ALTO → poligonok szintetizálódnak a téglalapokból.
- Tesztek: `backend/tests/`. Az ALTO konvertert sorról-sorra ellenőrizzük a referencia JSON-hoz (`examples/Bakonykuti_V1_049.json`).
- **PAGE XML-hez jelenleg nincs valódi minta a `examples/`-ben** — a spec alapján íródott. Első élesben érkezett mintával érdemes validálni.

---

## Lokális futtatás

A `backend/` mappából:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Aztán nyisd: <http://localhost:8000>. Swagger: `/docs`. Tesztek: `pytest -q`.

---

## Lehetséges következő lépések

### Közeli (post-M1)
- A frontend tudjon kérni egy URL-en lévő képet — pl. ha a backend tölti fel és visszaad egy `image_url`-t a konverziós válaszban
- Kép feltöltés endpoint + session-szintű ideiglenes tárolás
- PAGE XML konverter validálása valódi mintával (Transkribus / eScriptorium export)
- Példa fájlok kiválasztása a `/examples/`-ből UI-ról (gyors demo)
- Tényleges deployment (Render / Hetzner / Docker)

### Közép-/hosszú táv
- Felhasználói regisztráció + autentikáció
- Perzisztens tárolás (SQLite induláshoz, később Postgres)
- Kötegelt feltöltés (mappa / sok oldal egyszerre)
- Külső HTR API integráció (a nyers képből automatikus kimenet)
- Több oldal kezelése (kötet / katalógus nézet)
- Sor splittelése / mergelése / újrarajzolása
- Export PAGE XML / ALTO / sima szöveg formátumba

Ha valamelyiket elkezdjük, ide írjuk a döntéseket.
