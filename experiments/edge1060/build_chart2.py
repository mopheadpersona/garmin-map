#!/usr/bin/env python3
"""Pattern chart: the same dashed line written in every way the TYP format allows.

    python3 build_chart2.py <main folder with tools/> <lat> <lon> <out.img>

Rows from north to south (a thick red bar marks the north side, a thin red line the west side):
   1  solid line (reference)
   2  bitmap, two opaque colours
   3  bitmap, colour + transparent
   4  as 3, UseOrientation=N
   5  as 3, UseOrientation=Y
   6  bitmap with day and night colours (4 colours)
   7  tall bitmap, dashes on one side only (how cycle routes are drawn)
   8  bitmap, fine dots
   9  bitmap on a standard type (0x0a)
  10  dashes as real geometry: 6 m dash, 4 m gap
  11  dashes as real geometry: 3 m dash, 3 m gap
  12  dashes as real geometry beside a solid white road (route overlay as geometry)
  13..17 standard types with NO entry in the TYP: 0x14 railway, 0x16 trail, 0x1c boundary,
         0x26 intermittent stream, 0x1b ferry (what the firmware draws by itself)
Below the rows four squares: solid fill, two-colour pattern, colour + transparent pattern, 4-colour pattern.
"""
import os
import tempfile
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("EDGE1060_WORK") or os.path.join(tempfile.gettempdir(), "garmin-map-edge1060")
os.makedirs(WORK, exist_ok=True)
sys.path.insert(0, HERE)
from build_chart import Osm  # noqa: E402

FID = 7103
LENGTH = 200.0
STEP = 15.0
BLUE, YELLOW, MAGENTA, GREEN, RED = "#0040FF", "#FFE000", "#D238B8", "#00A000", "#E00000"
DASH = "XXXXXXXXXX......XXXXXXXXXX......"
DOTS = "XX..XX..XX..XX..XX..XX..XX..XX.."


def build_osm(lat, lon, path):
    osm = Osm(lat, lon)
    x0, x1 = -LENGTH / 2, LENGTH / 2
    top = 110.0
    rows = {}
    for n in range(1, 18):
        rows[n] = top - (n - 1) * STEP
    for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 13, 14, 15, 16, 17):
        osm.way([(x0, rows[n]), (x1, rows[n])], {"chart:row": str(n)})

    def dashes(y, dash, gap, tag):
        x = x0
        while x < x1:
            osm.way([(x, y), (min(x + dash, x1), y)], {"chart:row": tag})
            x += dash + gap
    dashes(rows[10], 6.0, 4.0, "10")
    dashes(rows[11], 3.0, 3.0, "11")
    osm.way([(x0, rows[12]), (x1, rows[12])], {"chart:row": "12road"})
    dashes(rows[12] + 5.0, 6.0, 4.0, "12")
    # orientation marks, of a type that is known to be drawn
    osm.way([(x0 - 12, top + 14), (x1, top + 14)], {"chart:frame": "north"})
    osm.way([(x0 - 12, top + 14), (x0 - 12, rows[17] - 50)], {"chart:frame": "west"})
    # white backdrop and the four pattern squares
    osm.rect(-400, -400, 400, 400, {"chart:poly": "back"})
    y = rows[17] - 14
    for i in range(4):
        x = x0 + i * 52
        osm.rect(x, y - 36, x + 40, y, {"chart:poly": "p%d" % (i + 1)})
    osm.write(path)


def write_style(style):
    os.makedirs(style)
    open(os.path.join(style, "version"), "w").write("1\n")
    open(os.path.join(style, "info"), "w").write("summary: pattern chart\nversion=0.1\n")
    open(os.path.join(style, "options"), "w").write("levels = 0:24, 1:23, 2:22, 3:21, 4:20, 5:19, 6:18\n")
    open(os.path.join(style, "points"), "w").write("")
    types = {"1": 0x11000, "2": 0x11001, "3": 0x11002, "4": 0x11003, "5": 0x11004, "6": 0x11005,
             "7": 0x11006, "8": 0x11007, "9": 0x0a, "10": 0x11008, "11": 0x11009, "12": 0x1100a,
             "12road": 0x1100b, "13": 0x14, "14": 0x16, "15": 0x1c, "16": 0x26, "17": 0x1b}
    lines = ["chart:row=%s [0x%02x resolution 18]" % (k, v) for k, v in types.items()]
    lines += ["chart:frame=north [0x1100c resolution 18]", "chart:frame=west [0x1100d resolution 18]"]
    open(os.path.join(style, "lines"), "w").write("\n".join(lines) + "\n")
    polys = ["chart:poly=back [0x05 resolution 18]"]
    polys += ["chart:poly=p%d [0x%02x resolution 18]" % (i, 0x10 + i) for i in range(1, 5)]
    open(os.path.join(style, "polygons"), "w").write("\n".join(polys) + "\n")


