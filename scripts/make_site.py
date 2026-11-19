#!/usr/bin/env python3
"""Готовит данные для конфигуратора цветов (папка site/).

    python3 scripts/make_site.py typ             # где в файле карты лежит каждый цвет (секунды)
    python3 scripts/make_site.py maps            # карты, которые страница отдаёт на выгрузку
    python3 scripts/make_site.py frames [кадр]   # перекрашиваемые кадры: QMapShack, ~10 с на снимок
    python3 scripts/make_site.py titles          # названия мест из SCENES в готовые кадры, без пересъёмки
    python3 scripts/make_site.py all

Страница ничего не собирает на сервере. Она опирается на два свойства формата.

Выгрузка. Цвета лежат в TYP — маленьком подфайле внутри .img, и каждый цвет палитры
занимает там известные байты. Команда typ находит эти байты: компилирует TYP с палитрой
из одних нулей и по разу с каждым цветом, включённым в одном канале, и смотрит, какие
байты поменялись. Браузеру остаётся вписать новые значения в готовую карту.

Приборы. Карта собирается в двух вариантах (DEVICES): обычная и для Edge 1050/1060
(./build.sh <регион> --edge1060). TYP у них разный, поэтому таблица байтов у каждого своя:
site/data/typ.json и site/data/typ-1060.json. Палитра, легенда и превью общие. Ночные цвета
карты для Edge 1050/1060 от палитры страницы не зависят, и страница их не трогает.

Превью. Картинка QMapShack линейно зависит от каждого цвета палитры (сглаживание — это
смешивание в долях). Команда frames снимает кадр с чёрной палитрой (base) и кадры, где
три цвета палитры включены по одному на канал R, G, B. Разность с base даёт для каждого
цвета карту его «веса» в каждом пикселе; страница складывает веса с выбранными цветами.
Кадр ref — настоящий рендер с палитрой по умолчанию, по нему проверяется сложение.
"""

import glob
import hashlib
import importlib
import json
import math
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
DATA = os.path.join(SITE, "data")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "typ"))

import screenshots as shots  # noqa: E402

PREVIEW_REGION = "prague"      # кадры снимаются с малой карты: она быстрее открывается
PREVIEW_FID = 7001
CODE_PAGE = 1252

# Языки страницы: первый — язык по умолчанию. Все названия ниже задаются на двух языках.
LANGS = ("en", "cs")


def tr(en, cs):
    return {"en": en, "cs": cs}


# Карты на выгрузку: регион (имя regions/<регион>.conf), название на странице
MAPS = [
    ("czech", tr("Czechia", "Česko")),
    ("prague", tr("Prague and Brdy", "Praha a Brdy")),
]

# Варианты карты по приборам: id, суффикс файлов (out/<регион><суффикс>.img, site/data/typ<суффикс>.json).
# Какие модели к какому варианту относятся, написано в текстах страницы (site/i18n.js).
DEVICES = [
    ("classic", ""),            # Edge 530, 830, 1030, 1040: обычная сборка
    ("edge1060", "-1060"),      # Edge 1050, 1060: ./build.sh <регион> --edge1060
]
EDGE1060_BUILD = os.path.join(ROOT, "experiments", "edge1060", "build.sh")

# Кадры превью: id, название, широта, долгота, экраны (имена из screenshots.SCREENS)
SCENES = [
    ("interchange", tr("Interchange", "Dálniční křižovatka"), 50.1749, 14.4528, ("2-500m", "3-150m")),  # D8, съезд Здибы
    ("center",      tr("City", "Město"),                      50.0870, 14.4208, ("2-500m", "3-150m")),  # Старе-Место
    ("brdy-forest", tr("Forest", "Les"),                      49.7001, 13.8561, ("2-500m", "3-150m")),  # Средние Брды
    ("outskirts",   tr("Outskirts", "Okraj města"),           49.9760, 14.3930, ("2-500m", "3-150m")),  # Збраслав
]

