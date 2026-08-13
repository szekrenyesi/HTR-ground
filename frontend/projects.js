// ─── Projektek böngésző ─────────────────────────────────────────

const contentEl    = document.getElementById('content');
const breadcrumbEl = document.getElementById('breadcrumb');
const loginStatus  = document.getElementById('login-status');
const statsBar     = document.getElementById('stats-bar');

// Sub-path deployment: a HTML meta tagből vesszük a prefixet.
// Üres string root deployment esetén; pl. "/htr-ground" sub-path módban.
const ROOT_PATH = document.querySelector('meta[name="root-path"]')?.content || '';
function api(path) { return ROOT_PATH + path; }

// Státusz-lista cache (a backend adja a /api/status-values-en)
let statusValues = null;

// A location.pathname-ból kivágjuk a ROOT_PATH-ot ÉS a /projects prefixet → user_path
function currentPath() {
  let p = window.location.pathname;
  if (ROOT_PATH && p.startsWith(ROOT_PATH)) p = p.slice(ROOT_PATH.length);
  p = p.replace(/^\/projects\/?/, '').replace(/\/+$/, '');
  return p; // "" | "Bakonykuti" | "Bakonykuti/1949"
}

function fmtDate(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  // Rövid ISO-szerű: 2026-07-01 14:32
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fmtSize(bytes) {
  if (!bytes && bytes !== 0) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' kB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Escape HTML kompletten
function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]);
}

// Session info cache — a jogosultsághoz szükséges (import gomb / delete gomb)
let sessionInfo = { authenticated: false };

// A legutóbbi folder-listázás cache-e — a törlés-modal olvassa a stats-hoz
let lastFolderData = null;

function canImport() {
  return sessionInfo.is_admin || (sessionInfo.groups || []).includes('import');
}
function isAdmin() {
  return !!sessionInfo.is_admin;
}

// Login state widget + session info feltöltése
async function setupLoginStatus() {
  try {
    const info = await fetch(api('/api/session')).then(r => r.json());
    sessionInfo = info;
    if (info.authenticated) {
      const name = info.display_name || info.username;
      const adminTag = info.is_admin ? ' <span title="admin" class="admin-star">★</span>' : '';
      loginStatus.innerHTML = `Belépve mint <strong class="user-name">${esc(name)}</strong>${adminTag} · <a href="#" class="btn-link-plain" id="logout-link">Kilépés</a>`;
      document.getElementById('logout-link').addEventListener('click', async ev => {
        ev.preventDefault();
        await fetch(api('/logout'), { method: 'POST' });
        window.location.href = ROOT_PATH + '/';
      });
    } else {
      loginStatus.innerHTML = `<a href="${ROOT_PATH}/login" class="btn-link-plain">Belépés</a>`;
    }
    // A „+ Új" dropdown csak import-jogúaknak látszik
    document.getElementById('new-menu-wrap').hidden = !canImport();
  } catch (_) {}
}

function renderBreadcrumb(crumbs) {
  const parts = crumbs.map((c, i) => {
    const isLast = i === crumbs.length - 1;
    if (isLast) return `<span class="current">${esc(c.name)}</span>`;
    const href = c.path ? `${ROOT_PATH}/projects/${c.path}` : `${ROOT_PATH}/projects`;
    return `<a href="${href}" data-crumb="${esc(c.path)}">${esc(c.name)}</a>`;
  });
  breadcrumbEl.innerHTML = parts.join('<span class="sep">›</span>');
}

