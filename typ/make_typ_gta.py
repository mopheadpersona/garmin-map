#!/usr/bin/env python3
"""Writes style-gta/typ.txt: the TYP of the GTA look, day and night colours, for mkgmap.

    python3 typ/make_typ_gta.py [target]

Day colours were measured from the light GTA VI map (gtabase.com screenshots, 25.11.2026), night
colours from the dark in-game pause map. Those marked "estimated" had no sample and are guessed.
Widths are screen pixels of the Edge 1050/1060 (267 ppi), one value per map level; the levels and
their types are in style-gta/lines.
"""

import math
import os
import sys

# --------------------------------------------------------------------------
# Colours: (day, night)
# --------------------------------------------------------------------------
LAND = ("#6D9985", "#0E142C")
TOWN = ("#9EA5AC", "#2C3B5E")
FOREST = ("#5F8C70", "#122036")       # night estimated
PARK = ("#50866D", "#16293C")         # night estimated
BUILDING = ("#9DACBF", "#46567B")
WATER = ("#49A2BA", "#474A80")
SHALLOW = ("#51ABC3", "#3E4274")      # water in the wetland pattern; night estimated
SAND = ("#E3D5A6", "#3C3F55")         # day from an in-game screenshot, night estimated
ROAD = ("#D1D2DC", "#9094AA")         # night: the game's #6A6E84 brightened for the screen
LANE = ("#E3D6AE", "#C2B993")         # lanes of primary and secondary roads; night estimated
GOLD = ("#BCA36B", "#A38B57")         # lanes of motorways (the user's colour, 25.11.2026); night estimated
GRAVEL = ("#BFBFC7", "#6E7288")       # gravel roads and cycleways (the user's colour); night estimated
TRAIL = ("#A3A3AD", "#555A72")        # trails and rough tracks: darker than gravel (the user, 25.11.2026)
RAIL = ("#A5B4CA", "#5A6688")         # night estimated
RAIL_EDGE = ("#8C9AB2", "#3E4A6A")    # estimated
LABEL = ("#000000", "#F2F4FA")        # black by day (the user, 25.11.2026), white at night

# --------------------------------------------------------------------------
# Lines. Widths per level: 24, 23, 22, 21, 20, 18-19. A number is a plain line;
# a pair (fill, border) is a line with a border on each side; None: not on that level.
# --------------------------------------------------------------------------
LEVELS = ("24", "23", "22", "21", "20", "18-19")
PREFIX = (0x10d, 0x111, 0x115, 0x119, 0x11a, 0x11b)

# class number, name, fill, border colour, widths
LINES = [
    (0x00, "Stream", WATER, None, (3, 2, None, None, None, None)),
    (0x01, "River, canal", WATER, None, (9, 7, 6, 5, 4, 3)),
    (0x02, "Railway yard", RAIL, RAIL_EDGE, ((2, 1), (1, 1), None, None, None, None)),
    (0x03, "Railway", RAIL, RAIL_EDGE, ((3, 1), (2, 1), (2, 1), (1, 1), (1, 1), 2)),
    (0x04, "Taxiway", ROAD, None, (8, 5, None, None, None, None)),
    (0x05, "Runway", ROAD, None, (26, 16, 11, 7, None, None)),
    (0x06, "Service road", ROAD, None, (7, 5, None, None, None, None)),
    (0x07, "Street", ROAD, None, (12, 8, 5, 3, None, None)),
    (0x08, "Tertiary road", ROAD, None, (14, 10, 7, 5, 3, None)),
    (0x09, "Secondary road", LANE, ROAD, ((6, 5), (4, 4), (3, 3), (2, 2), (2, 1), (1, 1))),
    (0x0a, "Primary road", LANE, ROAD, ((7, 5), (4, 4), (3, 3), (3, 2), (3, 1), (2, 1))),
    (0x0b, "Motorway ramp", GOLD, ROAD, ((5, 3), (4, 2), (3, 2), (2, 1), None, None)),
    (0x0c, "Motorway, trunk road", GOLD, ROAD, ((10, 4), (7, 3), (5, 3), (4, 2), (3, 2), (3, 1))),
    (0x0d, "Gravel road, cycleway", GRAVEL, None, (6, 4, 3, None, None, None)),
    (0x0e, "Trail, rough track", TRAIL, None, (6, None, None, None, None, None)),
]