# Легенда страницы: группы и подписи цветов. Все имена — из make_typ.PALETTE_NAMES.
EDGE = tr("casing", "obrys")
LEGEND = [
    (tr("Roads", "Silnice"), [
        ("GREEN", tr("Motorway, cycling banned", "Dálnice, zákaz vjezdu cyklistů")),
        ("GREEN_EDGE", EDGE),
        ("PRIMARY", tr("Primary road", "Silnice I. třídy")), ("PRIMARY_EDGE", EDGE),
        ("SECONDARY", tr("Secondary road", "Silnice II. třídy")), ("SECONDARY_EDGE", EDGE),
        ("WHITE", tr("Streets and tertiary roads", "Ulice a silnice III. třídy")),
        ("WHITE_EDGE", EDGE),
        ("PEDESTRIAN", tr("Pedestrian zone", "Pěší zóna")), ("PEDESTRIAN_EDGE", EDGE),
        ("NO_ENTRY", tr("No entry, dots", "Zákaz vjezdu, tečky")),
        ("RAIL", tr("Railway, bridge edges", "Železnice, okraje mostů")),
    ]),
    (tr("Gravel and trails", "Nezpevněné cesty a pěšiny"), [
        ("GRAVEL", tr("Gravel road, double track", "Šotolina, polní cesta")),
        ("GRAVEL_EDGE", EDGE),
        ("BAD_TRACK", tr("Rough track", "Rozbitá cesta")),
        ("PATH", tr("Path, steps", "Pěšina, schody")),
        ("HARD_PATH", tr("Difficult trail, S2 and up", "Náročná stezka, S2 a výše")),
    ]),
    (tr("Cycle routes", "Cyklotrasy"), [
        ("CYCLE", tr("Cycleway, cycle route", "Cyklostezka, cyklotrasa")),
        ("MTB", tr("MTB route", "MTB trasa")),
    ]),
    (tr("Land", "Krajina"), [
        ("BG", tr("Background", "Pozadí")),
        ("BUILTUP", tr("Built-up area", "Zástavba")),
        ("INDUSTRIAL", tr("Industrial area, quarry", "Průmyslová zóna, lom")),
        ("FOREST", tr("Forest", "Les")),
        ("PARK", tr("Park, garden", "Park, zahrada")),
        ("MEADOW", tr("Meadow, grass", "Louka, trávník")),
        ("PLANTATION", tr("Vineyard, hop garden, golf", "Vinice, chmelnice, golf")),
        ("PLANTATION_MARK", tr("pattern", "vzor")),
        ("CEMETERY", tr("Cemetery", "Hřbitov")),
        ("CEMETERY_CROSS", tr("crosses", "křížky")),
        ("CLOSED_HATCH", tr("Restricted area", "Oblast se zákazem vstupu")),
    ]),
    (tr("Water", "Voda"), [
        ("WATER", tr("Water", "Voda")),
        ("WETLAND", tr("Wetland, intermittent stream", "Mokřad, občasný potok")),
    ]),
    (tr("Other", "Ostatní"), [
        ("FERRY", tr("Ferry", "Přívoz")),
        ("BORDER", tr("National border", "Státní hranice")),
        ("LABEL", tr("Labels", "Popisky")),
    ]),
]

ZERO = "#000000"
CHANNELS = ("#FF0000", "#00FF00", "#0000FF")


def die(message):
    sys.exit("ОШИБКА: " + message)


def tool_paths():
    java = os.path.join(ROOT, "tools/env/lib/jvm/bin/java")
    if not os.path.exists(java):
        java = shutil.which("java") or die("не найдена Java (ожидается tools/env)")
    jars = sorted(glob.glob(os.path.join(ROOT, "tools/mkgmap-r*/mkgmap.jar")))
    if not jars:
        die("нет tools/mkgmap-r*/mkgmap.jar")
    return java, jars[-1]


def load_make_typ(custom=None):
    """Модуль make_typ с палитрой по умолчанию или с подменой (словарь имя -> цвет)."""
    handle = None
    if custom is not None:
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(custom, handle)
        handle.close()
        os.environ["TYP_PALETTE"] = handle.name
    else:
        os.environ.pop("TYP_PALETTE", None)
    try:
        module = importlib.reload(importlib.import_module("make_typ"))
    finally:
        os.environ.pop("TYP_PALETTE", None)
        if handle:
            os.remove(handle.name)
    return module


