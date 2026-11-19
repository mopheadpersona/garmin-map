#!/usr/bin/env python3
"""Type chart: which extended line types the device draws, readable in one or two photos at the 80 m zoom.

    python3 build_chart4.py <main folder with tools/> <lat> <lon> <out.img>

One short thick line per type 0x1TTSS, TT = 0x0c .. 0x20, SS = 0x00 .. 0x1f.
  * two panels: the north one holds SS 0x00-0x0f, the south one SS 0x10-0x1f;
  * in a panel a row is one TT, 0x0c at the north; rows come in groups of four (0x0c-0x0f, 0x10-0x13, ...);
  * columns run west to east, in groups of four; even TT rows are blue, odd rows green;
  * a red mark (type 0x11c10, known to be drawn) stands west of every row and north of every column,
    so a missing line shows as a hole in the grid.
The two digits north-east of the chart are the resolution of the level on screen.
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

FID = 7105
NAME = "CHART 4"
STEP = 360.0 / 2 ** 22
LEVELS = [24, 23, 22, 21, 20, 19, 18]
ROWS = list(range(0x0c, 0x21))
MARK = 0x11c10
BG = "#E7E4D8"
PITCH_X, PITCH_Y, GAP = 3.0, 1.5, 1.0          # lattice steps


def row_y(n):
    return n * PITCH_Y + (n // 4) * GAP


def col_x(n):
    return n * PITCH_X + (n // 4) * GAP


def build_osm(lat, lon, path):
    lat0, lon0 = round(lat / STEP) * STEP, round(lon / STEP) * STEP
    osm = Osm(lat0, lon0)
    kx, ky = STEP * 111320.0 * math.cos(math.radians(lat0)), STEP * 111320.0
    width = col_x(15) + 1.0
    panel = row_y(len(ROWS) - 1)
    height = 2 * panel + 8.0

    def m(x, y):
        return (x - width / 2.0) * kx, (height / 2.0 - y) * ky

    def line(type_id, *points):
        osm.way([m(x, y) for x, y in points], {"chart:t": "0x%05x" % type_id})

    osm.rect(*m(-8, height + 4), *m(width + 6, -8), {"chart:poly": "back"})
    for half in (0, 1):
        top = half * (panel + 8.0)
        for c in range(16):                                   # column marks
            x = col_x(c) + 0.5
            line(MARK, (x, top - 2.5), (x, top - 1.5))
        if half:
            line(MARK, (-3.0, top - 4.0), (width, top - 4.0))  # bar between the panels
        for r, tt in enumerate(ROWS):
            y = top + row_y(r)
            line(MARK, (-3.0, y), (-2.0, y))
            for c in range(16):
                line(0x10000 | (tt << 8) | (half * 16 + c), (col_x(c), y), (col_x(c) + 1.0, y))
    for res in LEVELS:
        x, y_top = m(width - 6.0, -7.0)
        for n, ch in enumerate(str(res)):
            digit(osm, ch, x + n * 2.2 * ky, y_top, 3 * ky, {"chart:level": str(res)})
    osm.write(path)


def write_style(style):
    os.makedirs(style)
    open(os.path.join(style, "version"), "w").write("1\n")
    open(os.path.join(style, "info"), "w").write("summary: type chart\nversion=0.1\n")
    open(os.path.join(style, "options"), "w").write("levels = 0:24, 1:23, 2:22, 3:21, 4:20, 5:19, 6:18\n")
    open(os.path.join(style, "points"), "w").write("")
    types = [0x10000 | (tt << 8) | ss for tt in ROWS for ss in range(32)]
    lines = ["chart:t=0x%05x [0x%05x resolution 18]" % (t, t) for t in sorted(set(types) | {MARK})]
    open(os.path.join(style, "lines"), "w").write("\n".join(lines) + "\n")
    polys = ["chart:poly=back [0x05 resolution 18]"]
    polys += ["chart:level=%d [0x13 resolution %d-%d]" % (res, res, res) for res in LEVELS]
    open(os.path.join(style, "polygons"), "w").write("\n".join(polys) + "\n")


def write_typ(path):
    out = ["[_id]", "ProductCode=1", "FID=%d" % FID, "CodePage=1252", "[end]", "",
           "[_drawOrder]", "Type=0x05,1", "Type=0x13,2", "[end]", ""]
    out += ["[_polygon]", "Type=0x05", 'Xpm="0 0 1 0"', '"X c %s"' % BG, "[end]", ""]
    out += ["[_polygon]", "Type=0x13", 'Xpm="0 0 1 0"', '"X c #101010"', "[end]", ""]
    for tt in ROWS:
        for ss in range(32):
            type_id = 0x10000 | (tt << 8) | ss
            colour = "#E00000" if type_id == MARK else ("#0040FF" if tt % 2 == 0 else "#00A000")
            out += ["[_line]", "Type=0x%05x" % type_id, "LineWidth=5", 'Xpm="0 0 1 0"', '"1 c %s"' % colour,
                    "[end]", ""]
    open(path, "w").write("\n".join(out) + "\n")


def main():
    main_dir, lat, lon, target = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    work = os.path.join(WORK, "work-chart4")
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
    print("chart 4: %.2f MB -> %s" % (os.path.getsize(target) / 1e6, target))


if __name__ == "__main__":
    main()
