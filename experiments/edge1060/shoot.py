#!/usr/bin/env python3
"""Frames of one map at chosen places, zooms and map levels; optionally glued into one sheet.

    python3 shoot.py <repo> <img> <out dir> <prefix> <lat,lon> <zoom:bits[:label]> [...]

zoom = metres per screen point in QMapShack, bits = Garmin resolution to show.
"""
import math
import os
import shutil
import sys

repo, img, out_dir, prefix = sys.argv[1:5]
lat, lon = map(float, sys.argv[5].split(","))
frames = [a.split(":") for a in sys.argv[6:]]
sys.path.insert(0, os.path.join(repo, "scripts"))
import screenshots as s  # noqa: E402

s.is_blank = lambda png: False
os.makedirs(s.WORK, exist_ok=True)
os.makedirs(out_dir, exist_ok=True)
map_dir = os.path.join(s.WORK, "maps")
shutil.rmtree(map_dir, ignore_errors=True)
os.makedirs(map_dir)
map_file = os.path.join(map_dir, "prague.img")
shutil.copy(img, map_file)


def probe():
    image, window_w = s.capture(None, lat, lon, 15.0, 0, back="#FF00FF")
    k = round(image[0] / window_w)
    left, top, right, bottom = s.find_canvas(image)
    return image[:2], k, (left + right) // 2, (top + bottom) // 2


probe_size, k, cx, cy = probe()
cols = []
for frame in frames:
    zoom, bits = float(frame[0]), int(frame[1])
    label = frame[2] if len(frame) > 2 else "%gm-res%d" % (zoom, bits)
    for _attempt in range(4):
        image, _ = s.capture(map_file, lat, lon, zoom, bits - s.natural_bits(zoom))
        if image[:2] == probe_size:
            break
        probe_size, k, cx, cy = probe()
    fw, fh = s.FRAME_W * k, s.FRAME_H * k
    _w, _h, rows = image
    x0, y0 = cx - fw // 2, cy - fh // 2
    rows = [bytearray(row[x0 * 3:(x0 + fw) * 3]) for row in rows[y0:y0 + fh]]
    s.write_png(os.path.join(out_dir, "%s_%s.png" % (prefix, label)), fw, rows)
    cols.append((fw, rows))
    print("shot", prefix, label, flush=True)

GAP = 12
sheet = []
for y in range(len(cols[0][1])):
    row = bytearray()
    for i, (width, rows) in enumerate(cols):
        if i:
            row += b"\xff\xff\xff" * GAP
        row += rows[y]
    sheet.append(row)
s.write_png(os.path.join(out_dir, "%s_sheet.png" % prefix), sum(c[0] for c in cols) + GAP * (len(cols) - 1), sheet)
print("sheet", prefix)