def edge1060_typ(custom):
    """TYP карты для Edge 1050/1060 с принятым видом: его пишет цепочка experiments/edge1060."""
    work = tempfile.mkdtemp(prefix="garmin-typ1060-")
    # Переменные EDGE1060_* из окружения сюда не попадают: странице нужен вид по умолчанию.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("EDGE1060_") and key != "TYP_PALETTE"}
    try:
        if custom is not None:
            env["TYP_PALETTE"] = os.path.join(work, "palette.json")
            with open(env["TYP_PALETTE"], "w", encoding="utf-8") as handle:
                json.dump(custom, handle)
        res = subprocess.run(["bash", EDGE1060_BUILD, "--profile", os.path.join(work, "profile")],
                             env=env, capture_output=True, text=True)
        if res.returncode != 0:
            die("experiments/edge1060/build.sh --profile:\n" + res.stdout[-2000:] + res.stderr[-2000:])
        with open(os.path.join(work, "profile", "typ.txt"), encoding="utf-8") as handle:
            return handle.read()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def typ_text(custom, fid, device="classic"):
    """Текст TYP для компилятора mkgmap."""
    text = load_make_typ(custom).build() if device == "classic" else edge1060_typ(custom)
    return text.replace("@FID@", str(fid)).replace("@CODEPAGE@", str(CODE_PAGE))


def names():
    return list(load_make_typ().PALETTE_NAMES)


def defaults():
    return load_make_typ().palette()


def rgb(colour):
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