def write_typ(path):
    out = ["[_id]", "ProductCode=1", "FID=%d" % FID, "CodePage=1252", "[end]", "",
           "[_drawOrder]", "Type=0x05,1", "Type=0x11,2", "Type=0x12,2", "Type=0x13,2", "Type=0x14,2", "[end]", ""]
    out += ["[_polygon]", "Type=0x05", 'Xpm="0 0 1 0"', '"X c #FFFFFF"', "[end]", ""]
    out += ["[_polygon]", "Type=0x11", 'Xpm="0 0 1 0"', '"X c %s"' % BLUE, "[end]", ""]
    checker = [("XXXX...." * 4 if (y // 4) % 2 == 0 else "....XXXX" * 4) for y in range(32)]
    stripes = [("XXXX" + "." * 4) * 4 for _ in range(32)]
    out += ["[_polygon]", "Type=0x12", 'Xpm="32 32 2 1"', '"X c %s"' % BLUE, '". c %s"' % YELLOW] + ['"%s"' % r for r in checker] + ["[end]", ""]
    out += ["[_polygon]", "Type=0x13", 'Xpm="32 32 2 1"', '"X c %s"' % BLUE, '". c none"'] + ['"%s"' % r for r in stripes] + ["[end]", ""]
    out += ["[_polygon]", "Type=0x14", 'Xpm="32 32 4 1"', '"X c %s"' % BLUE, '". c %s"' % YELLOW,
            '"3 c #80A0FF"', '"4 c #202020"'] + ['"%s"' % r for r in checker] + ["[end]", ""]

    def solid(t, colour, width, edge=None, border=0):
        b = ["[_line]", "Type=0x%02x" % t, "LineWidth=%d" % width]
        if border:
            b += ["BorderWidth=%d" % border, 'Xpm="0 0 2 0"', '"1 c %s"' % colour, '"2 c %s"' % edge]
        else:
            b += ['Xpm="0 0 1 0"', '"1 c %s"' % colour]
        return b + ["[end]", ""]

    def bitmap(t, rows, c1, c2, extra=(), colours=2, night=()):
        b = ["[_line]", "Type=0x%02x" % t] + list(extra)
        b += ['Xpm="32 %d %d 1"' % (len(rows), colours), '"X c %s"' % c1, '". c %s"' % (c2 or "none")]
        b += ['"%s c %s"' % (ch, col) for ch, col in night]
        return b + ['"%s"' % r for r in rows] + ["[end]", ""]

    out += solid(0x11000, BLUE, 6)
    out += bitmap(0x11001, [DASH] * 6, BLUE, YELLOW)
    out += bitmap(0x11002, [DASH] * 6, BLUE, None)
    out += bitmap(0x11003, [DASH] * 6, BLUE, None, extra=["UseOrientation=N"])
    out += bitmap(0x11004, [DASH] * 6, BLUE, None, extra=["UseOrientation=Y"])
    out += bitmap(0x11005, [DASH] * 6, BLUE, YELLOW, colours=4, night=(("3", "#80A0FF"), ("4", "#202020")))
    out += bitmap(0x11006, [DASH] * 3 + ["." * 32] * 13, MAGENTA, None)
    out += bitmap(0x11007, [DOTS] * 4, BLUE, None)
    out += bitmap(0x0a, [DASH] * 6, MAGENTA, None)
    out += solid(0x11008, GREEN, 4)
    out += solid(0x11009, GREEN, 3)
    out += solid(0x1100a, MAGENTA, 3)
    out += solid(0x1100b, "#FFFFFF", 6, "#5C5447", 2)
    out += solid(0x1100c, RED, 8)
    out += solid(0x1100d, RED, 2)
    open(path, "w").write("\n".join(out) + "\n")


def main():
    main_dir, lat, lon, target = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    work = os.path.join(WORK, "work-chart2")
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
           "--family-id=%d" % FID, "--product-id=1", "--family-name=CHART 2", "--series-name=CHART 2",
           "--area-name=CHART 2", "--description=CHART 2", "--mapname=%d0001" % FID,
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
    print("chart 2: %.2f MB -> %s" % (os.path.getsize(target) / 1e6, target))
    for l in [l for l in text.splitlines() if l.strip()][:12]:
        print("   ", l[:220])


if __name__ == "__main__":
    main()
