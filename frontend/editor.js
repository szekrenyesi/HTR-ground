// ─── Állapot ────────────────────────────────────────────────────
let data     = null;
let origData = null;
let imgW = 0, imgH = 0;
let selected = null;    // { ri, li }
let edited   = new Set();

// Zoom: null = fit-to-panel, number = fraction of natural size
const ZOOM_STEPS = [0.1, 0.15, 0.2, 0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0];
let zoomFit  = true;
let zoomStep = 8; // index into ZOOM_STEPS, used when not in fit mode

let viewMode   = 'page'; // 'page' | 'detail'
let detailZoom = 1.0;

let imgContrast = 1.0;
let dimContext  = true;   // sor kiemelése a kontextushoz képest (alapból be)
const CONTRAST_STEPS = [1.0, 1.5, 2.0, 3.0];

let loadedFilename = null;   // a betöltött fájl neve — mentés basename-jéhez
let loadedImageBlob = null;  // a betöltött kép Blob-ja — PDF exporthoz kell

// ─── Mód: 'demo' (feltöltés) vagy 'project' (szerver-oldali fájl) ─────
const projectContext = readProjectContext();
const editorMode = projectContext ? 'project' : 'demo';

// ─── Vissza gomb ─────────────────────────────────────────────────
// - Demo módban: főoldalra
// - Projekt módban: a projekt-mappához
(function setupBackButton() {
  const backBtn = document.getElementById('back-btn');
  if (!backBtn) return;
  // file:// módban ne mutassuk (nincs hova visszalépni)
  if (location.protocol === 'file:') return;
  let target = '/';
  let title  = 'Vissza a főoldalra';
  if (editorMode === 'project') {
    target = projectContext.path ? `/projects/${projectContext.path}` : '/projects';
    title  = 'Vissza a projekt-mappához';
  }
  backBtn.title = title;
  backBtn.style.display = 'flex';
  backBtn.addEventListener('click', () => { window.location.href = target; });
})();

function readProjectContext() {
  // /projects/edit?path=…&basename=… → { path, basename }
  if (!window.location.pathname.startsWith('/projects/edit')) return null;
  const p = new URLSearchParams(window.location.search);
  const path     = p.get('path')     || '';
  const basename = p.get('basename') || '';
  if (!basename) return null;
  return { path, basename };
}

// ─── DOM refs ───────────────────────────────────────────────────
const imgEl           = document.getElementById('page-image');
const overlay         = document.getElementById('overlay');
const imgCont         = document.getElementById('image-container');
const noImgHint       = document.getElementById('no-image-hint');
const textPanel       = document.getElementById('text-panel');
const statusEl        = document.getElementById('status');
const saveBtn         = document.getElementById('save-btn');
const zoomLabel       = document.getElementById('zoom-label');
const imagePanel      = document.getElementById('image-panel');
const imagePanelWrap  = document.getElementById('image-panel-wrap');
const detailCanvas    = document.getElementById('detail-canvas');
const detailMeta      = document.getElementById('detail-meta');
const detailEmpty     = document.getElementById('detail-empty');
const viewToggleBtn   = document.getElementById('view-toggle-btn');
const contrastBtn     = document.getElementById('contrast-btn');
const outlineBtn      = document.getElementById('outline-btn');

// ─── Kép szűrők ─────────────────────────────────────────────────

// Kontextus szűrője — ha a kiemelés be van kapcsolva, a kontextus mindig
// sötétebb a polygonnál; ha ki, akkor uniform a polygonnal (nincs fókusz)
function buildContextFilter(baseDim) {
  if (!dimContext) return buildLineFilter();
  if (imgContrast === 1.0) return `brightness(${baseDim})`;
  // Magas kontraszton is megtartjuk a kiemelést: a polygon szűrőjéből indulunk,
  // és a brightness-t lecsökkentjük, hogy a kontextus sötétebb maradjon
  const k     = imgContrast - 1.0;
  const lineB = 1.0 - k * 0.18;
  const lineC = 1.0 + k * 0.8;
  const b     = (lineB * 0.6).toFixed(3);   // ~60% of polygon brightness
  return `brightness(${b}) contrast(${lineC.toFixed(3)})`;
}

