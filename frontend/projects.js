// ─── Projektek böngésző ─────────────────────────────────────────

const contentEl    = document.getElementById('content');
const breadcrumbEl = document.getElementById('breadcrumb');
const loginStatus  = document.getElementById('login-status');

// Státusz-lista cache (a backend adja a /api/status-values-en)
let statusValues = null;

// A location.pathname-ból kivágjuk a /projects prefixet → user_path
function currentPath() {
  const p = window.location.pathname.replace(/^\/projects\/?/, '').replace(/\/+$/, '');
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

// Login state widget
function setupLoginStatus() {
  fetch('/api/session').then(r => r.json()).then(info => {
    if (info.authenticated) {
      const name = info.display_name || info.username;
      const adminTag = info.is_admin ? ' <span title="admin" style="color:#f0d060;">★</span>' : '';
      loginStatus.innerHTML = `Belépve mint <strong style="color:#d8d8e0;">${esc(name)}</strong>${adminTag} · <a href="#" class="btn-link-plain" id="logout-link">Kilépés</a>`;
      document.getElementById('logout-link').addEventListener('click', async ev => {
        ev.preventDefault();
        await fetch('/logout', { method: 'POST' });
        window.location.href = '/';
      });
    } else {
      loginStatus.innerHTML = '<a href="/login" class="btn-link-plain">Belépés</a>';
    }
  }).catch(() => {});
}

function renderBreadcrumb(crumbs) {
  const parts = crumbs.map((c, i) => {
    const isLast = i === crumbs.length - 1;
    if (isLast) return `<span class="current">${esc(c.name)}</span>`;
    const href = c.path ? `/projects/${c.path}` : '/projects';
    return `<a href="${href}" data-crumb="${esc(c.path)}">${esc(c.name)}</a>`;
  });
  breadcrumbEl.innerHTML = parts.join('<span class="sep">›</span>');
}

function renderSubfolders(subfolders) {
  if (!subfolders.length) return '';
  const items = subfolders.map(f => `
    <a class="item" href="/projects/${esc(f.path)}" data-navigate="${esc(f.path)}">
      <span class="icon">📁</span>
      <div class="meta">
        <div class="name">${esc(f.name)}</div>
      </div>
      <span class="modified">${fmtDate(f.modified)}</span>
    </a>
  `).join('');
  return `
    <div class="section-title">Almappák (${subfolders.length})</div>
    <div class="item-list">${items}</div>
  `;
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
    const href = `/projects/edit?${q}`;
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
    const res = await fetch(`/api/project-status?${q}`, {
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

// Kliens-oldali event delegáció: badge kattintás vs. sor kattintás
document.addEventListener('click', ev => {
  const badge = ev.target.closest('.status-badge');
  if (badge) {
    ev.preventDefault();
    ev.stopPropagation();
    openStatusMenu(badge);
    return;
  }
  const item = ev.target.closest('.item[data-href]');
  if (item && !ev.target.closest('.status-menu')) {
    window.location.href = item.dataset.href;
    return;
  }
  // Bárhova máshova kattintva a menük becsukódnak
  if (!ev.target.closest('.status-menu')) closeAllStatusMenus();
});
document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape') closeAllStatusMenus();
});

async function ensureStatusValues() {
  if (statusValues) return;
  try {
    const res = await fetch('/api/status-values');
    if (res.ok) statusValues = await res.json();
  } catch (_) { /* offline / nincs backend — legfeljebb nem nyílik a menu */ }
}

async function loadFolder(path) {
  contentEl.innerHTML = '<div class="state-msg">Betöltés…</div>';
  const url = path ? `/api/projects/${path}` : '/api/projects';
  try {
    const res = await fetch(url);
    if (res.status === 401) {
      // Nem vagyunk beléptetve — redirect a login oldalra
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
      return;
    }
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch (_) {}
      throw new Error(msg);
    }
    const body = await res.json();
    renderBreadcrumb(body.breadcrumb);
    const html = renderSubfolders(body.subfolders) + renderPairs(body.pairs, body.path);
    contentEl.innerHTML = html || '<div class="state-msg">Üres mappa.</div>';
  } catch (err) {
    contentEl.innerHTML = `<div class="state-msg error">Hiba: ${esc(err.message)}</div>`;
  }
}

setupLoginStatus();
ensureStatusValues();
loadFolder(currentPath());

// A projektek listáját 20 mp-enként frissítsük — így a presence "élőnek" tűnik.
// Csak akkor futtatjuk, ha a tab aktív (nem pazaroljuk a hálózatot háttérben).
setInterval(() => {
  if (document.visibilityState === 'visible') loadFolder(currentPath());
}, 20000);
