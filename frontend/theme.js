/*
  HTR-ground téma-kezelés.

  Prioritás:
    1. localStorage (`htrground-theme`)      — kézi választás
    2. <meta name="default-theme">           — szerver-oldali config default
    3. "dark"                                — végső fallback

  A body-render ELŐTT alkalmazza a témát (data-theme attribútum a <html>-en),
  hogy ne legyen villogás első betöltéskor.

  A `#theme-toggle` gomb megjelenítése/felirata automatikus.
*/
(function() {
  const STORAGE_KEY = 'htrground-theme';

  function serverDefault() {
    const m = document.querySelector('meta[name="default-theme"]');
    const v = m ? m.getAttribute('content') : null;
    return v === 'light' ? 'light' : 'dark';
  }

  function loadTheme() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
    return serverDefault();
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    const btn = document.getElementById('theme-toggle');
    if (btn) {
      // Ikonok: a gomb annak a témának a jelét mutatja, amire vált (destination).
      // Ez a webes konvenció (Wikipedia, GitHub, stb.).
      // A `🌞` (sun with face) az egyszerű `☀`-nál jobban rendereldő emoji,
      // színes és a `🌙`-hoz hasonló méretű minden rendszeren.
      btn.textContent = theme === 'light' ? '🌙' : '🌞';
      btn.title = theme === 'light'
        ? 'Váltás sötét témára'
        : 'Váltás világos témára';
    }
  }

  function toggle() {
    const current = document.documentElement.getAttribute('data-theme') || loadTheme();
    const next = current === 'light' ? 'dark' : 'light';
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
  }

  // Alkalmazás azonnal — mielőtt a body megjelenne
  applyTheme(loadTheme());

  // Gomb bekötése DOM-ready után
  const setup = () => {
    const btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.addEventListener('click', toggle);
      // Frissítjük a feliratot, mert az applyTheme(loadTheme()) még a gomb létezése előtt futott
      applyTheme(document.documentElement.getAttribute('data-theme') || loadTheme());
    }
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setup);
  } else {
    setup();
  }
})();
