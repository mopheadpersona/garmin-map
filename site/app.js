// Конфигуратор цветов карты. Данные готовит scripts/make_site.py:
//   data/palette.json — имена, цвета по умолчанию и легенда;
//   data/scenes.json  — перекрашиваемые кадры;
//   data/typ.json     — где в файле карты лежит каждый цвет;
//   data/maps.json    — карты на выгрузку;
//   data/presets.json — готовые наборы цветов (правится руками).
// Тексты интерфейса — в i18n.js; названия из данных приходят сразу на всех языках.

import { LANGUAGES, STRINGS } from './i18n.js';

const $ = (selector) => document.querySelector(selector);

// Вид образца в легенде: [вид, парный цвет]. Парный нужен, чтобы показать заливку вместе с обводкой.
const SAMPLE = {
  GREEN: ['road', 'GREEN_EDGE'], GREEN_EDGE: ['casing', 'GREEN'],
  PRIMARY: ['road', 'PRIMARY_EDGE'], PRIMARY_EDGE: ['casing', 'PRIMARY'],
  SECONDARY: ['road', 'SECONDARY_EDGE'], SECONDARY_EDGE: ['casing', 'SECONDARY'],
  WHITE: ['road', 'WHITE_EDGE'], WHITE_EDGE: ['casing', 'WHITE'],
  PEDESTRIAN: ['road', 'PEDESTRIAN_EDGE'], PEDESTRIAN_EDGE: ['casing', 'PEDESTRIAN'],
  NO_ENTRY: ['dots', 'WHITE'], RAIL: ['rail', 'WHITE'],
  GRAVEL: ['road', 'GRAVEL_EDGE'], GRAVEL_EDGE: ['casing', 'GRAVEL'],
  BAD_TRACK: ['longdash'], PATH: ['dash'], HARD_PATH: ['dash'],
  CYCLE: ['line'], MTB: ['dotline'],
  PLANTATION_MARK: ['marks', 'PLANTATION'], CEMETERY_CROSS: ['marks', 'CEMETERY'],
  CLOSED_HATCH: ['hatch'], WETLAND: ['wet'],
  FERRY: ['dash'], BORDER: ['longdash'], LABEL: ['text'],
};
const SUB_KINDS = new Set(['casing', 'marks']);
const STORAGE_KEY = 'garmin-map-palette-v1';
const LANGUAGE_KEY = 'garmin-map-language-v1';
const HISTORY_KEY = 'garmin-map-history-v1';
const HISTORY_LIMIT = 50;
const MERGE_MS = 600;
const SETS_KEY = 'garmin-map-sets-v1';
const LINK_KEY = 'garmin-map-link-v1';            // цвета из последней открытой ссылки
const SETS_LIMIT = 100;
const NAME_LIMIT = 40;
const OWN_PREFIX = 'own:';                        // значение пункта списка для своего набора
const LINK_PARAM = 'c';
const DEFAULT_LANGUAGE = LANGUAGES[0][0];

const state = {
  names: [], defaults: {}, legend: [], presets: [],
  palette: {},
  sets: [], lastSet: '', form: null,
  history: { base: {}, steps: [], pos: 0, pending: null },
  groups: [], frames: [], frame: null, engine: null, engines: new Map(),
  showDefaults: false,
  typ: null, maps: [], mapBlobs: new Map(),
  language: DEFAULT_LANGUAGE,
};

// ---------------------------------------------------------------- язык и сообщения

// Ошибка с ключом текста: переводится в момент показа, а не в момент броска.
const fail = (key, params) => Object.assign(new Error(key), { key, params });
const explain = (error) => (error.key ? t(error.key, error.params) : error.message);

function t(key, params = {}) {
  const text = STRINGS[state.language][key] ?? STRINGS[DEFAULT_LANGUAGE][key] ?? key;
  return text.replace(/\{(\w+)\}/g, (whole, name) => {
    const value = params[name];
    if (value === undefined) return whole;
    return value instanceof Error ? explain(value) : String(value);
  });
}

// Название из данных: строка или объект {en, cs}.
const pick = (value) => (value && typeof value === 'object'
  ? value[state.language] ?? value[DEFAULT_LANGUAGE] ?? Object.values(value)[0] ?? ''
  : value ?? '');

// Сообщения запоминаются ключом, чтобы при смене языка показать их заново.
const messages = new Map();

function say(element, key, params, isError = false) {
  messages.set(element, key ? { key, params, isError } : null);
  element.textContent = key ? t(key, params) : '';
  element.classList.toggle('error', Boolean(key && isError));
}

function initialLanguage() {
  const known = (code) => LANGUAGES.some(([id]) => id === code);
  const fromUrl = new URLSearchParams(location.search).get('lang');
  if (known(fromUrl)) return fromUrl;
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    if (known(saved)) return saved;
  } catch (error) { /* не страшно */ }
  return DEFAULT_LANGUAGE;
}

function applyStaticTexts() {
  document.documentElement.lang = state.language;
  document.title = t('pageTitle');
  for (const node of document.querySelectorAll('[data-i18n]')) node.textContent = t(node.dataset.i18n);
  for (const node of document.querySelectorAll('[data-i18n-label]')) node.setAttribute('aria-label', t(node.dataset.i18nLabel));
  for (const node of document.querySelectorAll('[data-i18n-title]')) node.title = t(node.dataset.i18nTitle);
  for (const button of document.querySelectorAll('#languages button')) {
    button.setAttribute('aria-pressed', String(button.lang === state.language));
  }
  for (const [element, message] of messages) {
    if (message) element.textContent = t(message.key, message.params);
  }
}

function buildLanguages() {
  const root = $('#languages');
  root.textContent = '';
  for (const [code, title] of LANGUAGES) {
    const button = document.createElement('button');
    button.type = 'button';
    button.lang = code;
    button.textContent = title;
    button.addEventListener('click', () => setLanguage(code));
    root.append(button);
  }
}

