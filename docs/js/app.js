/* Simple Craft Launcher — логика сайта.
   Никаких библиотек: чистый JS.

   1) Кнопка «Скачать» сама берёт самый свежий релиз с GitHub API —
      после новых релизов править сайт не нужно.
   2) Переключатель тёмной/светлой темы (запоминается в localStorage).
   3) Мобильное меню, лайтбокс для скриншотов, появление блоков при прокрутке.
*/

const REPO = 'artemiy207/Simple-Craft-Launcher';
const RELEASES_PAGE = `https://github.com/${REPO}/releases`;

/* ── 1. Последний релиз: ссылка, размер и версия ─────────────── */
async function loadLatestRelease() {
  const btn      = document.getElementById('download');
  const sizeLbl  = document.getElementById('dl-size');
  const verLbl   = document.getElementById('dl-version');
  const aboutVer = document.getElementById('about-version');

  try {
    const res = await fetch(`https://api.github.com/repos/${REPO}/releases/latest`, {
      headers: { 'Accept': 'application/vnd.github+json' }
    });
    if (!res.ok) throw new Error('no release');
    const data = await res.json();

    const exe = (data.assets || []).find(a => a.name.toLowerCase().endsWith('.exe'));
    const zip = (data.assets || []).find(a => a.name.toLowerCase().endsWith('.zip'));
    const asset = exe || zip;

    if (asset && btn) btn.href = asset.browser_download_url;
    if (asset && sizeLbl) {
      sizeLbl.textContent = '≈ ' + (asset.size / 1048576).toFixed(1) + ' МБ';
    }
    const version = (data.tag_name || data.name || '').replace(/^v/i, '');
    if (version) {
      if (verLbl)   verLbl.textContent = version;
      if (aboutVer) aboutVer.textContent = version;
    }
  } catch (e) {
    // Нет интернета, лимит API или релиза ещё нет — оставляем ссылку на страницу релизов
    if (btn) btn.href = RELEASES_PAGE;
  }
}

/* ── 2. Тема: тёмная / светлая ───────────────────────────────── */
function initTheme() {
  const root  = document.documentElement;
  const btn   = document.getElementById('theme');
  const saved = localStorage.getItem('scl-theme');
  const system = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';

  const apply = (theme) => {
    root.setAttribute('data-theme', theme);
    if (btn) btn.textContent = theme === 'light' ? '☀️' : '🌙';
  };

  apply(saved || system);

  if (btn) {
    btn.addEventListener('click', () => {
      const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      localStorage.setItem('scl-theme', next);
      apply(next);
    });
  }
}

/* ── 3. Мобильное меню ───────────────────────────────────────── */
function initMenu() {
  const burger = document.getElementById('burger');
  const nav    = document.getElementById('nav');
  if (!burger || !nav) return;

  burger.addEventListener('click', () => nav.classList.toggle('open'));
  nav.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => nav.classList.remove('open'));
  });
}

/* ── 4. Лайтбокс для скриншотов ──────────────────────────────── */
function initLightbox() {
  const box = document.getElementById('lightbox');
  const img = document.getElementById('lightbox-img');
  if (!box || !img) return;

  // Страховка: пока не открыли — лайтбокс закрыт. Гасим тремя способами сразу
  // (атрибут hidden + inline display + aria), чтобы он не перекрыл страницу,
  // даже если внешний style.css пришёл из старого кэша.
  box.hidden = true;
  box.style.display = 'none';
  box.setAttribute('aria-hidden', 'true');

  const open = (src, alt) => {
    img.src = src;
    img.alt = alt || 'Скриншот';
    box.hidden = false;
    box.style.display = 'flex';
    box.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  };
  const close = () => {
    box.hidden = true;
    box.style.display = 'none';
    box.setAttribute('aria-hidden', 'true');
    img.removeAttribute('src');   // пустая картинка не должна тянуть запрос и рисовать alt
    img.alt = '';
    document.body.style.overflow = '';
  };

  document.querySelectorAll('.shots img, .hero-shot img').forEach(picture => {
    picture.addEventListener('click', () => open(picture.src, picture.alt));
  });
  box.addEventListener('click', close);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !box.hidden) close();
  });
}

/* ── 5. Появление блоков при прокрутке ───────────────────────── */
function initReveal() {
  const items = document.querySelectorAll('.reveal');
  if (!('IntersectionObserver' in window)) {
    items.forEach(el => el.classList.add('on'));
    return;
  }
  const watcher = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('on');
        watcher.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });

  items.forEach((el, index) => {
    el.style.transitionDelay = Math.min(index % 6, 5) * 60 + 'ms';
    watcher.observe(el);
  });
}

/* ── запуск ──────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initMenu();
  initLightbox();
  initReveal();
  loadLatestRelease();

  const year = document.getElementById('year');
  if (year) year.textContent = new Date().getFullYear();
});
