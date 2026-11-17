#!/usr/bin/env python3
"""Собирает style/typ.txt — TYP в текстовом виде для компилятора mkgmap.

Толщины линий в TYP задаются в пикселях экрана и не меняются с масштабом,
поэтому у каждого класса линии есть до четырёх вариантов типа — по одному
на ступень масштаба (см. style/lines). Здесь лежит одна таблица на все
ступени, чтобы толщины и цвета правились в одном месте.

    python3 typ/make_typ.py            # пишет style/typ.txt

Толщины подобраны под Edge 1050 (480x800). Для Edge 830 (246x322) нужен
второй набор толщин — добавить вторую таблицу и параметр.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import icons  # noqa: E402

# --------------------------------------------------------------------------
# Палитра. Основа — SPEC.md; отмечено, что изменено по ходу работы.
# --------------------------------------------------------------------------
BG = "#F1EFE6"
FOREST = "#D3E2BF"
PARK = "#C6E2A6"             # парки и сады: свежее и насыщеннее леса (проба, сверх SPEC)
MEADOW = "#E4EDCB"           # луга и газоны: бледно-зелёные (проба, сверх SPEC)
PLANTATION = "#E0EBC8"       # виноградник, хмельник, гольф (сверх SPEC)
PLANTATION_MARK = "#8FA66E"
BUILTUP = "#E2D3B8"
INDUSTRIAL = "#DAD7CE"
CEMETERY = "#DDE6CF"
CEMETERY_CROSS = "#6F7F63"
WATER = "#A9C8E0"
WETLAND = "#7FB2D6"          # из мокапа: штрихи болота темнее воды
CLOSED_HATCH = "#8E8B82"     # из мокапа
GREEN, GREEN_EDGE = "#A8D57E", "#4F8A3C"           # заливка задана заказчиком: rgb(168, 213, 126)
PRIMARY, PRIMARY_EDGE = "#F7CE84", "#8A5A14"       # заливка задана заказчиком: rgb(247, 206, 132)
SECONDARY, SECONDARY_EDGE = "#F8EE87", "#8C7A3A"   # заливка задана заказчиком: rgb(248, 238, 135)
WHITE, WHITE_EDGE = "#FFFFFF", "#8C8270"
PEDESTRIAN, PEDESTRIAN_EDGE = "#F4ECDC", "#B5A88C"   # из мокапа
CYCLE = "#D238B8"
MTB = "#0E8A7D"
RAIL = "#33312D"             # железная дорога, бортики мостов, стрелки
NO_ENTRY = "#B3261E"         # из мокапа: красные точки
GRAVEL, GRAVEL_EDGE = "#F5EBD8", "#8F7A5C"
BAD_TRACK = "#5A4630"
PATH = "#6B5A3C"
HARD_PATH = "#A32D2D"
FERRY = "#1F5FBF"
BORDER = "#7A5C8E"
LABEL = "#1B1B1A"

# Все цвета палитры по именам — в том порядке, в каком их видит конфигуратор (site/).
PALETTE_NAMES = (
    "BG", "FOREST", "PARK", "MEADOW", "PLANTATION", "PLANTATION_MARK", "BUILTUP", "INDUSTRIAL",
    "CEMETERY", "CEMETERY_CROSS", "WATER", "WETLAND", "CLOSED_HATCH",
    "GREEN", "GREEN_EDGE", "PRIMARY", "PRIMARY_EDGE", "SECONDARY", "SECONDARY_EDGE",
    "WHITE", "WHITE_EDGE", "PEDESTRIAN", "PEDESTRIAN_EDGE", "CYCLE", "MTB", "RAIL", "NO_ENTRY",
    "GRAVEL", "GRAVEL_EDGE", "BAD_TRACK", "PATH", "HARD_PATH", "FERRY", "BORDER", "LABEL",
)


def _override_palette():
    """Подмена цветов из JSON-файла {"ИМЯ": "#RRGGBB"}; путь — в переменной TYP_PALETTE.
    Нужна конфигуратору (scripts/make_site.py). Стоит до таблиц: они читают цвета при загрузке."""
    path = os.environ.get("TYP_PALETTE")
    if not path:
        return
    import json
    with open(path, encoding="utf-8") as handle:
        custom = json.load(handle)
    unknown = sorted(set(custom) - set(PALETTE_NAMES))
    if unknown:
        sys.exit("TYP_PALETTE: неизвестные цвета %s" % ", ".join(unknown))
    globals().update({name: value.upper() for name, value in custom.items()})


_override_palette()


def palette():
    """Действующая палитра: имя -> "#RRGGBB"."""
    return {name: globals()[name] for name in PALETTE_NAMES}


# --------------------------------------------------------------------------
# Номера типов линий
# --------------------------------------------------------------------------
TIERS = ("24", "23", "22", "18-21")          # ступени масштаба: индекс -> разрешения Garmin
LAYER_UNDER, LAYER_BASE, LAYER_BRIDGE, LAYER_OVER = 0, 1, 3, 4   # тоннели, дороги, мосты, накладки


def line_type(tier, rank, layer=LAYER_BASE):
    """0x1TTSS: TT = ступень и слой, SS = место в порядке отрисовки."""
    return 0x10000 | ((0x40 + 0x10 * tier + layer) << 8) | rank


def common_type(rank):
    """Линии, одинаковые на всех масштабах."""
    return 0x18000 | rank


def lighten(colour, share=0.5):
    """Осветление для тоннелей: смесь с белым."""
    rgb = [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(round(c + (255 - c) * share) for c in rgb)


# --------------------------------------------------------------------------
# Узоры линий: список строк по 32 символа, высота = толщина линии.
# X — первый цвет, точка — второй (или прозрачно).
# --------------------------------------------------------------------------
def rail_bitmap(height):
    """Тёмная линия с белыми штрихами внутри."""
    return ["X" * 32 if y in (0, height - 1) else ("." * 8 + "X" * 8) * 2 for y in range(height)]


def no_entry_bitmap(height):
    """Белая полоса с красными точками."""
    dot = 3 if height >= 6 else 2
    dotted = "".join("." if x % 8 < dot else "X" for x in range(32))
    return ["X" * 32 if y in (0, height - 1) else dotted for y in range(height)]


def dash_bitmap(height, start, end, period=16):
    """Штрихи: закрашены столбцы start..end-1 в каждом периоде."""
    row = "".join("X" if start <= x % period < end else "." for x in range(32))
    return [row] * height


def edge_dash_bitmap(height, edge):
    """Сплошная заливка (точки), по краям пунктирная обводка (X): штрих 10, пробел 6."""
    dashed = "".join("X" if x % 16 < 10 else "." for x in range(32))
    return [dashed if y < edge or y >= height - edge else "." * 32 for y in range(height)]


def footbridge_bitmap(height, edge):
    """Мостик: тёмные бортики, фон между ними, по оси тёмный пунктир тропы."""
    dashed = "".join("X" if x % 8 < 5 else "." for x in range(32))
    middle = (height // 2 - 1, height // 2)
    rows = []
    for y in range(height):
        if y < edge or y >= height - edge:
            rows.append("X" * 32)
        else:
            rows.append(dashed if y in middle else "." * 32)
    return rows


def side_bitmap(offset, thickness, pattern, bottom=False):
    """Узор сбоку от линии: полоска толщиной thickness на расстоянии offset от оси.
    Остальная высота прозрачна. bottom=True — с другой стороны."""
    height = 2 * (offset + thickness)
    row = "".join("X" if pattern(x) else "." for x in range(32))
    rows = [row if y < thickness else "." * 32 for y in range(height)]
    return rows[::-1] if bottom else rows


# --------------------------------------------------------------------------
# Основной слой. Ступени идут в порядке TIERS: 24, 23, 22, 18-21;
# None — на этой ступени типа нет.
#   SOLID:  (толщина, обводка)
#   BITMAP: высота узора
# --------------------------------------------------------------------------
SOLID = [
    # rank  название                     заливка     обводка          24       23       22       18-21
    (0x00, "Ручей",                      WATER,      None,            (3, 0),  (2, 0),  None,    None),
    (0x01, "Река, канал",                WATER,      None,            (5, 0),  (4, 0),  (3, 0),  (2, 0)),
    (0x08, "Асфальтовая дорожка",        WHITE,      GRAVEL_EDGE,     (3, 1),  (2, 1),  None,    None),
    (0x0a, "Хорошая гравийка",           GRAVEL,     GRAVEL_EDGE,     (6, 2),  (5, 2),  (3, 1),  None),
    (0x0d, "Проезд запрещён, подложка",  WHITE_EDGE, None,            (10, 0), (6, 0),  None,    None),
    (0x0f, "Пешеходная зона",            PEDESTRIAN, PEDESTRIAN_EDGE, (8, 2),  None,    None,    None),
    (0x10, "Улица, проезд",              WHITE,      WHITE_EDGE,      (6, 2),  (4, 1),  (2, 1),  None),
    (0x12, "Дорога III класса",          WHITE,      WHITE_EDGE,      (8, 2),  (6, 1),  (4, 1),  (2, 1)),
    (0x13, "Дорога II класса",           SECONDARY,  SECONDARY_EDGE,  (10, 2), (7, 2),  (6, 1),  (3, 1)),
    (0x14, "Дорога I класса",            PRIMARY,    PRIMARY_EDGE,    (12, 2), (9, 2),  (7, 2),  (4, 1)),
    (0x15, "Съезд, дорога для авто",     GREEN,      GREEN_EDGE,      (6, 2),  (4, 1),  (3, 1),  (2, 1)),
    (0x16, "Автомагистраль, запрет",     GREEN,      GREEN_EDGE,      (10, 2), (8, 2),  (7, 2),  (6, 1)),
    # Велодорожка лежит поверх заливок дорог. Обводка того же цвета нужна, чтобы
    # QMapShack рисовал её во втором проходе, вместе с заливками (см. NOTES.md).
    (0x18, "Велодорожка",                CYCLE,      CYCLE,           (2, 1),  (1, 1),  (1, 1),  None),
]

BITMAP = [
    # rank  название                     узор                                   цвет 1      цвет 2    высота: 24, 23, 22, 18-21
    (0x02, "Пересыхающий ручей",         lambda h: dash_bitmap(h, 0, 5, 8),     WETLAND,    None,     (3, 2, None, None)),
    (0x03, "Железная дорога",            rail_bitmap,                           RAIL,       WHITE,    (5, 4, 3, 3)),
    (0x04, "Плохой грунт",               lambda h: dash_bitmap(h, 0, 10),       BAD_TRACK,  None,     (4, 3, None, None)),
    (0x05, "Тропа",                      lambda h: dash_bitmap(h, 0, 5, 8),     PATH,       None,     (3, 2, None, None)),
    (0x06, "Сложная тропа",              lambda h: dash_bitmap(h, 0, 5, 8),     HARD_PATH,  None,     (3, 3, None, None)),
    (0x07, "Лестница",                   lambda h: dash_bitmap(h, 0, 2, 4),     PATH,       None,     (8, None, None, None)),
    (0x09, "Двухколейка",                lambda h: edge_dash_bitmap(h, 2 if h > 5 else 1), GRAVEL_EDGE, GRAVEL, (10, 9, 5, None)),
    (0x0b, "Строится, подложка",         lambda h: dash_bitmap(h, 0, 10),       WHITE_EDGE, None,     (10, 6, None, None)),
    (0x0c, "Строится",                   lambda h: dash_bitmap(h, 1, 9),        WHITE,      None,     (6, 4, None, None)),
    (0x0e, "Проезд запрещён",            no_entry_bitmap,                       WHITE,      NO_ENTRY, (6, 4, None, None)),
]

# Подписи на линиях основного слоя: rank -> (размер шрифта, цвет). У остальных подписей нет.
LINE_LABELS = {
    0x05: ("NormalFont", PATH),
    0x06: ("NormalFont", HARD_PATH),
}

# Классы дорог, у которых есть варианты «тоннель» и «мост»
ROAD_RANKS = (0x10, 0x12, 0x13, 0x14, 0x15, 0x16)


def route_dash(x):
    return x % 16 < 10


def route_dot(x):
    return x % 8 < 3


# Накладки маршрутов (слой LAYER_OVER): rank, название, цвет, узор, с другой стороны?,
# толщина, отступ от оси по ступеням 24 / 23 / 22
ROUTES = [
    (0x01, "Веломаршрут",                  CYCLE, route_dash, False, 3, (8, 7, 5)),
    (0x02, "Веломаршрут у широкой дороги", CYCLE, route_dash, False, 3, (11, 9, 7)),
    (0x03, "МТБ-маршрут",                  MTB,   route_dot,  True,  3, (8, 7, None)),
    (0x04, "МТБ-маршрут у широкой дороги", MTB,   route_dot,  True,  3, (11, 9, None)),
]


# --------------------------------------------------------------------------
# Площади: тип, название, уровень отрисовки (больше = выше), цвета, узор
# --------------------------------------------------------------------------
def hatch_bitmap():
    """Диагональная штриховка, шаг 16 px, линия 2 px."""
    return ["".join("X" if (x + y) % 16 < 2 else "." for x in range(32)) for y in range(32)]


def wetland_bitmap():
    """Горизонтальные штрихи в шахматном порядке."""
    rows = []
    for y in range(32):
        if y % 16 in (4, 5):
            rows.append(("X" * 8 + "." * 8) * 2)
        elif y % 16 in (12, 13):
            rows.append(("." * 8 + "X" * 8) * 2)
        else:
            rows.append("." * 32)
    return rows


def cemetery_bitmap():
    """Два крестика на плитку."""
    grid = [["."] * 32 for _ in range(32)]
    for cx, top in ((7, 3), (23, 19)):
        for y in range(top, top + 12):          # вертикаль 2x12
            grid[y][cx] = grid[y][cx + 1] = "X"
        for x in range(cx - 3, cx + 5):         # перекладина 8x2
            grid[top + 3][x] = grid[top + 4][x] = "X"
    return ["".join(r) for r in grid]


def glyph_bitmap(glyph):
    """Два значка на плитку 32x32 в шахматном порядке."""
    grid = [["."] * 32 for _ in range(32)]
    for ox, oy in ((5, 4), (21, 20)):
        for y, line in enumerate(glyph):
            for x, ch in enumerate(line):
                if ch == "X":
                    grid[oy + y][ox + x] = "X"
    return ["".join(r) for r in grid]


VINE = [".XXX.", "X...X", "X....", ".XX..", "...X.", "....X", "X...X", ".XXX."]
HOP = ["..X..", ".XX..", "X.X..", "..XX.", "..X.X", ".XX..", "X.X..", "..X..", "..X.."]
RING = [".XXXX.", "X....X", "X....X", "X....X", "X....X", ".XXXX."]

POLYGONS = [
    # тип   название              уровень  цвет 1           цвет 2      узор
    (0x4b, "Фон",                 1,       BG,              None,       None),
    (0x01, "Застройка",           2,       BUILTUP,         None,       None),
    (0x52, "Луг, газон",          3,       MEADOW,          None,       None),
    (0x17, "Парк, сад",           4,       PARK,            None,       None),
    (0x50, "Лес",                 5,       FOREST,          None,       None),
    (0x4e, "Виноградник",         5,       PLANTATION_MARK, PLANTATION, lambda: glyph_bitmap(VINE)),
    (0x4f, "Хмельник",            5,       PLANTATION_MARK, PLANTATION, lambda: glyph_bitmap(HOP)),
    (0x18, "Гольф-поле",          5,       WHITE,           PLANTATION, lambda: glyph_bitmap(RING)),
    (0x0c, "Промзона, карьер",    6,       INDUSTRIAL,      None,       None),
    (0x1a, "Кладбище",            7,       CEMETERY_CROSS,  CEMETERY,   cemetery_bitmap),
    (0x13, "Пешеходная площадь",  7,       PEDESTRIAN,      None,       None),
    (0x51, "Болото",              8,       WETLAND,         None,       wetland_bitmap),
    (0x3c, "Вода",                9,       WATER,           None,       None),
    (0x04, "Закрытая территория", 10,      CLOSED_HATCH,    None,       hatch_bitmap),
]

# --------------------------------------------------------------------------
# Точки: тип, название, размер подписи, значок (None — только подпись).
# В TYP три размера шрифта, поэтому city и town подписаны одинаково.
# --------------------------------------------------------------------------
POINTS = [
    (0x0300, "Город (city)",     "LargeFont",  None),
    (0x0700, "Город (town)",     "LargeFont",  None),
    (0x0a00, "Село (village)",   "NormalFont", None),
    (0x0d00, "Деревня (hamlet)", "SmallFont",  None),
    # Значки: скруглённый квадрат 22x22 с белым символом, без подписи
    (0x2e02, "Продуктовый магазин", "NoLabel", lambda: icons.icon_xpm("shop", icons.DARK)),
    (0x2f01, "Заправка",            "NoLabel", lambda: icons.icon_xpm("fuel", icons.DARK)),
    (0x2f08, "Станция",             "NoLabel", lambda: icons.icon_xpm("station", icons.DARK)),
    (0x5000, "Питьевая вода",       "NoLabel", lambda: icons.icon_xpm("water", icons.BLUE)),
    (0x6511, "Родник",              "NoLabel", lambda: icons.icon_xpm("spring", icons.BLUE)),
    (0x6508, "Брод",                "NoLabel", lambda: icons.icon_xpm("ford", icons.BLUE)),
    (0x6402, "Навес (lean-to)",     "NoLabel", lambda: icons.icon_xpm("shelter", icons.BROWN)),
    (0x6403, "Закрытый шелтер",     "NoLabel", lambda: icons.icon_xpm("hut", icons.BROWN)),
    (0x6614, "Перевал",             "SmallFont", lambda: icons.icon_xpm("pass", icons.BROWN)),
    (0x2f03, "Велоремонт",          "NoLabel", lambda: icons.icon_xpm("repair", icons.DARK)),
    (0x4e00, "Туалет",              "NoLabel", lambda: icons.icon_xpm("toilet", icons.DARK)),
]


# --------------------------------------------------------------------------
# Сборка списка линий: (тип, вид, название, параметры)
# --------------------------------------------------------------------------
def collect_lines():
    lines = []

    def solid(type_id, name, fill, edge, width, border):
        lines.append((type_id, "solid", name, (fill, edge, width, border), None))

    def bitmap(type_id, name, rows, colour1, colour2, label=None):
        lines.append((type_id, "bitmap", name, (rows, colour1, colour2), label))

    roads = {}                                        # rank -> (название, заливка, обводка, размеры)
    for rank, name, fill, edge, *per_tier in SOLID:
        roads[rank] = (name, fill, edge, per_tier)
        for tier, spec in enumerate(per_tier):
            if spec:
                solid(line_type(tier, rank), "%s, разрешение %s" % (name, TIERS[tier]), fill, edge, *spec)

    for rank, name, pattern, colour1, colour2, heights in BITMAP:
        for tier, height in enumerate(heights):
            if height:
                bitmap(line_type(tier, rank), "%s, разрешение %s" % (name, TIERS[tier]),
                       pattern(height), colour1, colour2, LINE_LABELS.get(rank))

    for tier in (0, 1):                               # тоннели и мосты: экраны 3 и 4
        res = TIERS[tier]
        for rank in ROAD_RANKS:
            name, fill, edge, per_tier = roads[rank]
            width, border = per_tier[tier]
            # Тоннель: осветлённая заливка, пунктирная обводка
            bitmap(line_type(tier, rank, LAYER_UNDER), "Тоннель: %s, разрешение %s" % (name, res),
                   edge_dash_bitmap(width + 2 * border, border), edge, lighten(fill))
            # Мост: та же заливка, тёмные бортики на пиксель шире обводки
            solid(line_type(tier, rank, LAYER_BRIDGE), "Мост: %s, разрешение %s" % (name, res),
                  fill, RAIL, width, border + 1)
        gravel_width, gravel_border = roads[0x0a][3][tier]
        solid(line_type(tier, 0x0a, LAYER_BRIDGE), "Мост: грунтовая дорога, разрешение %s" % res,
              GRAVEL, RAIL, gravel_width, gravel_border + 1)
        cycle_width, cycle_border = roads[0x18][3][tier]
        solid(line_type(tier, 0x18, LAYER_BRIDGE), "Мост: велодорожка, разрешение %s" % res,
              CYCLE, RAIL, cycle_width + 2 * cycle_border, 2)
        bitmap(line_type(tier, 0x05, LAYER_BRIDGE), "Пешеходный мостик, разрешение %s" % res,
               footbridge_bitmap(8 if tier == 0 else 6, 2 if tier == 0 else 1), RAIL, BG)
        bitmap(line_type(tier, 0x05, LAYER_OVER), "Подземный переход, разрешение %s" % res,
               dash_bitmap(4 if tier == 0 else 3, 0, 5, 8), WHITE, None)

    for rank, name, colour, pattern, bottom, thickness, offsets in ROUTES:
        for tier, offset in enumerate(offsets):
            if offset:
                bitmap(line_type(tier, rank, LAYER_OVER), "%s, разрешение %s" % (name, TIERS[tier]),
                       side_bitmap(offset, thickness, pattern, bottom), colour, None)

    bitmap(common_type(0x00), "Паром", dash_bitmap(2, 0, 9), FERRY, None)
    border_row = "".join("X" if x < 16 or 22 <= x < 26 else "." for x in range(32))
    bitmap(common_type(0x01), "Государственная граница", [border_row] * 3, BORDER, None)
    return lines


# --------------------------------------------------------------------------
# Вывод
# --------------------------------------------------------------------------
def xpm_colours(first, second):
    """Строки цветов для двухцветного узора; второй цвет None = прозрачный."""
    return ['"X c %s"' % first, '". c %s"' % (second or "none")]


def emit_polygon(out, type_id, name, colour1, colour2, pattern):
    out += ["[_polygon]", "; %s" % name, "Type=0x%02x" % type_id]
    if pattern is None:
        out += ['Xpm="0 0 1 0"', '"X c %s"' % colour1]
    else:
        rows = pattern()
        assert len(rows) == 32 and all(len(r) == 32 for r in rows), name
        out.append('Xpm="32 32 2 1"')
        out += xpm_colours(colour1, colour2)
        out += ['"%s"' % r for r in rows]
    out += ["[end]", ""]


def emit_line(out, type_id, kind, name, params, label):
    out += ["[_line]", "; %s" % name, "Type=0x%05x" % type_id]
    if label:
        out += ["ExtendedLabels=Y", "FontStyle=%s" % label[0], "DayCustomColor=%s" % label[1]]
    if kind == "solid":
        fill, edge, width, border = params
        out.append("LineWidth=%d" % width)
        if border:
            out += ["BorderWidth=%d" % border, 'Xpm="0 0 2 0"', '"1 c %s"' % fill, '"2 c %s"' % edge]
        else:
            out += ['Xpm="0 0 1 0"', '"1 c %s"' % fill]
    else:
        rows, colour1, colour2 = params
        assert all(len(r) == 32 for r in rows), name
        out.append('Xpm="32 %d 2 1"' % len(rows))
        out += xpm_colours(colour1, colour2)
        out += ['"%s"' % r for r in rows]
    out += ["[end]", ""]


def emit_point(out, type_id, name, font, icon):
    out += ["[_point]", "; %s" % name, "Type=0x%04x" % type_id,
            "ExtendedLabels=Y", "FontStyle=%s" % font, "DayCustomColor=%s" % LABEL]
    if icon is None:                      # значка нет: один прозрачный пиксель
        out += ['DayXpm="1 1 1 1"', '". c none"', '"."']
    else:
        out += icon
    out += ["[end]", ""]


def build():
    out = [
        "; -*- coding: utf-8 -*-",
        "; Сгенерировано typ/make_typ.py — руками не править, правки вносить в таблицы скрипта.",
        "; @FID@ и @CODEPAGE@ подставляет build.sh из конфига региона.",
        "",
        "[_id]",
        "ProductCode=1",
        "FID=@FID@",
        "CodePage=@CODEPAGE@",
        "[end]",
        "",
        "[_drawOrder]",
    ]
    for type_id, _name, level, *_ in sorted(POLYGONS, key=lambda p: p[2]):
        out.append("Type=0x%02x,%d" % (type_id, level))
    out += ["[end]", ""]

    for type_id, name, _level, colour1, colour2, pattern in POLYGONS:
        emit_polygon(out, type_id, name, colour1, colour2, pattern)

    seen = set()
    for entry in sorted(collect_lines(), key=lambda e: e[0]):
        assert entry[0] not in seen, hex(entry[0])
        seen.add(entry[0])
        emit_line(out, *entry)

    for type_id, name, font, icon in POINTS:
        emit_point(out, type_id, name, font, icon() if icon else None)
    return "\n".join(out)


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "style", "typ.txt")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(build())
    print("TYP: %s" % target)