function setLanguage(code) {
  if (code === state.language) return;
  state.language = code;
  try { localStorage.setItem(LANGUAGE_KEY, code); } catch (error) { /* не страшно */ }
  const url = new URL(location.href);
  if (url.searchParams.has('lang')) {            // иначе после обновления страницы вернётся язык из ссылки
    url.searchParams.set('lang', code);
    history.replaceState(null, '', url);
  }
  applyStaticTexts();
  if (!state.names.length) return;               // данные ещё не загружены
  buildPresets();
  buildLegend();
  refreshLegend();
  renderHistory();
  buildRegions();
  renderCompare();
  if (state.frames.length) {
    buildScenes();
    if (state.frame) { markFrameControls(); renderScale(); }
  }
}

// ---------------------------------------------------------------- цвета

const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));

// Принимает #RRGGBB, RRGGBB, #RGB и запись «rgb(247, 206, 132)» или «247, 206, 132».
function parseColour(text) {
  const value = text.trim();
  let match = value.match(/^#?([0-9a-f]{6})$/i);
  if (match) return '#' + match[1].toUpperCase();
  match = value.match(/^#?([0-9a-f])([0-9a-f])([0-9a-f])$/i);
  if (match) return ('#' + match[1] + match[1] + match[2] + match[2] + match[3] + match[3]).toUpperCase();
  match = value.match(/^(?:rgb\s*\()?\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})\s*\)?$/i);
  if (match && match.slice(1).every((n) => Number(n) <= 255)) {
    return '#' + match.slice(1).map((n) => Number(n).toString(16).padStart(2, '0')).join('').toUpperCase();
  }
  return null;
}

async function getJSON(url) {
  const response = await fetch(url, { cache: 'no-cache' });
  if (!response.ok) throw fail('fileFailed', { url, status: response.status });
  return response.json();
}

// ---------------------------------------------------------------- перекраска кадра
//
// Пиксель = base + сумма по цветам палитры (вес цвета в этом пикселе × цвет).
// Веса берутся из кадров, где три цвета палитры включены по одному на канал.

async function loadPixels(url) {
  const response = await fetch(url, { cache: 'no-cache' });
  if (!response.ok) throw fail('fileFailed', { url, status: response.status });
  const bitmap = await createImageBitmap(await response.blob(), { colorSpaceConversion: 'none' });
  const canvas = typeof OffscreenCanvas === 'undefined'
    ? Object.assign(document.createElement('canvas'), { width: bitmap.width, height: bitmap.height })
    : new OffscreenCanvas(bitmap.width, bitmap.height);
  const context = canvas.getContext('2d', { willReadFrequently: true });
  context.drawImage(bitmap, 0, 0);
  if (bitmap.close) bitmap.close();
  return context.getImageData(0, 0, canvas.width, canvas.height);
}

async function buildEngine(frame) {
  const base = await loadPixels(`${frame.dir}/base.png`);
  const count = base.width * base.height;
  const basePixels = base.data;
  const layers = {};
  const images = await Promise.all(state.groups.map((group) => loadPixels(`${frame.dir}/${group.file}.png`)));
  state.groups.forEach((group, g) => {
    const pixels = images[g].data;
    const sizes = [0, 0, 0];
    for (let p = 0, o = 0; p < count; p++, o += 4) {
      if (pixels[o] > basePixels[o]) sizes[0]++;
      if (pixels[o + 1] > basePixels[o + 1]) sizes[1]++;
      if (pixels[o + 2] > basePixels[o + 2]) sizes[2]++;
    }
    group.names.forEach((name, k) => {
      const index = new Uint32Array(sizes[k]);
      const weight = new Uint8Array(sizes[k]);
      for (let p = 0, o = k, n = 0; p < count; p++, o += 4) {
        const w = pixels[o] - basePixels[o];
        if (w > 0) { index[n] = p; weight[n++] = w; }
      }
      layers[name] = { index, weight };
    });
    images[g] = null;
  });
  const out = new ImageData(base.width, base.height);
  out.data.fill(255);
  return { frame, count, base: basePixels, layers, sum: new Int32Array(count * 3), out, shown: null };
}

function renderFull(engine, palette) {
  const { count, base, sum, layers, out } = engine;
  for (let p = 0, o = 0, j = 0; p < count; p++, o += 4, j += 3) {
    sum[j] = base[o] * 255; sum[j + 1] = base[o + 1] * 255; sum[j + 2] = base[o + 2] * 255;
  }
  for (const name of state.names) {
    const layer = layers[name];
    if (!layer) continue;
    const [r, g, b] = hexToRgb(palette[name]);
    const { index, weight } = layer;
    for (let n = 0; n < index.length; n++) {
      const j = index[n] * 3, w = weight[n];
      sum[j] += w * r; sum[j + 1] += w * g; sum[j + 2] += w * b;
    }
  }
  const data = out.data;
  for (let p = 0, o = 0, j = 0; p < count; p++, o += 4, j += 3) {
    data[o] = sum[j] / 255; data[o + 1] = sum[j + 1] / 255; data[o + 2] = sum[j + 2] / 255;
  }
  engine.shown = { ...palette };
}

// Изменился один цвет: пересчитываются только пиксели, где он есть.
function renderOne(engine, name, hex) {
  const layer = engine.layers[name];
  const before = hexToRgb(engine.shown[name]);
  const after = hexToRgb(hex);
  engine.shown[name] = hex;
  if (!layer) return;
  const dr = after[0] - before[0], dg = after[1] - before[1], db = after[2] - before[2];
  const { index, weight } = layer;
  const { sum } = engine;
  const data = engine.out.data;
  for (let n = 0; n < index.length; n++) {
    const p = index[n], j = p * 3, o = p * 4, w = weight[n];
    sum[j] += w * dr; sum[j + 1] += w * dg; sum[j + 2] += w * db;
    data[o] = sum[j] / 255; data[o + 1] = sum[j + 1] / 255; data[o + 2] = sum[j + 2] / 255;
  }
}

function paint() {
  const canvas = $('#view');
  const { out } = state.engine;
  if (canvas.width !== out.width || canvas.height !== out.height) {
    canvas.width = out.width; canvas.height = out.height;
  }
  canvas.getContext('2d').putImageData(out, 0, 0);
}

const visiblePalette = () => (state.showDefaults ? state.defaults : state.palette);

