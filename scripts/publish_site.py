#!/usr/bin/env python3
"""Выкладка конфигуратора цветов на GitHub Pages.

    python3 scripts/publish_site.py dist     # собрать папку build/pages
    python3 scripts/publish_site.py push     # отправить её в ветку gh-pages одним коммитом

dist. Копирует site/ в build/pages. Карты режутся на части по 40 МБ: git не принимает файлы
больше 100 МБ, а страница склеивает части сама. В имени части — начало контрольной суммы
карты, поэтому после пересборки у частей новые адреса и старый кэш к новой карте не подмешается.
Проверить папку до выкладки: python3 scripts/serve_site.py 8766 build/pages

push. В build/pages создаётся репозиторий из одного коммита и отправляется в ветку gh-pages
с заменой (--force). История не копится нарочно: иначе каждая пересборка карт добавляла бы
в репозиторий весь их размер. В эту ветку попадает только готовая страница, исходников проекта
в ней нет. Третьим аргументом можно дать строку, которая допишется в конец сообщения коммита.

Репозиторий создан один раз командой gh repo create mopheadpersona/garmin-map --public;
Pages включился сам при первой отправке ветки gh-pages.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
DIST = os.path.join(ROOT, "build", "pages")

REMOTE = "git@github.com:mopheadpersona/garmin-map.git"
BRANCH = "gh-pages"
PAGE_URL = "https://mopheadpersona.github.io/garmin-map/"
# Адрес автора — служебный адрес GitHub, чтобы личная почта не попадала в открытый репозиторий.
AUTHOR_NAME = "mopheadpersona"
AUTHOR_EMAIL = "39918189+mopheadpersona@users.noreply.github.com"

PART_BYTES = 40 << 20
PAGES_LIMIT = 1 << 30           # предел размера сайта на GitHub Pages (мягкий): 1 ГБ
PAGE_FILES = ("index.html", "app.js", "i18n.js", "style.css", "gta.js", "gta.css")

README = """# Map colours for Garmin Edge

Pick the colours of a cycling map for Garmin Edge, check them on real map views and download
the map as an `.img` file: <%s>

The map is recoloured in your browser. Nothing is uploaded and nothing is stored on a server.

This branch holds only the built page and the map files. The maps are split into parts because
of the file size limit; the page joins them when you press “Download .img”.

Map data © OpenStreetMap contributors, available under the Open Database License (ODbL):
<https://www.openstreetmap.org/copyright>. The maps are compiled with mkgmap.
""" % PAGE_URL


def die(message):
    sys.exit("ОШИБКА: " + message)


def split_map(entry, target_dir):
    """Режет карту на части. Возвращает запись для maps.json с частями вместо одного файла."""
    src = os.path.realpath(os.path.join(SITE, entry["file"]))
    if not os.path.exists(src):
        die("нет файла карты %s — ./build.sh %s и scripts/make_site.py maps" % (entry["file"], entry["id"]))
    if os.path.getsize(src) != entry["bytes"]:
        die("размер %s не тот, что в maps.json: запустите scripts/make_site.py maps" % entry["file"])
    digest = hashlib.sha256()
    with open(src, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    tag = digest.hexdigest()[:10]
    parts = []
    with open(src, "rb") as handle:
        while True:
            data = handle.read(PART_BYTES)
            if not data:
                break
            name = "maps/%s-%s.%02d.bin" % (entry["id"], tag, len(parts))
            with open(os.path.join(target_dir, name), "wb") as out:
                out.write(data)
            parts.append({"file": name, "bytes": len(data)})
    result = {key: value for key, value in entry.items() if key != "file"}
    result["sha256"] = digest.hexdigest()
    result["parts"] = parts
    return result


def cmd_dist():
    with open(os.path.join(SITE, "data", "maps.json"), encoding="utf-8") as handle:
        maps = json.load(handle)
    if not maps:
        die("в site/data/maps.json нет карт: scripts/make_site.py maps")
    shutil.rmtree(DIST, ignore_errors=True)
    os.makedirs(os.path.join(DIST, "maps"))
    for name in PAGE_FILES:
        shutil.copy(os.path.join(SITE, name), os.path.join(DIST, name))
    shutil.copytree(os.path.join(SITE, "data"), os.path.join(DIST, "data"),
                    ignore=shutil.ignore_patterns(".DS_Store", "maps.json"))
    listing = []
    for entry in maps:
        item = split_map(entry, DIST)
        listing.append(item)
        print("%s: %d МБ, частей %d" % (entry["id"], entry["bytes"] >> 20, len(item["parts"])))
    with open(os.path.join(DIST, "data", "maps.json"), "w", encoding="utf-8") as handle:
        json.dump(listing, handle, ensure_ascii=False, indent=1)
    with open(os.path.join(DIST, ".nojekyll"), "w") as handle:      # Pages отдаёт файлы как есть
        pass
    with open(os.path.join(DIST, "README.md"), "w", encoding="utf-8") as handle:
        handle.write(README)
    total = sum(os.path.getsize(os.path.join(folder, name))
                for folder, _dirs, names in os.walk(DIST) for name in names)
    print("%s: %d МБ" % (os.path.relpath(DIST, ROOT), total >> 20))
    if total > PAGES_LIMIT:
        print("ВНИМАНИЕ: страница больше 1 ГБ — это предел GitHub Pages. Уберите карту из MAPS "
              "в scripts/make_site.py или вынесите карты на другой хостинг.")


def git(*args):
    res = subprocess.run(["git", "-C", DIST] + list(args), capture_output=True, text=True)
    if res.returncode != 0:
        die("git %s:\n%s" % (" ".join(args), (res.stdout + res.stderr)[-2000:]))
    return res.stdout


def cmd_push(trailer=None):
    if not os.path.exists(os.path.join(DIST, "index.html")):
        die("нет build/pages — сначала dist")
    shutil.rmtree(os.path.join(DIST, ".git"), ignore_errors=True)
    git("init", "-q", "-b", BRANCH)
    git("config", "user.name", AUTHOR_NAME)
    git("config", "user.email", AUTHOR_EMAIL)
    git("add", "-A")
    message = "Publish the map colours page, %s" % time.strftime("%Y-%m-%d")
    if trailer:
        message += "\n\n" + trailer
    git("commit", "-q", "-m", message)
    print("отправляю в %s (%s), это несколько минут" % (REMOTE, BRANCH), flush=True)
    git("push", "--force", REMOTE, "%s:%s" % (BRANCH, BRANCH))
    print(PAGE_URL)


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "dist":
        cmd_dist()
    elif command == "push":
        cmd_push(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
