/* Временная проверка логики лайтбокса (в git не коммитится, удаляется после прогона).
   Запуск: node _lightbox_test.js   — из корня репозитория. */
const fs = require('fs');
const vm = require('vm');

function makeEl(id) {
  return {
    id, hidden: false, style: {}, attrs: {}, handlers: {},
    setAttribute(k, v) { this.attrs[k] = String(v); },
    removeAttribute(k) { delete this.attrs[k]; },
    addEventListener(t, fn) { (this.handlers[t] = this.handlers[t] || []).push(fn); },
  };
}

const box = makeEl('lightbox');
const img = makeEl('lightbox-img');
box.hidden = true;                                  // как в index.html: <div ... hidden>

const picture = makeEl('shot');
picture.src = 'assets/screenshot-1.png';
picture.alt = 'Главное окно';

const docHandlers = {};
const document = {
  getElementById: (id) => ({ lightbox: box, 'lightbox-img': img }[id] || null),
  querySelectorAll: (sel) => (String(sel).includes('shots img') ? [picture] : []),
  addEventListener: (t, fn) => { (docHandlers[t] = docHandlers[t] || []).push(fn); },
  documentElement: { setAttribute() {} },
  body: { style: {} },
};

const context = {
  document,
  window: { matchMedia: () => ({ matches: false }) },
  localStorage: { getItem: () => null, setItem: () => {} },
  console,
  fetch: () => Promise.reject(new Error('нет сети — это нормально для теста')),
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('docs/js/app.js', 'utf8'), context);

const fire = (t, ev) => (docHandlers[t] || []).forEach(fn => fn(ev || {}));
const click = (el) => (el.handlers.click || []).forEach(fn => fn({}));

fire('DOMContentLoaded');

const results = [];
const check = (name, ok) => results.push((ok ? ' OK   ' : ' FAIL ') + name);

/* 1. после загрузки лайтбокс закрыт — страница не перекрыта */
check('после загрузки box.hidden = true', box.hidden === true);
check('после загрузки inline display = none', box.style.display === 'none');
check('после загрузки aria-hidden = true', box.attrs['aria-hidden'] === 'true');
check('после загрузки у картинки нет src', !img.src);

/* 2. клик по скриншоту открывает лайтбокс */
click(picture);
check('после клика по скриншоту box.hidden = false', box.hidden === false);
check('после клика по скриншоту inline display = flex', box.style.display === 'flex');
check('после клика подставлен src картинки', img.src === picture.src);
check('после клика aria-hidden = false', box.attrs['aria-hidden'] === 'false');
check('после клика страница не прокручивается (overflow = hidden)',
      document.body.style.overflow === 'hidden');

/* 3. клик по оверлею закрывает */
click(box);
check('после клика по фону box.hidden = true', box.hidden === true);
check('после клика по фону inline display = none', box.style.display === 'none');
check('после закрытия alt очищен', img.alt === '');
check('после закрытия прокрутка вернулась', document.body.style.overflow === '');

/* 4. Escape закрывает (и не падает, когда уже закрыто) */
click(picture);
fire('keydown', { key: 'Escape' });
check('Escape закрывает лайтбокс', box.hidden === true && box.style.display === 'none');
fire('keydown', { key: 'Escape' });
check('повторный Escape не ломает состояние', box.hidden === true);

console.log(results.join('\n'));
const failed = results.filter(r => r.startsWith(' FAIL')).length;
console.log(failed ? `\nПРОВАЛЕНО: ${failed}` : '\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ');
process.exit(failed ? 1 : 0);