async function showFrame(frame) {
  state.frame = frame;
  const status = $('#frame-status');
  say(status, 'frameLoading');
  status.hidden = false;
  markFrameControls();
  try {
    const key = frame.dir;
    let engine = state.engines.get(key);
    if (!engine) {
      engine = await buildEngine(frame);
      state.engines.set(key, engine);
      // Кадр занимает десятки мегабайт памяти: держим три последних.
      while (state.engines.size > 3) state.engines.delete(state.engines.keys().next().value);
    }
    if (state.frame !== frame) return;          // пока грузился, выбрали другой кадр
    state.engine = engine;
    renderFull(engine, visiblePalette());
    paint();
    renderScale();
    $('#scale').hidden = false;
    status.hidden = true;
  } catch (error) {
    say(status, 'frameFailed', { error });
  }
}

const distance = (metres) => (metres >= 1000
  ? t('kilometres', { value: metres / 1000 }) : t('metres', { value: metres }));

function renderScale() {
  const frame = state.frame;
  const bar = frame.scaleMetres / (frame.metresPerPx * frame.density);
  $('#scale-bar').style.width = `${bar / 4.8}cqw`;
  $('#scale-label').textContent = distance(frame.scaleMetres);
}

// ---------------------------------------------------------------- палитра и легенда

function saveLocal() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state.palette)); } catch (error) { /* не страшно */ }
}

function loadLocal() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    if (!saved) return null;
    const palette = { ...state.defaults };
    for (const name of state.names) {
      const colour = typeof saved[name] === 'string' && parseColour(saved[name]);
      if (colour) palette[name] = colour;
    }
    return palette;
  } catch (error) {
    return null;
  }
}

const samePalette = (a, b) => state.names.every((name) => a[name] === b[name]);

function refreshLegend() {
  document.documentElement.style.setProperty('--map-bg', state.palette.BG);
  for (const row of document.querySelectorAll('.row')) {
    const name = row.dataset.name;
    const pair = (SAMPLE[name] || [])[1];
    row.style.setProperty('--c', state.palette[name]);
    if (pair) row.style.setProperty('--pair', state.palette[pair]);
    row.classList.toggle('changed', state.palette[name] !== state.defaults[name]);
    const hex = row.querySelector('.hex');
    if (document.activeElement !== hex) { hex.value = state.palette[name]; hex.classList.remove('invalid'); }
    row.querySelector('input[type="color"]').value = state.palette[name].toLowerCase();
  }
  renderSetTools();
}

function leaveDefaultsView() {
  if (!state.showDefaults) return false;
  state.showDefaults = false;
  renderCompare();
  return true;
}

function renderCompare() {
  const button = $('#compare');
  button.setAttribute('aria-pressed', String(state.showDefaults));
  button.textContent = t(state.showDefaults ? 'compareOn' : 'compareOff');
}

// Меняет один цвет на экране и в сохранённой палитре. История об этом ещё не знает.
function applyColour(name, hex) {
  if (state.palette[name] === hex) return false;
  state.palette[name] = hex;
  const wasDefaults = leaveDefaultsView();
  if (state.engine) {
    if (wasDefaults) renderFull(state.engine, state.palette);
    else renderOne(state.engine, name, hex);
    paint();
  }
  refreshLegend();
  saveLocal();
  return true;
}

function applyPalette(palette) {
  state.palette = { ...palette };
  leaveDefaultsView();
  if (state.engine) { renderFull(state.engine, state.palette); paint(); }
  refreshLegend();
  saveLocal();
}

// Цвет из палитры браузера меняется на лету; шагом истории он становится, когда выбор закончен.
function previewColour(name, hex) {
  if (state.history.pending && state.history.pending !== name) settle();
  if (applyColour(name, hex)) state.history.pending = name;
}

function setColour(name, hex) {
  settle();
  if (applyColour(name, hex)) record('colour');
}

function setPalette(palette, kind, ref) {
  settle();
  applyPalette(palette);
  record(kind, ref);
}

// ---------------------------------------------------------------- история правок
//
// Шаг — палитра после правки; base — палитра до первого шага; pos — сколько шагов применено.
// Что именно изменилось в шаге, видно из сравнения с предыдущей палитрой и отдельно не хранится.

const paletteAt = (pos) => (pos > 0 ? state.history.steps[pos - 1].palette : state.history.base);
const changedNames = (before, after) => state.names.filter((name) => before[name] !== after[name]);

// Записывает шагом всё, чем палитра отличается от текущего шага. Виды шага: picker (палитра браузера),
// colour (код цвета, возврат исходного), preset (готовый набор, ref — его id), set (свой набор, ref — его имя),
// file (набор из файла), link (набор из ссылки).
function record(kind, ref) {
  const history = state.history;
  history.pending = null;
  const changed = changedNames(paletteAt(history.pos), state.palette);
  if (!changed.length) return;
  const now = Date.now();
  const last = history.steps[history.pos - 1];
  // Часть браузеров шлёт change на каждое движение в палитре: быстрые правки одного цвета — один шаг.
  const merge = kind === 'picker' && last && last.kind === 'picker' && now - last.at < MERGE_MS
    && history.pos === history.steps.length
    && changedNames(paletteAt(history.pos - 1), last.palette).join() === changed.join();
  if (merge) {
    last.palette = { ...state.palette };
    last.at = now;
    if (!changedNames(paletteAt(history.pos - 1), last.palette).length) { history.steps.pop(); history.pos--; }
  } else {
    history.steps.length = history.pos;          // правка после шагов назад отбрасывает отменённые шаги
    history.steps.push({ palette: { ...state.palette }, kind, ref, at: now });
    if (history.steps.length > HISTORY_LIMIT) history.base = history.steps.shift().palette;
    history.pos = history.steps.length;
  }
  renderHistory();
  saveHistory();
}

function settle() {
  if (state.history.pending) record('picker');
}

function goTo(pos) {
  const history = state.history;
  const target = Math.max(0, Math.min(pos, history.steps.length));
  if (target === history.pos) return;
  history.pos = target;
  applyPalette(paletteAt(target));
  renderHistory();
  saveHistory();
}

function stepHistory(delta) {
  settle();
  goTo(state.history.pos + delta);
}

