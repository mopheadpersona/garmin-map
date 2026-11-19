#!/usr/bin/env python3
"""Test chart for a Garmin device: which line types it draws and which map level it shows at each zoom.

    python3 build_chart.py <main folder with tools/> <lat> <lon> <out.img>

What is on the chart (centre = lat/lon):
  * a grid of short lines, one per extended line type 0x1TTSS: rows TT = 0x00 (bottom) .. 0x37 (top),
    columns SS = 0x00 (left) .. 0x1f; rows are blue (even TT), green (odd TT), magenta (TT % 8 == 0);
  * two rows of standard line types above it: 0x01..0x1f, then 0x20..0x3f (red / orange);
  * a red frame line on the left and a red base line under the grid (type 0x02, known to be drawn);
  * for every map level (resolution 24..18) a tinted background and the number of the resolution
    written in block digits at four sizes, present at that level only.
"""
import math
import os
import tempfile
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("EDGE1060_WORK") or os.path.join(tempfile.gettempdir(), "garmin-map-edge1060")
os.makedirs(WORK, exist_ok=True)
FID = 7103
ROWS = range(0x00, 0x38)
COLS = range(0x00, 0x20)
DX, SEG, GROUP_GAP = 14.0, 10.0, 6.0        # metres
DY = 8.0
LEVELS = [24, 23, 22, 21, 20, 19, 18]
TINT = {24: "#FFFFFF", 23: "#FFF2A0", 22: "#FFC8DC", 21: "#C8F0B4", 20: "#B4ECF0", 19: "#FFD2A0", 18: "#D2D2D2"}
TINT_TYPE = {24: 0x01, 23: 0x02, 22: 0x03, 21: 0x04, 20: 0x05, 19: 0x06, 18: 0x07}
DIGIT_TYPE = 0x13
SEGMENTS = {  # seven-segment digits: a top, b top-right, c bottom-right, d bottom, e bottom-left, f top-left, g middle
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
    "5": "afgcd", "6": "afgecd", "7": "abc", "8": "abcdefg", "9": "abcdfg",
}


