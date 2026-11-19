#!/usr/bin/env python3
"""Cut patterned lines into real dashes, one set per map level (for devices that ignore TYP line bitmaps).

    python3 cut1060.py <candidates.opl> <output prefix> [coarse|less|fine] [scale]

scale: for a TYP with thicker lines (profile1060.py --bold=<scale>): dashes get longer and route
overlays move further from the road by the same factor.

Input: OPL with node locations on ways (osmium add-locations-to-ways; cat -f opl,locations_on_ways=true).
Output: an OSM change file that
  * creates the dash pieces: ways tagged gm:lv=<resolution> and gm:ab=a|b, carrying the tags the style
    needs to classify them (so the class is still decided by style/lines, not here);
  * creates route overlays as offset dashes: gm:rt=bike|mtb, gm:far=yes for wide roads;
  * creates the ground: squares tagged gm:ground=yes over every place that has data (and one square
    around it). In night mode the Edge 1060 paints the map background (type 0x4b) with its own dark
    blue whatever the TYP says; an ordinary polygon under everything takes the night colour of the TYP;
  * marks every original way that was cut with gm:cut: all (pieces replace it), 21 or 20 (pieces
    replace it down to that resolution), twin (it stays as the plain band under the pieces).
"""
import math
import os
import re
import sys
from xml.sax.saxutils import quoteattr

U24 = 40007863.0 / 2 ** 24                     # metres per Garmin unit at resolution 24
LEVELS = (24, 23, 22, 21, 20, 19, 18)
# Which look of the style (0 = closest .. 3 = overview) a level carries, and metres per screen pixel
# where the device shows that level. Two layouts:
# Read on an Edge 1060 from the level marks (marks.py), zooms 80 / 120 / 200 / 300 / 500 m:
#   Map Detail Less    24 23 22 22 21
#   Map Detail Normal  24 24 23 23 22
#   Map Detail More    24 24 24 24 23
#   less    for Map Detail Less: the canonical levels, and level 21 carries the look of level 22
#   fine    for Map Detail Normal: the levels of the canonical style as they are
#   coarse  the first attempt, for a device that showed 23 at 50-80 m and 22 at 120 m: looks moved down
LAYOUTS = {
    "coarse": ({24: 0, 23: 0, 22: 1, 21: 1, 20: 2, 19: 3, 18: 3}, {24: 0.4, 23: 0.93, 22: 2.2, 21: 3.5, 20: 7.0}),
    "less": ({24: 0, 23: 1, 22: 2, 21: 2, 20: 3, 19: 3, 18: 3}, {24: 0.9, 23: 1.8, 22: 3.5, 21: 7.5}),
    "fine": ({24: 0, 23: 1, 22: 2, 21: 3, 20: 3, 19: 3, 18: 3}, {24: 1.2, 23: 3.5, 22: 7.5}),
}
TIER, MPP = LAYOUTS["fine"]


def upto(tier):
    """Levels that carry the looks 0..tier."""
    return tuple(level for level in LEVELS if TIER[level] <= tier)
# Dash and gap in lattice steps. The device rounds the ends of every piece, so a plain dash comes
# out longer than cut by the width of the line and the gap shorter by as much: the gaps of plain
# dashes are cut wide. Pieces laid on a band or alternating without a gap ("track", "dot", "rail") keep theirs.
RHYTHM = {"path": (2.0, 3.2), "bad": (2.6, 3.6), "track": (2.6, 1.6), "steps": (0.6, 2.6), "dot": (1.5, 2.5),
          "rail": (3.6, 3.6), "route": (2.2, 3.4), "routedot": (0.6, 3.0)}
ROUTE_OFFSET_PX = {False: (8, 7, 5), True: (11, 9, 7)}     # from typ/make_typ.py ROUTES, by tier
KEEP = ("highway", "area", "motorroad", "bicycle", "access", "footway", "surface", "tracktype", "tunnel",
        "bridge", "mtb:scale", "construction", "railway", "service", "waterway", "intermittent")
