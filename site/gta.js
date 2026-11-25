// Режим «GTA VI style»: готовая карта в стиле карты GTA VI (./build.sh prague --gta). Цвета в ней
// не меняются, поэтому редактора нет: рассказ, мини-карта с кадрами днём и ночью, легенда и выгрузка.
// Кадры и места — data/gta.json (scripts/make_site.py gta), карта — запись с device "gta" в data/maps.json.
// Режим открывается ссылкой ?map=gta; переключатель в шапке меняет адрес без перезагрузки страницы.
// Переключатель «День / Ночь» под картой перекрашивает всю страницу вместе с кадром и легендой.

const $ = (selector) => document.querySelector(selector);
const PARAM = 'map';
const VALUE = 'gta';
// Жирные начертания нужны только этому режиму: грузятся, когда он открывается.
const FONTS = 'https://fonts.googleapis.com/css2?family=Sofia+Sans+Extra+Condensed:ital,wght@0,800;1,800;1,900&family=Sofia+Sans+Semi+Condensed:wght@700&display=swap';

// Легенда: группа, строки (подпись, образец днём, образец ночью). Цвета — из typ/make_typ_gta.py.
const LAND = ['#6D9985', '#0E142C'];
const lanes = (fill, edge, h, b) => `<div class="k-line" style="height:${h}px;background:${fill};border-block:${b}px solid ${edge}"></div>`;
const solid = (colour, h) => `<div class="k-line" style="height:${h}px;background:${colour}"></div>`;
const area = (colour) => `<div class="k-area" style="background:${colour}"></div>`;
const houses = (ground, house) => `<div class="k-area" style="background:${ground};display:flex;gap:5px;align-items:center;justify-content:center">`
  + `<i style="width:17px;height:13px;background:${house}"></i><i style="width:11px;height:18px;background:${house}"></i><i style="width:15px;height:11px;background:${house}"></i></div>`;
const wet = (water, land) => `<div class="k-area" style="background:radial-gradient(circle at 25% 40%, ${water} 0 5px, transparent 6px), `
  + `radial-gradient(circle at 70% 65%, ${water} 0 6px, transparent 7px), radial-gradient(circle at 52% 22%, ${water} 0 3px, transparent 4px), ${land}"></div>`;
const text = (colour) => `<span class="k-text" style="color:${colour}">PRAHA</span>`;
const KEY = [
  ['gtaKeyRoads', [
    ['gtaKeyMotorway', lanes('#BCA36B', '#D1D2DC', 14, 4), lanes('#A38B57', '#9094AA', 14, 4)],
    ['gtaKeyMainRoad', lanes('#E3D6AE', '#D1D2DC', 13, 4), lanes('#C2B993', '#9094AA', 13, 4)],
    ['gtaKeyStreet', solid('#D1D2DC', 9), solid('#9094AA', 9)],
    ['gtaKeyGravel', solid('#BFBFC7', 6), solid('#6E7288', 6)],
    ['gtaKeyTrail', solid('#A3A3AD', 5), solid('#555A72', 5)],
    ['gtaKeyRail', lanes('#A5B4CA', '#8C9AB2', 5, 1), lanes('#5A6688', '#3E4A6A', 5, 1)],
  ]],
  ['gtaKeyLand', [
    ['gtaKeyFields', area(LAND[0]), area(LAND[1])],
    ['gtaKeyTown', area('#9EA5AC'), area('#2C3B5E')],
    ['gtaKeyHouses', houses('#9EA5AC', '#9DACBF'), houses('#2C3B5E', '#46567B')],
    ['gtaKeyForest', area('#5F8C70'), area('#122036')],
    ['gtaKeyPark', area('#50866D'), area('#16293C')],
  ]],
  ['gtaKeyWater', [
    ['gtaKeyRiver', area('#49A2BA'), area('#474A80')],
    ['gtaKeyWetland', wet('#51ABC3', LAND[0]), wet('#3E4274', LAND[1])],
  ]],
  ['gtaKeyLabels', [
    ['gtaKeyPlaces', text('#000000'), text('#F2F4FA')],
  ]],
];

let api = null;          // помощники из app.js: t, pick, say, maps, fetchMap, download, onColour
const view = {
  active: false, data: null, built: false, fontsLoaded: false,
  scene: 'center', screen: '200m',
  // ?time=day|night в ссылке, иначе по часам посетителя
  time: (() => {
    const asked = new URLSearchParams(location.search).get('time');
    if (asked === 'day' || asked === 'night') return asked;
    const hour = new Date().getHours();
    return hour >= 7 && hour < 19 ? 'day' : 'night';
  })(),
};

export const isGta = () => view.active;
const wanted = () => new URLSearchParams(location.search).get(PARAM) === VALUE;

function loadFonts() {
  if (view.fontsLoaded) return;
  view.fontsLoaded = true;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = FONTS;
  document.head.append(link);
}