function renderSubfolders(subfolders) {
  if (!subfolders.length) return '';
  const admin = isAdmin();
  const items = subfolders.map(f => `
    <a class="item" href="${ROOT_PATH}/projects/${esc(f.path)}" data-navigate="${esc(f.path)}">
      <span class="icon">📁</span>
      <div class="meta">
        <div class="name">${esc(f.name)}</div>
        ${renderInlineStats(f.stats)}
      </div>
      <button type="button" class="folder-export-btn"
              data-export-path="${esc(f.path)}"
              title="Ez az almappa exportálása ZIP-be">Export ↓</button>
      ${admin ? `<button type="button" class="row-delete-btn" data-delete-kind="folder" data-delete-path="${esc(f.path)}" data-delete-name="${esc(f.name)}" title="Mappa törlése">×</button>` : ''}
      <span class="modified">${fmtDate(f.modified)}</span>
    </a>
  `).join('');
  return `
    <div class="section-title">Almappák (${subfolders.length})</div>
    <div class="item-list">${items}</div>
  `;
}

// Kompakt egy soros stats a mappa sorába — halványabb, kis dot + szám csak
function renderInlineStats(stats) {
  if (!stats || !stats.total) return '';
  const parts = Object.entries(stats.counts).map(([status, count]) => {
    const cls = statusCssClass(status);
    return `<span class="inline-stat"><span class="stat-dot ${cls}"></span>${count} ${esc(status)}</span>`;
  });
  parts.push(`<span class="inline-stat-total">${stats.total} összesen</span>`);
  return `<div class="inline-stats">${parts.join('')}</div>`;
}

function fmtIso(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function statusCssClass(value) {
  // Az ékezetes „ellenőrzésre vár"-ból lesz „ellenőrzésre-vár"
  return 'status-' + String(value || '').replace(/\s+/g, '-');
}

function renderStatusBadge(pair, folderPath) {
  const meta = pair.meta || { status: 'új' };
  const cls  = statusCssClass(meta.status);
  const dataAttr = ` data-path="${esc(folderPath || '')}" data-basename="${esc(pair.basename)}" data-current="${esc(meta.status)}"`;
  return `<span class="status-badge ${cls}"${dataAttr} title="Kattints státusz-váltáshoz">${esc(meta.status)}</span>`;
}

function renderAuditLine(pair) {
  const m = pair.meta || {};
  const parts = [];
  if (m.status_changed_by && m.status_changed_at) {
    parts.push(`<span title="státusz állítva: ${esc(fmtIso(m.status_changed_at))} · ${esc(m.status_changed_by)}"><strong>st.</strong> ${esc(m.status_changed_by)}</span>`);
  }
  if (m.edited_by && m.edited_at) {
    parts.push(`<span title="mentve: ${esc(fmtIso(m.edited_at))} · ${esc(m.edited_by)}"><strong>szerk.</strong> ${esc(m.edited_by)}</span>`);
  }
  if (!parts.length) return '';
  return `<div class="audit">${parts.join(' · ')}</div>`;
}

function renderPresenceLine(pair) {
  const p = pair.presence;
  if (!p || !p.users || !p.users.length) return '';
  const names = p.users.map(u => esc(u.username)).join(', ');
  const label = p.users.length === 1
    ? `${names} itt van`
    : `${p.users.length} felhasználó (${names}) itt van`;
  return `<div class="presence" title="Jelenleg aktív"><span class="pulse"></span>${label}</div>`;
}

function renderPairs(pairs, folderPath) {
  if (!pairs.length) return '';
  const items = pairs.map(pair => {
    const image = pair.image;
    const ann   = pair.annotation;

    let icon = '🖼️';
    let subParts = [];

    if (image && ann) {
      icon = '📄';
      subParts.push(`<span>${esc(image.filename)}</span>`);
      subParts.push(`<span>${esc(ann.filename)}</span>`);
      subParts.push(`<span class="badge-fmt">${esc(ann.format)}</span>`);
    } else if (ann && !image) {
      icon = '📝';
      subParts.push(`<span>${esc(ann.filename)}</span>`);
      subParts.push(`<span class="badge-fmt">${esc(ann.format)}</span>`);
      subParts.push(`<span class="warn">nincs kép</span>`);
    } else if (image && !ann) {
      icon = '🖼️';
      subParts.push(`<span>${esc(image.filename)}</span>`);
      subParts.push(`<span class="warn">nincs átirat</span>`);
    }

    // Editor megnyitása a szerver-fájllal — a státusz badge NEM redirectel
    const q = new URLSearchParams({ path: folderPath || '', basename: pair.basename });
    const href = `${ROOT_PATH}/projects/edit?${q}`;
    const admin = isAdmin();
    return `
      <div class="item" data-href="${href}">
        <span class="icon">${icon}</span>
        <div class="meta">
          <div class="name">${esc(pair.basename)}</div>
          <div class="sub">${subParts.join('')}</div>
          ${renderAuditLine(pair)}
          ${renderPresenceLine(pair)}
        </div>
        <div class="status-wrap">${renderStatusBadge(pair, folderPath)}</div>
        ${admin ? `<button type="button" class="row-delete-btn" data-delete-kind="pair" data-delete-path="${esc(folderPath || '')}" data-delete-name="${esc(pair.basename)}" title="Pár törlése">×</button>` : ''}
        <span class="modified">${fmtDate(pair.modified)}</span>
      </div>
    `;
  }).join('');
  return `
    <div class="section-title">Fájlok (${pairs.length})</div>
    <div class="item-list">${items}</div>
  `;
}

// ─── Státusz-badge interakció ────────────────────────────────────
function closeAllStatusMenus() {
  document.querySelectorAll('.status-menu.open').forEach(m => m.classList.remove('open'));
}

function openStatusMenu(badgeEl) {
  closeAllStatusMenus();
  if (!statusValues) return;
  const current = badgeEl.dataset.current;
  const path    = badgeEl.dataset.path;
  const basename = badgeEl.dataset.basename;
  const menu = document.createElement('div');
  menu.className = 'status-menu open';
  menu.innerHTML = statusValues.values.map(v => {
    const cls = v === current ? 'current' : '';
    return `<button class="${cls}" data-value="${esc(v)}">${esc(v)}</button>`;
  }).join('');
  badgeEl.parentElement.appendChild(menu);

  menu.addEventListener('click', async ev => {
    const btn = ev.target.closest('button[data-value]');
    if (!btn) return;
    const newStatus = btn.dataset.value;
    menu.remove();
    if (newStatus === current) return;
    await updateStatus(path, basename, newStatus);
  });
}

async function updateStatus(path, basename, newStatus) {
  const q = new URLSearchParams({ path, basename });
  try {
    const res = await fetch(api(`/api/project-status?${q}`), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus }),
    });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch(_) {}
      throw new Error(msg);
    }
    // Sikeres — újratöltjük az aktuális mappát
    await loadFolder(currentPath());
  } catch (err) {
    alert('Státusz-módosítási hiba:\n' + err.message);
  }
}

