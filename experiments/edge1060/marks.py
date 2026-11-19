#!/usr/bin/env python3
"""Level marks: at each given place the number of the map level, drawn as polygons on that level only.

    python3 marks.py <out.osm> <lat,lon> [<lat,lon> ...]

A photo of the device then shows which level (Garmin resolution 24..18) it has on screen at that
zoom. The number stands north-east of the place and is larger on the coarser levels. Ways are tagged
gm:mark=<resolution>; the rules come from profile1060.py --marks.
"""
import math
import sys

SIZE = {24: 40.0, 23: 100.0, 22: 250.0, 21: 500.0, 20: 1000.0, 19: 2000.0, 18: 2000.0}     # metres
SEGMENTS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
            "5": "afgcd", "6": "afgecd", "7": "abc", "8": "abcdefg", "9": "abcdfg"}
NODE, WAY = 40_000_000_000, 4_000_000_000


def boxes(ch, x, top, h):
    """Seven-segment digit as rectangles (x0, y0, x1, y1), metres."""
    wd, t, mid = h / 2.0, h / 7.0, top - h / 2.0
    seg = {"a": (x, top - t, x + wd, top), "d": (x, top - h, x + wd, top - h + t),
           "g": (x, mid - t / 2, x + wd, mid + t / 2), "f": (x, mid, x + t, top),
           "b": (x + wd - t, mid, x + wd, top), "e": (x, top - h, x + t, mid),
           "c": (x + wd - t, top - h, x + wd, mid)}
    return [seg[s] for s in SEGMENTS[ch]]


def main():
    target, places = sys.argv[1], [tuple(map(float, a.split(","))) for a in sys.argv[2:]]
    nodes, ways = [], []
    for lat0, lon0 in places:
        kx = 111320.0 * math.cos(math.radians(lat0))
        for level, h in SIZE.items():
            for n, ch in enumerate(str(level)):
                for x0, y0, x1, y1 in boxes(ch, 0.25 * h + n * 0.7 * h, 1.25 * h, h):
                    refs = []
                    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                        nodes.append((NODE + len(nodes) + 1, lat0 + y / 111320.0, lon0 + x / kx))
                        refs.append(nodes[-1][0])
                    ways.append((WAY + len(ways) + 1, refs + refs[:1], level))
    with open(target, "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="marks">\n')
        for nid, lat, lon in nodes:
            fh.write('<node id="%d" version="1" timestamp="2026-11-19T00:00:00Z" lat="%.7f" lon="%.7f"/>\n'
                     % (nid, lat, lon))
        for wid, refs, level in ways:
            fh.write('<way id="%d" version="1" timestamp="2026-11-19T00:00:00Z">%s<tag k="gm:mark" v="%d"/></way>\n'
                     % (wid, "".join('<nd ref="%d"/>' % r for r in refs), level))
        fh.write("</osm>\n")
    print("marks: %d places, %d polygons -> %s" % (len(places), len(ways), target))


if __name__ == "__main__":
    main()
