#!/usr/bin/env python3
"""Ground squares for the GTA look: closed ways tagged gta:ground=yes over a bounding box.

    python3 scripts/ground_squares.py <west,south,east,north> <out.osm>

In night mode the Edge 1060 paints the map background (type 0x4b) its own dark blue, whatever the
TYP says; ordinary polygons keep their TYP night colour (experiments/edge1060/README.md). The squares
are 0.04 degrees, smaller than any splitter tile, so every tile gets its own, and they reach one
square past the box. Ids start high so they do not collide with OSM ids.
"""

import math
import sys

STEP = 0.04
FIRST_NODE, FIRST_WAY = 30_000_000_000, 3_000_000_000


def main():
    west, south, east, north = (float(v) for v in sys.argv[1].split(","))
    cols = range(math.floor(west / STEP) - 1, math.ceil(east / STEP) + 1)
    rows = range(math.floor(south / STEP) - 1, math.ceil(north / STEP) + 1)
    ids = {}
    with open(sys.argv[2], "w", encoding="utf-8") as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="ground_squares.py">\n')
        for j in range(rows.start, rows.stop + 1):
            for i in range(cols.start, cols.stop + 1):
                ids[(i, j)] = FIRST_NODE + len(ids)
                out.write(' <node id="%d" version="1" lat="%.7f" lon="%.7f"/>\n' % (ids[(i, j)], j * STEP, i * STEP))
        way = FIRST_WAY
        for j in rows:
            for i in cols:
                refs = [ids[(i, j)], ids[(i + 1, j)], ids[(i + 1, j + 1)], ids[(i, j + 1)], ids[(i, j)]]
                out.write(' <way id="%d" version="1">%s<tag k="gta:ground" v="yes"/></way>\n'
                          % (way, "".join('<nd ref="%d"/>' % r for r in refs)))
                way += 1
        out.write("</osm>\n")
    print("ground squares: %d" % (way - FIRST_WAY))


if __name__ == "__main__":
    main()
