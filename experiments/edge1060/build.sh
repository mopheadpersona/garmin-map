#!/bin/bash
# Experimental build for the Garmin Edge 1050/1060: patterned lines as real dashes.
#
#   experiments/edge1060/build.sh <region> <normal|fine> <out.img> [main folder]
#
#   <region>       regions/<region>.conf; its extract build/<region>/<region>.osm.pbf must exist
#                  (run ./build.sh <region> once in the main folder)
#   normal | fine  which map levels carry which look, see cut1060.py
#   [main folder]  where tools/ and build/ live; default: the repository root
#
# Work files go to $EDGE1060_WORK (default: the system temp folder), nothing is written into the repository.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
[ $# -ge 3 ] || { sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }
REGION="$1"; LAYOUT="$2"; OUT="$3"; MAIN="${4:-$REPO}"
case "$LAYOUT" in normal|fine) ;; *) echo "layout must be normal or fine" >&2; exit 1 ;; esac

WORK="${EDGE1060_WORK:-${TMPDIR:-/tmp}/garmin-map-edge1060}/$REGION-$LAYOUT"
EXTRACT="$MAIN/build/$REGION/$REGION.osm.pbf"
CONF="$MAIN/regions/$REGION.conf"
OSMIUM="$MAIN/tools/env/bin/osmium"
JAVA="$MAIN/tools/env/lib/jvm/bin/java"; [ -x "$JAVA" ] || JAVA="$MAIN/tools/env/bin/java"
SPLITTER="$(ls -d "$MAIN"/tools/splitter-r*/splitter.jar | sort -V | tail -1)"
for f in "$EXTRACT" "$CONF" "$OSMIUM" "$JAVA" "$SPLITTER"; do
  [ -e "$f" ] || { echo "missing: $f" >&2; exit 1; }
done
# shellcheck disable=SC1090
NAME=""; MAP_ID=""; source "$CONF"

mkdir -p "$WORK"
cd "$WORK"
step() { printf '\n=== %s ===\n' "$*"; }

step "1/6 lines that carry a pattern"
"$OSMIUM" tags-filter "$EXTRACT" \
  w/highway=path,footway,track,steps,construction w/railway=rail w/waterway=stream \
  w/tunnel=yes w/access=no,private w/bicycle=no r/route=bicycle,mtb \
  -o cand.osm.pbf --overwrite
"$OSMIUM" add-locations-to-ways cand.osm.pbf -o cand-loc.osm.pbf --overwrite
"$OSMIUM" cat cand-loc.osm.pbf -f opl,locations_on_ways=true -o cand.opl --overwrite

step "2/6 cut into pieces ($LAYOUT levels)"
python3 "$HERE/cut1060.py" cand.opl pieces "$LAYOUT"

step "3/6 merge the pieces into the extract"
"$OSMIUM" cat pieces.nodes.opl pieces.ways.opl -o pieces.osm.pbf --overwrite
"$OSMIUM" apply-changes "$EXTRACT" pieces.modify.osc -o marked.osm.pbf --overwrite
"$OSMIUM" merge marked.osm.pbf pieces.osm.pbf -o data.osm.pbf --overwrite

step "4/6 splitter"
rm -rf split
mkdir split
"$JAVA" -Xmx4g -jar "$SPLITTER" --output-dir=split --mapid="${MAP_ID}0001" --max-nodes=1200000 \
  --keep-complete=true --description="$NAME" data.osm.pbf > splitter.log 2>&1 \
  || { tail -30 splitter.log; exit 1; }
echo "tiles: $(ls split/*.osm.pbf | wc -l | tr -d ' ')"

step "5/6 style and TYP for the device"
if [ "$LAYOUT" = fine ]; then
  python3 "$HERE/profile1060.py" "$REPO" "$WORK/profile" --fine
else
  python3 "$HERE/profile1060.py" "$REPO" "$WORK/profile"
fi

step "6/6 mkgmap"
python3 "$HERE/build_region.py" "$REPO" "$MAIN" "$REGION" "$OUT" \
  --split="$WORK/split" --style="$WORK/profile/style" --typ="$WORK/profile/typ.txt" \
  --tag="-$LAYOUT" --merge-lines