# --------------------------------------------------------------------------
# typ: ячейки цветов в скомпилированном TYP
# --------------------------------------------------------------------------
def compile_typs(palettes, work, device="classic"):
    """palettes: {метка: палитра или None}. Возвращает {метка: байты TYP}."""
    java, jar = tool_paths()
    sources = []
    for label, custom in palettes.items():
        path = os.path.join(work, label + ".txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(typ_text(custom, PREVIEW_FID, device))
        sources.append(path)
    out = os.path.join(work, "out")
    for start in range(0, len(sources), 40):
        res = subprocess.run([java, "-jar", jar, "--output-dir=" + out] + sources[start:start + 40],
                             capture_output=True, text=True)
        if res.returncode != 0:
            die("mkgmap не скомпилировал TYP:\n" + res.stdout[-2000:] + res.stderr[-2000:])
    result = {}
    for label in palettes:
        with open(os.path.join(out, label + ".typ"), "rb") as handle:
            result[label] = handle.read()
    return result


def find_slots(device="classic"):
    """Ячейки цветов: (смещение в TYP, номер цвета, канал, вид) и таблицы пересчёта."""
    order = names()
    base = {name: ZERO for name in order}
    palettes = {"zero": base, "default": None}
    for index, name in enumerate(order):
        for channel, colour in enumerate(CHANNELS):
            palettes["c%02d_%d" % (index, channel)] = dict(base, **{name: colour})
    rng = random.Random(7)
    trial = {name: "#%06X" % rng.randrange(1 << 24) for name in order}
    palettes["trial"] = trial

    work = tempfile.mkdtemp(prefix="garmin-typ-")
    try:
        typs = compile_typs(palettes, work, device)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    zero = typs["zero"]
    header = struct.unpack_from("<H", zero, 0)[0]      # в заголовке дата сборки, цветов там нет
    size = len(zero)
    if any(len(data) != size for data in typs.values()):
        die("размер TYP зависит от цветов — вписывать цвета в готовый файл нельзя")

    lighten = [rgb(load_make_typ().lighten("#%02X0000" % value))[0] for value in range(256)]
    kinds = {(0, 255): 0, (lighten[0], lighten[255]): 1}   # 0 — цвет как есть, 1 — осветлённый (тоннели)
    slots, taken = [], {}
    for index, name in enumerate(order):
        for channel in range(3):
            data = typs["c%02d_%d" % (index, channel)]
            for pos in range(header, size):
                if data[pos] == zero[pos]:
                    continue
                kind = kinds.get((zero[pos], data[pos]))
                if kind is None:
                    die("непонятная ячейка цвета %s по смещению %d: %d -> %d" %
                        (name, pos, zero[pos], data[pos]))
                if pos in taken:
                    die("смещение %d занято двумя цветами: %s и %s" % (pos, taken[pos], name))
                taken[pos] = name
                slots.append((pos, index, channel, kind))
    slots.sort()
    luts = [list(range(256)), lighten]

    def predict(custom):
        data = bytearray(zero)
        for pos, index, channel, kind in slots:
            data[pos] = luts[kind][rgb(custom[order[index]])[channel]]
        return bytes(data)

    for label, custom in (("default", defaults()), ("trial", trial)):
        if predict(custom)[header:] != typs[label][header:]:
            die("проверка не сошлась: вписанные цвета (%s) дают не тот TYP, что компилятор" % label)
    unused = [name for name in order if name not in taken.values()]
    if unused:
        die("цвета нигде не используются в TYP: " + ", ".join(unused))
    return {"size": size, "header": header, "slots": slots, "lighten": lighten}


def cmd_typ():
    order = names()
    palette = defaults()
    legend_names = [name for _group, items in LEGEND for name, _title in items]
    if sorted(legend_names) != sorted(order):
        die("LEGEND и make_typ.PALETTE_NAMES расходятся: %s" %
            sorted(set(legend_names) ^ set(order)))
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "palette.json"), "w", encoding="utf-8") as handle:
        json.dump({
            "names": order,
            "defaults": palette,
            "legend": [{"title": group, "items": [{"name": n, "title": t} for n, t in items]}
                       for group, items in LEGEND],
        }, handle, ensure_ascii=False, indent=1)
    for device, suffix in DEVICES:
        info = find_slots(device)
        target = os.path.join(DATA, "typ%s.json" % suffix)
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(info, handle, separators=(",", ":"))
        print("%s: TYP %d байт, ячеек цвета %d (из них осветлённых %d), проверка на двух палитрах сошлась" %
              (os.path.relpath(target, ROOT), info["size"], len(info["slots"]),
               sum(1 for s in info["slots"] if s[3] == 1)))


# --------------------------------------------------------------------------
# maps: карты на выгрузку
# --------------------------------------------------------------------------
def typ_location(path):
    """Где в контейнере .img лежит TYP: (размер блока, номера блоков, размер подфайла)."""
    with open(path, "rb") as handle:
        head = handle.read(0x600)
        block = 1 << (head[0x61] + head[0x62])
        pos, blocks, size = 0x600, [], None
        while True:
            handle.seek(pos)
            entry = handle.read(512)
            if len(entry) < 512 or entry[0] != 1:
                break
            if entry[9:12] == b"TYP":
                if struct.unpack_from("<H", entry, 0x10)[0] == 0:
                    size = struct.unpack_from("<I", entry, 12)[0]
                blocks += [b for b in struct.unpack_from("<240H", entry, 0x20) if b != 0xFFFF]
            pos += 512
    if size is None:
        die("в %s нет TYP" % path)
    return block, blocks, size