class Osm:
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.nodes, self.ways, self.next = [], [], 1

    def node(self, x, y):
        lat = self.lat0 + y / 111320.0
        lon = self.lon0 + x / (111320.0 * math.cos(math.radians(self.lat0)))
        self.nodes.append((self.next, lat, lon))
        self.next += 1
        return self.next - 1

    def way(self, points, tags, closed=False):
        refs = [self.node(x, y) for x, y in points]
        if closed:
            refs.append(refs[0])
        self.ways.append((self.next, refs, tags))
        self.next += 1

    def rect(self, x0, y0, x1, y1, tags):
        self.way([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], tags, closed=True)

    def write(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="chart">\n')
            for nid, lat, lon in self.nodes:
                fh.write('<node id="%d" version="1" lat="%.7f" lon="%.7f"/>\n' % (nid, lat, lon))
            for wid, refs, tags in self.ways:
                fh.write('<way id="%d" version="1">' % wid)
                fh.write("".join('<nd ref="%d"/>' % r for r in refs))
                fh.write("".join('<tag k="%s" v="%s"/>' % kv for kv in tags.items()))
                fh.write("</way>\n")
            fh.write("</osm>\n")


def column_x(col):
    return col * DX + (col // 8) * GROUP_GAP


def digit(osm, ch, x, y_top, h, tags):
    """Block digit, height h, width h/2, left edge x, top edge y_top."""
    w, t = h / 2.0, h / 7.0
    mid = y_top - h / 2.0
    boxes = {
        "a": (x, y_top - t, x + w, y_top),
        "d": (x, y_top - h, x + w, y_top - h + t),
        "g": (x, mid - t / 2, x + w, mid + t / 2),
        "f": (x, mid, x + t, y_top),
        "b": (x + w - t, mid, x + w, y_top),
        "e": (x, y_top - h, x + t, mid),
        "c": (x + w - t, y_top - h, x + w, mid),
    }
    for seg in SEGMENTS[ch]:
        osm.rect(*boxes[seg], tags)


def build_osm(lat, lon, path):
    osm = Osm(lat, lon)
    width = column_x(COLS[-1]) + SEG
    x0 = -width / 2.0
    y0 = -150.0                                   # bottom row of the grid
    for r, tt in enumerate(ROWS):
        for col in COLS:
            x = x0 + column_x(col)
            y = y0 + r * DY
            osm.way([(x, y), (x + SEG, y)], {"chart:t": "0x%05x" % (0x10000 | (tt << 8) | col)})
    top = y0 + len(ROWS) * DY
    for i, std in enumerate(range(0x01, 0x40)):   # standard types, two rows above the grid
        row, col = (0, std) if std < 0x20 else (1, std - 0x20)
        x = x0 + column_x(col)
        y = top + 8.0 + row * DY
        osm.way([(x, y), (x + SEG, y)], {"chart:t": "0x%02x" % std})
    # frame of a type that is known to be drawn
    osm.way([(x0 - 8, y0 - 4), (x0 - 8, top + 20)], {"chart:frame": "yes"})
    osm.way([(x0 - 8, y0 - 6), (x0 + width, y0 - 6)], {"chart:frame": "yes"})
    for r, tt in enumerate(ROWS):                 # ticks at every eighth row
        if tt % 8 == 0:
            y = y0 + r * DY
            osm.way([(x0 - 20, y), (x0 - 8, y)], {"chart:frame": "yes"})
    # levels: tint and the number of the resolution at four sizes, below the grid
    for res in LEVELS:
        osm.rect(-20000, -20000, 20000, 20000, {"chart:tint": str(res)})
        y_top = y0 - 16.0
        for h in (60.0, 240.0, 960.0, 3840.0):
            text = str(res)
            total = len(text) * h / 2.0 + (len(text) - 1) * h * 0.2
            x = -total / 2.0
            for ch in text:
                digit(osm, ch, x, y_top, h, {"chart:digit": str(res)})
                x += h / 2.0 + h * 0.2
            y_top -= h + max(40.0, h * 0.25)
    osm.write(path)
    return len(osm.ways)


def write_style(style):
    os.makedirs(style)
    open(os.path.join(style, "version"), "w").write("1\n")
    open(os.path.join(style, "info"), "w").write("summary: test chart\nversion=0.1\n")
    open(os.path.join(style, "options"), "w").write("levels = 0:24, 1:23, 2:22, 3:21, 4:20, 5:19, 6:18\n")
    open(os.path.join(style, "points"), "w").write("")
    lines = ["chart:frame=yes [0x02 resolution 22]"]
    for tt in ROWS:
        for col in COLS:
            t = 0x10000 | (tt << 8) | col
            lines.append("chart:t=0x%05x [0x%05x resolution 22]" % (t, t))
    for std in range(0x01, 0x40):
        if std != 0x02:
            lines.append("chart:t=0x%02x [0x%02x resolution 22]" % (std, std))
        else:
            lines.append("chart:t=0x02 [0x02 resolution 22]")
    open(os.path.join(style, "lines"), "w").write("\n".join(lines) + "\n")
    polys = []
    for res in LEVELS:
        polys.append("chart:tint=%d [0x%02x resolution %d-%d]" % (res, TINT_TYPE[res], res, res))
        polys.append("chart:digit=%d [0x%02x resolution %d-%d]" % (res, DIGIT_TYPE, res, res))
    open(os.path.join(style, "polygons"), "w").write("\n".join(polys) + "\n")


def write_typ(path):
    out = ["[_id]", "ProductCode=1", "FID=%d" % FID, "CodePage=1252", "[end]", "", "[_drawOrder]"]
    out += ["Type=0x%02x,1" % TINT_TYPE[res] for res in LEVELS] + ["Type=0x%02x,2" % DIGIT_TYPE, "[end]", ""]
    for res in LEVELS:
        out += ["[_polygon]", "Type=0x%02x" % TINT_TYPE[res], 'Xpm="0 0 1 0"', '"X c %s"' % TINT[res], "[end]", ""]
    out += ["[_polygon]", "Type=0x%02x" % DIGIT_TYPE, 'Xpm="0 0 1 0"', '"X c #101010"', "[end]", ""]

    def line(t, colour):
        return ["[_line]", "Type=0x%02x" % t, "LineWidth=3", 'Xpm="0 0 1 0"', '"1 c %s"' % colour, "[end]", ""]
    for tt in ROWS:
        colour = "#E000E0" if tt % 8 == 0 else ("#0040FF" if tt % 2 == 0 else "#00A000")
        for col in COLS:
            out += line(0x10000 | (tt << 8) | col, colour)
    for std in range(0x01, 0x40):
        out += line(std, "#E00000" if std % 2 else "#FF8000")
    open(path, "w").write("\n".join(out) + "\n")


def main():
    main_dir, lat, lon, target = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    work = os.path.join(WORK, "work-chart")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(os.path.join(work, "img"))
    osm = os.path.join(work, "chart.osm")
    ways = build_osm(lat, lon, osm)
    write_style(os.path.join(work, "style"))
    typ = os.path.join(work, "chart-typ.txt")
    write_typ(typ)
    jar = sorted(d for d in os.listdir(os.path.join(main_dir, "tools")) if d.startswith("mkgmap-r"))[-1]
    java = next(p for p in (os.path.join(main_dir, "tools/env/lib/jvm/bin/java"),
                            os.path.join(main_dir, "tools/env/bin/java")) if os.access(p, os.X_OK))
    cmd = [java, "-Xmx2g", "-jar", os.path.join(main_dir, "tools", jar, "mkgmap.jar"),
           "--output-dir=" + os.path.join(work, "img"), "--style-file=" + os.path.join(work, "style"),
           "--family-id=%d" % FID, "--product-id=1", "--family-name=CHART", "--series-name=CHART",
           "--area-name=CHART", "--description=CHART", "--mapname=%d0001" % FID,
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
    notes = [l for l in text.splitlines() if l.strip()]
    print("chart: %d ways, %.2f MB -> %s; log lines: %d" % (ways, os.path.getsize(target) / 1e6, target, len(notes)))
    for l in notes[:12]:
        print("   ", l[:220])


if __name__ == "__main__":
    main()
