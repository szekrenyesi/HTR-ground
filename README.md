# HTR-ground

Webes javító eszköz HTR (Handwritten Text Recognition) kimenetekhez — *ground truth* előállítására.

A felhasználó az automatikus felismerés szövegét tudja javítani vizuális kontextusban: bal oldalt az oldalkép, jobb oldalt a szövegsorok.

## Demo / playground

A backend egy demo / playground szerepet is betölt: feltöltheted az HTR kimenetedet (**ALTO XML**, **PAGE XML**, vagy a belső **JSON** formátum), és a felület konvertálja a szerkesztő által értett struktúrára.

## Komponensek

- **`frontend/editor.html`** — vanilla HTML/CSS/JS szerkesztő. Build nélkül futtatható.
- **`backend/`** — FastAPI app: a szerkesztő kiszolgálása + formátum konverzió.
- **`examples/`** — minta fájlok (kép, JSON, ALTO).

## Lokális futtatás

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Nyisd meg: <http://localhost:8000>

Részletek: [`backend/README.md`](backend/README.md), kontextus AI-asszisztáláshoz: [`CLAUDE.md`](CLAUDE.md).

## Tesztek

```bash
cd backend
pytest -q
```