def cmd_maps():
    target_dir = os.path.join(SITE, "maps")
    os.makedirs(target_dir, exist_ok=True)
    listing = []
    for device, suffix in DEVICES:
        with open(os.path.join(DATA, "typ%s.json" % suffix), encoding="utf-8") as handle:
            typ_size = json.load(handle)["size"]
        flag = " --edge1060" if device == "edge1060" else ""
        for region, title in MAPS:
            name = region + suffix
            src = os.path.join(ROOT, "out", name + ".img")
            if not os.path.exists(src):
                print("нет out/%s.img — пропущена (./build.sh %s%s)" % (name, region, flag))
                continue
            block, blocks, size = typ_location(src)
            if size != typ_size:
                die("TYP в out/%s.img (%d байт) собран другим стилем, чем сейчас (%d): пересоберите карту" %
                    (name, size, typ_size))
            link = os.path.join(target_dir, name + ".img")
            if os.path.lexists(link):
                os.remove(link)
            os.symlink(os.path.relpath(src, target_dir), link)     # локально хватает ссылки
            listing.append({"id": name, "region": region, "device": device, "title": title,
                            "file": "maps/%s.img" % name, "bytes": os.path.getsize(src),
                            "block": block, "typBlocks": blocks, "typSize": size})
            print("%s: %d МБ, TYP в блоках %s по %d байт" % (name, os.path.getsize(src) >> 20, blocks, block))
    with open(os.path.join(DATA, "maps.json"), "w", encoding="utf-8") as handle:
        json.dump(listing, handle, ensure_ascii=False, indent=1)


