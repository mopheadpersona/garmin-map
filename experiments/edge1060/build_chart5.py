#!/usr/bin/env python3
"""Junction chart: a street ending on a wider road, built in different ways, to find one the device draws clean.

    python3 build_chart5.py <main folder with tools/> <lat> <lon> <out.img>

On the Edge 1060 the fill of a street that ends on a wider road is drawn over that road up to its
axis. Every cell here is one way of building the junction; the photo (80 m zoom, north up) shows
which of them come out without the white patch. S = street (white), Y = secondary road (yellow),
P = primary road (orange); widths as in the bold TYP. J = the junction point.

Row 1  street from the south:  1 Y, then S starting at J    2 Y, then S ending at J
                               3 S starting at J, then Y    4 S ending at J, then Y
                               5 Y with a vertex at J       6 Y made of two ways that meet at J
Row 2  the same six with the street from the north
Row 3  Y runs north-south:     1 S from the west, starts at J    2 from the west, ends at J
                               3 from the east, starts at J      4 from the east, ends at J
                               5 as 1, S written first           6 as 3, S written first
Row 4  cell 1 of row 1 plus:   1 the yellow fill once more, plain, a higher number in the same layer
                               2 the same in the bridge layer   3 the same in the overlay layer
                               4 the whole Y once more, with its casing, in the bridge layer
                               5 the street on a number above Y   6 the street as a plain white line
Row 5  crossings:              1 Y, then S across (one way)     2 S across, then Y
                               3 S across with a vertex at J    4 S as two ways that start at J
                               5 as 4 plus the yellow fill in the bridge layer
                               6 the street on a number above Y, across
Row 6  1-3 the street stops short of the axis by 0.5, 1 and 1.25 lattice steps (5, 10, 12 m)
       4 Y ending on P    5 P ending on Y    6 S ending on S
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_chart3 as base  # noqa: E402
from build_chart import Osm, digit  # noqa: E402

STEP = base.STEP
COLS, ROWS = 76, 53
WHITE, EDGE, RED = base.WHITE, base.EDGE, base.RED
YELLOW, YELLOW_EDGE = "#F8EE87", "#8C7A3A"
T = {
    "S": (0x10d10, WHITE, EDGE, 9, 3), "Y": (0x10d13, YELLOW, YELLOW_EDGE, 15, 3),
    "P": (0x10d14, base.PRIMARY, base.PRIMARY_EDGE, 18, 3),
    "S2": (0x10d17, WHITE, EDGE, 9, 3), "Splain": (0x10d1c, WHITE, None, 9, 0),
    "Ytop": (0x10d1e, YELLOW, None, 15, 0), "Ytop_bridge": (0x10e1e, YELLOW, None, 15, 0),
    "Ytop_over": (0x10f1e, YELLOW, None, 15, 0), "Y_bridge": (0x10e1d, YELLOW, YELLOW_EDGE, 15, 3),
    "north": (0x11c10, RED, None, 8, 0), "west": (0x11c11, RED, None, 2, 0),
}


def build_osm(lat, lon, path):
    lat0, lon0 = round(lat / STEP) * STEP, round(lon / STEP) * STEP
    osm = Osm(lat0, lon0)
    kx, ky = STEP * 111320.0 * math.cos(math.radians(lat0)), STEP * 111320.0

    def m(x, y):
        return (x - COLS / 2.0) * kx, (ROWS / 2.0 - y) * ky

    def line(kind, *points):
        osm.way([m(x, y) for x, y in points], {"chart:t": kind})

    def centre(row, cell):
        return 4 + 12 * cell + 6, 5 + 8 * row + 4

    def through(row, cell, kind="Y", vertical=False, vertex=False, split=False):
        xc, yc = centre(row, cell)
        a, b = ((xc, yc - 3), (xc, yc + 3)) if vertical else ((xc - 3.5, yc), (xc + 3.5, yc))
        if split:
            line(kind, a, (xc, yc))
            line(kind, (xc, yc), b)
        elif vertex:
            line(kind, a, (xc, yc), b)
        else:
            line(kind, a, b)

    def stem(row, cell, side, kind="S", ends_at_j=False, short=0.0):
        xc, yc = centre(row, cell)
        dx, dy = {"s": (0, 1), "n": (0, -1), "w": (-1, 0), "e": (1, 0)}[side]
        length = 3.0 if dx == 0 else 4.0
        near = (xc + dx * short, yc + dy * short)
        far = (xc + dx * length, yc + dy * length)
        line(kind, *((far, near) if ends_at_j else (near, far)))

    osm.rect(*m(-6, ROWS + 4), *m(COLS + 6, -6), {"chart:poly": "back"})
    line("north", (0, 0), (COLS, 0))
    line("west", (0, 0), (0, ROWS))
    for res in base.LEVELS:
        x, top = m(COLS - 7, 1.0)
        for n, ch in enumerate(str(res)):
            digit(osm, ch, x + n * 2.2 * ky, top, 3 * ky, {"chart:level": str(res)})
    for row in range(6):
        x, top = m(0.6, 5 + 8 * row + 2.5)
        digit(osm, str(row + 1), x, top, 3 * ky, {"chart:poly": "ink"})

    for row, side in ((0, "s"), (1, "n")):
        through(row, 0); stem(row, 0, side)
        through(row, 1); stem(row, 1, side, ends_at_j=True)
        stem(row, 2, side); through(row, 2)
        stem(row, 3, side, ends_at_j=True); through(row, 3)
        through(row, 4, vertex=True); stem(row, 4, side)
        through(row, 5, split=True); stem(row, 5, side)

    for cell, side, at_end, first in ((0, "w", False, False), (1, "w", True, False), (2, "e", False, False),
                                      (3, "e", True, False), (4, "w", False, True), (5, "e", False, True)):
        if first:
            stem(2, cell, side, ends_at_j=at_end)
        through(2, cell, vertical=True)
        if not first:
            stem(2, cell, side, ends_at_j=at_end)

    for cell, extra in enumerate(("Ytop", "Ytop_bridge", "Ytop_over", "Y_bridge")):
        through(3, cell); stem(3, cell, "s"); through(3, cell, kind=extra)
    through(3, 4); stem(3, 4, "s", kind="S2")
    through(3, 5); stem(3, 5, "s", kind="Splain")

    def across(row, cell, kind="S", vertex=False):
        xc, yc = centre(row, cell)
        points = [(xc, yc - 3), (xc, yc + 3)]
        line(kind, *(points[:1] + [(xc, yc)] + points[1:] if vertex else points))

    through(4, 0); across(4, 0)
    across(4, 1); through(4, 1)
    through(4, 2); across(4, 2, vertex=True)
    through(4, 3); stem(4, 3, "n"); stem(4, 3, "s")
    through(4, 4); stem(4, 4, "n"); stem(4, 4, "s"); through(4, 4, kind="Ytop_bridge")
    through(4, 5); across(4, 5, kind="S2")

    for cell, short in enumerate((0.5, 1.0, 1.25)):
        through(5, cell); stem(5, cell, "s", short=short)
    through(5, 3, kind="P"); stem(5, 3, "s", kind="Y")
    through(5, 4); stem(5, 4, "s", kind="P")
    through(5, 5, kind="S"); stem(5, 5, "s")
    osm.write(path)


if __name__ == "__main__":
    base.T, base.FID, base.NAME, base.WORK_NAME = T, 7106, "CHART 5", "work-chart5"
    base.COLS, base.ROWS = COLS, ROWS
    base.build_osm = build_osm
    base.main()