// Kiemelt sor / oldalkép szűrője — a kontraszttal arányosan sötétít, hogy a kontraszt
// a kontextushoz hasonló módon tudjon dolgozni (összenyomott hisztogramot kihúzni)
function buildLineFilter() {
  if (imgContrast === 1.0) return 'none';
  const k = imgContrast - 1.0;              // 0.5 / 1.0 / 2.0
  const b = (1.0 - k * 0.18).toFixed(3);     // 0.91 / 0.82 / 0.64
  const c = (1.0 + k * 0.8).toFixed(3);      // 1.40 / 1.80 / 2.60
  return `brightness(${b}) contrast(${c})`;
}

function applyImageFilters() {
  imgEl.style.filter = buildLineFilter();
  if (viewMode === 'detail') updateDetailView();
}

contrastBtn.addEventListener('click', () => {
  const idx  = CONTRAST_STEPS.indexOf(imgContrast);
  imgContrast = CONTRAST_STEPS[(idx + 1) % CONTRAST_STEPS.length];
  contrastBtn.textContent = imgContrast === 1.0 ? 'Kont.' : `K ${imgContrast}×`;
  contrastBtn.classList.toggle('active', imgContrast !== 1.0);
  applyImageFilters();
});

outlineBtn.addEventListener('click', () => {
  dimContext = !dimContext;
  outlineBtn.classList.toggle('active', dimContext);
  if (viewMode === 'detail') updateDetailView();
});

// ─── HTR fájl betöltése (JSON kliens-oldalt, XML a backenden keresztül) ───
document.getElementById('json-input').addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;
  const ext  = (file.name.split('.').pop() || '').toLowerCase();
  const isJson = ext === 'json';
  if (isJson) loadJsonFile(file);
  else        loadViaBackend(file);
});

function loadJsonFile(file) {
  const reader = new FileReader();
  reader.onload = ev => {
    try {
      installPage(JSON.parse(ev.target.result), file.name);
    } catch(err) {
      alert('Hibás JSON fájl:\n' + err.message);
    }
  };
  reader.readAsText(file);
}

async function loadViaBackend(file) {
  // XML (ALTO / PAGE) → POST /api/convert
  const label = document.getElementById('json-label');
  const prev  = label.textContent;
  label.textContent = 'Konvertálás…';
  try {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch('/api/convert', { method: 'POST', body: form });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch(_) {}
      throw new Error(msg);
    }
    const body = await res.json();
    installPage(body.page, file.name);
  } catch(err) {
    label.textContent = prev;
    // Tipikus eset: nincs backend (pl. file:// vagy más statikus szerver).
    const hint = (window.location.protocol === 'file:')
      ? '\n\nA XML konverzióhoz a backend kell. Indítsd el a backend/ mappából:\n  uvicorn app.main:app --reload\nés nyisd meg: http://localhost:8000'
      : '';
    alert('Konverziós hiba:\n' + err.message + hint);
  }
}

function installPage(pageObj, filename) {
  data     = pageObj;
  origData = JSON.parse(JSON.stringify(pageObj));
  loadedFilename = filename || null;
  edited.clear();
  selected = null;
  renderTextPanel();
  updateOverlay();
  updateStatus();
  updateDetailView();
  saveBtn.disabled = false;
  const label = document.getElementById('json-label');
  if (label) {
    label.classList.add('loaded');
    label.textContent = filename;
  }
}