// Kliens-oldali event delegáció: badge / almappa-export / delete / sor kattintás
document.addEventListener('click', ev => {
  const badge = ev.target.closest('.status-badge');
  if (badge) {
    ev.preventDefault();
    ev.stopPropagation();
    openStatusMenu(badge);
    return;
  }
  // Almappa Export gomb — ne indítson navigációt a mappára, csak a modalt nyissa
  const folderExport = ev.target.closest('.folder-export-btn');
  if (folderExport) {
    ev.preventDefault();
    ev.stopPropagation();
    openExportModal(folderExport.dataset.exportPath);
    return;
  }
  // Sor-szintű törlés (admin)
  const rowDelete = ev.target.closest('.row-delete-btn');
  if (rowDelete) {
    ev.preventDefault();
    ev.stopPropagation();
    openDeleteModal(rowDelete.dataset.deleteKind, rowDelete.dataset.deletePath, rowDelete.dataset.deleteName);
    return;
  }
  const item = ev.target.closest('.item[data-href]');
  if (item && !ev.target.closest('.status-menu')) {
    window.location.href = item.dataset.href;
    return;
  }
  // Bárhova máshova kattintva a menük becsukódnak
  if (!ev.target.closest('.status-menu')) closeAllStatusMenus();
  if (!ev.target.closest('#new-menu-wrap')) closeNewMenu();
});
document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape') closeAllStatusMenus();
});