// «Дорога I класса, обводка»: у вложенных строк легенды своё название ничего не говорит без парного.
function colourTitle(name) {
  const find = (wanted) => {
    for (const group of state.legend) {
      const item = group.items.find((entry) => entry.name === wanted);
      if (item) return pick(item.title);
    }
    return wanted;
  };
  const [kind, pair] = SAMPLE[name] || [];
  return SUB_KINDS.has(kind) && pair ? `${find(pair)}, ${find(name)}` : find(name);
}

function stepTitle(index) {
  const step = state.history.steps[index];
  if (step.kind === 'file') return t('historyFile');
  if (step.kind === 'link') return t('historyLink');
  if (step.kind === 'set' && step.ref) return `${t('presetLabel')}: ${step.ref}`;
  if (step.kind === 'preset') {
    const preset = state.presets.find((p) => p.id === step.ref);
    if (preset || step.ref === 'default') return `${t('presetLabel')}: ${preset ? pick(preset.title) : t('presetDefault')}`;
  }
  const changed = changedNames(paletteAt(index), step.palette);
  if (changed.length === 1) return `${colourTitle(changed[0])}: ${step.palette[changed[0]]}`;
  return t('historySeveral', { count: changed.length });
}

// Образец шага: один цвет или до четырёх полосок, взятых равномерно из изменённых цветов (обводки — в последнюю очередь).
function stepColours(index) {
  const step = state.history.steps[index];
  const changed = changedNames(paletteAt(index), step.palette);
  const main = changed.filter((name) => !SUB_KINDS.has((SAMPLE[name] || [])[0]));
  const names = main.length ? main : changed;
  const count = Math.min(4, names.length);
  return Array.from({ length: count }, (unused, i) => step.palette[names[Math.floor(i * names.length / count)]]);
}

function renderHistory() {
  const { steps, pos } = state.history;
  const mac = /Mac|iPhone|iPad/.test(navigator.platform);
  const back = $('#history-back');
  const forward = $('#history-forward');
  back.setAttribute('aria-disabled', String(pos === 0));
  forward.setAttribute('aria-disabled', String(pos === steps.length));
  back.title = `${t('historyBack')} (${mac ? '⌘Z' : 'Ctrl+Z'})`;
  forward.title = `${t('historyForward')} (${mac ? '⇧⌘Z' : 'Ctrl+Y'})`;

  const strip = $('#history-strip');
  while (strip.children.length > steps.length) strip.lastElementChild.remove();
  steps.forEach((step, index) => {
    let button = strip.children[index];
    if (!button) {
      button = document.createElement('button');
      button.type = 'button';
      button.className = 'swatch';
      strip.append(button);
    }
    const title = stepTitle(index);
    button.title = title;
    button.setAttribute('aria-label', title);
    button.classList.toggle('ahead', index >= pos);
    if (index === pos - 1) button.setAttribute('aria-current', 'step');
    else button.removeAttribute('aria-current');
    button.textContent = '';
    for (const colour of stepColours(index)) {
      const stripe = document.createElement('i');
      stripe.style.background = colour;
      button.append(stripe);
    }
  });

  // Новый шаг виден справа; если текущий шаг ушёл за край, лента подвигается к нему.
  const current = strip.children[pos - 1];
  if (!current || pos === steps.length) {
    strip.scrollLeft = current ? strip.scrollWidth : 0;
  } else {
    const margin = 12;
    const left = current.offsetLeft - margin;
    const right = current.offsetLeft + current.offsetWidth + margin;
    if (left < strip.scrollLeft) strip.scrollLeft = left;
    else if (right > strip.scrollLeft + strip.clientWidth) strip.scrollLeft = right - strip.clientWidth;
  }
}

// История живёт, пока открыта вкладка, и переживает обновление страницы.
function saveHistory() {
  const { base, steps, pos } = state.history;
  const list = (palette) => state.names.map((name) => palette[name]);
  try {
    sessionStorage.setItem(HISTORY_KEY, JSON.stringify({
      names: state.names,
      base: list(base),
      steps: steps.map((step) => ({ colours: list(step.palette), kind: step.kind, ref: step.ref })),
      pos,
    }));
  } catch (error) { /* не страшно */ }
}

function loadHistory() {
  const history = { base: { ...state.palette }, steps: [], pos: 0, pending: null };
  state.history = history;
  try {
    const saved = JSON.parse(sessionStorage.getItem(HISTORY_KEY) || 'null');
    if (!saved || !Array.isArray(saved.names) || saved.names.join() !== state.names.join()) return;
    const palette = (list) => Object.fromEntries(state.names.map((name, i) => {
      const colour = typeof list[i] === 'string' && parseColour(list[i]);
      if (!colour) throw new Error('colour');
      return [name, colour];
    }));
    const base = palette(saved.base);
    const steps = saved.steps.map((step) => ({
      palette: palette(step.colours),
      kind: ['picker', 'colour', 'preset', 'set', 'file', 'link'].includes(step.kind) ? step.kind : 'colour',
      ref: cleanName(step.ref) || undefined,
      at: 0,
    }));
    const { pos } = saved;
    if (steps.length > HISTORY_LIMIT || !Number.isInteger(pos) || pos < 0 || pos > steps.length) return;
    Object.assign(history, { base, steps, pos });
  } catch (error) {
    return;                                      // запись повреждена: история начинается заново
  }
  // Палитра могла измениться мимо истории (правка не успела стать шагом, другая вкладка): это ещё один шаг.
  record('colour');
}

