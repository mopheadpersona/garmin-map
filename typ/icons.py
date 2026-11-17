"""Значки точек: скруглённый квадрат 22x22 px с белым символом (SPEC.md, «Точки»).

Значки рисуются из простых фигур в координатах мокапа (центр в нуле,
от -11 до 11) и растрируются со сглаживанием. На выходе — XPM для TYP.
"""

import math

SIZE = 22
SS = 4                      # сглаживание: 4x4 отсчёта на пиксель
DARK = "#33312D"
BLUE = "#1F5FBF"
BROWN = "#6B5A3C"
WHITE = (255, 255, 255)


# --- фигуры: функции (x, y) -> внутри ли точка --------------------------------
def stroke(points, width):
    """Ломаная со скруглёнными концами."""
    half = width / 2.0
    segments = list(zip(points, points[1:]))

    def inside(x, y):
        for (x1, y1), (x2, y2) in segments:
            dx, dy = x2 - x1, y2 - y1
            length2 = dx * dx + dy * dy
            t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length2))
            if math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)) <= half:
                return True
        return False
    return inside


def polygon(points):
    def inside(x, y):
        hit = False
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                hit = not hit
        return hit
    return inside


def circle(cx, cy, radius):
    return lambda x, y: math.hypot(x - cx, y - cy) <= radius


def rounded_rect(x0, y0, x1, y1, radius):
    def inside(x, y):
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            return False
        cx = min(max(x, x0 + radius), x1 - radius)
        cy = min(max(y, y0 + radius), y1 - radius)
        return math.hypot(x - cx, y - cy) <= radius
    return inside


def wave(y0, width):
    """Волна на всю ширину значка."""
    pts = [(-6.5 + i * 0.5, y0 - 1.0 * math.sin(2 * math.pi * i * 0.5 / 6.5)) for i in range(27)]
    return stroke(pts, width)


def drop(tip_y, cy, radius):
    """Капля: круг и остриё сверху."""
    half = radius * 0.86
    return [circle(0, cy, radius), polygon([(0, tip_y), (-half, cy - radius * 0.5), (half, cy - radius * 0.5)])]


# --- символы: (белые фигуры, фигуры цвета фона поверх белого) ------------------
SYMBOLS = {
    "shop": ([polygon([(-6, -1), (6, -1), (4, 5.5), (-4, 5.5)]),
              stroke([(-3, -1), (0, -5.5), (3, -1)], 1.6)], []),
    "fuel": ([rounded_rect(-5, -5.5, 1.5, 5.5, 0.5),
              stroke([(1.5, -2), (5, -2), (5, 4.5)], 1.6)],
             [rounded_rect(-3.5, -4, 0, -1, 0.3)]),
    "station": ([rounded_rect(-4.5, -6.5, 4.5, 3.5, 2),
                 stroke([(-3, 4.5), (-5, 7)], 1.6), stroke([(3, 4.5), (5, 7)], 1.6)],
                [rounded_rect(-2.5, -4.5, 2.5, -1.5, 0.3)]),
    "water": (drop(-6.5, 2.5, 4.8), []),
    "spring": (drop(-7.5, -1.5, 3.6) + [wave(6, 1.6)], []),
    "ford": ([wave(-2, 1.8), wave(3.5, 1.8)], []),
    "shelter": ([stroke([(-6.5, 4), (0, -5), (6.5, 4)], 2.0),
                 stroke([(-4, 4), (-4, 6)], 2.0), stroke([(4, 4), (4, 6)], 2.0)], []),
    "pass": ([stroke([(-6.5, -5.5), (-4.3, -3), (-3.1, 0), (-4.3, 3), (-6.5, 5.5)], 2.0),
              stroke([(6.5, -5.5), (4.3, -3), (3.1, 0), (4.3, 3), (6.5, 5.5)], 2.0)], []),
}

def arc(cx, cy, radius, start, end, width):
    """Дуга окружности, углы в градусах (0 — вправо, по часовой на экране)."""
    pts = [(cx + radius * math.cos(math.radians(a)), cy + radius * math.sin(math.radians(a)))
           for a in range(start, end + 1, 15)]
    return stroke(pts, width)


# Закрытый шелтер: домик с дверью (открытый навес — "shelter": крыша на столбах)
SYMBOLS["hut"] = ([polygon([(-7.5, 0.5), (0, -6.5), (7.5, 0.5), (5.2, 0.5), (5.2, 6.2), (-5.2, 6.2), (-5.2, 0.5)])],
                  [rounded_rect(-1.6, 1.4, 1.6, 6.5, 0.2)])
# Туалет: буквы WC
SYMBOLS["toilet"] = ([stroke([(-7.6, -3.5), (-6.0, 3.5), (-4.4, -1.2), (-2.8, 3.5), (-1.2, -3.5)], 1.5),
                      arc(4.3, 0, 3.4, 50, 310, 1.5)], [])
# Велоремонт: гаечный ключ
SYMBOLS["repair"] = ([stroke([(-5.5, 5.5), (1.5, -1.5)], 2.6), circle(3.2, -3.2, 3.6)],
                     [stroke([(3.6, -3.6), (7.5, -7.5)], 2.4)])

OUTER = rounded_rect(-11, -11, 11, 11, 5)
INNER = rounded_rect(-9.8, -9.8, 9.8, 9.8, 3.8)      # между OUTER и INNER — белая рамка

CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def hex_to_rgb(colour):
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


def icon_xpm(symbol, background):
    """Строки DayXpm для значка."""
    white_shapes, cut_shapes = SYMBOLS[symbol]
    bg = hex_to_rgb(background)
    pixels = []
    for py in range(SIZE):
        row = []
        for px in range(SIZE):
            in_icon = white = 0
            for sy in range(SS):
                for sx in range(SS):
                    x = px + (sx + 0.5) / SS - SIZE / 2.0
                    y = py + (sy + 0.5) / SS - SIZE / 2.0
                    if not OUTER(x, y):
                        continue
                    in_icon += 1
                    if not INNER(x, y):
                        white += 1
                    elif any(s(x, y) for s in white_shapes) and not any(s(x, y) for s in cut_shapes):
                        white += 1
            if in_icon < SS * SS / 2:
                row.append(None)                                   # прозрачный угол
            else:
                level = round(4.0 * white / in_icon) / 4.0         # пять ступеней сглаживания
                row.append(tuple(round(b + (w - b) * level) for b, w in zip(bg, WHITE)))
        pixels.append(row)

    palette = {}
    for row in pixels:
        for value in row:
            if value not in palette:
                palette[value] = CHARS[len(palette)]
    out = ['DayXpm="%d %d %d 1"' % (SIZE, SIZE, len(palette))]
    for value, char in palette.items():
        out.append('"%s c %s"' % (char, "none" if value is None else "#%02X%02X%02X" % value))
    for row in pixels:
        out.append('"%s"' % "".join(palette[v] for v in row))
    return out


if __name__ == "__main__":
    # Просмотр значков в терминале: python3 typ/icons.py
    for name in SYMBOLS:
        print(name)
        for line in icon_xpm(name, DARK)[1:]:
            if " c " not in line:
                print("  " + line.strip('"').replace("a", " "))
