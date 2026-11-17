#!/usr/bin/env python3
"""Открывает out/<регион>.img в QMapShack и оставляет окно пользователю (см. view.sh)."""

import hashlib
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import screenshots as shots  # noqa: E402

region = sys.argv[1] if len(sys.argv) > 1 else "prague"
src = os.path.join(shots.ROOT, "out", region + ".img")
if not os.path.exists(src):
    sys.exit("нет %s — сначала ./build.sh %s" % (src, region))

# Копия вне ~/Desktop: QMapShack не спрашивает доступ к папке, а пересборка
# не портит файл, открытый в программе.
work = os.path.join(os.environ.get("TMPDIR", "/tmp"), "garmin-map-view")
cfg = os.path.join(work, "qms.ini")
map_file = os.path.join(work, region + ".img")
os.makedirs(work, exist_ok=True)

def viewer_pids():
    return subprocess.run(["pgrep", "-f", cfg], capture_output=True, text=True).stdout.split()


# Закрываем прежнее окно просмотра (только своё, с этим файлом настроек).
# Сначала вежливо, чтобы QMapShack сохранил место и масштаб; не вышло — принудительно.
if viewer_pids():
    try:
        subprocess.run(["osascript", "-e", 'tell application id "org.qlandkarte.QMapShack" to quit'],
                       capture_output=True, timeout=8)
    except subprocess.TimeoutExpired:
        pass
    for _ in range(10):
        if not viewer_pids():
            break
        time.sleep(0.5)
    for pid in viewer_pids():
        subprocess.run(["kill", pid])
    time.sleep(0.5)

# Место и масштаб берём из прежних настроек, если QMapShack их сохранил.
# При сохранении он даёт виду своё имя (key_...), поэтому ищем по окончанию ключа.
keep = {}
if os.path.exists(cfg):
    with open(cfg, encoding="utf-8") as handle:
        for line in handle:
            key, _, value = line.rstrip("\n").partition("=")
            if key.startswith("Views\\") and key.endswith("\\posFocus"):
                keep["Views\\View1\\posFocus"] = value
            elif key.startswith("Views\\") and key.endswith("\\map2\\zoomIndex"):
                keep["Views\\View1\\map2\\zoomIndex"] = value

shutil.copy(src, map_file)
places = shots.PLACES.get(region)
lat, lon = (places[0][1], places[0][2]) if places else (50.0, 14.4)
shots.write_config(cfg, map_file, lat, lon, 15.0, 0, fixed_window=False)
if len(keep) == 2:
    with open(cfg, encoding="utf-8") as handle:
        lines = [l for l in handle.read().splitlines() if l.partition("=")[0] not in keep]
    lines[1:1] = ["%s=%s" % item for item in keep.items()]
    with open(cfg, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

subprocess.run(["open", "-n", "-a", shots.QMS_APP, "--args", "-n", "-c", cfg], check=True)
print("QMapShack открыт с картой %s (%s)" % (region, time.strftime("%H:%M", time.localtime(os.path.getmtime(src)))))
