#!/usr/bin/env python3
"""Out-of-tree mkgmap run: style and TYP from one checkout, split tiles and tools from the main folder.

    python3 build_region.py <repo with style/> <main folder> <region> <out.img> [--transparent]

Same mkgmap options as build.sh; nothing is written into either folder (work files go to
$EDGE1060_WORK or the system temp folder).

Options: --split=<dir with splitter tiles>  --style=<style dir>  --typ=<typ.txt>  --name=<map name>
         --fid=<family id>  --tag=<suffix of the work folder>  --merge-lines  --transparent
"""
import os
import tempfile
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("EDGE1060_WORK") or os.path.join(tempfile.gettempdir(), "garmin-map-edge1060")
os.makedirs(WORK, exist_ok=True)


def conf(main, region):
    text = open(os.path.join(main, "regions", region + ".conf"), encoding="utf-8").read()
    get = lambda k, d=None: (re.search(r'^%s="?([^"\n#]*?)"?\s*(#.*)?$' % k, text, re.M) or [None, d])[1]
    return get("NAME"), int(get("MAP_ID")), get("CODE_PAGE", "1252"), get("DRAW_PRIORITY", "31")


def main():
    repo, main_dir, region, target = sys.argv[1:5]
    transparent = "--transparent" in sys.argv
    opt = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[5:] if a.startswith("--") and "=" in a}
    typ_src = opt.get("--typ", os.path.join(repo, "style", "typ.txt"))
    style_dir = opt.get("--style", os.path.join(repo, "style"))
    tag = opt.get("--tag", "")
    name, fid, codepage, priority = conf(main_dir, region)
    name = opt.get("--name", name)
    new_fid = int(opt.get("--fid", fid))
    work = os.path.join(WORK, "work-" + region + ("-t" if transparent else "") + tag)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(os.path.join(work, "img"))
    typ = os.path.join(work, region + "-typ.txt")
    text = open(typ_src, encoding="utf-8").read()
    open(typ, "w", encoding="utf-8").write(text.replace("@FID@", str(new_fid)).replace("@CODEPAGE@", codepage))

    split = opt.get("--split", os.path.join(main_dir, "build", region, "split"))
    tiles = sorted(f for f in os.listdir(split) if re.fullmatch(r"\d{8}\.osm\.pbf", f))
    args = os.path.join(work, "template.args")
    with open(args, "w") as fh:
        for tile in tiles:
            fh.write("mapname: %d%s\ndescription: %s\ninput-file: %s\n\n"
                     % (new_fid, tile[4:8], name, os.path.join(split, tile)))

    jar = sorted(d for d in os.listdir(os.path.join(main_dir, "tools")) if d.startswith("mkgmap-r"))[-1]
    java = next(p for p in (os.path.join(main_dir, "tools/env/lib/jvm/bin/java"),
                            os.path.join(main_dir, "tools/env/bin/java")) if os.access(p, os.X_OK))
    cmd = [java, "-Xmx" + os.environ.get("EDGE1060_HEAP", "4g"), "-jar", os.path.join(main_dir, "tools", jar, "mkgmap.jar"),
           "--output-dir=" + os.path.join(work, "img"), "--style-file=" + style_dir,
           "--family-id=%d" % new_fid, "--product-id=1",
           "--family-name=" + name, "--series-name=" + name, "--area-name=" + name,
           "--code-page=" + codepage, "--lower-case", "--order-by-decreasing-area", "--add-pois-to-areas",
           "--reduce-point-density-polygon=3", "--draw-priority=" + priority]
    if transparent:
        cmd.append("--transparent")
    if "--merge-lines" in sys.argv:
        cmd.append("--merge-lines")
    cmd += ["--gmapsupp", "-c", args, typ]
    log = os.path.join(work, "mkgmap.log")
    with open(log, "w") as fh:
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=work).returncode
    out = open(log, errors="replace").read()
    bad = [l for l in out.splitlines()
           if re.search(r"^SEVERE|^ERROR|Error in style|Exception in thread|^java\.|Number of (MapFailed|Exit)Exceptions: [1-9]", l)]
    warn = [l for l in out.splitlines() if l.startswith("WARNING") and "max-jobs" not in l]
    img = os.path.join(work, "img", "gmapsupp.img")
    if rc or bad or not os.path.exists(img):
        print("FAILED rc=%s\n%s" % (rc, "\n".join((bad or out.splitlines())[:30])))
        sys.exit(1)
    shutil.copy(img, target)
    print("%s: %s, id %d, %d tiles, %.1f MB, warnings %d -> %s"
          % (region, name, fid, len(tiles), os.path.getsize(target) / 1e6, len(warn), target))


if __name__ == "__main__":
    main()