PAVED = {"asphalt", "paved", "concrete", "concrete:plates", "concrete:lanes", "paving_stones"}
BIG = {"trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link"}
LOCAL = {"tertiary", "tertiary_link", "unclassified", "residential", "living_street", "service", "road"}
ROAD = {"motorway", "motorway_link"} | BIG | LOCAL
HIDE_NOACCESS = os.environ.get("EDGE1060_NOACCESS") in ("plain", "hide")   # no red dots: nothing to cut
STAMP = "2026-11-19T00:00:00Z"
NEW_NODE, NEW_WAY = 30_000_000_000, 3_000_000_000


def unescape(text):
    return re.sub(r"%([0-9a-fA-F]+)%", lambda m: chr(int(m.group(1), 16)), text)


def parse_tags(field):
    tags = {}
    if field:
        for item in field.split(","):
            key, _, value = item.partition("=")
            tags[unescape(key)] = unescape(value)
    return tags


def plan(tags):
    """-> (rhythm, kinds of pieces to write, levels, gm:cut) for a way that has to be cut, else None.
    Mirrors section 1 of style/lines only as far as needed to know the pattern."""
    hw = tags.get("highway")
    if hw:
        if tags.get("area") == "yes":
            return None
        tunnel = tags.get("tunnel") == "yes"
        bridge = tags.get("bridge") not in (None, "no")
        if hw in ROAD:
            if tunnel:
                return ("track", "ab", upto(1), "all")
            if hw in LOCAL and tags.get("motorroad") != "yes":
                private = tags.get("access") in ("no", "private") and \
                    tags.get("bicycle") not in ("yes", "designated", "permissive")
                if (private or tags.get("bicycle") == "no") and not HIDE_NOACCESS:
                    return ("dot", "ab", upto(1), "21")
            return None
        if hw == "steps":
            return ("steps", "ab" if bridge else "a", upto(1) if (tunnel or bridge) else upto(0), "21")
        if hw in ("path", "footway"):
            if hw == "footway" and tags.get("footway") in ("sidewalk", "crossing", "traffic_island", "access_aisle"):
                return None
            if not tunnel and (tags.get("bicycle") == "designated" or tags.get("surface") in PAVED):
                return None
            return ("path", "ab" if bridge else "a", upto(1), "21")
        if hw == "track":
            surface, grade = tags.get("surface"), tags.get("tracktype")
            if surface in PAVED or grade in ("grade1", "grade2"):
                return None
            if grade == "grade3":
                twin = True
            elif grade in ("grade4", "grade5"):
                twin = False
            elif surface in ("compacted", "fine_gravel"):
                return None
            elif surface in ("ground", "grass", "sand", "dirt", "earth", "mud"):
                twin = False
            else:
                twin = True
            # twin track: the band itself stays one uncut line (gm:cut=twin), pieces carry the dashed casing
            if twin:
                return ("track", "ab" if bridge else "a", upto(2), "twin")
            return ("bad", "ab" if bridge else "a", upto(1), "21")
        if hw == "construction":
            if tags.get("construction") in ("footway", "path", "cycleway", "steps", "track", "pedestrian",
                                            "bridleway", "platform"):
                return None
            return ("track", "a", upto(1), "21")
        return None
    if tags.get("railway") == "rail" and tags.get("tunnel") != "yes":
        # railway: dark pieces and white cased pieces of the same width take turns. No dark line runs
        # under them: on the device it came out over the white dashes in places
        return ("rail", "ab", upto(1) if "service" in tags else LEVELS, "all")
    if tags.get("waterway") == "stream" and tags.get("intermittent") == "yes" and "tunnel" not in tags:
        return ("path", "a", upto(1), "all")
    return None


def is_cycleway(tags):
    """The way is drawn as a cycleway (class cycleway of style/lines): the route overlay beside it adds nothing."""
    hw = tags.get("highway")
    return hw == "cycleway" or (hw in ("path", "footway") and tags.get("bicycle") == "designated")


def is_far(tags):
    """Route overlay sits further out along wide roads (classes primary, secondary, green_wide)."""
    hw = tags.get("highway")
    if hw == "motorway":
        return True
    ban = tags.get("motorroad") == "yes" or (tags.get("bicycle") == "no" and hw in BIG)
    if ban:
        return hw in ("trunk", "primary", "secondary")
    return hw in BIG


