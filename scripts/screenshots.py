#!/usr/bin/env python3
"""Снимает скриншоты карты в QMapShack: 4 места x 4 масштаба из SPEC.md.

    python3 scripts/screenshots.py <шаг> [регион] [место]     # например: 5a prague

Результат: screenshots/<шаг>/<место>_<экран>.png, кадр 480x640 точек —
область карты на экране Edge 1050 (карта занимает 80 % высоты 800).

Как это работает. QMapShack управляется только мышью, поэтому для каждого
кадра пишется файл настроек (ключ -c): карта, центр, масштаб. Программа
запускается, окно снимается через screencapture и программа закрывается.

Про разрешение. QMapShack сам выбирает, какой уровень карты показать на
данном масштабе, и делает это не так, как Edge. Чтобы кадр показывал именно
тот уровень, который стиль отводит этому экрану (style/options), скрипт
подбирает настройку карты adjustDetailLevel. То есть кадры показывают,
как стиль задуман, а не как Edge на самом деле переключает уровни.
"""

import hashlib
import itertools
import math
import os
import shutil
import struct
import subprocess
import sys
import time
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QMS_APP = "/Applications/QMapShack.app"
# Каталог вне ~/Desktop: иначе macOS спросит у QMapShack доступ к папке
WORK = os.path.join(os.environ.get("TMPDIR", "/tmp"), "garmin-map-qms")

FRAME_W, FRAME_H = 480, 640      # область карты на Edge 1050, точки
_CAPTURE_NO = itertools.count(1)

# Шаги масштаба QMapShack (метров проекции Меркатора на точку экрана)
ZOOM_STEPS = [0.10, 0.15, 0.20, 0.30, 0.50, 0.70, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0,
              50.0, 70.0, 100.0, 150.0, 200.0, 300.0, 500.0, 700.0, 1000.0]

# Экраны SPEC.md: имя, шаг масштаба QMapShack, разрешение Garmin по style/options,
# и линейка, которая рисуется на кадре (метры, подпись)
SCREENS = [
    ("1-2km",  50.0, 20, 2000, "2 km"),
    ("2-500m", 15.0, 22,  500, "500 m"),
    ("3-150m",  3.0, 23,  150, "150 m"),   # при 5.0 QMapShack не рисует подписи на линиях
    ("4-50m",   1.5, 24,   50, "50 m"),
]

# Места: имя, широта, долгота
PLACES = {
    "prague": [
        ("center",      50.0870, 14.4208),   # Старе-Место
        ("outskirts",   49.9760, 14.3930),   # Збраслав
        ("brdy-forest", 49.7001, 13.8561),   # лес в Средних Брдах, развилка лесных дорог
        ("interchange", 50.1749, 14.4528),   # D8, съезд Здибы
    ],
}


def natural_bits(scale):
    """Какое разрешение QMapShack выбрал бы сам (CMapIMG::scale2bits)."""
    table = [(70000, 2), (50000, 3), (30000, 4), (20000, 5), (15000, 6), (10000, 7), (7000, 8), (5000, 9),
             (3000, 10), (2000, 11), (1500, 12), (1000, 13), (700, 14), (500, 15), (300, 16), (200, 17),
             (100, 18), (70, 19), (30, 20), (15, 21), (7, 22), (3, 23)]
    for limit, bits in table:
        if scale >= limit:
            return bits
    return 24


def qvariant_pointf(x, y):
    """QPointF в том виде, в каком его хранит QSettings в ini-файле."""
    raw = struct.pack(">I", 26) + struct.pack(">dd", x, y)
    return "@Variant(" + "".join("\\x%02x" % b for b in raw) + ")"


def qt_bytes(raw):
    return "@ByteArray(" + "".join("\\x%02x" % b for b in raw) + ")"


