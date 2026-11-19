#!/usr/bin/env python3
"""Style and TYP for devices that ignore TYP line bitmaps and switch map levels early (Edge 1050/1060).

    python3 profile1060.py <repo> <out dir> [--fine | --less | --coarse] [--bold[=1.5]] [--bold-far=1.25]
                           [--dash=2] [--cycleway-wide] [--plain-noaccess | --hide-noaccess]
                           [--night=same|<palette.json>] [--casing-layer] [--marks]

--fine:   the levels of the canonical style; fits Map Detail Normal on the Edge 1060 (default).
--less:   for Map Detail Less: as --fine, and level 21 (the 500 m zoom) carries the look of level 22.
--coarse: the first attempt: the four looks moved to coarser levels (24 -> 24, 23; 23 -> 22, 21; ...).
--bold:   every line width and casing multiplied by the factor, for the dense screen of the
          Edge 1050/1060 (267 ppi). Cut the pieces with the same factor (cut1060.py ... <scale>).
--bold-far: another factor for the two far looks (canonical levels 22 and 18-21); default: as --bold.
--dash:   the factor for plain dashes (paths, bad tracks) and route overlays; default: as --bold.
--cycleway-wide: the cycleway line about twice as wide.
--plain-noaccess: roads closed to bicycles (class "noaccess": red dots on white) are drawn as
          ordinary roads of their kind, without the red.
--hide-noaccess: such roads are not drawn at all.
--night=same: every area and line gets its night colours written out, equal to the day colours.
          Without them the Edge 1060 in night mode paints some areas (industrial, quarry) black.
--night=<palette.json>: night colours from a file {"NAME": "#RRGGBB"} with the names of the palette of
          typ/make_typ.py, e.g. night-palette.json beside this script (the dark theme). A night colour
          belongs to the name, not to the value of the day colour: day colours may change (TYP_PALETTE,
          the colours page) or coincide, the night colours stay.
--casing-layer:  a road is two lines, a dark one of the full width in the lowest layer and a plain
          fill above it, instead of one line with BorderWidth. Every casing then lies under every fill.
--marks:  rules for the level marks (marks.py): a number on the map that tells which level is shown.

Writes <out dir>/style (mkgmap style) and <out dir>/typ.txt. Two changes against the canonical style:
  * levels: with --less or --coarse the four looks of the style sit on other resolutions (see cut1060.py
    for what the device shows at which zoom);
  * patterned lines are not TYP bitmaps: the data holds ready-cut pieces (cut1060.py, tags gm:lv and
    gm:ab) and every piece is a plain solid line; a pattern is an alternation of two solid types.
"""
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile

repo, out = sys.argv[1], sys.argv[2]
BOLD = next((float(a[7:]) if a.startswith("--bold=") else 1.5 for a in sys.argv
             if a == "--bold" or a.startswith("--bold=")), 1.0)
BOLD_FAR = next((float(a[11:]) for a in sys.argv if a.startswith("--bold-far=")), BOLD)
DASH = next((float(a[7:]) for a in sys.argv if a.startswith("--dash=")), BOLD)
# The Edge 1060 draws 0x10c00-0x10c07 only (build_chart4.py), so the road tunnels of the closest look,
# 0x10c10-0x10c16, go to free places among the road types of the same look.
MOVED = {0x10c10: 0x10d11, 0x10c12: 0x10d17, 0x10c13: 0x10d1c, 0x10c14: 0x10d1d, 0x10c15: 0x10d1e, 0x10c16: 0x10d1f}
STEPS_WIDTH = 6                 # steps are a row of dots: a wide dash with round ends would be a blob
CYCLEWAY_WIDE = {0: (5, 2), 1: (3, 2), 2: (3, 1)} if "--cycleway-wide" in sys.argv else {}
HIDE_NOACCESS = "--hide-noaccess" in sys.argv
PLAIN_NOACCESS = "--plain-noaccess" in sys.argv
MARK_TYPE = 0x0e                # polygon type of the level marks
GROUND_TYPE = 0x03              # polygon type of the ground squares (cut1060.py), drawn right above the background
CASING_LAYER = "--casing-layer" in sys.argv
if CASING_LAYER:                # the old experiment keeps its numbering
    MOVED = {}
