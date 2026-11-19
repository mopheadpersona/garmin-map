#!/bin/bash
# Map for the Garmin Edge 1050/1060: patterned lines as real dashes, a style and a TYP for that screen.
#
#   experiments/edge1060/build.sh <region> <default|fine|less|coarse> <out.img> [main folder]
#   experiments/edge1060/build.sh --profile <dir>      only the style and the TYP of the look, into <dir>
#
# The regular way to run it is ./build.sh <region> --edge1060 in the repository root: that makes the
# extract first and writes out/<region>-1060.img.
#
#   <region>       regions/<region>.conf; its extract build/<region>/<region>.osm.pbf must exist
#   default | fine | less | coarse  which map levels carry which look, see cut1060.py:
#                  fine for Map Detail Normal, less for Map Detail Less; default is the layout of
#                  the accepted look (less)
#   [main folder]  where tools/ and build/ live; default: the repository root
#
# Work files go to $EDGE1060_WORK (default: the system temp folder). The large ones are deleted as the
# build goes and the tiles at the end; EDGE1060_KEEP=1 keeps the tiles.
#
# With no variable set this builds the look accepted on the device on 19.11.2026. To try another one
# set a variable, also to an empty value (EDGE1060_NIGHT= gives a TYP without night colours):
#   EDGE1060_BOLD=1.5              thicker lines: every width and casing times this factor
#   EDGE1060_BOLD_FAR=1.25         another factor for the two far looks (empty: as EDGE1060_BOLD)
#   EDGE1060_DASH=2                factor for plain dashes and route overlays (empty: as EDGE1060_BOLD)
#   EDGE1060_CYCLEWAY=wide         the cycleway line about twice as wide
#   EDGE1060_NOACCESS=plain        roads closed to bicycles are drawn as ordinary roads, without the red dots
#                                  (hide: they are not drawn at all; empty: red dots)
#   EDGE1060_NIGHT=<palette.json>  night colours from a file, full path (default: night-palette.json here;
#                                  same: night colours equal to the day colours)
#   EDGE1060_HEAP=6g               Java heap for splitter and mkgmap
# Off unless set:
#   EDGE1060_CASING=layer          road casings as separate lines under all fills
#   EDGE1060_MARKS="lat,lon ..."   level marks at these places (marks.py)
#   EDGE1060_NAME="Praha B"        map name on the device (default: the name of the region)
#   EDGE1060_FID=7012              family id; two maps on one device need different ids
#   TYP_PALETTE=colours.json       colour overrides, see typ/make_typ.py

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
usage() { sed -n '2,35p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

ACCEPTED_LAYOUT=less
BOLD="${EDGE1060_BOLD-1.5}"; BOLD="${BOLD:-1}"
BOLD_FAR="${EDGE1060_BOLD_FAR-1.25}"
DASH="${EDGE1060_DASH-2}"
CYCLEWAY="${EDGE1060_CYCLEWAY-wide}"
NOACCESS="${EDGE1060_NOACCESS-plain}"
NIGHT="${EDGE1060_NIGHT-$HERE/night-palette.json}"
HEAP="${EDGE1060_HEAP:-6g}"
MARKS="${EDGE1060_MARKS:-}"
export EDGE1060_NOACCESS="$NOACCESS" EDGE1060_HEAP="$HEAP"      # read by cut1060.py and build_region.py

# Style and TYP of the look -> <dir>/style, <dir>/typ.txt
profile() {
  local args=("--$LAYOUT" "--bold=$BOLD")
  [ -n "$BOLD_FAR" ] && args+=("--bold-far=$BOLD_FAR")
  [ -n "$DASH" ] && args+=("--dash=$DASH")
  [ -n "$NIGHT" ] && args+=("--night=$NIGHT")
  [ "$CYCLEWAY" = wide ] && args+=(--cycleway-wide)
  [ "$NOACCESS" = hide ] && args+=(--hide-noaccess)
  [ "$NOACCESS" = plain ] && args+=(--plain-noaccess)
  [ "${EDGE1060_CASING:-}" = layer ] && args+=(--casing-layer)
  [ -n "$MARKS" ] && args+=(--marks)
  python3 "$HERE/profile1060.py" "$REPO" "$1" "${args[@]}"
}

if [ "${1:-}" = --profile ]; then
  [ $# -eq 2 ] || usage
  LAYOUT="$ACCEPTED_LAYOUT"
  profile "$2"
  exit 0
fi

[ $# -ge 3 ] || usage
REGION="$1"; LAYOUT="$2"; OUT="$3"; MAIN="${4:-$REPO}"
[ "$LAYOUT" = default ] && LAYOUT="$ACCEPTED_LAYOUT"
case "$LAYOUT" in fine|less|coarse) ;; *) echo "layout must be default, fine, less or coarse" >&2; exit 1 ;; esac
case "$OUT" in /*) ;; *) OUT="$PWD/$OUT" ;; esac

export EDGE1060_WORK="${EDGE1060_WORK:-${TMPDIR:-/tmp}/garmin-map-edge1060}"
WORK="$EDGE1060_WORK/$REGION-$LAYOUT"
EXTRACT="$MAIN/build/$REGION/$REGION.osm.pbf"
CONF="$MAIN/regions/$REGION.conf"
OSMIUM="${OSMIUM:-$MAIN/tools/env/bin/osmium}"
if [ -z "${JAVA:-}" ]; then
  JAVA="$MAIN/tools/env/lib/jvm/bin/java"; [ -x "$JAVA" ] || JAVA="$MAIN/tools/env/bin/java"
fi
export JAVA
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
"$JAVA" "-Xmx$HEAP" -jar "$SPLITTER" --output-dir=split --mapid="${MAP_ID}0001" --max-nodes=1200000 \
  --keep-complete=true --description="$NAME" data.osm.pbf > splitter.log 2>&1 \
  || { tail -30 splitter.log; exit 1; }
rm -f data.osm.pbf marked.osm.pbf pieces.osm.pbf pieces.modify.osc
echo "tiles: $(ls split/*.osm.pbf | wc -l | tr -d ' ')"

step "5/6 style and TYP for the device"
profile "$WORK/profile"

step "6/6 mkgmap"
python3 "$HERE/build_region.py" "$REPO" "$MAIN" "$REGION" "$OUT" \
  --split="$WORK/split" --style="$WORK/profile/style" --typ="$WORK/profile/typ.txt" \
  --tag="-$LAYOUT" --merge-lines ${EDGE1060_NAME:+"--name=$EDGE1060_NAME"} ${EDGE1060_FID:+"--fid=$EDGE1060_FID"}
# The tiles are as large as the map itself, twice over: gone unless asked for. Logs and the style stay.
[ "${EDGE1060_KEEP:-}" = 1 ] || rm -rf "$WORK/split" "$EDGE1060_WORK/work-$REGION-$LAYOUT/img"