def opl_escape(text):
    return "".join(c if (c.isalnum() or c in "_:-./+") else "%%%04x%%" % ord(c) for c in text)


class Out:
    """Pieces go to <dst>.nodes.opl and <dst>.ways.opl (both sorted by id), the re-tagged
    originals to <dst>.modify.osc. Everything is written as it comes, nothing is kept in memory."""

    def __init__(self, dst):
        self.nodes_fh = open(dst + ".nodes.opl", "w", encoding="utf-8")
        self.ways_fh = open(dst + ".ways.opl", "w", encoding="utf-8")
        self.osc_fh = open(dst + ".modify.osc", "w", encoding="utf-8")
        self.osc_fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<osmChange version="0.6" generator="cut1060">\n<modify>\n')
        self.node_id, self.way_id = NEW_NODE, NEW_WAY
        self.nodes = self.ways = self.modified = 0

    def node(self, lon, lat):
        self.node_id += 1
        self.nodes += 1
        self.nodes_fh.write("n%d v1 dV c0 t%s i0 u T x%.7f y%.7f\n" % (self.node_id, STAMP, lon, lat))
        return self.node_id

    def way(self, refs, tags):
        self.way_id += 1
        self.ways += 1
        self.ways_fh.write("w%d v1 dV c0 t%s i0 u T%s N%s\n" % (
            self.way_id, STAMP,
            ",".join("%s=%s" % (opl_escape(k), opl_escape(v)) for k, v in tags.items()),
            ",".join("n%d" % r for r in refs)))

    def modify(self, oid, version, nodes, tags):
        self.modified += 1
        self.osc_fh.write('<way id="%d" version="%d" timestamp="%s">%s%s</way>\n' % (
            oid, version + 1, STAMP, "".join('<nd ref="%d"/>' % nid for nid, _a, _b in nodes),
            "".join("<tag k=%s v=%s/>" % (quoteattr(k), quoteattr(v)) for k, v in tags.items())))

    def close(self):
        self.osc_fh.write("</modify>\n</osmChange>\n")
        for fh in (self.nodes_fh, self.ways_fh, self.osc_fh):
            fh.close()


TOLERANCE = 0.10            # how far (in lattice steps) a cut point may lie from the drawn line


def near_lattice_point(cur, end, need, remain, sx, sy, unit):
    """A lattice point for a cut `need` metres along the drawn segment cur -> end (both lattice
    points). The device joins lattice points with straight lines, so a cut point that is off the
    segment bends it: prefer points that are practically on it, even if the piece gets longer or
    shorter than asked. Returns (iu, iv, metres along) or None when the segment is too short."""
    dx, dy = (end[0] - cur[0]) * sx, (end[1] - cur[1]) * sy
    tol = TOLERANCE * min(sx, sy)
    best = None
    for window in (0.8, 1.6, 2.6, 4.0):
        lo, hi = max(need - window * unit, 0.8 * unit), min(need + window * unit, remain - 0.8 * unit)
        if lo > hi:
            continue
        u = sorted((cur[0] + (end[0] - cur[0]) * lo / remain, cur[0] + (end[0] - cur[0]) * hi / remain))
        v = sorted((cur[1] + (end[1] - cur[1]) * lo / remain, cur[1] + (end[1] - cur[1]) * hi / remain))
        for iu in range(int(math.floor(u[0])) - 1, int(math.ceil(u[1])) + 2):
            for iv in range(int(math.floor(v[0])) - 1, int(math.ceil(v[1])) + 2):
                px, py = (iu - cur[0]) * sx, (iv - cur[1]) * sy
                along = (px * dx + py * dy) / remain
                if not lo <= along <= hi:
                    continue
                off = abs(px * dy - py * dx) / remain
                key = (0, abs(along - need)) if off <= tol else (1, off)
                if best is None or key < best[0]:
                    best = (key, iu, iv, along)
        if best and best[0][0] == 0:
            break
    return best[1:] if best else None