async function loadImageFromUrl(url, displayName) {
  // Blob is szükséges lehet a PDF exporthoz — fetch-el megszerezzük egyszer
  try {
    const res = await fetch(url);
    if (res.ok) loadedImageBlob = await res.blob();
  } catch (_) { /* nem kritikus, a PDF-nél derül ki */ }
  imgEl.onload = () => {
    imgW = imgEl.naturalWidth;
    imgH = imgEl.naturalHeight;
    noImgHint.style.display = 'none';
    if (viewMode === 'page') imgCont.style.display = 'inline-block';
    applyZoom();
    updateOverlay();
    updateDetailView();
    const label = document.getElementById('img-label');
    if (label) {
      label.classList.add('loaded');
      label.textContent = displayName || 'kép';
    }
  };
  imgEl.src = url;
}

// ─── Image loading ──────────────────────────────────────────────
document.getElementById('img-input').addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;
  loadedImageBlob = file;
  const url = URL.createObjectURL(file);
  imgEl.onload = () => {
    imgW = imgEl.naturalWidth;
    imgH = imgEl.naturalHeight;
    noImgHint.style.display = 'none';
    if (viewMode === 'page') imgCont.style.display = 'inline-block';
    applyZoom();
    updateOverlay();
    updateDetailView();
    document.getElementById('img-label').classList.add('loaded');
    document.getElementById('img-label').textContent = file.name;
  };
  imgEl.src = url;
});

// ─── Zoom ───────────────────────────────────────────────────────
function applyZoom() {
  if (!imgW || viewMode === 'detail') return;
  if (zoomFit) {
    const panelH = imagePanel.clientHeight - 24;
    imgEl.style.width     = '';
    imgEl.style.height    = 'auto';
    imgEl.style.maxWidth  = '100%';
    imgEl.style.maxHeight = panelH + 'px';
    requestAnimationFrame(() => {
      const eff = Math.round(imgEl.clientWidth / imgW * 100);
      zoomLabel.textContent = `Illesztés (${eff}%)`;
      updateOverlay();
      if (selected) scrollImageToLine(selected.ri, selected.li, 'instant');
    });
  } else {
    const z = ZOOM_STEPS[zoomStep];
    imgEl.style.maxWidth  = 'none';
    imgEl.style.maxHeight = 'none';
    imgEl.style.height    = 'auto';
    imgEl.style.width     = Math.round(imgW * z) + 'px';
    zoomLabel.textContent = Math.round(z * 100) + '%';
    updateOverlay();
    if (selected) scrollImageToLine(selected.ri, selected.li, 'instant');
  }
}

function currentEffectiveZoom() {
  if (!imgW) return 1;
  return imgEl.clientWidth / imgW;
}

function zoomIn() {
  if (viewMode === 'detail') {
    detailZoom = Math.min(12, +(detailZoom * 1.4).toFixed(2));
    updateDetailView(); updateDetailZoomLabel(); return;
  }
  if (!imgW) return;
  const cur = currentEffectiveZoom();
  const next = ZOOM_STEPS.findIndex(s => s > cur + 0.005);
  if (next === -1) return;
  zoomFit = false; zoomStep = next; applyZoom();
}

function zoomOut() {
  if (viewMode === 'detail') {
    detailZoom = Math.max(0.5, +(detailZoom / 1.4).toFixed(2));
    updateDetailView(); updateDetailZoomLabel(); return;
  }
  if (!imgW) return;
  const cur = currentEffectiveZoom();
  let prev = -1;
  for (let i = ZOOM_STEPS.length - 1; i >= 0; i--) {
    if (ZOOM_STEPS[i] < cur - 0.005) { prev = i; break; }
  }
  if (prev === -1) return;
  zoomFit = false; zoomStep = prev; applyZoom();
}

function resetZoom() {
  if (viewMode === 'detail') {
    detailZoom = 1.0; updateDetailView(); updateDetailZoomLabel(); return;
  }
  zoomFit = true; applyZoom();
  if (selected) scrollImageToLine(selected.ri, selected.li);
}

function updateDetailZoomLabel() {
  zoomLabel.textContent = detailZoom === 1.0 ? 'Illesztés' : `${detailZoom.toFixed(1)}×`;
}

document.getElementById('zoom-in').addEventListener('click', zoomIn);
document.getElementById('zoom-out').addEventListener('click', zoomOut);
zoomLabel.addEventListener('click', resetZoom);

