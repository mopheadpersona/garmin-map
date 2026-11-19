#!/usr/bin/env python3
"""Stacking chart: in which order the device lays lines over each other, and how wide it draws them.

    python3 build_chart3.py <main folder with tools/> <lat> <lon> <out.img>

Made for one photo at the 80 m zoom (about 400 x 560 m). All line ends sit on the lattice of
resolution 22, so nothing moves when the device changes the map level. North side: thick red bar,
west side: thin red line. The big digit left of a block is its number; the two digits in the top
right corner (and the large ones below the chart) are the resolution of the level on screen.

Block 1  plain lines crossing, RED = lower type number, BLUE = higher. From west to east:
           1 same TT, red written first     2 same TT, blue written first
           3 as 1, directions swapped       4 red 0x11116 against blue 0x11502 (TT against SS)
           5 red wide, blue narrow          6 red narrow, blue wide
Block 2  lines with a casing (LineWidth + BorderWidth):
           1 street crossing a primary road (primary = higher type)
           2 street crossing a street (same type, two ways)
           3 street ending on the primary   4 primary ending on the street
           5 plain red line (lower type) under a cased street
           6 street on a bridge (layer above, dark casing) over the primary
Block 3  casing as a separate dark line under a plain fill (casings in the lowest layer):
           1 crossing    2 street ending on the primary    3 primary ending on the street
           4 street: TYP casing (north) against separate casing (south)
           5 primary: the same comparison
           6 line ends: a short plain line and a short cased line
Block 4  lines laid on each other along their length:
           west column                              east column
           railway as built (cased white dashes)    railway, white dashes without casing
           railway, numbers reversed                twin track as built
           path dashes                              separate casing, numbers reversed
Block 5  widths: LineWidth 1 2 3 4 5 6 8 10 12 from north to south; west = no casing,
         middle = BorderWidth 1, east = BorderWidth 2. Under it five slanted lines:
         width 1, 2, 3 plain, then 3 + casing 1, then 6 + casing 2.
"""
import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("EDGE1060_WORK") or os.path.join(tempfile.gettempdir(), "garmin-map-edge1060")
os.makedirs(WORK, exist_ok=True)
sys.path.insert(0, HERE)
from build_chart import Osm, digit  # noqa: E402

FID = 7104
NAME = "CHART 3"
WORK_NAME = "work-chart3"
STEP = 360.0 / 2 ** 22                       # lattice of resolution 22, degrees
LEVELS = [24, 23, 22, 21, 20, 19, 18]
COLS, ROWS = 64, 58                          # chart size in lattice steps

RED, BLUE = "#E00000", "#0040FF"
BG, WHITE, EDGE = "#E7E4D8", "#FFFFFF", "#5C5447"
PRIMARY, PRIMARY_EDGE = "#F7CE84", "#8A5A14"
RAIL, GRAVEL, GRAVEL_EDGE, PATH = "#33312D", "#F5EBD8", "#7A6547", "#6B5A3C"

# name -> (type, fill, casing, LineWidth, BorderWidth)
T = {                                        # the low byte of an extended type goes up to 0x1f only
    "r8": (0x11110, RED, None, 8, 0), "b8": (0x11114, BLUE, None, 8, 0),
    "r8x": (0x11116, RED, None, 8, 0), "b8x": (0x11502, BLUE, None, 8, 0),
    "r12": (0x11111, RED, None, 12, 0), "b4": (0x11115, BLUE, None, 4, 0),
    "r4": (0x11112, RED, None, 4, 0), "b12": (0x11117, BLUE, None, 12, 0),
    "under": (0x10d0e, RED, None, 6, 0),
    "street": (0x10d10, WHITE, EDGE, 6, 2), "primary": (0x10d14, PRIMARY, PRIMARY_EDGE, 12, 2),
    "bridge": (0x10e10, WHITE, RAIL, 6, 3),
    "street_case": (0x10c10, EDGE, None, 10, 0), "primary_case": (0x10c14, PRIMARY_EDGE, None, 16, 0),
    "street_fill": (0x10d1c, WHITE, None, 6, 0), "primary_fill": (0x10d1d, PRIMARY, None, 12, 0),
    "cap": (0x10d1e, BLUE, None, 12, 0),
    "rail": (0x10d03, RAIL, None, 5, 0), "rail_cased": (0x10d1b, WHITE, RAIL, 3, 1),
    "rail_plain": (0x10d1a, WHITE, None, 3, 0),
    "rail_hi": (0x10d1f, RAIL, None, 5, 0), "white_lo": (0x10d02, WHITE, None, 3, 0),
    "twin_band": (0x10d19, GRAVEL, None, 6, 0), "twin_piece": (0x10d09, GRAVEL, GRAVEL_EDGE, 6, 2),
    "path": (0x10d05, PATH, None, 3, 0),
    "case_hi": (0x10d17, EDGE, None, 10, 0), "fill_lo": (0x10d01, WHITE, None, 6, 0),
    "north": (0x11c10, RED, None, 8, 0), "west": (0x11c11, RED, None, 2, 0),
}
WIDTHS = (1, 2, 3, 4, 5, 6, 8, 10, 12)
for n, width in enumerate(WIDTHS):
    T["w%d" % width] = (0x10f00 + 3 * n, RAIL, None, width, 0)
    T["w%db1" % width] = (0x10f01 + 3 * n, WHITE, EDGE, width, 1)
    T["w%db2" % width] = (0x10f02 + 3 * n, WHITE, EDGE, width, 2)