function setupHistory() {
  $('#history-back').addEventListener('click', () => stepHistory(-1));
  $('#history-forward').addEventListener('click', () => stepHistory(1));
  const strip = $('#history-strip');
  strip.addEventListener('click', (event) => {
    const button = event.target.closest('.swatch');
    if (!button) return;
    settle();
    goTo([...strip.children].indexOf(button) + 1);
  });
  document.addEventListener('keydown', (event) => {
    if (!(event.metaKey || event.ctrlKey) || event.altKey) return;
    // В поле кода цвета работает обычная отмена ввода.
    if (event.target instanceof Element && event.target.closest('input[type="text"], textarea')) return;
    // Буква берётся с клавиши как она подписана (на чешской раскладке Z и Y поменяны местами),
    // а при нелатинской раскладке — по месту клавиши.
    const letter = /^[a-z]$/i.test(event.key) ? event.key.toLowerCase() : { KeyZ: 'z', KeyY: 'y' }[event.code];
    const back = letter === 'z' && !event.shiftKey;
    const forward = (letter === 'z' && event.shiftKey) || (letter === 'y' && event.ctrlKey && !event.metaKey && !event.shiftKey);
    if (!back && !forward) return;
    event.preventDefault();
    stepHistory(back ? -1 : 1);
  });
  window.addEventListener('pagehide', settle);
}

function buildLegend() {
  const root = $('#legend');
  root.textContent = '';
  for (const group of state.legend) {
    const section = document.createElement('div');
    section.className = 'group';
    const heading = document.createElement('h2');
    const groupTitle = pick(group.title);
    heading.textContent = groupTitle;
    section.append(heading);
    for (const item of group.items) {
      const [kind] = SAMPLE[item.name] || ['area'];
      const row = document.createElement('div');
      row.className = `row k-${kind}${SUB_KINDS.has(kind) ? ' sub' : ''}`;
      row.dataset.name = item.name;

      const well = document.createElement('span');
      well.className = 'well';
      const sample = document.createElement('span');
      sample.className = 'sample';
      const itemTitle = pick(item.title);
      if (kind === 'text') sample.textContent = 'Aa';
      const picker = document.createElement('input');
      picker.type = 'color';
      picker.setAttribute('aria-label', t('pickColour', { group: groupTitle, item: itemTitle }));
      picker.addEventListener('input', () => previewColour(item.name, picker.value.toUpperCase()));
      picker.addEventListener('change', () => { previewColour(item.name, picker.value.toUpperCase()); settle(); });
      well.append(sample, picker);

      const label = document.createElement('span');
      label.className = 'name';
      label.textContent = itemTitle;

      const hex = document.createElement('input');
      hex.className = 'hex';
      hex.type = 'text';
      hex.spellcheck = false;
      hex.setAttribute('aria-label', t('colourCode', { group: groupTitle, item: itemTitle }));
      const commit = () => {
        const colour = parseColour(hex.value);
        hex.classList.toggle('invalid', !colour);
        if (colour) { setColour(item.name, colour); hex.value = colour; }
      };
      hex.addEventListener('change', commit);
      hex.addEventListener('keydown', (event) => { if (event.key === 'Enter') { commit(); hex.blur(); } });
      hex.addEventListener('blur', () => { hex.value = state.palette[item.name]; hex.classList.remove('invalid'); });

      const undo = document.createElement('button');
      undo.type = 'button';
      undo.className = 'undo';
      undo.textContent = '↺';
      undo.title = t('restoreColour');
      undo.setAttribute('aria-label', t('restoreColourOf', { item: itemTitle }));
      undo.addEventListener('click', () => setColour(item.name, state.defaults[item.name]));

      row.append(well, label, hex, undo);
      section.append(row);
    }
    root.append(section);
  }
}

// Список наборов: исходный, готовые и группа своих. Пункт «свой, не сохранён» добавляет renderSetTools, когда он нужен.
function buildPresets() {
  const select = $('#preset');
  select.textContent = '';
  const add = (parent, value, title) => {
    const option = document.createElement('option');
    option.value = value; option.textContent = title;
    parent.append(option);
  };
  add(select, 'default', t('presetDefault'));
  for (const preset of state.presets) add(select, preset.id, pick(preset.title));
  if (!state.sets.length) return;
  const group = document.createElement('optgroup');
  group.label = t('ownSets');
  for (const set of state.sets) add(group, OWN_PREFIX + set.name, set.name);
  select.append(group);
}

function setupPresets() {
  const select = $('#preset');
  select.addEventListener('change', () => {
    const value = select.value;
    if (value === 'custom') return;
    say($('#palette-message'), null);
    if (value.startsWith(OWN_PREFIX)) {
      const set = state.sets.find((item) => item.name === value.slice(OWN_PREFIX.length));
      if (set) setPalette(set.palette, 'set', set.name);
      return;
    }
    const preset = state.presets.find((p) => p.id === value);
    state.lastSet = '';
    setPalette({ ...state.defaults, ...(preset ? preset.colors : {}) }, 'preset', preset ? preset.id : 'default');
  });
}

// ---------------------------------------------------------------- свои наборы и ссылка
//
// Свои наборы лежат в localStorage целыми палитрами. Ссылка несёт набор после «#», поэтому на сервер он не уходит:
// #c=ИМЯ-RRGGBB.ИМЯ-RRGGBB, только цвета, которые отличаются от исходных.
// Данные из хранилища и из ссылки чужие: берутся известные имена цветов и значения вида #RRGGBB, остальное отбрасывается.

function cleanName(value) {
  if (typeof value !== 'string') return '';
  const text = value.replace(/[\u0000-\u001F\u007F-\u009F]/g, ' ').replace(/\s+/g, ' ').trim();
  return [...text].slice(0, NAME_LIMIT).join('').trim();
}

function cleanPalette(colours) {
  if (!colours || typeof colours !== 'object') return null;
  const palette = { ...state.defaults };
  let used = 0;
  for (const name of state.names) {
    const value = colours[name];
    if (typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value)) { palette[name] = value.toUpperCase(); used++; }
  }
  return used ? palette : null;
}

function loadSets() {
  try {
    const saved = JSON.parse(localStorage.getItem(SETS_KEY) || 'null');
    if (!Array.isArray(saved)) return [];
    const sets = [];
    for (const item of saved) {
      if (sets.length >= SETS_LIMIT) break;
      const name = cleanName(item && item.name);
      const palette = cleanPalette(item && item.colors);
      if (name && palette && !sets.some((set) => set.name === name)) sets.push({ name, palette });
    }
    return sets;
  } catch (error) {
    return [];
  }
}

