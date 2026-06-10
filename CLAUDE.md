# HTR-WEBTOOL

> Webes javító eszköz HTR (Handwritten Text Recognition) kimenetekhez.
> A felhasználó az automatikus felismerés szövegét tudja javítani vizuális kontextusban: bal oldalt az oldalkép, jobb oldalt a szövegsorok.

A felhasználóval **magyarul** kommunikálj.

---

## Projekt állapota

- **Jelenleg készen:** egyetlen, önálló webes felület — `editor.html` (vanilla HTML/CSS/JS, semmi build, semmi függőség).
- **Még nincs:** backend, HTR motor integráció, batch feldolgozás, autentikáció, perzisztens tárolás.
  A felhasználó kézzel tölt be JSON-t és képet, és kézzel ment le `corrected.json`-t.

---

## Fájlstruktúra

```
HTR-WEBTOOL/
├── editor.html              # a teljes alkalmazás egy fájlban
├── Bakonykuti_V1_049.jpg    # példa oldalkép
└── Bakonykuti_V1_049.json   # példa HTR kimenet (ehhez a képhez)
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

- A koordináták az eredeti kép pixelterében vannak (a példa: ~4400×... px-es szkennelt oldal).
- A `text` a szerkesztendő mező. Minden más metaadat változatlan marad mentéskor.
- A mentett `corrected.json` ugyanezt a struktúrát adja vissza, csak a `text` mezők frissültek.

---

## Az editor felépítése (`editor.html`)

### Felület

- **Toolbar (felül):** JSON betöltés, kép betöltés, zoom kontroll, kontraszt léptetés, kiemelés ki/be, mentés gomb, státusz.
- **Bal panel (~56% szélesség):** kép panel.
- **Jobb panel:** szövegsorok régiónként csoportosítva, soronként egy input mező.

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

- **Sötét téma**, sárga az „aktív/szerkesztett" jelzés, kék az „interaktív elem" (sor poligon), piros szaggatott a régió.
- A felület **magyar nyelvű**.
- Vanilla JS, **nincs build lépés** — közvetlenül megnyitható böngészőben (`file://` is működik a `FileReader` miatt).
- Egyetlen fájl: stílus, markup és JS mind az `editor.html`-ben. Egyelőre szándékos, hogy gyors a vasprototípus.
- A koordináták és poligonok **a kép natív pixelterében** vannak; minden képernyő-skálázás a `currentEffectiveZoom()` / `scale` faktorokkal történik.

---

## Lehetséges következő lépések (még nem eldöntött)

- Több oldal kezelése (mappa / lista nézet)
- Backend a JSON-ok tárolására és HTR motor meghívására
- Sor splittelése / mergelése / újrarajzolása
- Billentyűparancsok kibővítése
- Export más formátumba (PAGE XML, ALTO, sima szöveg)

Ha valamelyiket elkezdjük, ide írjuk a döntéseket.