def build_osm(lat, lon, path):
    lat0, lon0 = round(lat / STEP) * STEP, round(lon / STEP) * STEP
    osm = Osm(lat0, lon0)
    kx, ky = STEP * 111320.0 * math.cos(math.radians(lat0)), STEP * 111320.0

    def m(x, y):
        """Chart coordinates (lattice steps, x east, y south, origin top left) -> metres from the centre."""
        return (x - COLS / 2.0) * kx, (ROWS / 2.0 - y) * ky

    def line(kind, *points):
        osm.way([m(x, y) for x, y in points], {"chart:t": kind})

    def dashes(kind, x0, x1, y, dash, gap):
        x = x0
        while x + dash <= x1 + 1e-9:
            line(kind, (x, y), (x + dash, y))
            x += dash + gap

    def label(number, y):
        x, top = m(0.6, y)
        digit(osm, str(number), x, top, 3 * ky, {"chart:poly": "ink"})

    osm.rect(*m(-6, ROWS + 4), *m(COLS + 6, -6), {"chart:poly": "back"})
    line("north", (0, 0), (COLS, 0))
    line("west", (0, 0), (0, ROWS))
    for res in LEVELS:                                       # the level on screen, top right corner
        x, top = m(COLS - 7, 1.2)
        for n, ch in enumerate(str(res)):
            digit(osm, ch, x + n * 2.2 * ky, top, 3 * ky, {"chart:level": str(res)})

    def cell(n, yc):
        x0 = 4 + 10 * n
        return x0, x0 + 5, yc

    def cross(n, yc, horizontal, vertical, vertical_first=False):
        x0, xc, _ = cell(n, yc)
        pair = [(horizontal, (x0 + 1, yc), (x0 + 9, yc)), (vertical, (xc, yc - 2), (xc, yc + 2))]
        for kind, a, b in (pair[::-1] if vertical_first else pair):
            line(kind, a, b)

    def tee(n, yc, through, stem):
        x0, xc, _ = cell(n, yc)
        line(through, (x0 + 1, yc), (x0 + 9, yc))
        line(stem, (xc, yc), (xc, yc + 2))

    # Block 1: plain lines
    label(1, 6.5)
    cross(0, 8, "r8", "b8")
    cross(1, 8, "r8", "b8", vertical_first=True)
    cross(2, 8, "b8", "r8")
    cross(3, 8, "r8x", "b8x")
    cross(4, 8, "r12", "b4")
    cross(5, 8, "r4", "b12")

    # Block 2: lines with a TYP casing
    label(2, 12.5)
    cross(0, 14, "street", "primary")
    cross(1, 14, "street", "street")
    tee(2, 14, "primary", "street")
    tee(3, 14, "street", "primary")
    cross(4, 14, "under", "street")
    cross(5, 14, "bridge", "primary")

    # Block 3: casing as a separate line
    label(3, 18.5)
    for kinds in (("street_case", "primary_case"), ("street_fill", "primary_fill")):
        cross(0, 20, *kinds)
        tee(1, 20, kinds[1], kinds[0])
        tee(2, 20, kinds[0], kinds[1])
    for n, name in ((3, "street"), (4, "primary")):
        x0 = cell(n, 20)[0]
        line(name, (x0 + 1, 18.5), (x0 + 9, 18.5))
        line(name + "_case", (x0 + 1, 21.5), (x0 + 9, 21.5))
        line(name + "_fill", (x0 + 1, 21.5), (x0 + 9, 21.5))
    x0 = cell(5, 20)[0]
    line("cap", (x0 + 2, 18.5), (x0 + 5, 18.5))
    line("cap", (x0 + 7, 17.5), (x0 + 7, 19.5))
    line("street", (x0 + 2, 21.5), (x0 + 5, 21.5))
    line("street", (x0 + 7, 20.5), (x0 + 7, 22.5))

    # Block 4: lines laid along each other (west column x 4..30, east column x 36..62)
    label(4, 25.5)
    west, east = (4, 30), (36, 62)
    line("rail", (west[0], 25), (west[1], 25))
    dashes("rail_cased", *west, 25, 0.75, 0.75)
    line("rail", (east[0], 25), (east[1], 25))
    dashes("rail_plain", *east, 25, 0.75, 0.75)
    line("rail_hi", (west[0], 27), (west[1], 27))
    dashes("white_lo", *west, 27, 0.75, 0.75)
    line("twin_band", (east[0], 27), (east[1], 27))
    dashes("twin_piece", *east, 27, 1.0, 0.75)
    dashes("path", *west, 29, 1.0, 0.5)
    line("case_hi", (east[0], 29), (east[1], 29))
    line("fill_lo", (east[0], 29), (east[1], 29))

    # Block 5: widths
    label(5, 32.5)
    y = 32.0
    for width in WIDTHS:
        line("w%d" % width, (4, y), (22, y))
        line("w%db1" % width, (24, y), (42, y))
        line("w%db2" % width, (44, y), (62, y))
        y += 2 if width < 6 else 3
    for n, kind in enumerate(("w1", "w2", "w3", "w3b1", "w6b2")):
        line(kind, (4 + 12 * n, 57), (14 + 12 * n, 54))

    # The level again, large, for the zooms where the chart itself is too small to read
    top = m(0, ROWS + 8)[1]
    for height in (240.0, 960.0, 3840.0):
        for res in LEVELS:
            for n, ch in enumerate(str(res)):
                digit(osm, ch, -0.6 * height + n * 0.7 * height, top, height, {"chart:level": str(res)})
        top -= height * 1.25
    osm.write(path)