async function ensureStatusValues() {
  if (statusValues) return;
  try {
    const res = await fetch(api('/api/status-values'));
    if (res.ok) statusValues = await res.json();
  } catch (_) { /* offline / nincs backend — legfeljebb nem nyílik a menu */ }
}

async function loadFolder(path) {
  contentEl.innerHTML = '<div class="state-msg">Betöltés…</div>';
  const url = path ? api(`/api/projects/${path}`) : api('/api/projects');
  try {
    const res = await fetch(url);
    if (res.status === 401) {
      // Nem vagyunk beléptetve — redirect a login oldalra
      window.location.href = `${ROOT_PATH}/login?next=${encodeURIComponent(window.location.pathname)}`;
      return;
    }
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch (_) {}
      throw new Error(msg);
    }
    const body = await res.json();
    lastFolderData = body;  // a törlés-modal (per-subfolder stats) használja
    renderBreadcrumb(body.breadcrumb);
    renderStats(body.stats, !body.path);  // atRoot = üres path → nincs fejléc stats
    const html = renderSubfolders(body.subfolders) + renderPairs(body.pairs, body.path);
    contentEl.innerHTML = html || '<div class="state-msg">Üres mappa.</div>';
    // Fejléc Export gomb: csak akkor, ha ebben a mappában vannak PÁROK
    // (különben csak almappák — azoknak saját Export gombjuk van)
    exportBtn.hidden = !body.pairs || body.pairs.length === 0;
  } catch (err) {
    contentEl.innerHTML = `<div class="state-msg error">Hiba: ${esc(err.message)}</div>`;
    exportBtn.hidden = true;
    statsBar.hidden = true;
  }
}

// Fejléc stats — a body.stats.counts sorrendjében (workflow-sorrend). A
// gyökérben (path === "") NEM mutatjuk, mert az összes projekt aggregátuma
// információként nem hasznos.
function renderStats(stats, atRoot) {
  if (atRoot || !stats || !stats.total) {
    statsBar.hidden = true;
    return;
  }
  const parts = [];
  const entries = Object.entries(stats.counts);
  entries.forEach(([status, count], i) => {
    const cls = statusCssClass(status);
    parts.push(`
      <span class="stat-item">
        <span class="stat-dot ${cls}"></span>
        <span class="stat-count">${count}</span>
        <span class="stat-label">${esc(status)}</span>
      </span>
    `);
    if (i < entries.length - 1) parts.push('<span class="stat-sep">·</span>');
  });
  parts.push(`<span class="stat-total">${stats.total} összesen</span>`);
  statsBar.innerHTML = parts.join('');
  statsBar.hidden = false;
}

// ─── Export modal ─────────────────────────────────────────────────
const exportBtn      = document.getElementById('export-btn');
const exportBackdrop = document.getElementById('export-backdrop');
const exportClose    = document.getElementById('export-close');
const exportCancel   = document.getElementById('export-cancel');
const exportSubmit   = document.getElementById('export-submit');
const exportTarget   = document.getElementById('export-target');
const exportRecursive = document.getElementById('export-recursive');
const exportCheckAll  = document.getElementById('export-check-all');
const exportChecks    = () => document.querySelectorAll(
  '.export-check-sub input[type="checkbox"]'
);
const exportToast    = document.getElementById('export-toast');

// Az éppen exportálandó path — a modal ezt küldi az API-nak
let exportModalPath = '';

function openExportModal(path) {
  exportModalPath = path || currentPath();
  exportTarget.textContent = exportModalPath ? `/${exportModalPath}` : '/projects (gyökér)';
  exportBackdrop.hidden = false;
  updateExportSubmitState();
}
function closeExportModal() {
  exportBackdrop.hidden = true;
}