def cut(out, pts, ids, kx, a_len, b_len, emit, tags, min_tail, grid):
    """Cut a line into alternating pieces a, b, a, ... and write those listed in `emit`.
    pts: [(lon, lat)], ids: node ids, or None for points that need a new node."""
    sx, sy = grid * kx, grid * 110540.0
    unit = sy
    verts = []                                              # the line as the device will draw it
    for (lon, lat), nid in zip(pts, ids):
        q = (round(lon / grid), round(lat / grid))
        if verts and verts[-1][:2] == q:
            continue
        verts.append((q[0], q[1], nid))
    if len(verts) < 2:
        return 0
    made = 0

    def node_of(v):
        return v[2] if v[2] is not None else out.node(v[0] * grid, v[1] * grid)

    def flush(kind, refs, length):
        nonlocal made
        if len(refs) >= 2 and kind in emit and length >= min_tail:
            piece = dict(tags)
            piece["gm:ab"] = kind
            out.way(refs, piece)
            made += 1

    refs = [node_of(verts[0])]
    cur = verts[0][:2]
    kind, target, piece_len, i = "a", a_len, 0.0, 0
    while i < len(verts) - 1:
        end = verts[i + 1][:2]
        remain = math.hypot((end[0] - cur[0]) * sx, (end[1] - cur[1]) * sy)
        need = target - piece_len
        found = None
        if remain > need + 0.8 * unit:
            found = near_lattice_point(cur, end, max(need, 0.8 * unit), remain, sx, sy, unit)
        if found is None:                                   # go on to the vertex; cut there if it is time
            piece_len += remain
            ref = node_of(verts[i + 1])
            refs.append(ref)
            cur, i = end, i + 1
            if piece_len < target - 0.8 * unit:
                continue
        else:
            iu, iv, along = found
            piece_len += along
            ref = out.node(iu * grid, iv * grid)
            refs.append(ref)
            cur = (iu, iv)
        flush(kind, refs, piece_len)
        refs, piece_len = [ref], 0.0
        kind = "b" if kind == "a" else "a"
        target = b_len if kind == "b" else a_len
    flush(kind, refs, piece_len)
    return made


def offset_line(pts, kx, dist):
    """Parallel line, dist metres to the left of the direction of travel (negative = right)."""
    xy = [(lon * kx, lat * 110540.0) for lon, lat in pts]
    res = []
    for i, (x, y) in enumerate(xy):
        normals = []
        for j in (i - 1, i):
            if 0 <= j < len(xy) - 1:
                dx, dy = xy[j + 1][0] - xy[j][0], xy[j + 1][1] - xy[j][1]
                length = math.hypot(dx, dy)
                if length > 0:
                    normals.append((-dy / length, dx / length))
        if not normals:
            return []
        nx, ny = sum(n[0] for n in normals) / len(normals), sum(n[1] for n in normals) / len(normals)
        norm = math.hypot(nx, ny)
        if norm < 1e-6:
            nx, ny, scale = normals[0][0], normals[0][1], 1.0
        else:
            nx, ny = nx / norm, ny / norm
            scale = min(1.0 / max(norm, 0.5), 2.0)          # miter, limited at sharp corners
        res.append(((x + nx * dist * scale) / kx, (y + ny * dist * scale) / 110540.0))
    return res


GROUND_STEP = 0.04          # degrees; smaller than any tile of splitter, so that no tile misses its squares


def ground(out, cells):
    """Squares over the cells that hold data and their neighbours."""
    wide = {(i + di, j + dj) for i, j in cells for di in (-1, 0, 1) for dj in (-1, 0, 1)}
    corner = {}

    def node(i, j):
        if (i, j) not in corner:
            corner[(i, j)] = out.node(i * GROUND_STEP, j * GROUND_STEP)
        return corner[(i, j)]

    for i, j in sorted(wide):
        refs = [node(i, j), node(i + 1, j), node(i + 1, j + 1), node(i, j + 1)]
        out.way(refs + refs[:1], {"gm:ground": "yes"})
    return len(wide)


NODE_RE = re.compile(r"n(\d+)x(-?[\d.]+)y(-?[\d.]+)$")