def write_style(style):
    os.makedirs(style)
    open(os.path.join(style, "version"), "w").write("1\n")
    open(os.path.join(style, "info"), "w").write("summary: stacking chart\nversion=0.1\n")
    open(os.path.join(style, "options"), "w").write("levels = 0:24, 1:23, 2:22, 3:21, 4:20, 5:19, 6:18\n")
    open(os.path.join(style, "points"), "w").write("")
    lines = ["chart:t=%s [0x%05x resolution 18]" % (name, spec[0]) for name, spec in T.items()]
    open(os.path.join(style, "lines"), "w").write("\n".join(lines) + "\n")
    polys = ["chart:poly=back [0x05 resolution 18]", "chart:poly=ink [0x13 resolution 18]"]
    polys += ["chart:level=%d [0x13 resolution %d-%d]" % (res, res, res) for res in LEVELS]
    open(os.path.join(style, "polygons"), "w").write("\n".join(polys) + "\n")


def write_typ(path):
    out = ["[_id]", "ProductCode=1", "FID=%d" % FID, "CodePage=1252", "[end]", "",
           "[_drawOrder]", "Type=0x05,1", "Type=0x13,2", "[end]", ""]
    out += ["[_polygon]", "Type=0x05", 'Xpm="0 0 1 0"', '"X c %s"' % BG, "[end]", ""]
    out += ["[_polygon]", "Type=0x13", 'Xpm="0 0 1 0"', '"X c #101010"', "[end]", ""]
    seen = set()
    for name, (type_id, fill, edge, width, border) in sorted(T.items(), key=lambda kv: kv[1][0]):
        assert type_id not in seen, name
        seen.add(type_id)
        out += ["[_line]", "; %s" % name, "Type=0x%05x" % type_id, "LineWidth=%d" % width]
        if border:
            out += ["BorderWidth=%d" % border, 'Xpm="0 0 2 0"', '"1 c %s"' % fill, '"2 c %s"' % edge]
        else:
            out += ['Xpm="0 0 1 0"', '"1 c %s"' % fill]
        out += ["[end]", ""]
    open(path, "w").write("\n".join(out) + "\n")


def main():
    main_dir, lat, lon, target = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    work = os.path.join(WORK, WORK_NAME)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(os.path.join(work, "img"))
    osm = os.path.join(work, "chart.osm")
    build_osm(lat, lon, osm)
    write_style(os.path.join(work, "style"))
    typ = os.path.join(work, "chart-typ.txt")
    write_typ(typ)
    jar = sorted(d for d in os.listdir(os.path.join(main_dir, "tools")) if d.startswith("mkgmap-r"))[-1]
    java = next(p for p in (os.path.join(main_dir, "tools/env/lib/jvm/bin/java"),
                            os.path.join(main_dir, "tools/env/bin/java")) if os.access(p, os.X_OK))
    cmd = [java, "-Xmx2g", "-jar", os.path.join(main_dir, "tools", jar, "mkgmap.jar"),
           "--output-dir=" + os.path.join(work, "img"), "--style-file=" + os.path.join(work, "style"),
           "--family-id=%d" % FID, "--product-id=1", "--family-name=" + NAME, "--series-name=" + NAME,
           "--area-name=" + NAME, "--description=" + NAME, "--mapname=%d0001" % FID,
           "--code-page=1252", "--draw-priority=31", "--transparent",
           "--min-size-polygon=0", "--reduce-point-density=0", "--reduce-point-density-polygon=0",
           "--merge-lines=no", "--gmapsupp", osm, typ]
    log = os.path.join(work, "mkgmap.log")
    with open(log, "w") as fh:
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=work).returncode
    text = open(log, errors="replace").read()
    img = os.path.join(work, "img", "gmapsupp.img")
    if rc or not os.path.exists(img):
        print("FAILED rc=%s\n%s" % (rc, "\n".join(text.splitlines()[:40])))
        sys.exit(1)
    shutil.copy(img, target)
    print("%s: %.2f MB -> %s" % (NAME, os.path.getsize(target) / 1e6, target))
    for row in [row for row in text.splitlines() if row.strip()][:12]:
        print("   ", row[:220])


if __name__ == "__main__":
    main()