// Ctrl+scroll: page panel → oldal zoom, detail canvas → részlet zoom
imagePanel.addEventListener('wheel', e => {
  if (!e.ctrlKey || viewMode !== 'page') return;
  e.preventDefault();
  if (e.deltaY < 0) zoomIn(); else zoomOut();
}, { passive: false });

detailCanvas.addEventListener('wheel', e => {
  if (!e.ctrlKey) return;
  e.preventDefault();
  if (e.deltaY < 0) zoomIn(); else zoomOut();
}, { passive: false });

// ─── Text panel rendering ───────────────────────────────────────
function renderTextPanel() {
  textPanel.innerHTML = '';
  if (!data) return;

  data.regions.forEach((region, ri) => {
    const block = document.createElement('div');
    block.className = 'region-block';

    const header = document.createElement('div');
    header.className = 'region-header';
    header.textContent = `Régió ${ri + 1}  ·  ${region.lines.length} sor`;
    block.appendChild(header);

    region.lines.forEach((line, li) => {
      const key = `${ri}-${li}`;
      const row = document.createElement('div');
      row.className = 'line-row' + (edited.has(key) ? ' edited' : '');
      row.id = `row-${ri}-${li}`;

      const num = document.createElement('span');
      num.className = 'line-num';
      num.textContent = li + 1;

      const input = document.createElement('input');
      input.type      = 'text';
      input.className = 'line-input';
      input.value     = line.text || '';
      input.spellcheck = false;

      const dot = document.createElement('span');
      dot.className = 'edit-dot';
      dot.title = 'Szerkesztve';

      input.addEventListener('focus', () => selectLine(ri, li, false));
      row.addEventListener('mousedown', ev => {
        if (ev.target !== input) { selectLine(ri, li, false); ev.preventDefault(); }
      });

      input.addEventListener('input', () => {
        data.regions[ri].lines[li].text = input.value;
        const orig = origData.regions[ri].lines[li].text;
        if (input.value !== orig) {
          edited.add(key); row.classList.add('edited');
        } else {
          edited.delete(key); row.classList.remove('edited');
        }
        updateStatus();
      });

      input.addEventListener('keydown', ev => {
        if (ev.key === 'Enter' || ev.key === 'ArrowDown') {
          ev.preventDefault(); jumpLine(ri, li, +1);
        } else if (ev.key === 'ArrowUp') {
          ev.preventDefault(); jumpLine(ri, li, -1);
        } else if (ev.key === 'Escape') {
          input.blur();
        }
      });

      row.append(num, input, dot);
      block.appendChild(row);
    });

    textPanel.appendChild(block);
  });
}

function jumpLine(ri, li, dir) {
  const flat = [];
  data.regions.forEach((r, rIdx) => r.lines.forEach((_, lIdx) => flat.push([rIdx, lIdx])));
  const idx  = flat.findIndex(([r, l]) => r === ri && l === li);
  const next = flat[idx + dir];
  if (!next) return;
  const [nri, nli] = next;
  selectLine(nri, nli, true);
  const row = document.getElementById(`row-${nri}-${nli}`);
  if (row) { row.querySelector('input').focus(); row.scrollIntoView({ block: 'nearest' }); }
}

// ─── Selection ──────────────────────────────────────────────────
function selectLine(ri, li, scrollText = true) {
  document.querySelectorAll('.line-row.selected').forEach(el => el.classList.remove('selected'));
  document.querySelectorAll('#overlay .line-poly.selected').forEach(el => el.classList.remove('selected'));

  selected = { ri, li };

  const row = document.getElementById(`row-${ri}-${li}`);
  if (row) {
    row.classList.add('selected');
    if (scrollText) row.scrollIntoView({ block: 'nearest' });
  }

  const poly = document.getElementById(`poly-${ri}-${li}`);
  if (poly) {
    poly.classList.add('selected');
    scrollImageToLine(ri, li);
  }

  updateDetailView();
}