# --------------------------------------------------------------------------
# frames: перекрашиваемые кадры
# --------------------------------------------------------------------------
def frame_palettes():
    """Палитры съёмки: base, группы по три цвета, ref. Возвращает [(метка, палитра, [имена])]."""
    order = names()
    base = {name: ZERO for name in order}
    result = [("base", base, [])]
    for start in range(0, len(order), 3):
        group = order[start:start + 3]
        result.append(("g%02d" % (start // 3 + 1), dict(base, **dict(zip(group, CHANNELS))), group))
    result.append(("ref", None, []))
    return result


def assemble_maps(palettes, work):
    """Карта превью с каждым TYP: склейка готовых тайлов, секунда на карту."""
    java, jar = tool_paths()
    tiles = sorted(glob.glob(os.path.join(ROOT, "build", PREVIEW_REGION, "img", "%d*.img" % PREVIEW_FID)))
    if not tiles:
        die("нет тайлов build/%s/img — сначала ./build.sh %s" % (PREVIEW_REGION, PREVIEW_REGION))
    maps = {}
    for label, custom, _group in palettes:
        typ = os.path.join(work, label + "-typ.txt")
        with open(typ, "w", encoding="utf-8") as handle:
            handle.write(typ_text(custom, PREVIEW_FID))
        out = os.path.join(work, "asm-" + label)
        res = subprocess.run([java, "-Xmx2g", "-jar", jar, "--output-dir=" + out,
                              "--family-id=%d" % PREVIEW_FID, "--product-id=1", "--family-name=preview",
                              "--series-name=preview", "--code-page=%d" % CODE_PAGE, "--gmapsupp"] + tiles + [typ],
                             capture_output=True, text=True)
        # Каждой карте своя папка: у склеенных карт одинаковый заголовок, а QMapShack различает
        # карты в одной папке по нему и рисует не ту, которую просили.
        target = os.path.join(work, "maps", label, "preview.img")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if res.returncode != 0 or not os.path.exists(os.path.join(out, "gmapsupp.img")):
            die("mkgmap не склеил карту %s:\n%s" % (label, res.stdout[-2000:] + res.stderr[-2000:]))
        shutil.move(os.path.join(out, "gmapsupp.img"), target)
        shutil.rmtree(out, ignore_errors=True)
        maps[label] = target
    return maps


def cmd_frames(only=None):
    palettes = frame_palettes()
    os.makedirs(shots.WORK, exist_ok=True)
    work = os.path.join(shots.WORK, "site")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    print("склеиваю %d карт для съёмки" % len(palettes), flush=True)
    maps = assemble_maps(palettes, work)
    screens = {name: (zoom, bits, metres) for name, zoom, bits, metres, _label in shots.SCREENS}
    lat0, lon0 = SCENES[0][2], SCENES[0][3]

    def probe():
        image, window_w = shots.capture(None, lat0, lon0, 15.0, 0, back="#FF00FF")
        k = round(image[0] / window_w)
        left, top, right, bottom = shots.find_canvas(image)
        if right - left < shots.FRAME_W * k or bottom - top < shots.FRAME_H * k:
            die("область карты QMapShack меньше кадра %dx%d" % (shots.FRAME_W, shots.FRAME_H))
        return image[:2], k, (left + right) // 2, (top + bottom) // 2

    probe_size, k, cx, cy = probe()
    index_path = os.path.join(DATA, "scenes.json")
    done = {}
    if only and os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as handle:
            done = {(f["scene"], f["screen"]): f for f in json.load(handle)["frames"]}

    for scene, title, lat, lon, scene_screens in SCENES:
        for screen in scene_screens:
            key = "%s_%s" % (scene, screen)
            if only and only not in (scene, key):
                continue
            zoom, bits, metres = screens[screen]
            adjust = bits - shots.natural_bits(zoom)
            out_dir = os.path.join(DATA, "frames", key)
            os.makedirs(out_dir, exist_ok=True)
            digests = {}
            for label, _custom, _group in palettes:
                for _attempt in range(4):
                    image, _ = shots.capture(maps[label], lat, lon, zoom, adjust)
                    if image[:2] == probe_size:
                        break
                    probe_size, k, cx, cy = probe()
                else:
                    die("окно QMapShack меняет размер между запусками")
                fw, fh = shots.FRAME_W * k, shots.FRAME_H * k
                x0, y0 = cx - fw // 2, cy - fh // 2
                rows = [bytes(row[x0 * 3:(x0 + fw) * 3]) for row in image[2][y0:y0 + fh]]
                shots.write_png(os.path.join(out_dir, label + ".png"), fw, rows)
                digests[label] = hashlib.md5(b"".join(rows)).hexdigest()
                print("%s/%s.png" % (key, label), flush=True)
            # Кадр группы может совпасть с base (её цветов в кадре нет), но не с другой группой
            # и не с ref: это значит, что QMapShack показал не ту карту.
            seen = {digests["base"]: "base"}
            for label, digest in digests.items():
                if label != "base" and digest != digests["base"]:
                    if digest in seen:
                        die("кадры %s и %s в %s одинаковые — снята не та карта" % (seen[digest], label, key))
                    seen[digest] = label
            if digests["ref"] == digests["base"]:
                die("кадр ref в %s совпал с base — снята не та карта" % key)
            done[(scene, screen)] = {
                "scene": scene, "sceneTitle": title, "screen": screen,
                "dir": "data/frames/" + key, "width": fw, "height": fh, "density": k,
                "metresPerPx": zoom * math.cos(math.radians(lat)) / k, "scaleMetres": metres,
            }
            write_scene_index(index_path, done, palettes)
    shutil.rmtree(work, ignore_errors=True)


def write_scene_index(path, done, palettes):
    """Пишется после каждого кадра: готовые кадры видны на странице, пока снимаются остальные."""
    order = [(scene, screen) for scene, _t, _la, _lo, screens in SCENES for screen in screens]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({
            "groups": [{"file": label, "names": group} for label, _custom, group in palettes if group],
            "frames": [done[key] for key in order if key in done],
        }, handle, ensure_ascii=False, indent=1)


def cmd_titles():
    """Названия мест из SCENES — в готовый scenes.json, без пересъёмки кадров."""
    path = os.path.join(DATA, "scenes.json")
    if not os.path.exists(path):
        die("нет site/data/scenes.json — сначала снимите кадры (frames)")
    with open(path, encoding="utf-8") as handle:
        index = json.load(handle)
    titles = {scene: title for scene, title, _la, _lo, _screens in SCENES}
    for frame in index["frames"]:
        if frame["scene"] not in titles:
            die("кадр %s есть в scenes.json, но места нет в SCENES" % frame["scene"])
        frame["sceneTitle"] = titles[frame["scene"]]
        frame.pop("screenTitle", None)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=1)
    print("названия мест обновлены: %d кадров" % len(index["frames"]))


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "typ":
        cmd_typ()
    elif command == "titles":
        cmd_titles()
    elif command == "maps":
        cmd_maps()
    elif command == "frames":
        cmd_frames(sys.argv[2] if len(sys.argv) > 2 else None)
    elif command == "all":
        cmd_typ()
        cmd_maps()
        cmd_frames()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
