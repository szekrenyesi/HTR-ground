// ─── Projektek böngésző ─────────────────────────────────────────

const contentEl    = document.getElementById('content');
const breadcrumbEl = document.getElementById('breadcrumb');
const loginStatus  = document.getElementById('login-status');

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
      loginStatus.innerHTML = 'Be van lépve · <a href="#" class="btn-link-plain" id="logout-link">Kilépés</a>';
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

    // Editor megnyitása a szerver-fájllal
    const q = new URLSearchParams({ path: folderPath || '', basename: pair.basename });
    const href = `/projects/edit?${q}`;
    return `
      <a class="item" href="${href}">
        <span class="icon">${icon}</span>
        <div class="meta">
          <div class="name">${esc(pair.basename)}</div>
          <div class="sub">${subParts.join('')}</div>
        </div>
        <span class="modified">${fmtDate(pair.modified)}</span>
      </a>
    `;
  }).join('');
  return `
    <div class="section-title">Fájlok (${pairs.length})</div>
    <div class="item-list">${items}</div>
  `;
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
loadFolder(currentPath());