function scrollImageToLine(ri, li, behavior = 'smooth') {
  if (!imgW || !imgEl.clientWidth) return;
  const [x, y, w, h] = data.regions[ri].lines[li].rect;
  const scale = imgEl.clientWidth / imgW;
  const cx    = (x + w / 2) * scale;
  const cy    = (y + h / 2) * scale;
  imagePanel.scrollTo({
    left: cx - imagePanel.clientWidth  / 2,
    top:  cy - imagePanel.clientHeight / 2,
    behavior
  });
}

// ─── SVG overlay ────────────────────────────────────────────────
function updateOverlay() {
  overlay.innerHTML = '';
  if (!data || !imgEl.clientWidth || !imgW) return;

  overlay.setAttribute('viewBox', `0 0 ${imgW} ${imgH}`);
  overlay.style.width  = imgEl.clientWidth  + 'px';
  overlay.style.height = imgEl.clientHeight + 'px';

  data.regions.forEach(region => {
    overlay.appendChild(makePoly(region.coords, 'region-poly', null));
  });

  data.regions.forEach((region, ri) => {
    region.lines.forEach((line, li) => {
      const poly = makePoly(line.coords, 'line-poly', `poly-${ri}-${li}`);
      if (selected && selected.ri === ri && selected.li === li) poly.classList.add('selected');
      poly.addEventListener('click', () => {
        selectLine(ri, li, true);
        const row = document.getElementById(`row-${ri}-${li}`);
        if (row) { row.scrollIntoView({ block: 'nearest' }); row.querySelector('input').focus(); }
      });
      overlay.appendChild(poly);
    });
  });
}

function makePoly(coords, cls, id) {
  const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
  poly.setAttribute('points', coords.map(p => p[0] + ',' + p[1]).join(' '));
  poly.classList.add(cls);
  if (id) poly.id = id;
  return poly;
}

new ResizeObserver(() => {
  if (viewMode === 'page') { if (zoomFit) applyZoom(); else updateOverlay(); }
  else updateDetailView();
}).observe(imagePanelWrap);

// ─── View toggle ────────────────────────────────────────────────
function setViewMode(mode) {
  viewMode = mode;
  if (mode === 'page') {
    imgCont.style.display      = imgW ? 'inline-block' : 'none';
    noImgHint.style.display    = imgW ? 'none' : '';
    detailCanvas.style.display = 'none';
    detailEmpty.style.display  = 'none';
    detailMeta.textContent     = '';
    viewToggleBtn.textContent  = 'Részlet nézet';
    viewToggleBtn.classList.remove('active');
    applyZoom();
  } else {
    imgCont.style.display      = 'none';
    noImgHint.style.display    = 'none';
    detailCanvas.style.display = 'block';
    viewToggleBtn.textContent  = 'Oldal nézet';
    viewToggleBtn.classList.add('active');
    detailZoom = 1.0;
    dimContext = true;
    outlineBtn.classList.add('active');
    updateDetailZoomLabel();
    updateDetailView();
  }
}

viewToggleBtn.addEventListener('click', () =>
  setViewMode(viewMode === 'page' ? 'detail' : 'page')
);