# Place of each separate casing in the tunnel layer (its ranks 0x17-0x1f are free): rank of the road -> rank
CASE_RANK = {rank: 0x17 + n for n, rank in enumerate((0x08, 0x0a, 0x0f, 0x10, 0x12, 0x13, 0x14, 0x15, 0x16))}


def load_make_typ():
    spec = importlib.util.spec_from_file_location("make_typ", os.path.join(repo, "typ", "make_typ.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The TYP is written with name tags in place of the colours: "{BG}", and "{WHITE~}" for the lightened
# colour of a tunnel. The tags become day colours at the very end (resolve), and a night colour is
# looked up by the name in the tag. With the values of the day colours as keys two equal day colours
# would share one night colour, and the colours page probes the TYP with palettes where all are equal.
_plain = load_make_typ()
DAY = _plain.palette()                          # name -> day colour, TYP_PALETTE applied
TAG = re.compile(r"\{([A-Z_]+)(~?)\}")
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as _handle:
    json.dump({name: "{%s}" % name for name in DAY}, _handle)
_asked = os.environ.get("TYP_PALETTE")
os.environ["TYP_PALETTE"] = _handle.name
try:
    mt = load_make_typ()
finally:
    os.remove(_handle.name)
    if _asked is None:
        del os.environ["TYP_PALETTE"]
    else:
        os.environ["TYP_PALETTE"] = _asked
mt.lighten = lambda tag: "{%s~}" % TAG.fullmatch(tag).group(1)


def resolve(text):
    """Name tags -> day colours."""
    return TAG.sub(lambda m: _plain.lighten(DAY[m.group(1)]) if m.group(2) else DAY[m.group(1)], text)

if "--less" in sys.argv:        # Map Detail Less: level 21 is on screen at 500 m and takes the look of 22
    TIER = {24: 0, 23: 1, 22: 2, 21: 2, 20: 3, 19: 3, 18: 3}
    NEW = {24: (24, 24), 23: (23, 23), 22: (21, 22), 21: (20, 20), 20: (20, 20), 19: (19, 19), 18: (18, 18)}
elif "--coarse" not in sys.argv:    # canonical levels
    TIER = {24: 0, 23: 1, 22: 2, 21: 3, 20: 3, 19: 3, 18: 3}
    NEW = {level: (level, level) for level in TIER}
else:                           # --coarse: the looks moved to coarser levels
    TIER = {24: 0, 23: 0, 22: 1, 21: 1, 20: 2, 19: 3, 18: 3}
    NEW = {24: (23, 24), 23: (21, 22), 22: (20, 20), 21: (19, 19), 20: (19, 19), 19: (18, 18), 18: (18, 18)}
B_TWIN, B_NOENTRY, B_RAIL = 0x19, 0x1A, 0x1B
UNDER, BASE, BRIDGE, OVER = mt.LAYER_UNDER, mt.LAYER_BASE, mt.LAYER_BRIDGE, mt.LAYER_OVER
solid_spec = {r[0]: r for r in mt.SOLID}
bitmap_spec = {r[0]: r for r in mt.BITMAP}


def T(tier, rank, layer=BASE):
    return mt.line_type(tier, rank, layer)


# ---------------------------------------------------------------- TYP
original = mt.collect_lines
FIRST = mt.FIRST_TYPE
COMMON = FIRST + 4 * len(mt.TIERS)


def decode(type_id):
    byte, rank = (type_id >> 8) & 0xFF, type_id & 0xFF
    if byte == COMMON:
        return None, None, rank
    return (byte - FIRST) // 4, (byte - FIRST) % 4, rank


def separate_casing(type_id):
    """Is the casing of this road type drawn as a line of its own (--casing-layer)?"""
    tier, layer, rank = decode(type_id)
    if not CASING_LAYER or tier is None or layer != BASE or rank not in CASE_RANK:
        return False
    spec = solid_spec[rank][4 + tier]
    return bool(spec and spec[1])


def casing_type(type_id):
    tier, _layer, rank = decode(type_id)
    return T(tier, CASE_RANK[rank], UNDER)


def w(pixels, tier=0):
    """A width or a casing of the canonical TYP in pixels of this TYP (--bold, --bold-far)."""
    factor = BOLD if tier in (0, 1) else BOLD_FAR
    return max(1, int(pixels * factor + 0.5)) if pixels else 0


def wd(pixels, tier=0):
    """Width of a plain dash or of a route overlay (--dash)."""
    factor = DASH if tier in (0, 1) else DASH * BOLD_FAR / BOLD
    return max(1, int(pixels * factor + 0.5)) if pixels else 0


def collect():
    lines = []
    for type_id, kind, name, params, label in original():
        tier, layer, rank = decode(type_id)
        if kind != "bitmap":
            fill, edge, width, border = params
            if rank == 0x18 and tier in CYCLEWAY_WIDE:          # cycleway, and the cycleway on a bridge
                if layer == BASE:
                    lines.append((type_id, kind, name, (fill, edge) + CYCLEWAY_WIDE[tier], label))
                else:
                    total = CYCLEWAY_WIDE[tier][0] + 2 * CYCLEWAY_WIDE[tier][1]
                    lines.append((type_id, kind, name, (fill, edge, total, w(border, tier)), label))
                continue
            if separate_casing(type_id):
                lines.append((casing_type(type_id), kind, name + " (обводка)",
                              (edge, None, w(width, tier) + 2 * w(border, tier), 0), None))
                border = 0
            lines.append((type_id, kind, name, (fill, edge if border else None, w(width, tier), w(border, tier)), label))
            continue
        rows, colour1, colour2 = params
        height = len(rows)
        a, b = None, None
        if tier is None:                                    # ferry, state border: stay continuous
            a = (colour1, None, w(2 if rank == 0 else 3, tier), 0)
        elif layer == UNDER:                                # road tunnel: paler road, dashed casing
            _r, _n, fill, edge, *per_tier = solid_spec[rank]
            width, border = w(per_tier[tier][0], tier), w(per_tier[tier][1], tier)
            a = (mt.lighten(fill), edge, width, border)
            b = (T(tier, rank - 0x10, UNDER), (mt.lighten(fill), mt.lighten(fill), width, border))
        elif layer == BRIDGE:                               # footbridge
            a = (mt.BG, mt.RAIL, w(4, tier), w(2 if tier == 0 else 1, tier))
        elif layer == OVER:
            a = (colour1, None, wd(height if rank == 0x05 else 3, tier), 0)  # underpass / route overlay
        elif rank == 0x03:                                  # railway: dark, white dashes inside
            edge = w(1, tier)
            a = (mt.RAIL, None, w(height, tier), 0)
            b = (T(tier, B_RAIL), (mt.WHITE, mt.RAIL, max(w(height, tier) - 2 * edge, 1), edge))
        elif rank == 0x09:                                  # twin track: dashed casing
            edge = 2 if height > 5 else 1
            a = (mt.GRAVEL, mt.GRAVEL_EDGE, w(height - 2 * edge, tier), w(edge, tier))
            b = (T(tier, B_TWIN), (mt.GRAVEL, None, w(height - 2 * edge, tier), 0))
        elif rank == 0x0C:                                  # under construction: cased white dashes
            a = (mt.WHITE, mt.WHITE_EDGE, w(height, tier), w(2 if tier == 0 else 1, tier))
        elif rank == 0x0E:                                  # no entry: red dots in a cased white road
            border = w(2 if tier == 0 else 1, tier)
            a = (mt.NO_ENTRY, mt.WHITE_EDGE, w(height, tier), border)
            b = (T(tier, B_NOENTRY), (mt.WHITE, mt.WHITE_EDGE, w(height, tier), border))
        elif rank == 0x07:                                  # steps: a row of dots
            a = (colour1, None, STEPS_WIDTH, 0)
        elif rank in (0x04, 0x05, 0x06):                    # plain dashes: paths, bad track
            a = (colour1, None, wd(height, tier), 0)
        else:                                               # intermittent stream
            a = (colour1, None, w(height, tier), 0)
        lines.append((type_id, "solid", name, a, label))
        if b:
            lines.append((b[0], "solid", name + " (промежуток)", b[1], None))
    return [(MOVED.get(entry[0], entry[0]),) + tuple(entry[1:]) for entry in lines]


mt.collect_lines = collect
NIGHT = next((a[8:] for a in sys.argv if a.startswith("--night=")), "")
NIGHT_PALETTE, NIGHT_MISSING = {}, set()     # name -> night colour; names with no night colour
MARK_COLOUR = "#101010"                      # level marks: not a colour of the palette
# A white road is as white in a tunnel as outside (white cannot be lightened), and by night it keeps
# its colour there too. The other roads fade half-way to the ground in a tunnel.
TUNNEL_AS_ROAD = ("WHITE",)


def mix(colour, other, share):
    a = [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * share) for x, y in zip(a, b))


if NIGHT not in ("", "same"):
    with open(NIGHT, encoding="utf-8") as handle:
        NIGHT_PALETTE = {name: value.upper() for name, value in json.load(handle).items()}
    unknown = sorted(set(NIGHT_PALETTE) - set(DAY))
    assert not unknown, "night palette: unknown colours %s" % ", ".join(unknown)


def night(colour):
    """The colour of the night display for a day colour (a name tag)."""
    if not NIGHT_PALETTE:                    # --night=same
        return colour
    if colour == MARK_COLOUR:
        return NIGHT_PALETTE.get("LABEL", "#F0F0EC")
    name, lightened = TAG.fullmatch(colour).groups()
    if name not in NIGHT_PALETTE:
        NIGHT_MISSING.add(name)
        return colour
    if lightened and name not in TUNNEL_AS_ROAD:
        return mix(NIGHT_PALETTE[name], NIGHT_PALETTE.get("BG", "#000000"), 0.5)
    return NIGHT_PALETTE[name]


def emit_polygon_night(out, type_id, name, colour1, colour2, pattern):
    out += ["[_polygon]", "; %s" % name, "Type=0x%02x" % type_id]
    if pattern is None:
        out += ['Xpm="0 0 2 0"', '"X c %s"' % colour1, '"3 c %s"' % night(colour1)]
    else:
        rows = pattern()
        assert len(rows) == 32 and all(len(r) == 32 for r in rows), name
        out += ['Xpm="32 32 4 1"', '"X c %s"' % colour1, '". c %s"' % (colour2 or "none"),
                '"3 c %s"' % night(colour1), '"4 c %s"' % (night(colour2) if colour2 else "none")]
        out += ['"%s"' % r for r in rows]
    out += ["[end]", ""]


def emit_line_night(out, type_id, kind, name, params, label):
    assert kind == "solid", name
    fill, edge, width, border = params
    out += ["[_line]", "; %s" % name, "Type=0x%05x" % type_id]
    if label:
        out += ["ExtendedLabels=Y", "FontStyle=%s" % label[0], "DayCustomColor=%s" % label[1],
                "NightCustomColor=%s" % night(label[1])]
    out.append("LineWidth=%d" % width)
    if border:
        out += ["BorderWidth=%d" % border, 'Xpm="0 0 4 0"', '"1 c %s"' % fill, '"2 c %s"' % edge,
                '"3 c %s"' % night(fill), '"4 c %s"' % night(edge)]
    else:
        out += ['Xpm="0 0 2 0"', '"1 c %s"' % fill, '"3 c %s"' % night(fill)]
    out += ["[end]", ""]


def emit_point_night(out, type_id, name, font, icon):
    out += ["[_point]", "; %s" % name, "Type=0x%04x" % type_id, "ExtendedLabels=Y", "FontStyle=%s" % font,
            "DayCustomColor=%s" % mt.LABEL, "NightCustomColor=%s" % night(mt.LABEL)]
    out += ['DayXpm="1 1 1 1"', '". c none"', '"."'] if icon is None else icon
    out += ["[end]", ""]


if NIGHT:
    mt.emit_polygon, mt.emit_line, mt.emit_point = emit_polygon_night, emit_line_night, emit_point_night
MARKS = "--marks" in sys.argv
# The ground lies right above the background 0x4b; every other area moves one step up.
mt.POLYGONS = ([entry for entry in mt.POLYGONS if entry[0] == 0x4b]
               + [(GROUND_TYPE, "Земля (подложка под ночной режим)", 2, mt.BG, None, None)]
               + [(entry[0], entry[1], entry[2] + 1) + tuple(entry[3:]) for entry in mt.POLYGONS if entry[0] != 0x4b])
if MARKS:
    mt.POLYGONS.append((MARK_TYPE, "Отметка уровня карты", 12, MARK_COLOUR, None, None))

# ---------------------------------------------------------------- style
style = os.path.join(out, "style")
shutil.rmtree(style, ignore_errors=True)
os.makedirs(style)
for name in ("info", "version", "options", "relations"):
    shutil.copy(os.path.join(repo, "style", name), style)


def remap_min(match):
    return "resolution %d" % NEW[int(match.group(1))][0]


for name in ("polygons", "points"):
    text = open(os.path.join(repo, "style", name), encoding="utf-8").read()
    text = re.sub(r"resolution (\d+)(?!-)", remap_min, text)
    if name == "polygons":
        text += "\n# Подложка земли (cut1060.py): фон 0x4b прибор ночью красит по-своему.\n" \
                "gm:ground=yes [0x%02x resolution 18]\n" % GROUND_TYPE
    if MARKS and name == "polygons":
        text += "\n# Отметки уровня (marks.py): число видно только на своём уровне карты.\n" + "".join(
            "gm:mark=%d [0x%02x resolution %d-%d]\n" % (level, MARK_TYPE, level, level) for level in TIER)
    open(os.path.join(style, name), "w", encoding="utf-8").write(text)

canon = open(os.path.join(repo, "style", "lines"), encoding="utf-8").read()
marker = "# ---------------------------------------------------------------------------\n# 2."
section1, rest = canon.split(marker, 1)
if PLAIN_NOACCESS:              # the class is never given, the road falls through to its ordinary class
    assert section1.count("{ set gm:cls=noaccess }") == 2
    section1 = section1.replace("{ set gm:cls=noaccess }", "{ set gm:noentry=yes }")

ROADS = [("gm:cls=green_wide", 0x16), ("gm:cls=green_link", 0x15), ("gm:cls=primary", 0x14),
         ("gm:cls=secondary", 0x13), ("gm:cls=tertiary", 0x12)]
PATHLIKE_TUN = "(gm:cls=path | gm:cls=hardpath | gm:cls=paved_path | gm:cls=cycleway | gm:cls=steps)"
PATHLIKE_BR = "(gm:cls=path | gm:cls=hardpath | gm:cls=paved_path | gm:cls=badtrack | gm:cls=steps)"
SOLID_CLS = [("green_wide", 0x16), ("green_link", 0x15), ("primary", 0x14), ("secondary", 0x13),
             ("tertiary", 0x12), ("street", 0x10), ("cycleway", 0x18), ("gravel", 0x0A),
             ("paved_path", 0x08), ("pedestrian", 0x0F)]
DASH_CLS = [("badtrack", 0x04), ("hardpath", 0x06), ("path", 0x05), ("steps", 0x07)]


def has_solid(rank, tier):
    return solid_spec[rank][4 + tier] is not None


def has_bitmap(rank, tier):
    return bitmap_spec[rank][5][tier] is not None


def piece_rules():
    r = []
    for level in (24, 23, 22, 21, 20, 19, 18):
        t = TIER[level]
        lv = "gm:lv=%d" % level
        res = "resolution %d-%d" % (level, level)
        r.append("\n# --- куски для разрешения %d (ступень %s) ---" % (level, mt.TIERS[t]))
        # route overlays: offset dashes made by cut1060.py
        for key, near, far in (("bike", 0x01, 0x02), ("mtb", 0x03, 0x04)):
            offsets = {row[0]: row[6] for row in mt.ROUTES}
            if t < len(offsets[near]) and offsets[near][t]:
                r.append("%s & gm:rt=%s & gm:far!=yes [0x%05x %s]" % (lv, key, T(t, near, OVER), res))
                r.append("%s & gm:rt=%s & gm:far=yes [0x%05x %s]" % (lv, key, T(t, far, OVER), res))
        if t <= 1:
            for cond, rank in ROADS + [("(gm:cls=street | gm:cls=noaccess)", 0x10)]:
                r.append("%s & gm:tun=yes & %s & gm:ab=a [0x%05x %s]" % (lv, cond, T(t, rank, UNDER), res))
                r.append("%s & gm:tun=yes & %s & gm:ab=b [0x%05x %s]" % (lv, cond, T(t, rank - 0x10, UNDER), res))
            r.append("%s & gm:tun=yes & %s & gm:ab=a [0x%05x %s]" % (lv, PATHLIKE_TUN, T(t, 0x05, OVER), res))
            r.append("%s & gm:tun=yes & %s { set gm:cls=none }" % (lv, PATHLIKE_TUN))
            for cond, rank in ROADS + [("gm:cls=street", 0x10), ("gm:cls=cycleway", 0x18),
                                       ("(gm:cls=gravel | gm:cls=twintrack)", 0x0A), (PATHLIKE_BR, 0x05)]:
                r.append("%s & gm:br=yes & %s [0x%05x %s continue]" % (lv, cond, T(t, rank, BRIDGE), res))
        for cls, rank in SOLID_CLS:
            if has_solid(rank, t):
                if separate_casing(T(t, rank)):
                    r.append("%s & gm:cls=%s [0x%05x %s continue]" % (lv, cls, casing_type(T(t, rank)), res))
                r.append("%s & gm:cls=%s [0x%05x %s]" % (lv, cls, T(t, rank), res))
        if has_bitmap(0x09, t):
            r.append("%s & gm:cls=twintrack & gm:ab=a [0x%05x %s]" % (lv, T(t, 0x09), res))
        for cls, rank in DASH_CLS:
            if has_bitmap(rank, t):
                r.append("%s & gm:cls=%s & gm:ab=a [0x%05x %s]" % (lv, cls, T(t, rank), res))
        if has_bitmap(0x0E, t):
            r.append("%s & gm:cls=noaccess & gm:ab=a [0x%05x %s]" % (lv, T(t, 0x0E), res))
            r.append("%s & gm:cls=noaccess & gm:ab=b [0x%05x %s]" % (lv, T(t, B_NOENTRY), res))
        if has_bitmap(0x0C, t):
            r.append("%s & gm:cls=construction & gm:ab=a [0x%05x %s]" % (lv, T(t, 0x0C), res))
        if has_bitmap(0x03, t):
            r.append("%s & railway=rail & gm:ab=a [0x%05x %s]" % (lv, T(t, 0x03), res))
            r.append("%s & railway=rail & gm:ab=b [0x%05x %s]" % (lv, T(t, B_RAIL), res))
        if has_bitmap(0x02, t):
            r.append("%s & waterway=stream & intermittent=yes & gm:ab=a [0x%05x %s]" % (lv, T(t, 0x02), res))
    return "\n".join(r)


def original_rules(text):
    """Canonical sections 2-7 for ways that were not cut: resolutions moved, route overlays dropped,
    and a guard so that a cut way is drawn only on the levels its pieces do not cover."""
    out_lines, pending = [], []
    for raw in text.split("\n"):
        stripped = raw.strip()
        if not pending and (not stripped or stripped.startswith("#")):
            out_lines.append(raw)
            continue
        pending.append(stripped)
        joined = " ".join(pending)
        if "]" not in joined and not joined.endswith("}"):
            continue
        pending = []
        if "gm:bike" in joined or "gm:mtb" in joined:
            continue
        if "[" not in joined:
            out_lines.append(joined)
            continue
        cond, bracket = joined[:joined.rindex("[")].strip(), joined[joined.rindex("["):]
        m = re.search(r"resolution (\d+)(?:-(\d+))?", bracket)
        low = int(m.group(1))
        high = int(m.group(2)) if m.group(2) else None
        if high is None:
            new = "resolution %d" % NEW[low][0]
            tier = 0 if low == 24 else None                 # "resolution 18" = on every level
        else:
            new = "resolution %d-%d" % (NEW[low][0], NEW[high][1])
            tier = TIER[low] if low == high else 3
            tier = {24: 0, 23: 1, 22: 2}.get(high, 3)
        guard = {0: "gm:cut!=21 & gm:cut!=twin & ", 1: "gm:cut!=21 & gm:cut!=twin & ",
                 2: "gm:cut!=twin & "}.get(tier, "")
        bracket = bracket.replace(m.group(0), new)
        type_text = re.match(r"\[\s*(0x[0-9a-fA-F]+)", bracket).group(1)
        if separate_casing(int(type_text, 16)):
            under = bracket.replace(type_text, "0x%05x" % casing_type(int(type_text, 16)))
            if "continue" not in under:
                under = under.rstrip("]").rstrip() + " continue]"
            out_lines.append("%sgm:lv!=* & (%s) %s" % (guard, cond, under))
        out_lines.append("%sgm:lv!=* & (%s) %s" % (guard, cond, bracket))
    return "\n".join(out_lines)


lines = [
    "# Сгенерировано profile1060.py из style/lines — руками не править.",
    "",
    "# Линия целиком заменена кусками (cut1060.py): сама не рисуется.",
    "gm:cut=all { set gm:cls=none; delete railway; delete waterway }",
    "",
    section1.rstrip(),
    "",
] + ([
    "# Дороги, закрытые для велосипеда, не рисуются (--hide-noaccess).",
    "gm:cls=noaccess { set gm:cls=none }",
    "",
] if HIDE_NOACCESS else []) + [
    "# Куски: подписей на них нет (иначе подпись была бы на каждом штрихе).",
    "gm:lv=* { delete mkgmap:label:1 }",
    piece_rules(),
    "",
    "# Кусок, для которого правила не нашлось, не рисуется.",
    "gm:lv=* { set gm:cls=none; delete railway; delete waterway }",
    "",
    "# Двухколейка: сама линия — ровная светлая полоса, пунктирную обводку дают куски.",
    "gm:cut=twin & gm:cls=twintrack [0x%05x resolution %d-%d continue]" % ((T(2, B_TWIN),) + NEW[22]),
    "gm:cut=twin & gm:cls=twintrack [0x%05x resolution %d-%d continue]" % ((T(1, B_TWIN),) + NEW[23]),
    "gm:cut=twin & gm:cls=twintrack [0x%05x resolution %d]" % (T(0, B_TWIN), NEW[24][0]),
    "",
    marker + original_rules(rest),
]
text = "\n".join(lines) + "\n"
for old, new in MOVED.items():
    assert "0x%05x" % new not in text
    text = text.replace("0x%05x" % old, "0x%05x" % new)
open(os.path.join(style, "lines"), "w", encoding="utf-8").write(text)
with open(os.path.join(out, "typ.txt"), "w", encoding="utf-8") as handle:
    handle.write(resolve(mt.build()))
if NIGHT_MISSING:
    print("no night colour for: %s (the day colour is kept)" % ", ".join(sorted(NIGHT_MISSING)))
print("style -> %s, typ -> %s" % (style, os.path.join(out, "typ.txt")))
