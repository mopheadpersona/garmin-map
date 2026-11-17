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
const DEFAULT_LANGUAGE = LANGUAGES[0][0];

const state = {
  names: [], defaults: {}, legend: [], presets: [],
  palette: {},
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

// Название из данных: строка или объект {en, cs, ru}.
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
  const select = $('#preset');
  const match = [{ id: 'default', colors: {} }, ...state.presets]
    .find((preset) => samePalette({ ...state.defaults, ...preset.colors }, state.palette));
  select.querySelector('[value="custom"]').hidden = Boolean(match);
  select.value = match ? match.id : 'custom';
  const note = $('#preset-note');
  const preset = match && state.presets.find((p) => p.id === match.id);
  note.textContent = preset ? pick(preset.note) : '';
  note.hidden = !note.textContent;
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

function setColour(name, hex) {
  if (state.palette[name] === hex) return;
  state.palette[name] = hex;
  const wasDefaults = leaveDefaultsView();
  if (state.engine) {
    if (wasDefaults) renderFull(state.engine, state.palette);
    else renderOne(state.engine, name, hex);
    paint();
  }
  refreshLegend();
  saveLocal();
}

function setPalette(palette) {
  state.palette = { ...palette };
  leaveDefaultsView();
  if (state.engine) { renderFull(state.engine, state.palette); paint(); }
  refreshLegend();
  saveLocal();
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
      picker.addEventListener('input', () => setColour(item.name, picker.value.toUpperCase()));
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

function buildPresets() {
  const select = $('#preset');
  select.textContent = '';
  const add = (value, title) => {
    const option = document.createElement('option');
    option.value = value; option.textContent = title;
    select.append(option);
    return option;
  };
  add('default', t('presetDefault'));
  for (const preset of state.presets) add(preset.id, pick(preset.title));
  add('custom', t('presetCustom')).hidden = true;
}

function setupPresets() {
  const select = $('#preset');
  select.addEventListener('change', () => {
    if (select.value === 'custom') return;
    const preset = state.presets.find((p) => p.id === select.value);
    setPalette({ ...state.defaults, ...(preset ? preset.colors : {}) });
  });
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
      setPalette(palette);
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

window.mapColours = { state, checkFrame, recolourMap, sha256, parseColour, setLanguage };

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

  buildPresets();
  setupPresets();
  buildLegend();
  refreshLegend();
  setupPaletteFiles();
  setupExport();

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