// ─── Detail view ────────────────────────────────────────────────
function updateDetailView() {
  if (viewMode !== 'detail') return;

  if (!selected || !imgW || !imgEl.complete || !imgEl.src) {
    detailEmpty.style.display = 'flex';
    detailMeta.textContent    = '';
    const ctx = detailCanvas.getContext('2d');
    ctx.clearRect(0, 0, detailCanvas.width, detailCanvas.height);
    return;
  }

  detailEmpty.style.display = 'none';

  const { ri, li } = selected;
  const [lx, ly, lw, lh] = data.regions[ri].lines[li].rect;

  // Padding shrinks as detailZoom grows → line fills more of the canvas
  const basePadY = Math.max(lh * 1.2, 60);
  const basePadX = Math.max(lw * 0.08, 100);
  const padY = Math.round(basePadY / detailZoom);
  const padX = Math.round(basePadX / detailZoom);

  const cropX = Math.max(0, lx - padX);
  const cropY = Math.max(0, ly - padY);
  const cropW = Math.min(imgW - cropX, lw + padX * 2);
  const cropH = Math.min(imgH - cropY, lh + padY * 2);

  const canvasH = imagePanelWrap.clientHeight;
  const canvasW = imagePanelWrap.clientWidth;

  detailCanvas.width  = canvasW;
  detailCanvas.height = canvasH;

  // Fit crop into canvas, preserving aspect ratio
  const scaleH  = canvasH / cropH;
  const scaleW  = canvasW / cropW;
  const scale   = Math.min(scaleH, scaleW);
  const drawW   = Math.round(cropW * scale);
  const drawH   = Math.round(cropH * scale);
  const offsetX = Math.round((canvasW - drawW) / 2);
  const offsetY = Math.round((canvasH - drawH) / 2);

  const ctx = detailCanvas.getContext('2d');
  ctx.fillStyle = '#0a0b10';
  ctx.fillRect(0, 0, canvasW, canvasH);

  // 1. Kontextus: sötétítés + BW (kontraszt nélkül)
  ctx.filter = buildContextFilter(0.80);
  ctx.drawImage(imgEl, cropX, cropY, cropW, cropH, offsetX, offsetY, drawW, drawH);
  ctx.filter = 'none';

  // 2. Polygon: eredeti fényerő + BW + kontraszt
  const line = data.regions[ri].lines[li];
  ctx.save();
  ctx.beginPath();
  line.coords.forEach((pt, i) => {
    const px = offsetX + (pt[0] - cropX) * scale;
    const py = offsetY + (pt[1] - cropY) * scale;
    i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
  });
  ctx.closePath();
  ctx.clip();
  ctx.filter = buildLineFilter();
  ctx.drawImage(imgEl, cropX, cropY, cropW, cropH, offsetX, offsetY, drawW, drawH);
  ctx.filter = 'none';
  ctx.restore();

  detailMeta.textContent = `R${ri + 1} · ${li + 1}. sor`;
}

// ─── Status ─────────────────────────────────────────────────────
function updateStatus() {
  if (!data) { statusEl.textContent = 'Nincs betöltve fájl'; statusEl.className = ''; return; }
  const total = data.regions.reduce((s, r) => s + r.lines.length, 0);
  if (edited.size > 0) {
    statusEl.textContent = `${edited.size} szerkesztett sor / ${total} összesen`;
    statusEl.className   = 'status-edited';
  } else {
    statusEl.textContent = `${total} sor betöltve`;
    statusEl.className   = '';
  }
}

// ─── Save + Export ──────────────────────────────────────────────
const saveMenu   = document.getElementById('save-menu');
const exportBtn  = document.getElementById('export-btn');
const saveCaret  = document.getElementById('save-caret');
const saveMenuHint = document.getElementById('save-menu-hint');

// Projekt módban tárolt kontextus: a backend válaszaiból
let projectSaveFormat = null;  // "json" | "alto-xml" | "page-xml"

function baseNameOf(filename) {
  if (!filename) return 'corrected';
  // Az összetett kiterjesztéseket is kezeljük: foo.alto.xml → foo
  let s = filename.replace(/\.(json|xml|alto|page|alto\.xml|page\.xml)$/i, '');
  // Ha az elsőnél nem talált (pl. .alto.xml → .alto marad), még egyszer
  s = s.replace(/\.(alto|page)$/i, '');
  return s || 'corrected';
}

function downloadBlob(blob, filename) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── Fő mentés gomb ──
saveBtn.addEventListener('click', ev => {
  if (saveBtn.disabled) return;
  ev.stopPropagation();
  if (editorMode === 'project') {
    saveInPlace();
  } else {
    // Demo mód: dropdown-nyitás
    saveMenu.classList.toggle('open');
  }
});

// ── Export gomb (csak projekt módban) ──
exportBtn.addEventListener('click', ev => {
  ev.stopPropagation();
  saveMenu.classList.toggle('open');
});