# --------------------------------------------------------------------------
# Areas, bottom to top: type, name, colours or a pattern, draw order
# --------------------------------------------------------------------------
AREAS = [
    (0x4b, "Map background", LAND, 1),
    (0x03, "Ground (squares under the map, for night mode)", LAND, 2),
    (0x01, "Town ground", TOWN, 3),
    (0x50, "Forest", FOREST, 4),
    (0x17, "Park, garden, cemetery", PARK, 5),
    (0x0c, "Sand", SAND, 5),
    (0x51, "Wetland", "wetland", 6),
    (0x3c, "Water", WATER, 7),
    (0x04, "Square, pedestrian area", ROAD, 8),
    (0x13, "House", BUILDING, 9),
]

# Labels: type, name, font
LABELS = [
    (0x0300, "City", "LargeFont"),
    (0x0700, "Town", "LargeFont"),
    (0x0a00, "Village", "NormalFont"),
    (0x0b00, "District", "NormalFont"),
    (0x0d00, "Hamlet", "SmallFont"),
]


def wetland_rows():
    """32x32 pattern of round pools, X water and . land; it tiles without seams."""
    pools = [(5, 6, 4.2), (19, 4, 3.0), (27, 14, 4.5), (12, 18, 5.0), (24, 27, 3.6), (3, 26, 3.2), (17, 30, 2.4)]
    rows = []
    for y in range(32):
        row = ""
        for x in range(32):
            wet = any(math.hypot(min(abs(x - px), 32 - abs(x - px)), min(abs(y - py), 32 - abs(y - py))) <= r
                      for px, py, r in pools)
            row += "X" if wet else "."
        rows.append('"%s"' % row)
    return rows


def area(type_id, name, colours, order):
    out = ["[_polygon]", "; " + name, "Type=0x%02x" % type_id]
    if colours == "wetland":
        out += ['Xpm="32 32 4 1"', '"X c %s"' % SHALLOW[0], '". c %s"' % LAND[0],
                '"3 c %s"' % SHALLOW[1], '"4 c %s"' % LAND[1]] + wetland_rows()
    else:
        out += ['Xpm="0 0 2 0"', '"X c %s"' % colours[0], '"3 c %s"' % colours[1]]
    return out + ["[end]", ""]


def line(type_id, name, fill, edge, width):
    out = ["[_line]", "; " + name, "Type=0x%05x" % type_id]
    if isinstance(width, tuple):
        out += ["LineWidth=%d" % width[0], "BorderWidth=%d" % width[1], 'Xpm="0 0 4 0"',
                '"1 c %s"' % fill[0], '"2 c %s"' % edge[0], '"3 c %s"' % fill[1], '"4 c %s"' % edge[1]]
    else:
        out += ["LineWidth=%d" % width, 'Xpm="0 0 2 0"', '"1 c %s"' % fill[0], '"3 c %s"' % fill[1]]
    return out + ["[end]", ""]


def label(type_id, name, font):
    return ["[_point]", "; " + name, "Type=0x%04x" % type_id, "ExtendedLabels=Y", "FontStyle=" + font,
            "DayCustomColor=" + LABEL[0], "NightCustomColor=" + LABEL[1],
            'DayXpm="1 1 1 1"', '". c none"', '"."', "[end]", ""]


def build():
    out = ["; -*- coding: utf-8 -*-",
           "; Written by typ/make_typ_gta.py, do not edit: change the tables of the script.",
           "; build.sh puts in @FID@ and @CODEPAGE@.", "",
           "[_id]", "ProductCode=1", "FID=@FID@", "CodePage=@CODEPAGE@", "[end]", "",
           "[_drawOrder]"]
    out += ["Type=0x%02x,%d" % (t, order) for t, _, _, order in AREAS]
    out += ["[end]", ""]
    for entry in AREAS:
        out += area(*entry)
    for number, name, fill, edge, widths in LINES:
        for prefix, level, width in zip(PREFIX, LEVELS, widths):
            if width is not None:
                out += line((prefix << 8) | number, "%s, resolution %s" % (name, level), fill, edge, width)
    for entry in LABELS:
        out += label(*entry)
    return "\n".join(out)


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "style-gta", "typ.txt")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(build())
    print("TYP: %s" % target)