// Список меняется только вместе с записью в хранилище: набор, который не сохранился, в списке не появляется.
function storeSets(sets) {
  try {
    localStorage.setItem(SETS_KEY, JSON.stringify(sets.map((set) => ({ name: set.name, colors: set.palette }))));
  } catch (error) {
    return false;
  }
  state.sets = sets;
  buildPresets();
  renderSetTools();
  return true;
}

// Чему равна палитра: своему набору, готовому набору или ничему. Свой набор важнее: иначе его было бы не удалить.
function currentSet() {
  const own = state.sets.find((set) => samePalette(set.palette, state.palette));
  if (own) return { own };
  const preset = [{ id: 'default', colors: {} }, ...state.presets]
    .find((item) => samePalette({ ...state.defaults, ...item.colors }, state.palette));
  return preset ? { preset } : {};
}

function freeName(stem) {
  const base = [...cleanName(stem)].slice(0, NAME_LIMIT - 4).join('');
  const taken = (name) => state.sets.some((set) => set.name === name);
  let name = base;
  for (let n = 2; taken(name); n++) name = `${base} ${n}`;
  return name;
}

// Список и первая кнопка следуют за палитрой: «Сохранить», пока цвета не сохранены, «Удалить» — когда это свой набор.
function renderSetTools() {
  const match = currentSet();
  const { form } = state;
  // Поле имени нужно, пока цвета не совпали с набором; поле со ссылкой — пока цвета те же, что в ссылке.
  if (form && (form.mode === 'name' ? Boolean(match.own || match.preset) : !samePalette(form.palette, state.palette))) closeForm();
  if (match.own) state.lastSet = match.own.name;

  // Пункт добавляется и убирается, а не прячется: скрытые пункты списка часть браузеров всё равно показывает.
  const select = $('#preset');
  const custom = select.querySelector('option[value="custom"]');
  if (match.own || match.preset) {
    if (custom) custom.remove();
  } else if (!custom) {
    const option = document.createElement('option');
    option.value = 'custom';
    option.textContent = t('presetCustom');
    select.append(option);
  }
  select.value = match.own ? OWN_PREFIX + match.own.name : match.preset ? match.preset.id : 'custom';
  const note = $('#preset-note');
  note.textContent = match.preset ? pick(match.preset.note) : '';
  note.hidden = !note.textContent;

  const save = $('#save-set');
  save.textContent = t(match.own ? 'deleteSet' : 'saveSet');
  save.title = match.own ? t('deleteSetTitle', { name: match.own.name }) : t(match.preset ? 'saveSetNothing' : 'saveSetTitle');
  // Не disabled: на готовом наборе кнопка объясняет, почему сохранять нечего.
  save.setAttribute('aria-disabled', String(Boolean(match.preset)));
  renderForm();
}

// Строка кнопок на время превращается в поле: имя нового набора (name) или ссылка, если буфер обмена недоступен (link).
function renderForm() {
  const { form } = state;
  if (!form) return;
  const input = $('#set-name');
  const label = t(form.mode === 'link' ? 'linkField' : 'setName');
  input.setAttribute('aria-label', label);
  input.placeholder = label;
  const name = cleanName(input.value);
  $('#set-confirm').textContent = t(state.sets.some((set) => set.name === name) ? 'replaceSet' : 'saveSet');
}

function openForm(mode, value) {
  state.form = { mode, palette: { ...state.palette } };
  $('#set-tools').hidden = true;
  $('#set-form').hidden = false;
  $('#set-confirm').hidden = mode === 'link';
  const input = $('#set-name');
  input.readOnly = mode === 'link';
  if (mode === 'link') input.removeAttribute('maxlength');
  else input.setAttribute('maxlength', NAME_LIMIT);
  input.value = value;
  input.classList.remove('invalid');
  renderForm();
  input.focus();
  input.select();
}

function closeForm(returnFocus = false) {
  if (!state.form) return;
  const button = $(state.form.mode === 'link' ? '#copy-link' : '#save-set');
  state.form = null;
  $('#set-form').hidden = true;
  $('#set-tools').hidden = false;
  if (returnFocus) button.focus();
}

function linkFor(palette) {
  const parts = state.names
    .filter((name) => palette[name] !== state.defaults[name])
    .map((name) => `${name}-${palette[name].slice(1)}`);
  const url = new URL(location.href);
  url.search = '';                                // язык страницы получатель выбирает сам
  url.hash = `${LINK_PARAM}=${parts.join('.')}`;
  return url.href;
}

// Набор из адреса страницы или null, если в адресе его нет. Пустое значение — исходные цвета.
function readLink() {
  const params = new URLSearchParams(location.hash.slice(1));
  if (!params.has(LINK_PARAM)) return null;
  const value = params.get(LINK_PARAM).slice(0, 2000);
  const palette = { ...state.defaults };
  let used = 0;
  for (const part of value.split('.')) {
    const match = part.match(/^([A-Za-z_]+)-([0-9A-Fa-f]{6})$/);
    const name = match && match[1].toUpperCase();
    if (!match || !state.names.includes(name)) continue;
    palette[name] = `#${match[2].toUpperCase()}`;
    used++;
  }
  return { palette, broken: Boolean(value) && !used };
}

// Открывает набор из ссылки одним шагом истории. Свои несохранённые цвета сначала уходят в список своих наборов:
// история живёт только до закрытия вкладки, а терять их нельзя. Если сохранить их не вышло, набор не открывается.
// После открытия набор из адреса убирается, иначе обновление страницы открывало бы его заново поверх новых правок.
function openLink() {
  const link = readLink();
  if (!link) return;
  const message = $('#palette-message');
  const forget = () => history.replaceState(history.state, '', location.pathname + location.search);
  if (link.broken) {
    forget();
    say(message, 'linkBroken', {}, true);
    return;
  }
  if (samePalette(link.palette, state.palette)) {
    forget();
    return;
  }
  settle();
  const match = currentSet();
  let kept = '';
  if (!match.own && !match.preset && !fromLastLink()) {
    kept = freeName(t('setBeforeLink'));
    const full = state.sets.length >= SETS_LIMIT;
    if (full || !storeSets([...state.sets, { name: kept, palette: { ...state.palette } }])) {
      say(message, 'linkNotOpened', {}, true);     // адрес не трогаем: ссылку можно открыть ещё раз, обновив страницу
      return;
    }
  }
  state.lastSet = '';
  setPalette(link.palette, 'link');
  try { localStorage.setItem(LINK_KEY, JSON.stringify(link.palette)); } catch (error) { /* не страшно: следующая ссылка сохранит эти цвета в список */ }
  forget();
  say(message, kept ? 'linkOpenedKept' : 'linkOpened', { name: kept });
}