// Menü bezárása kívülre kattintva
document.addEventListener('click', ev => {
  if (!saveMenu.contains(ev.target) && ev.target !== saveBtn && ev.target !== exportBtn) {
    saveMenu.classList.remove('open');
  }
});
document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape') saveMenu.classList.remove('open');
});

// Menü választás — formátum-export (letöltés)
saveMenu.addEventListener('click', async ev => {
  const btn = ev.target.closest('button[data-format]');
  if (!btn || !data) return;
  saveMenu.classList.remove('open');
  const fmt      = btn.dataset.format;
  const basename = (projectContext && projectContext.basename) || baseNameOf(loadedFilename);
  await exportAndDownload(fmt, basename);
});

async function exportAndDownload(format, basename) {
  // JSON: kliens-oldalt (file:// módban is működik)
  if (format === 'json') {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    downloadBlob(blob, `${basename}.json`);
    return;
  }

  // PDF: kép + page multipart
  if (format === 'pdf') {
    if (!loadedImageBlob) {
      alert('PDF exporthoz kell a képfájl is — tölts be egyet a "Kép betöltése" gombbal.');
      return;
    }
    try {
      const form = new FormData();
      form.append('page', JSON.stringify(data));
      form.append('image', loadedImageBlob, 'image');
      form.append('basename', basename);
      const res = await fetch('/api/export-pdf', { method: 'POST', body: form });
      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try { const j = await res.json(); if (j.detail) msg = j.detail; } catch(_) {}
        throw new Error(msg);
      }
      const blob = await res.blob();
      downloadBlob(blob, `${basename}.pdf`);
    } catch (err) {
      alert('PDF export hiba:\n' + err.message);
    }
    return;
  }

  // ALTO / PAGE: backend hívás JSON body-val
  try {
    const res = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page: data, format, basename, image_filename: '' }),
    });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch(_) {}
      throw new Error(msg);
    }
    const blob = await res.blob();
    const ext = format === 'alto-xml' ? '.alto.xml' : '.page.xml';
    downloadBlob(blob, `${basename}${ext}`);
  } catch (err) {
    const hint = (window.location.protocol === 'file:')
      ? '\n\nAz ALTO/PAGE exporthoz a backend kell. Indítsd el a backend/ mappából:\n  uvicorn app.main:app --reload\nés nyisd meg: http://localhost:8000/demo'
      : '';
    alert('Export hiba:\n' + err.message + hint);
  }
}