function updateExportSubmitState() {
  const anyChecked = Array.from(exportChecks()).some(c => c.checked);
  exportSubmit.disabled = !anyChecked;

  // A "mind" checkbox állapota: teljesen be = checked, teljesen ki = unchecked,
  // részleges = indeterminate
  const all = Array.from(exportChecks());
  const checkedCount = all.filter(c => c.checked).length;
  if (checkedCount === 0)            { exportCheckAll.checked = false; exportCheckAll.indeterminate = false; }
  else if (checkedCount === all.length) { exportCheckAll.checked = true;  exportCheckAll.indeterminate = false; }
  else                                { exportCheckAll.checked = false; exportCheckAll.indeterminate = true;  }
}

exportBtn.addEventListener('click', () => openExportModal(currentPath()));
exportClose.addEventListener('click', closeExportModal);
exportCancel.addEventListener('click', closeExportModal);
exportBackdrop.addEventListener('click', ev => {
  if (ev.target === exportBackdrop) closeExportModal();
});
document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape' && !exportBackdrop.hidden) closeExportModal();
});

// "mind" toggle
exportCheckAll.addEventListener('change', () => {
  const on = exportCheckAll.checked;
  exportChecks().forEach(c => { c.checked = on; });
  updateExportSubmitState();
});
// Egyedi checkboxok
exportChecks().forEach(c => c.addEventListener('change', updateExportSubmitState));

// Export gomb → letöltés
exportSubmit.addEventListener('click', async () => {
  const formats = [];
  let includeImages = 0, includeSidecars = 0;
  exportChecks().forEach(c => {
    if (!c.checked) return;
    if (c.dataset.format) formats.push(c.dataset.format);
    else if (c.dataset.extra === 'images')   includeImages   = 1;
    else if (c.dataset.extra === 'sidecars') includeSidecars = 1;
  });

  const params = new URLSearchParams({
    path: exportModalPath,
    formats: formats.join(','),
    include_images:   String(includeImages),
    include_sidecars: String(includeSidecars),
    recursive: exportRecursive.checked ? '1' : '0',
  });

  const previousText = exportSubmit.textContent;
  exportSubmit.disabled = true;
  exportSubmit.textContent = 'Készül…';

  try {
    const res = await fetch(api(`/api/project-export?${params}`));
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch(_) {}
      throw new Error(msg);
    }
    // Fájlnév a Content-Disposition-ből
    const cd = res.headers.get('content-disposition') || '';
    const nameMatch = cd.match(/filename="?([^"]+)"?/i);
    const filename  = nameMatch ? nameMatch[1] : 'export.zip';

    // Warning-ok (opcionális)
    const warnHeader = res.headers.get('x-htr-export-warnings');
    const warnings   = warnHeader ? JSON.parse(warnHeader) : null;

    const blob = await res.blob();
    downloadBlob(blob, filename);

    closeExportModal();
    if (warnings) showToast('warn', `Export kész — figyelmeztetésekkel:`, warnings);
    else          showToast('ok',   `Export kész: ${filename}`);
  } catch (err) {
    showToast('err', `Export hiba: ${err.message}`);
  } finally {
    exportSubmit.disabled = false;
    exportSubmit.textContent = previousText;
    updateExportSubmitState();
  }
});

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function showToast(kind, message, warnings) {
  exportToast.className = `export-toast ${kind}`;
  let html = `<button class="toast-close" type="button" aria-label="Bezár">×</button>`;
  html += `<div><strong>${esc(message)}</strong></div>`;
  if (warnings) {
    const parts = [];
    if (warnings.skipped_pdf?.length) {
      parts.push(`<li>${warnings.skipped_pdf.length} pár PDF-ként kihagyva (nincs kép)</li>`);
    }
    if (warnings.no_annotation?.length) {
      parts.push(`<li>${warnings.no_annotation.length} pár annotáció nélkül</li>`);
    }
    if (warnings.conversion_error?.length) {
      parts.push(`<li>${warnings.conversion_error.length} konverziós hiba</li>`);
    }
    if (parts.length) html += `<ul>${parts.join('')}</ul>`;
  }
  exportToast.innerHTML = html;
  exportToast.hidden = false;
  exportToast.querySelector('.toast-close').addEventListener('click', () => {
    exportToast.hidden = true;
  });
  // Auto-hide 8 mp után, ha nem warning
  if (kind === 'ok') {
    setTimeout(() => { exportToast.hidden = true; }, 4000);
  }
}