def window_geometry(x=40, y=40, width=1240, height=860, title=28):
    """Положение окна в формате QWidget::saveGeometry: окно всегда одного размера,
    на каком бы экране и с какими панелями его ни открыли."""
    frame = (x, y, x + width - 1, y + height - 1)
    inner = (x, y + title, x + width - 1, y + height - 1)
    raw = struct.pack(">IHH", 0x1D9D0CB, 3, 0)
    raw += struct.pack(">4i", *frame) + struct.pack(">4i", *inner)
    raw += struct.pack(">iBBi", 0, 0, 0, 1512) + struct.pack(">4i", *inner)
    return qt_bytes(raw)


def write_config(path, map_file, lat, lon, zoom, adjust, back="#F1EFE6", fixed_window=True):
    """Файл настроек QMapShack. Без map_file — пустое окно (для замера области карты)."""
    view = "Views\\View1\\"
    lines = [
        "[Canvas]",
        "canvasOrder=View1",
        "visibleCanvas=View1",
        "isScaleVisible=false",
        "isGridVisible=false",
        "POIText=true",
        view + "name=View 1",
        view + "scales=0",
        view + "backColor=" + back,
        view + "posFocus=" + qvariant_pointf(math.radians(lon), math.radians(lat)),
        view + "map2\\zoomIndex=%d" % ZOOM_STEPS.index(zoom),
    ]
    if map_file:
        with open(map_file, "rb") as handle:
            key = hashlib.md5(handle.read(4096)).hexdigest()
        lines += [
            "mapPath=" + os.path.dirname(map_file),
            view + "map2\\keysKnownMaps=" + key,
            view + "map2\\%s\\isActive=true" % key,
            view + "map2\\%s\\filename=%s" % (key, map_file),
            view + "map2\\%s\\adjustDetailLevel=%d" % (key, adjust),
        ]
    if fixed_window:
        lines += ["", "[MainWindow]", "geometry=" + window_geometry()]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


JXA = """
ObjC.import('CoreGraphics');
var list = ObjC.deepUnwrap(ObjC.castRefToObject(
    $.CGWindowListCopyWindowInfo($.kCGWindowListExcludeDesktopElements, 0)));
var out = [];
list.forEach(function (w) {
    if (w.kCGWindowOwnerPID == %d && w.kCGWindowLayer == 0) {
        var b = w.kCGWindowBounds;
        out.push([w.kCGWindowNumber, b.X, b.Y, b.Width, b.Height].join(' '));
    }
});
out.join('\\n');
"""


def find_window(pid):
    """Самое большое окно процесса: (id, x, y, ширина, высота) в точках."""
    res = subprocess.run(["osascript", "-l", "JavaScript", "-e", JXA % pid], capture_output=True, text=True)
    best = None
    for line in res.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) == 5:
            wid, x, y, w, h = int(parts[0]), *map(float, parts[1:])
            if best is None or w * h > best[3] * best[4]:
                best = (wid, x, y, w, h)
    return best


def capture(map_file, lat, lon, zoom, adjust, back="#F1EFE6"):
    """Кадр окна QMapShack; при сбое программа запускается заново (до трёх раз)."""
    error = None
    for _ in range(3):
        try:
            return capture_once(map_file, lat, lon, zoom, adjust, back)
        except RuntimeError as exc:
            error = exc
            time.sleep(2.0)
    raise error


