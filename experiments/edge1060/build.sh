#!/bin/bash
# Experimental build for the Garmin Edge 1050/1060: patterned lines as real dashes.
#
#   experiments/edge1060/build.sh <region> <fine|less|coarse> <out.img> [main folder]
#
#   <region>       regions/<region>.conf; its extract build/<region>/<region>.osm.pbf must exist
#                  (run ./build.sh <region> once in the main folder)
#   fine | less | coarse  which map levels carry which look, see cut1060.py:
#                  fine for Map Detail Normal, less for Map Detail Less
#   [main folder]  where tools/ and build/ live; default: the repository root
#
# Work files go to $EDGE1060_WORK (default: the system temp folder), nothing is written into the repository.
#
# Optional, through the environment:
#   EDGE1060_BOLD=1.5              thicker lines: every width and casing times this factor
#   EDGE1060_BOLD_FAR=1.25         another factor for the two far looks (default: as EDGE1060_BOLD)
#   EDGE1060_DASH=2                factor for plain dashes and route overlays (default: as EDGE1060_BOLD)
#   EDGE1060_CYCLEWAY=wide         the cycleway line about twice as wide
#   EDGE1060_NOACCESS=plain        roads closed to bicycles are drawn as ordinary roads, without the red dots
#                                  (hide: they are not drawn at all)
#   EDGE1060_NIGHT=same            night colours written out, equal to the day colours
#   EDGE1060_HEAP=6g               Java heap for splitter and mkgmap (default 4g)
#   EDGE1060_CASING=layer          road casings as separate lines under all fills
#   EDGE1060_MARKS="lat,lon ..."   level marks at these places (marks.py)
#   EDGE1060_NAME="Praha B"        map name on the device (default: the name of the region)
#   EDGE1060_FID=7012              family id; two maps on one device need different ids
#   TYP_PALETTE=colours.json       colour overrides, see typ/make_typ.py

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
[ $# -ge 3 ] || { sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }
REGION="$1"; LAYOUT="$2"; OUT="$3"; MAIN="${4:-$REPO}"
case "$LAYOUT" in fine|less|coarse) ;; *) echo "layout must be fine, less or coarse" >&2; exit 1 ;; esac
BOLD="${EDGE1060_BOLD:-1}"; MARKS="${EDGE1060_MARKS:-}"

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
python3 "$HERE/cut1060.py" cand.opl pieces "$LAYOUT" "$BOLD"

step "3/6 merge the pieces into the extract"
"$OSMIUM" cat pieces.nodes.opl pieces.ways.opl -o pieces.osm.pbf --overwrite
rm -f pieces.nodes.opl pieces.ways.opl cand.opl cand.osm.pbf cand-loc.osm.pbf      # the largest work files
"$OSMIUM" apply-changes "$EXTRACT" pieces.modify.osc -o marked.osm.pbf --overwrite
EXTRA=()
if [ -n "$MARKS" ]; then
  # shellcheck disable=SC2086
  python3 "$HERE/marks.py" marks.osm $MARKS
  EXTRA=(marks.osm)
fi
"$OSMIUM" merge marked.osm.pbf pieces.osm.pbf ${EXTRA[@]+"${EXTRA[@]}"} -o data.osm.pbf --overwrite

step "4/6 splitter"
rm -rf split
mkdir split
"$JAVA" "-Xmx${EDGE1060_HEAP:-4g}" -jar "$SPLITTER" --output-dir=split --mapid="${MAP_ID}0001" --max-nodes=1200000 \
  --keep-complete=true --description="$NAME" data.osm.pbf > splitter.log 2>&1 \
  || { tail -30 splitter.log; exit 1; }
rm -f data.osm.pbf marked.osm.pbf pieces.osm.pbf pieces.modify.osc
echo "tiles: $(ls split/*.osm.pbf | wc -l | tr -d ' ')"

step "5/6 style and TYP for the device"
PROFILE=("--bold=$BOLD")
PROFILE+=("--$LAYOUT")
[ -n "${EDGE1060_BOLD_FAR:-}" ] && PROFILE+=("--bold-far=$EDGE1060_BOLD_FAR")
[ -n "$MARKS" ] && PROFILE+=(--marks)
[ "${EDGE1060_CASING:-}" = layer ] && PROFILE+=(--casing-layer)
[ -n "${EDGE1060_DASH:-}" ] && PROFILE+=("--dash=$EDGE1060_DASH")
[ -n "${EDGE1060_NIGHT:-}" ] && PROFILE+=("--night=$EDGE1060_NIGHT")
[ "${EDGE1060_CYCLEWAY:-}" = wide ] && PROFILE+=(--cycleway-wide)
[ "${EDGE1060_NOACCESS:-}" = hide ] && PROFILE+=(--hide-noaccess)
[ "${EDGE1060_NOACCESS:-}" = plain ] && PROFILE+=(--plain-noaccess)
python3 "$HERE/profile1060.py" "$REPO" "$WORK/profile" "${PROFILE[@]}"

step "6/6 mkgmap"
python3 "$HERE/build_region.py" "$REPO" "$MAIN" "$REGION" "$OUT" \
  --split="$WORK/split" --style="$WORK/profile/style" --typ="$WORK/profile/typ.txt" \
  --tag="-$LAYOUT" --merge-lines ${EDGE1060_NAME:+"--name=$EDGE1060_NAME"} ${EDGE1060_FID:+"--fid=$EDGE1060_FID"}