// ─── „+ Új" dropdown menu ─────────────────────────────────────
const newMenuBtn  = document.getElementById('new-menu-btn');
const newMenu     = document.getElementById('new-menu');
function closeNewMenu()  { newMenu.classList.remove('open'); }
function toggleNewMenu() { newMenu.classList.toggle('open'); }
newMenuBtn.addEventListener('click', ev => { ev.stopPropagation(); toggleNewMenu(); });
newMenu.addEventListener('click', ev => {
  const btn = ev.target.closest('button[data-new]');
  if (!btn) return;
  closeNewMenu();
  const kind = btn.dataset.new;
  if (kind === 'folder') openNewFolderModal();
  else if (kind === 'files') openUploadModal('files');
  else if (kind === 'dir')   openUploadModal('dir');
});

// ─── Új mappa modal ────────────────────────────────────────────
const nfBackdrop = document.getElementById('newfolder-backdrop');
const nfParent   = document.getElementById('newfolder-parent');
const nfName     = document.getElementById('newfolder-name');
const nfSubmit   = document.getElementById('newfolder-submit');

function openNewFolderModal() {
  const p = currentPath();
  nfParent.textContent = p ? `/${p} alá` : '/projects gyökér alá';
  nfName.value = '';
  nfSubmit.disabled = true;
  nfBackdrop.hidden = false;
  setTimeout(() => nfName.focus(), 50);
}
nfName.addEventListener('input', () => {
  nfSubmit.disabled = nfName.value.trim().length === 0;
});
nfName.addEventListener('keydown', ev => {
  if (ev.key === 'Enter' && !nfSubmit.disabled) nfSubmit.click();
});
nfSubmit.addEventListener('click', async () => {
  const name = nfName.value.trim().replace(/^\/+|\/+$/g, '');
  if (!name) return;
  const parent = currentPath();
  const path   = parent ? `${parent}/${name}` : name;
  nfSubmit.disabled = true;
  try {
    const res = await fetch(api('/api/project-folder'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch(_) {}
      throw new Error(msg);
    }
    closeModal('newfolder');
    showToast('ok', `Mappa létrehozva: ${path}`);
    await loadFolder(currentPath());
  } catch (err) {
    showToast('err', `Létrehozási hiba: ${err.message}`);
    nfSubmit.disabled = false;
  }
});

// ─── Upload modal (fájlok VAGY mappa) ─────────────────────────
const upBackdrop  = document.getElementById('upload-backdrop');
const upTitle     = document.getElementById('upload-title');
const upHint      = document.getElementById('upload-hint');
const upTarget    = document.getElementById('upload-target');
const upFileList  = document.getElementById('upload-file-list');
const upSummary   = document.getElementById('upload-summary');
const upSubmit    = document.getElementById('upload-submit');
const upPickBtn   = document.getElementById('upload-pick-btn');
const upFilesIn   = document.getElementById('upload-files-input');
const upDirIn     = document.getElementById('upload-dir-input');

let uploadSelectedFiles = [];  // [{file, relPath, allowed}]

const ALLOWED_EXTS = ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.gif', '.xml', '.json'];
function hasAllowedExt(name) {
  const n = name.toLowerCase();
  return ALLOWED_EXTS.some(e => n.endsWith(e));
}

function openUploadModal(mode) {
  const p = currentPath();
  upTarget.textContent = p ? `/${p} alá` : '/projects gyökér alá';
  uploadSelectedFiles = [];
  upFileList.innerHTML = '';
  upSummary.textContent = '';
  upSubmit.disabled = true;
  upBackdrop.hidden = false;

  if (mode === 'files') {
    upTitle.textContent = 'Fájlok feltöltése';
    upHint.textContent  = 'Válaszd ki a fájlokat. Elfogadott: .jpg .jpeg .png .tif .tiff .gif .xml .json';
    upPickBtn.textContent = 'Fájlok kiválasztása';
    upPickBtn.onclick = () => upFilesIn.click();
  } else {
    upTitle.textContent = 'Mappa feltöltése';
    upHint.textContent  = 'Válassz ki egy mappát — az almappa-struktúra megmarad. Csak megengedett kiterjesztésű fájlok kerülnek fel.';
    upPickBtn.textContent = 'Mappa kiválasztása';
    upPickBtn.onclick = () => upDirIn.click();
  }
}

upFilesIn.addEventListener('change', ev => handlePicked(Array.from(ev.target.files), false));
upDirIn.addEventListener('change',   ev => handlePicked(Array.from(ev.target.files), true));

function handlePicked(fileList, isDir) {
  uploadSelectedFiles = fileList.map(f => {
    const rel = isDir ? (f.webkitRelativePath || f.name) : f.name;
    return { file: f, relPath: rel, allowed: hasAllowedExt(f.name) && !rel.split('/').some(p => p.startsWith('.')) };
  });
  // Render a listába
  const rows = uploadSelectedFiles.map(x => `
    <div class="file-row ${x.allowed ? '' : 'rejected'}">
      <span>${esc(x.relPath)}</span>
      <span class="size">${fmtSize(x.file.size)}${x.allowed ? '' : ' — kiterjesztés/rejtett'}</span>
    </div>
  `).join('');
  upFileList.innerHTML = rows;
  const ok = uploadSelectedFiles.filter(x => x.allowed).length;
  const bad = uploadSelectedFiles.length - ok;
  upSummary.innerHTML = `${ok} feltöltendő${bad > 0 ? ` · <span class="warn">${bad} kihagyva</span>` : ''}`;
  upSubmit.disabled = ok === 0;
}

upSubmit.addEventListener('click', async () => {
  const goodFiles = uploadSelectedFiles.filter(x => x.allowed);
  if (goodFiles.length === 0) return;
  upSubmit.disabled = true;
  const prev = upSubmit.textContent;
  upSubmit.textContent = 'Feltöltés…';
  try {
    const form = new FormData();
    const manifest = goodFiles.map(x => x.relPath);
    form.append('manifest', JSON.stringify(manifest));
    goodFiles.forEach(x => form.append('files', x.file, x.file.name));

    const q = new URLSearchParams({ path: currentPath() });
    const res = await fetch(api(`/api/project-upload?${q}`), { method: 'POST', body: form });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch(_) {}
      throw new Error(msg);
    }
    const body = await res.json();
    closeModal('upload');
    const upCount = body.uploaded.length;
    const skCount = body.skipped.length;
    if (skCount === 0) {
      showToast('ok', `${upCount} fájl feltöltve.`);
    } else {
      showToast('warn', `${upCount} feltöltve, ${skCount} kihagyva.`, {
        skipped: body.skipped.map(s => `${s.path} — ${s.reason}`),
      });
    }
    await loadFolder(currentPath());
  } catch (err) {
    showToast('err', `Feltöltési hiba: ${err.message}`);
    upSubmit.disabled = false;
    upSubmit.textContent = prev;
  }
});