def capture_once(map_file, lat, lon, zoom, adjust, back):
    """Запускает QMapShack с нужным видом и снимает его окно. Возвращает (пиксели, ширина окна в точках)."""
    # Файл настроек свой на каждый запуск. QMapShack при выходе записывает настройки обратно,
    # и с общим файлом он иногда затирал настройки следующего кадра: тот снимался с прежней
    # картой или с прежнего места.
    cfg = os.path.join(WORK, "qms-%d-%d.ini" % (os.getpid(), next(_CAPTURE_NO)))
    write_config(cfg, map_file, lat, lon, zoom, adjust, back)
    full = os.path.join(WORK, "full.png")
    bmp = os.path.join(WORK, "full.bmp")
    # open -g: окно открывается позади остальных и не забирает фокус у пользователя.
    # Свой домашний каталог нужен потому, что QMapShack не запускается вторым экземпляром
    # (файл-замок в ~/Library/Application Support), а окно просмотра (view.sh) может быть открыто.
    home = os.path.join(WORK, "home")
    os.makedirs(home, exist_ok=True)
    subprocess.run(["open", "-g", "-n", "--env", "CFFIXED_USER_HOME=" + home, "--env", "HOME=" + home,
                    "-a", QMS_APP, "--args", "-n", "-c", cfg], check=True)
    proc = None
    try:
        window = None
        for _ in range(60):
            time.sleep(0.5)
            if proc is None:
                found = subprocess.run(["pgrep", "-f", cfg], capture_output=True, text=True).stdout.split()
                if not found:
                    continue
                proc = int(found[0])
            window = find_window(proc)
            if window and window[3] > 600:
                break
        if not window:
            raise RuntimeError("окно QMapShack не появилось")
        time.sleep(2.0)                      # окно встаёт на место
        # Снимаем, пока два кадра подряд не совпадут: значит, карта дорисована
        # и индикатор загрузки пропал.
        previous, error = None, ""
        for _ in range(20):
            window = find_window(proc) or window         # окно может на миг пропасть из списка
            if os.path.exists(full):
                os.remove(full)
            res = subprocess.run(["screencapture", "-x", "-o", "-l", str(window[0]), full],
                                 capture_output=True, text=True)
            if res.returncode != 0 or not os.path.exists(full):
                error = res.stderr.strip()
                time.sleep(1.5)
                continue
            # Сравнивается только середина окна (там карта): по краям мигает курсор в поле поиска
            centre = os.path.join(WORK, "centre.png")
            subprocess.run(["sips", "-c", "600", "600", full, "--out", centre], capture_output=True, check=True)
            with open(centre, "rb") as handle:
                current = hashlib.md5(handle.read()).digest()
            # (в пробном кадре карты нет, там страница справки — норма)
            if current == previous and (map_file is None or not is_blank(centre)):
                break
            previous = current
            time.sleep(1.2)
        else:
            raise RuntimeError("кадр не получился: %s" %
                               (error + " (нужно разрешение на запись экрана)" if error else "карта не дорисовалась"))
    finally:
        if proc is not None:
            subprocess.run(["kill", str(proc)], capture_output=True)
            for _ in range(20):                  # ждём, пока программа действительно выйдет
                time.sleep(0.25)
                if subprocess.run(["kill", "-0", str(proc)], capture_output=True).returncode != 0:
                    break
            else:
                subprocess.run(["kill", "-9", str(proc)], capture_output=True)
                time.sleep(0.5)
        if os.path.exists(cfg):
            os.remove(cfg)
    # Снимок помечен профилем экрана (Display P3). Профиль снимается, чтобы числа цветов
    # остались теми, что нарисовал QMapShack (они равны цветам TYP), без пересчёта в sRGB.
    subprocess.run(["sips", "-d", "profile", full], capture_output=True, check=True)
    subprocess.run(["sips", "-s", "format", "bmp", full, "--out", bmp], capture_output=True, check=True)
    return read_bmp(bmp), window[3]


def is_blank(png):
    """Пока карта не включилась, QMapShack показывает белую страницу справки."""
    bmp = png[:-4] + ".bmp"
    subprocess.run(["sips", "-s", "format", "bmp", png, "--out", bmp], capture_output=True, check=True)
    _w, _h, rows = read_bmp(bmp)
    white = sum(row.count(bytes((255, 255, 255))) for row in rows[::8])
    total = sum(len(row) // 3 for row in rows[::8])
    return white > 0.6 * total


def read_bmp(path):
    """BMP -> (ширина, высота, строки сверху вниз в RGB)."""
    with open(path, "rb") as handle:
        data = handle.read()
    offset = struct.unpack_from("<I", data, 10)[0]
    width, height = struct.unpack_from("<ii", data, 18)
    bpp = struct.unpack_from("<H", data, 28)[0] // 8
    stride = (width * bpp + 3) & ~3
    rows = []
    for y in range(abs(height)):
        raw = data[offset + y * stride: offset + y * stride + width * bpp]
        rgb = bytearray(width * 3)
        rgb[0::3] = raw[2::bpp]
        rgb[1::3] = raw[1::bpp]
        rgb[2::3] = raw[0::bpp]
        rows.append(rgb)
    if height > 0:
        rows.reverse()
    return width, abs(height), rows


def write_png(path, width, rows):
    def chunk(tag, payload):
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, len(rows), 8, 2, 0, 0, 0)))
        handle.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        handle.write(chunk(b"IEND", b""))