// Включает или выключает режим. Вызывается до загрузки данных, чтобы страница не мигала редактором.
export function applyMode(active = wanted()) {
  view.active = active;
  const body = document.body;
  body.classList.toggle('gta', active);
  if (active) body.dataset.time = view.time;
  else delete body.dataset.time;
  $('.bench').hidden = active;
  $('#gta-page').hidden = !active;
  $('#lede').hidden = active;
  for (const link of document.querySelectorAll('#modes a')) {
    if ((link.dataset.mode === VALUE) === active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  if (active) loadFonts();
  if (api) {
    api.retitle();
    if (active && !view.built) build();
    if (!active) api.onColour();
  }
}

function go(active) {
  if (active === view.active) return;
  const url = new URL(location.href);
  if (active) url.searchParams.set(PARAM, VALUE);
  else url.searchParams.delete(PARAM);
  history.pushState(null, '', url);
  applyMode(active);
  window.scrollTo(0, 0);
}

// ---------------------------------------------------------------- мини-карта

const scene = () => view.data.scenes.find((item) => item.id === view.scene) || view.data.scenes[0];

function markButtons(root, attribute, value) {
  for (const button of root.querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset[attribute] === value));
}

function showFrame() {
  const { t } = api;
  const item = scene();
  const day = item.frames.day?.[view.screen];
  const night = item.frames.night?.[view.screen];
  const imgDay = $('#gta-page .mm-screen .d');
  const imgNight = $('#gta-page .mm-screen .n');
  if (day) imgDay.src = day;
  if (night) imgNight.src = night;
  imgDay.alt = t('gtaDayView');
  imgNight.alt = t('gtaNightView');
  const missing = !(view.time === 'day' ? day : night);
  const status = $('#gta-status');
  status.hidden = !missing;
  if (missing) api.say(status, 'gtaFrameMissing');
  $('#gta-place b').textContent = item.place;
  $('#gta-place span').textContent = item.street;
  markButtons($('#gta-scenes'), 'scene', item.id);
  markButtons($('#gta-screens'), 'screen', view.screen);
}

function setTime(time) {
  view.time = time;
  document.body.dataset.time = time;
  markButtons($('#gta-time'), 'time', time);
  api.say($('#gta-key-note'), time === 'day' ? 'gtaKeyNoteDay' : 'gtaKeyNoteNight');
  showFrame();
}

function buildScenes() {
  const { pick, t } = api;
  const scenes = $('#gta-scenes');
  scenes.textContent = '';
  for (const item of view.data.scenes) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.scene = item.id;
    button.textContent = pick(item.title);
    button.addEventListener('click', () => { view.scene = item.id; showFrame(); });
    scenes.append(button);
  }
  const screens = $('#gta-screens');
  screens.textContent = '';
  for (const label of view.data.screens) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.screen = label;
    button.textContent = t('metres', { value: parseInt(label, 10) });
    button.addEventListener('click', () => { view.screen = label; showFrame(); });
    screens.append(button);
  }
}

function buildKey() {
  const groups = KEY.map(([title, rows]) => `<div class="card"><h3 data-i18n="${title}">${api.t(title)}</h3>${rows.map(([name, day, night]) =>
    `<div class="k-row"><div class="k-well"><div class="d">${day}</div><div class="n">${night}</div></div><span data-i18n="${name}">${api.t(name)}</span></div>`).join('')}</div>`);
  $('#gta-key').innerHTML = `${groups[0]}${groups[1]}<div class="stack">${groups[2]}${groups[3]}</div>`;
}

// ---------------------------------------------------------------- выгрузка

const gtaMaps = () => api.maps().filter((map) => map.device === VALUE);

function buildRegions() {
  const select = $('#gta-region');
  const chosen = select.value;
  select.textContent = '';
  for (const map of gtaMaps()) {
    const option = document.createElement('option');
    option.value = map.id;
    option.textContent = api.t('mapOption', { title: api.pick(map.title), size: Math.round(map.bytes / 1048576) });
    option.selected = map.id === chosen;
    select.append(option);
  }
}

function setupDownload() {
  const button = $('#gta-download');
  const progress = $('#gta-progress');
  const message = $('#gta-message');
  buildRegions();
  if (!gtaMaps().length) {
    button.disabled = true;
    api.say(message, 'gtaNoMap', {}, true);
    return;
  }
  api.say(message, 'gtaExportHint');
  button.addEventListener('click', async () => {
    const map = gtaMaps().find((item) => item.id === $('#gta-region').value) || gtaMaps()[0];
    button.disabled = true;
    progress.hidden = false;
    progress.value = 0;
    api.say(message, 'downloading');
    try {
      const blob = await api.fetchMap(map, (share) => { progress.value = share; });
      const file = `${map.id}.img`;
      api.download(blob, file);
      api.say(message, 'exportDone', { file });
    } catch (error) {
      api.say(message, 'exportFailed', { error }, true);
    } finally {
      progress.hidden = true;
      button.disabled = false;
    }
  });
}

// ---------------------------------------------------------------- запуск

async function build() {
  view.built = true;
  buildKey();
  setupDownload();
  try {
    const response = await fetch('data/gta.json', { cache: 'no-cache' });
    if (!response.ok) throw new Error(String(response.status));
    view.data = await response.json();
  } catch (error) {
    const status = $('#gta-status');
    status.hidden = false;
    api.say(status, 'gtaNoFrames');
    return;
  }
  buildScenes();
  setTime(view.time);
}

// Тексты, которые собираются из данных, — после смены языка (остальное переводит app.js по data-i18n).
export function refreshGta() {
  if (!view.built) return;
  buildRegions();
  if (view.data) { buildScenes(); showFrame(); }
}

export function setupGta(helpers) {
  api = helpers;
  for (const link of document.querySelectorAll('#modes a')) {
    link.addEventListener('click', (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button) return;   // в новой вкладке — как обычная ссылка
      event.preventDefault();
      go(link.dataset.mode === VALUE);
    });
  }
  window.addEventListener('popstate', () => applyMode(wanted()));
  $('#gta-time').addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (button) setTime(button.dataset.time);
  });
  applyMode(wanted());
}