// ─── Törlés konfirmáció ───────────────────────────────────────
const delBackdrop = document.getElementById('delete-backdrop');
const delMessage  = document.getElementById('delete-message');
const delDetails  = document.getElementById('delete-details');
const delSubmit   = document.getElementById('delete-submit');

let deleteContext = null;  // { kind: 'folder'|'pair', path, name, basename }

function openDeleteModal(kind, path, name) {
  if (kind === 'folder') {
    // A mappa tartalmát a jelenlegi listázásból tudjuk kikövetkeztetni,
    // egyszerűbb egy külön query-vel: kérjük le a stats-ot
    deleteContext = { kind: 'folder', path, name };
    delMessage.innerHTML = `Törölni szeretnéd a <code>${esc(path)}</code> mappát <strong>rekurzívan</strong>?`;
    delDetails.textContent = 'Betöltés…';
    // A mappa aggregátumát külön API-hívás nélkül nem tudjuk; a stats-ot a listánk tartalmazza. Egyszerűsítés:
    // az aktuális folder-listázásból megpróbáljuk kiszedni ezt az almappát.
    const info = findSubfolderInCurrent(path);
    if (info && info.stats) {
      const total = info.stats.total || 0;
      const parts = Object.entries(info.stats.counts || {}).map(([s, n]) => `${n} ${s}`);
      delDetails.textContent = total > 0
        ? `${total} pár (${parts.join(', ')}) + almappák`
        : 'Üres mappa vagy csak almappák.';
    } else {
      delDetails.textContent = 'Tartalmi információ nem elérhető — a mappa és összes tartalma törlődik.';
    }
  } else {
    deleteContext = { kind: 'pair', path, basename: name };
    delMessage.innerHTML = `Törölni szeretnéd a <code>${esc(name)}</code> pár összes fájlját?`;
    delDetails.textContent = 'Kép + összes annotáció + státusz sidecar mind törlődik.';
  }
  delBackdrop.hidden = false;
}