// Цвета, которые пришли из прошлой ссылки и с тех пор не менялись, своими не считаются: в список они не уходят,
// иначе каждая открытая ссылка оставляла бы в нём чужой набор под именем «мои цвета».
function fromLastLink() {
  try {
    const palette = cleanPalette(JSON.parse(localStorage.getItem(LINK_KEY) || 'null'));
    return Boolean(palette && samePalette(palette, state.palette));
  } catch (error) {
    return false;
  }
}

function setupSets() {
  const message = $('#palette-message');
  const input = $('#set-name');

  $('#save-set').addEventListener('click', () => {
    settle();
    const match = currentSet();
    if (match.preset) {
      say(message, 'saveSetNothing');
    } else if (match.own) {
      const { name } = match.own;
      if (storeSets(state.sets.filter((set) => set !== match.own))) say(message, 'setDeleted', { name });
      else say(message, 'setNotSaved', {}, true);
    } else {
      openForm('name', state.lastSet || freeName(t('setDefaultName')));
    }
  });

  $('#set-form').addEventListener('submit', (event) => {
    event.preventDefault();
    if (!state.form || state.form.mode !== 'name') return;
    const name = cleanName(input.value);
    if (!name) {
      input.classList.add('invalid');
      input.focus();
      return;
    }
    const set = { name, palette: { ...state.palette } };
    const index = state.sets.findIndex((item) => item.name === name);
    if (index < 0 && state.sets.length >= SETS_LIMIT) {
      say(message, 'setsFull', {}, true);
      return;
    }
    const sets = index < 0 ? [...state.sets, set] : state.sets.map((item, i) => (i === index ? set : item));
    if (!storeSets(sets)) {
      say(message, 'setNotSaved', {}, true);
      return;
    }
    closeForm();
    // Фокус уходит на список, где теперь стоит имя набора, а не на кнопку, ставшую «Удалить»: повторный Enter ничего не сотрёт.
    $('#preset').focus();
    say(message, index < 0 ? 'setSaved' : 'setReplaced', { name });
  });
  input.addEventListener('input', () => {
    input.classList.remove('invalid');
    renderForm();
  });
  input.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeForm(true); });
  $('#set-cancel').addEventListener('click', () => closeForm(true));

  $('#copy-link').addEventListener('click', async () => {
    settle();
    const url = linkFor(state.palette);
    try {
      await navigator.clipboard.writeText(url);
      say(message, 'linkCopied');
    } catch (error) {
      openForm('link', url);                       // буфер обмена недоступен: ссылку копируют из поля
      say(message, 'linkManual');
    }
  });

  // Наборы, сохранённые в другой вкладке, появляются в списке сразу.
  window.addEventListener('storage', (event) => {
    if (event.key !== null && event.key !== SETS_KEY) return;
    state.sets = loadSets();
    buildPresets();
    renderSetTools();
  });
  window.addEventListener('hashchange', openLink);
}

function setupPaletteFiles() {
  const message = $('#palette-message');
  $('#save-palette').addEventListener('click', () => {
    const blob = new Blob([JSON.stringify(state.palette, null, 1) + '\n'], { type: 'application/json' });
    download(blob, 'palette.json');
    say(message, 'paletteSaved');
  });
  $('#load-palette').addEventListener('click', () => $('#palette-file').click());
  $('#palette-file').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    event.target.value = '';
    if (!file) return;
    try {
      const loaded = JSON.parse(await file.text());
      const palette = { ...state.defaults };
      let used = 0;
      for (const name of state.names) {
        const colour = typeof loaded[name] === 'string' && parseColour(loaded[name]);
        if (colour) { palette[name] = colour; used++; }
      }
      if (!used) throw fail('paletteEmpty');
      state.lastSet = '';
      setPalette(palette, 'file');
      say(message, 'paletteLoaded', { used, total: state.names.length });
    } catch (error) {
      say(message, 'paletteRejected', { error }, true);
    }
  });
}

// ---------------------------------------------------------------- кадры

function markFrameControls() {
  for (const button of document.querySelectorAll('#scenes button')) {
    button.setAttribute('aria-selected', String(button.dataset.scene === state.frame.scene));
  }
  const screens = $('#screens');
  screens.textContent = '';
  for (const frame of state.frames.filter((f) => f.scene === state.frame.scene)) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = distance(frame.scaleMetres);
    button.setAttribute('aria-pressed', String(frame === state.frame));
    button.addEventListener('click', () => showFrame(frame));
    screens.append(button);
  }
}

function buildScenes() {
  const tabs = $('#scenes');
  tabs.textContent = '';
  const seen = new Set();
  for (const frame of state.frames) {
    if (seen.has(frame.scene)) continue;
    seen.add(frame.scene);
    const button = document.createElement('button');
    button.type = 'button';
    button.role = 'tab';
    button.dataset.scene = frame.scene;
    button.textContent = pick(frame.sceneTitle);
    button.addEventListener('click', () => {
      const wanted = state.frame && state.frames.find((f) => f.scene === frame.scene && f.screen === state.frame.screen);
      showFrame(wanted || frame);
    });
    tabs.append(button);
  }
}

// ---------------------------------------------------------------- выгрузка карты
//
// Цвета лежат в подфайле TYP внутри .img. Его блоки читаются из скачанной карты,
// в известные байты вписываются выбранные цвета, остальной файл не меняется.

function download(blob, filename) {
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 60000);
}

// Карта лежит одним файлом (локально) или частями (на хостинге, где есть предел размера файла).
const mapParts = (map) => map.parts || [{ file: map.file, bytes: map.bytes }];

