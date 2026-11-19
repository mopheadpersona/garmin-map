#!/usr/bin/env python3
"""Style and TYP for devices that ignore TYP line bitmaps and switch map levels early (Edge 1050/1060).

    python3 profile1060.py <repo> <out dir> [--bold]

--bold: thicker lines and casings for the dense screen of the Edge 1050/1060.

Writes <out dir>/style (mkgmap style) and <out dir>/typ.txt. Two changes against the canonical style:
  * levels: the four looks of the style move to the resolutions the device really shows
        look "вплотную"  24      -> 24, 23        look "окрестности" 22    -> 20
        look "крупно"    23      -> 22, 21        look "обзор"       18-21 -> 19, 18
  * patterned lines are not TYP bitmaps: the data holds ready-cut pieces (cut1060.py, tags gm:lv and
    gm:ab) and every piece is a plain solid line; a pattern is an alternation of two solid types.
"""
import importlib.util
import os
import re
import shutil
import sys

repo, out = sys.argv[1], sys.argv[2]
BOLD = "--bold" in sys.argv
spec = importlib.util.spec_from_file_location("make_typ", os.path.join(repo, "typ", "make_typ.py"))
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)

if "--fine" in sys.argv:        # canonical levels; the device needs a higher Map Detail setting
    TIER = {24: 0, 23: 1, 22: 2, 21: 3, 20: 3, 19: 3, 18: 3}
    NEW = {level: (level, level) for level in TIER}
else:                           # Map Detail Normal: the looks moved to the levels the device shows
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


def collect():
    lines = []
    for type_id, kind, name, params, label in original():
        if kind != "bitmap":
            lines.append((type_id, kind, name, params, label))
            continue
        rows, colour1, colour2 = params
        height = len(rows)
        tier, layer, rank = decode(type_id)
        a, b = None, None
        if tier is None:                                    # ferry, state border: stay continuous
            a = (colour1, None, 2 if rank == 0 else 3, 0)
        elif layer == UNDER:                                # road tunnel: paler road, dashed casing
            _r, _n, fill, edge, *per_tier = solid_spec[rank]
            width, border = per_tier[tier]
            a = (mt.lighten(fill), edge, width, border)
            b = (T(tier, rank - 0x10, UNDER), (mt.lighten(fill), mt.lighten(fill), width, border))
        elif layer == BRIDGE:                               # footbridge
            a = (mt.BG, mt.RAIL, 4, 2 if tier == 0 else 1)
        elif layer == OVER:
            a = (colour1, None, height if rank == 0x05 else 3, 0)   # underpass / route overlay
        elif rank == 0x03:                                  # railway: dark, white dashes inside
            a = (mt.RAIL, None, height, 0)
            b = (T(tier, B_RAIL), (mt.WHITE, mt.RAIL, max(height - 2, 1), 1))
        elif rank == 0x09:                                  # twin track: dashed casing
            edge = 2 if height > 5 else 1
            a = (mt.GRAVEL, mt.GRAVEL_EDGE, height - 2 * edge, edge)
            b = (T(tier, B_TWIN), (mt.GRAVEL, None, height - 2 * edge, 0))
        elif rank == 0x0C:                                  # under construction: cased white dashes
            a = (mt.WHITE, mt.WHITE_EDGE, height, 2 if tier == 0 else 1)
        elif rank == 0x0E:                                  # no entry: red dots in a cased white road
            border = 2 if tier == 0 else 1
            a = (mt.NO_ENTRY, mt.WHITE_EDGE, height, border)
            b = (T(tier, B_NOENTRY), (mt.WHITE, mt.WHITE_EDGE, height, border))
        else:                                               # plain dashes: paths, bad track, steps, streams
            a = (colour1, None, height, 0)
        lines.append((type_id, "solid", name, a, label))
        if b:
            lines.append((b[0], "solid", name + " (промежуток)", b[1], None))
    if BOLD:
        lines = [bolder(entry) for entry in lines]
    return lines


def bolder(entry):
    """Thicker lines for a 267 ppi screen: a one-pixel casing there is a hairline."""
    type_id, kind, name, params, label = entry
    if kind != "solid":
        return entry
    fill, edge, width, border = params
    tier, layer, _rank = decode(type_id)
    close = tier in (0, 1)
    if layer == OVER:                                       # route dashes and underpass keep their weight
        return entry
    width = max(1, round(width * (1.35 if close else 1.25)))
    if border:
        border = max(2, round(border * 1.35)) if close else border
    return (type_id, kind, name, (fill, edge, width, border), label)


mt.collect_lines = collect

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
    open(os.path.join(style, name), "w", encoding="utf-8").write(text)

canon = open(os.path.join(repo, "style", "lines"), encoding="utf-8").read()
marker = "# ---------------------------------------------------------------------------\n# 2."
section1, rest = canon.split(marker, 1)

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
open(os.path.join(style, "lines"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
with open(os.path.join(out, "typ.txt"), "w", encoding="utf-8") as handle:
    handle.write(mt.build())
print("style -> %s, typ -> %s" % (style, os.path.join(out, "typ.txt")))
