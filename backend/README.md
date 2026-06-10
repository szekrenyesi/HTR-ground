# HTR-ground — backend

FastAPI alapú demo / playground backend.

## Mit csinál (M1 állapot)

- Kiszolgálja a frontend `editor.html`-t a `/` útvonalon.
- A `POST /api/convert` endpointon fogad HTR fájlokat (ALTO XML, PAGE XML,
  vagy a belső JSON), autodetektálja a formátumot, és visszaadja a belső
  JSON formátumot, amit az `editor.html` natívan ért.
- Példa fájlokat szolgál `/examples/...` alatt (kép, JSON, ALTO).

## Lokális futtatás

A `backend/` mappából:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# fejlesztő szerver, auto-reload
uvicorn app.main:app --reload --port 8000
```

Nyisd meg: <http://localhost:8000> — az editor jön be.
Swagger UI: <http://localhost:8000/docs>.

## Tesztek

```bash
cd backend
pytest -q
```

## Mappastruktúra

```
backend/
├── app/
│   ├── main.py              # FastAPI app, route-ok
│   ├── schema.py            # Page / Region / Line Pydantic modell
│   └── converters/
│       ├── __init__.py      # detect_format + convert dispatch
│       ├── alto.py          # ALTO XML → Page
│       ├── page.py          # PAGE XML → Page
│       └── htr_json.py      # natív JSON passthrough
├── tests/
│   ├── test_alto.py
│   ├── test_htr_json.py
│   └── test_api.py
└── requirements.txt
```

## API

### `POST /api/convert`

Bemenet (multipart):
- `file` (kötelező): a HTR fájl
- `format` (opcionális): `"alto-xml"` | `"page-xml"` | `"json"` — ha üres, autodetekció

Válasz:
```json
{
  "format_detected": "alto-xml",
  "page": {
    "regions": [...],
    "image_width": 5496,
    "image_height": 3670,
    "source_format": "alto-xml"
  }
}
```

### `GET /api/health`

```json
{"status": "ok"}
```

## Konverziós megjegyzések

- **ALTO XML** csak téglalapokat ad (HPOS/VPOS/WIDTH/HEIGHT). Az `editor.html`
  poligonokkal dolgozik, ezért a téglalapokból 4 sarokpontos poligont
  szintetizálunk. Ha az ALTO tartalmaz `<Shape><Polygon POINTS="..."/></Shape>`-et
  (v4+), azt használjuk a téglalap helyett.
- **PAGE XML** mindig ad poligont, így ott natívan átkerülnek a koordináták.
  A PAGE XML konverterhez egyelőre nincs valódi minta a `examples/`-ben;
  az első élesben érkezővel érdemes ellenőrizni.
- **A szöveg** az ALTO `String CONTENT="..."` attribútumából, a PAGE XML
  `<TextEquiv><Unicode>` elemből jön.