def read(src, kinds):
    """Objects of the OPL file one by one: (kind, id, version, tags, text of the node or member list)."""
    with open(src, encoding="utf-8") as fh:
        for line in fh:
            if line[0] not in kinds:
                continue
            fields = line.rstrip("\n").split(" ")
            tags, rest = {}, ""
            for field in fields[2:]:
                if field.startswith("T"):
                    tags = parse_tags(field[1:])
                elif field.startswith(("N", "M")):
                    rest = field[1:]
            yield line[0], int(fields[0][1:]), int(fields[1][1:]), tags, rest


def main():
    global TIER, MPP
    src, dst = sys.argv[1], sys.argv[2]
    TIER, MPP = LAYOUTS[sys.argv[3] if len(sys.argv) > 3 else "fine"]
    scale = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    # First pass: the ways of cycle and MTB routes. Relations come after the ways in the file.
    routes = {"bicycle": set(), "mtb": set()}
    for _kind, _oid, _version, tags, members in read(src, "r"):
        if tags.get("type") == "route" and tags.get("route") in routes:
            for member in members.split(","):
                if member.startswith("w"):
                    routes[tags["route"]].add(int(member[1:].split("@")[0]))
    # Second pass: the ways, one at a time.
    out = Out(dst)
    stats, read_ways, cells = {}, 0, set()
    for _kind, oid, version, tags, refs in read(src, "w"):
        nodes = []
        for item in refs.split(","):
            m = NODE_RE.match(item)
            if m:
                nodes.append((int(m.group(1)), float(m.group(2)), float(m.group(3))))
        if len(nodes) < 2:
            continue
        read_ways += 1
        for _id, lon, lat in nodes:
            cells.add((math.floor(lon / GROUND_STEP), math.floor(lat / GROUND_STEP)))
        kx = 111320.0 * math.cos(math.radians(nodes[0][2]))
        todo = plan(tags)
        if todo:
            rhythm, emit, levels, cut_tag = todo
            pts = [(lon, lat) for _id, lon, lat in nodes]
            ids = [nid for nid, _lon, _lat in nodes]
            base = {k: tags[k] for k in KEEP if k in tags}
            for res in levels:
                unit = U24 * 2 ** (24 - res)
                a_len, b_len = RHYTHM[rhythm][0] * unit * scale, RHYTHM[rhythm][1] * unit * scale
                piece = dict(base)
                piece["gm:lv"] = str(res)
                n = cut(out, pts, ids, kx, a_len, b_len, emit, piece, 0.5 * unit, 360.0 / 2 ** res)
                stats[(rhythm, res)] = stats.get((rhythm, res), 0) + n
            all_tags = dict(tags)
            all_tags["gm:cut"] = cut_tag
            out.modify(oid, version, nodes, all_tags)
        if "highway" in tags and tags.get("area") != "yes":
            for route, key, rhythm, levels, side in (("bicycle", "bike", "route", upto(2), 1),
                                                     ("mtb", "mtb", "routedot", upto(1), -1)):
                if oid not in routes[route] or (key == "bike" and is_cycleway(tags)):
                    continue
                far = is_far(tags)
                pts = [(lon, lat) for _id, lon, lat in nodes]
                for res in levels:
                    unit = U24 * 2 ** (24 - res)
                    px = (ROUTE_OFFSET_PX[far][TIER[res]] + 1.5) * scale
                    dist = max(px * MPP[res], (2.0 if far else 1.5) * unit)
                    line = offset_line(pts, kx, side * dist)
                    if len(line) < 2:
                        continue
                    piece = {"gm:rt": key, "gm:lv": str(res)}
                    if far:
                        piece["gm:far"] = "yes"
                    a_len, b_len = RHYTHM[rhythm][0] * unit * scale, RHYTHM[rhythm][1] * unit * scale
                    n = cut(out, line, [None] * len(line), kx, a_len, b_len, "a", piece, 0.5 * unit,
                            360.0 / 2 ** res)
                    stats[(key, res)] = stats.get((key, res), 0) + n
    squares = ground(out, cells)
    out.close()
    print("ways read %d, cut %d, new ways %d, new nodes %d, ground squares %d"
          % (read_ways, out.modified, out.ways, out.nodes, squares))
    for key in sorted(stats):
        print("   %-9s res %d: %d" % (key[0], key[1], stats[key]))


if __name__ == "__main__":
    main()