async function fetchMap(map, onProgress) {
  if (state.mapBlobs.has(map.id)) return state.mapBlobs.get(map.id);
  const blobs = [];
  let received = 0;
  for (const part of mapParts(map)) {
    const response = await fetch(part.file);
    if (!response.ok) throw fail('mapNotDownloaded', { status: response.status });
    const reader = response.body.getReader();
    const chunks = [];
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.length;
      onProgress(received / map.bytes);
    }
    const blob = new Blob(chunks);
    if (blob.size !== part.bytes) throw fail('mapIncomplete', { got: received, total: map.bytes });
    blobs.push(blob);
  }
  const blob = new Blob(blobs, { type: 'application/octet-stream' });
  if (blob.size !== map.bytes) throw fail('mapIncomplete', { got: blob.size, total: map.bytes });
  state.mapBlobs.clear();                         // в памяти держим одну карту
  state.mapBlobs.set(map.id, blob);
  return blob;
}

async function recolourMap(map, palette, onProgress = () => {}) {
  const { typ } = state;
  if (map.typSize !== typ.size) throw fail('styleMismatch');
  const blob = await fetchMap(map, onProgress);
  const size = map.block;
  const data = new Uint8Array(map.typBlocks.length * size);
  for (let i = 0; i < map.typBlocks.length; i++) {
    const start = map.typBlocks[i] * size;
    data.set(new Uint8Array(await blob.slice(start, start + size).arrayBuffer()), i * size);
  }
  if (String.fromCharCode(...data.subarray(2, 12)) !== 'GARMIN TYP') {
    throw fail('typNotFound');
  }
  const colours = state.names.map((name) => hexToRgb(palette[name]));
  for (const [position, index, channel, kind] of typ.slots) {
    const value = colours[index][channel];
    data[position] = kind === 1 ? typ.lighten[value] : value;
  }
  const order = map.typBlocks.map((block, i) => [block, i]).sort((a, b) => a[0] - b[0]);
  const parts = [];
  let cursor = 0;
  for (const [block, i] of order) {
    parts.push(blob.slice(cursor, block * size), data.subarray(i * size, (i + 1) * size));
    cursor = (block + 1) * size;
  }
  parts.push(blob.slice(cursor));
  return new Blob(parts, { type: 'application/octet-stream' });
}

function buildRegions() {
  const select = $('#region');
  const chosen = select.value;
  select.textContent = '';
  for (const map of state.maps) {
    const option = document.createElement('option');
    option.value = map.id;
    option.textContent = t('mapOption', { title: pick(map.title), size: Math.round(map.bytes / 1048576) });
    select.append(option);
  }
  if (chosen) select.value = chosen;
}

function setupExport() {
  const select = $('#region');
  buildRegions();
  const button = $('#download');
  const progress = $('#progress');
  const message = $('#export-message');
  if (!state.maps.length) {
    button.disabled = true;
    say(message, 'noMaps', {}, true);
    return;
  }
  say(message, 'exportHint');
  button.addEventListener('click', async () => {
    const map = state.maps.find((m) => m.id === select.value);
    button.disabled = true;
    progress.hidden = false;
    progress.value = 0;
    say(message, 'downloading');
    try {
      const result = await recolourMap(map, state.palette, (share) => { progress.value = share; });
      const file = `${map.id}-colours.img`;
      download(result, file);
      say(message, 'exportDone', { file });
    } catch (error) {
      say(message, 'exportFailed', { error }, true);
    } finally {
      progress.hidden = true;
      button.disabled = false;
    }
  });
}

// ---------------------------------------------------------------- проверки (вызываются из консоли)

// Сравнивает сложенный кадр с настоящим рендером: ref.png — палитра по умолчанию.
async function checkFrame(frame, palette = state.defaults, refUrl = `${frame.dir}/ref.png`) {
  const engine = await buildEngine(frame);
  renderFull(engine, palette);
  const ref = (await loadPixels(refUrl)).data;
  const out = engine.out.data;
  let max = 0, total = 0, over2 = 0, over8 = 0;
  for (let p = 0, o = 0; p < engine.count; p++, o += 4) {
    const d = Math.max(Math.abs(out[o] - ref[o]), Math.abs(out[o + 1] - ref[o + 1]), Math.abs(out[o + 2] - ref[o + 2]));
    if (d > max) max = d;
    total += d;
    if (d > 2) over2++;
    if (d > 8) over8++;
  }
  return { frame: frame.dir.split('/').pop(), pixels: engine.count, max, mean: +(total / engine.count).toFixed(4), over2, over8 };
}

async function sha256(blob) {
  const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer());
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

window.mapColours = { state, checkFrame, recolourMap, sha256, parseColour, setLanguage, linkFor };

// ---------------------------------------------------------------- запуск

async function start() {
  state.language = initialLanguage();
  buildLanguages();
  applyStaticTexts();
  renderCompare();
  say($('#frame-status'), 'frameLoading');

  const [palette, scenes, presets, typ, maps] = await Promise.all([
    getJSON('data/palette.json'),
    getJSON('data/scenes.json').catch(() => ({ groups: [], frames: [] })),
    getJSON('data/presets.json').catch(() => []),
    getJSON('data/typ.json'),
    getJSON('data/maps.json').catch(() => []),
  ]);
  Object.assign(state, {
    names: palette.names, defaults: palette.defaults, legend: palette.legend,
    presets, groups: scenes.groups, frames: scenes.frames, typ, maps,
  });
  state.palette = loadLocal() || { ...state.defaults };
  state.sets = loadSets();
  loadHistory();

  buildPresets();
  setupPresets();
  buildLegend();
  refreshLegend();
  setupHistory();
  renderHistory();
  setupSets();
  setupPaletteFiles();
  setupExport();
  try { openLink(); } catch (error) { /* набор из ссылки не открылся: страница запускается как обычно */ }

  $('#compare').addEventListener('click', () => {
    state.showDefaults = !state.showDefaults;
    renderCompare();
    if (state.engine) { renderFull(state.engine, visiblePalette()); paint(); }
  });

  if (state.frames.length) {
    buildScenes();
    await showFrame(state.frames[0]);
  } else {
    say($('#frame-status'), 'noFrames');
  }
}

start().catch((error) => {
  $('#frame-status').hidden = false;
  say($('#frame-status'), 'startFailed', { error });
});