// Projekt módban a fájl felülírása helyben
async function saveInPlace() {
  if (!projectContext || !data) return;
  const prevText = saveBtn.textContent;
  saveBtn.disabled = true;
  saveBtn.textContent = 'Mentés…';
  try {
    const q = new URLSearchParams({ path: projectContext.path, basename: projectContext.basename });
    const res = await fetch(`/api/project-file?${q}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page: data, image_filename: projectContext.imageFilename || '' }),
    });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch(_) {}
      throw new Error(msg);
    }
    const body = await res.json();
    // Sikeres mentés — origData frissítése, edited ürítése
    origData = JSON.parse(JSON.stringify(data));
    edited.clear();
    document.querySelectorAll('.line-row.edited').forEach(el => el.classList.remove('edited'));
    updateStatus();
    flashStatus(`Mentve: ${body.saved_filename}`, 'ok');
  } catch (err) {
    alert('Mentési hiba:\n' + err.message);
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = prevText;
  }
}

function flashStatus(msg, kind) {
  const prev = statusEl.textContent;
  const prevCls = statusEl.className;
  statusEl.textContent = msg;
  statusEl.className = kind === 'ok' ? 'status-edited' : '';
  setTimeout(() => { statusEl.textContent = prev; statusEl.className = prevCls; updateStatus(); }, 2000);
}

// ─── Presence: heartbeat + concurrent-editor warning ────────────
const HEARTBEAT_INTERVAL_MS = 25000;
let heartbeatTimer = null;

async function checkPresenceBeforeOpen() {
  // Ha van másik aktív user, konfirmáljunk (Anna itt van — biztos folytatod?)
  try {
    const q = new URLSearchParams({ path: projectContext.path, basename: projectContext.basename });
    const res = await fetch(`/api/presence?${q}`);
    if (!res.ok) return true; // presence hiba nem blokkolja a betöltést
    const body = await res.json();
    if (!body.others || !body.others.users || !body.others.users.length) return true;
    const names = body.others.users.map(u => u.username).join(', ');
    const msg = body.others.users.length === 1
      ? `${names} épp ezt a fájlt szerkeszti. Biztos folytatod? (Az utolsó mentés győz.)`
      : `${names} épp ezt a fájlt szerkeszti. Biztos folytatod? (Az utolsó mentés győz.)`;
    return window.confirm(msg);
  } catch (_) {
    return true;
  }
}

async function sendHeartbeat() {
  if (!projectContext) return;
  try {
    await fetch('/api/presence/heartbeat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: projectContext.path, basename: projectContext.basename }),
    });
  } catch (_) { /* offline / hálózat kimarad — nem baj */ }
}

function startHeartbeat() {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  sendHeartbeat();
  heartbeatTimer = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS);
}

function stopHeartbeatAndLeave() {
  if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
  if (!projectContext) return;
  const payload = JSON.stringify({ path: projectContext.path, basename: projectContext.basename });
  // sendBeacon: page unload alatt is megbízhatóan kimegy
  if (navigator.sendBeacon) {
    const blob = new Blob([payload], { type: 'application/json' });
    navigator.sendBeacon('/api/presence/leave', blob);
  } else {
    fetch('/api/presence/leave', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: payload, keepalive: true }).catch(() => {});
  }
}

window.addEventListener('beforeunload', stopHeartbeatAndLeave);

// ─── Projekt mód: inicializálás ─────────────────────────────────
async function initProjectMode() {
  if (!projectContext) return;

  // File upload gombok elrejtése, projekt-info kiírása
  document.querySelectorAll('.file-btn').forEach(el => el.style.display = 'none');
  const info = document.getElementById('project-info');
  info.style.display = 'flex';

  // Save gomb: nem dropdown, hanem inline save
  saveCaret.style.display = 'none';
  saveBtn.textContent = 'Mentés';
  exportBtn.style.display = 'inline-flex';
  saveMenuHint.textContent = 'Export letöltésként';

  // Ha valaki már itt van, konfirmáljunk mielőtt beltöltjük
  const proceed = await checkPresenceBeforeOpen();
  if (!proceed) {
    // Vissza a projekt-mappához
    const back = projectContext.path ? `/projects/${projectContext.path}` : '/projects';
    window.location.href = back;
    return;
  }

  // Autoload a projekt-fájl
  try {
    const q = new URLSearchParams({ path: projectContext.path, basename: projectContext.basename });
    const res = await fetch(`/api/project-file?${q}`);
    if (res.status === 401) {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
      return;
    }
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch(_) {}
      throw new Error(msg);
    }
    const body = await res.json();
    projectSaveFormat = body.save_format;
    projectContext.imageFilename = body.image_filename;

    // Projekt-info label kitöltés
    const pathParts = [body.path, body.basename].filter(Boolean).join(' / ');
    info.innerHTML = `
      <span class="path">${escapeHtml(body.path || '(gyökér)')} /</span>
      <span class="basename">${escapeHtml(body.basename)}</span>
      <span class="fmt">${escapeHtml(body.save_format)}</span>
    `;

    installPage(body.page, body.annotation_filename);

    if (body.image_url) {
      loadImageFromUrl(body.image_url, body.image_filename);
    }

    // Heartbeat indítás — mostantól bekerülünk a presence-be
    startHeartbeat();
  } catch (err) {
    alert('Betöltési hiba:\n' + err.message);
  }
}

function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  })[c]);
}

// Indítsd az auto-loadot ha projekt mód
initProjectMode();