def find_canvas(image):
    """Прямоугольник области карты: её фон в пробном кадре закрашен пурпурным."""
    width, height, rows = image
    marker = bytes((255, 0, 255)) * 8
    xs, ys = [], []
    for y, row in enumerate(rows):
        first = row.find(marker)
        if first >= 0:
            xs += [first // 3, (row.rfind(marker) + len(marker)) // 3]
            ys.append(y)
    if not ys:
        raise RuntimeError("не нашёл область карты в окне QMapShack")
    return min(xs), min(ys), max(xs), max(ys) + 1


# Шрифт 5x7 для подписи масштабной линейки
GLYPHS = {
    "0": "01110 10001 10011 10101 11001 10001 01110", "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00010 00100 01000 11111", "5": "11111 10000 11110 00001 00001 10001 01110",
    "k": "10000 10000 10010 10100 11000 10100 10010", "m": "00000 00000 11010 10101 10101 10101 10101",
    " ": "00000 00000 00000 00000 00000 00000 00000",
}


def fill(rows, x0, y0, x1, y1, colour):
    for y in range(max(0, y0), min(len(rows), y1)):
        rows[y][x0 * 3:x1 * 3] = bytes(colour) * (x1 - x0)


def draw_scale(rows, width, metres, metres_per_px, label, k):
    """Линейка с подписью в правом нижнем углу, как на мокапах. k — пикселей на точку."""
    length = int(round(metres / metres_per_px))
    x1 = width - 24 * k
    x0 = x1 - length
    y = len(rows) - 28 * k
    text_w = len(label) * 6 * 2 * k
    tx = (x0 + x1) // 2 - text_w // 2
    fill(rows, min(x0, tx) - 4 * k, y - 26 * k, x1 + 4 * k, y + 10 * k, (241, 239, 230))
    fill(rows, x0, y, x1, y + 2 * k, (17, 17, 17))
    fill(rows, x0, y - 5 * k, x0 + 2 * k, y + 7 * k, (17, 17, 17))
    fill(rows, x1 - 2 * k, y - 5 * k, x1, y + 7 * k, (17, 17, 17))
    for i, ch in enumerate(label):
        for gy, bits in enumerate(GLYPHS[ch].split()):
            for gx, bit in enumerate(bits):
                if bit == "1":
                    px, py = tx + (i * 6 + gx) * 2 * k, y - 22 * k + gy * 2 * k
                    fill(rows, px, py, px + 2 * k, py + 2 * k, (17, 17, 17))


def read_png(path):
    """Читает PNG, записанный write_png (RGB, без фильтров)."""
    with open(path, "rb") as handle:
        data = handle.read()
    pos, idat, width, height = 8, b"", 0, 0
    while pos < len(data):
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        if tag == b"IHDR":
            width, height = struct.unpack(">II", data[pos + 8:pos + 16])
        elif tag == b"IDAT":
            idat += data[pos + 8:pos + 8 + size]
        pos += 12 + size
    raw = zlib.decompress(idat)
    stride = width * 3 + 1
    return width, [raw[y * stride + 1:(y + 1) * stride] for y in range(height)]


def halve(rows):
    """Уменьшение вдвое усреднением 2x2."""
    out = []
    for y in range(0, len(rows) - 1, 2):
        r0, r1 = rows[y], rows[y + 1]
        row = bytearray(len(r0) // 2)
        for c in range(3):
            row[c::3] = bytes((a + b + d + e) >> 2 for a, b, d, e in
                              zip(r0[c::6], r0[c + 3::6], r1[c::6], r1[c + 3::6]))
        out.append(row)
    return out


def contact_sheets(out_dir, region, k):
    """Лист на каждое место: четыре масштаба в ряд, кадры 480x640."""
    gap = 16
    for place, _lat, _lon in PLACES[region]:
        frames = []
        for screen, *_ in SCREENS:
            path = os.path.join(out_dir, "%s_%s.png" % (place, screen))
            if not os.path.exists(path):
                break
            _w, rows = read_png(path)
            frames.append(halve(rows) if k == 2 else rows)
        else:
            sep = bytes((255, 255, 255)) * gap
            sheet = [sep.join(bytes(f[y]) for f in frames) for y in range(len(frames[0]))]
            target = os.path.join(out_dir, "_sheet_%s.png" % place)
            write_png(target, len(sheet[0]) // 3, sheet)
            print(os.path.relpath(target, ROOT))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    step = args[0]
    region = args[1] if len(args) > 1 else "prague"
    only = args[2] if len(args) > 2 else None          # одно место, для быстрой проверки
    src = os.path.join(ROOT, "out", region + ".img")
    if not os.path.exists(src):
        sys.exit("нет %s — сначала ./build.sh %s" % (src, region))
    for arg in sys.argv[1:]:
        if arg.startswith("--at="):                     # разовая проверка: --at=широта,долгота
            lat, lon = map(float, arg[5:].split(","))
            PLACES[region] = [("test", lat, lon)]
            only = None
    if region not in PLACES:
        sys.exit("для региона %s не заданы места съёмки (PLACES в этом файле)" % region)
    os.makedirs(WORK, exist_ok=True)
    map_dir = os.path.join(WORK, "maps")
    shutil.rmtree(map_dir, ignore_errors=True)
    os.makedirs(map_dir)
    map_file = os.path.join(map_dir, region + ".img")
    shutil.copy(src, map_file)
    out_dir = os.path.join(ROOT, "screenshots", step)
    os.makedirs(out_dir, exist_ok=True)

    if "--sheets-only" in sys.argv:
        contact_sheets(out_dir, region, 2)
        return

    _name, lat0, lon0 = PLACES[region][0]

    def probe():
        """Пробный кадр без карты: где в окне область карты и сколько пикселей в точке."""
        image, window_w = capture(None, lat0, lon0, 15.0, 0, back="#FF00FF")
        k = round(image[0] / window_w)
        left, top, right, bottom = find_canvas(image)
        if right - left < FRAME_W * k or bottom - top < FRAME_H * k:
            sys.exit("область карты QMapShack (%dx%d точек) меньше кадра %dx%d" %
                     ((right - left) // k, (bottom - top) // k, FRAME_W, FRAME_H))
        print("область карты: %dx%d точек, плотность x%d" % ((right - left) // k, (bottom - top) // k, k))
        return image[:2], k, (left + right) // 2, (top + bottom) // 2

    probe_size, k, cx, cy = probe()

    for place, lat, lon in PLACES[region]:
        if only and place != only:
            continue
        for screen, zoom, bits, metres, label in SCREENS:
            adjust = bits - natural_bits(zoom)
            for _attempt in range(4):
                image, _ = capture(map_file, lat, lon, zoom, adjust)
                if image[:2] == probe_size:
                    break
                probe_size, k, cx, cy = probe()   # окно открылось на другом экране: замеряем заново
            else:
                sys.exit("окно QMapShack меняет размер между запусками, кадр %s %s не снят" % (place, screen))
            fw, fh = FRAME_W * k, FRAME_H * k
            _w, _h, rows = image
            x0, y0 = cx - fw // 2, cy - fh // 2
            frame = [bytearray(row[x0 * 3:(x0 + fw) * 3]) for row in rows[y0:y0 + fh]]
            draw_scale(frame, fw, metres, zoom * math.cos(math.radians(lat)) / k, label, k)
            out = os.path.join(out_dir, "%s_%s.png" % (place, screen))
            write_png(out, fw, frame)
            print("%s  (разрешение %d, %.1f м/точку)" % (os.path.relpath(out, ROOT), bits,
                                                         zoom * math.cos(math.radians(lat))))
    contact_sheets(out_dir, region, k)


if __name__ == "__main__":
    main()