function findSubfolderInCurrent(path) {
  // A DOM-ból nem tudjuk kinyerni könnyen a stats-ot; a legutóbb kapott folderData-t tároljuk.
  if (!lastFolderData || !lastFolderData.subfolders) return null;
  return lastFolderData.subfolders.find(f => f.path === path) || null;
}

delSubmit.addEventListener('click', async () => {
  if (!deleteContext) return;
  const c = deleteContext;
  delSubmit.disabled = true;
  const prev = delSubmit.textContent;
  delSubmit.textContent = 'Törlés…';
  try {
    let res;
    if (c.kind === 'folder') {
      const q = new URLSearchParams({ path: c.path });
      res = await fetch(api(`/api/project-folder?${q}`), { method: 'DELETE' });
    } else {
      const q = new URLSearchParams({ path: c.path, basename: c.basename });
      res = await fetch(api(`/api/project-file?${q}`), { method: 'DELETE' });
    }
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch(_) {}
      throw new Error(msg);
    }
    closeModal('delete');
    showToast('ok', c.kind === 'folder'
      ? `Mappa törölve: ${c.path}`
      : `Pár törölve: ${c.basename}`);
    await loadFolder(currentPath());
  } catch (err) {
    showToast('err', `Törlési hiba: ${err.message}`);
  } finally {
    delSubmit.disabled = false;
    delSubmit.textContent = prev;
    deleteContext = null;
  }
});

// ─── Közös modal-close (× / Mégse / backdrop / Escape) ─────────
function closeModal(which) {
  document.getElementById(`${which}-backdrop`).hidden = true;
}
document.addEventListener('click', ev => {
  const close = ev.target.closest('[data-close]');
  if (close) closeModal(close.dataset.close);
  // Backdrop kattintás
  const backdrop = ev.target.classList?.contains('export-modal-backdrop') ? ev.target : null;
  if (backdrop && !backdrop.hidden) backdrop.hidden = true;
});
document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape') {
    ['newfolder', 'upload', 'delete'].forEach(w => closeModal(w));
    closeNewMenu();
  }
});

// ─── Indítás ───────────────────────────────────────────────────
setupLoginStatus().then(() => loadFolder(currentPath()));
ensureStatusValues();

// A projektek listáját 20 mp-enként frissítsük — így a presence "élőnek" tűnik.
// Csak akkor futtatjuk, ha a tab aktív (nem pazaroljuk a hálózatot háttérben).
setInterval(() => {
  if (document.visibilityState === 'visible') loadFolder(currentPath());
}, 20000);
