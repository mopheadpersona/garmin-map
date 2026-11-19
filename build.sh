#!/bin/bash
# Сборка карты Garmin для одного региона: выгрузка OSM -> вырезка -> splitter -> mkgmap -> out/<регион>.img
#
#   ./build.sh <регион> [--edge1060] [--update] [--force]
#
#   <регион>    имя файла regions/<регион>.conf
#   --edge1060  карта для Edge 1050/1060: out/<регион>-1060.img. Эти приборы не рисуют узоры линий,
#               поэтому пунктиры нарезаются настоящими штрихами (experiments/edge1060/README.md).
#               Сборка дольше, карта вдвое больше: Прага около 8 минут, Чехия около 30 минут
#               и до 8 ГБ временных файлов в build/edge1060/ (в конце удаляются)
#   --update    заново скачать исходные выгрузки, даже если они уже лежат в data/
#   --force     заново вырезать область, даже если вырезка свежее исходников

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

MKGMAP_JAR="$(ls -d tools/mkgmap-r*/mkgmap.jar 2>/dev/null | sort -V | tail -1 || true)"
SPLITTER_JAR="$(ls -d tools/splitter-r*/splitter.jar 2>/dev/null | sort -V | tail -1 || true)"
JAVA_HEAP="${JAVA_HEAP:-4g}"

die() { echo "ОШИБКА: $*" >&2; exit 1; }
step() { printf '\n=== %s ===\n' "$*"; }

# Ищем программу: сначала локальное окружение tools/env, потом PATH.
find_tool() {
  local name="$1"; shift
  local candidate
  for candidate in "$@"; do
    if [ -x "$candidate" ]; then echo "$candidate"; return 0; fi
  done
  command -v "$name" 2>/dev/null || return 1
}

# ---------- аргументы ----------
REGION=""
UPDATE=0
FORCE=0
EDGE1060=0
for arg in "$@"; do
  case "$arg" in
    --update) UPDATE=1 ;;
    --force)  FORCE=1 ;;
    --edge1060) EDGE1060=1 ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) die "неизвестный параметр $arg" ;;
    *)  [ -z "$REGION" ] || die "регион указан дважды"; REGION="$arg" ;;
  esac
done
if [ -z "$REGION" ]; then
  echo "Использование: ./build.sh <регион> [--edge1060] [--update] [--force]"
  echo "Доступные регионы:"
  ls regions/*.conf 2>/dev/null | sed 's|regions/||; s|\.conf$||; s|^|  |'
  exit 1
fi

CONF="regions/$REGION.conf"
[ -f "$CONF" ] || die "нет файла $CONF"

# ---------- конфиг региона ----------
NAME=""; SOURCES=""; BBOX=""; POLY=""; MAP_ID=""; CODE_PAGE="1252"
# Приоритет отрисовки: какая из карт на одной территории рисуется поверх. См. NOTES.md, раздел 9.
DRAW_PRIORITY="31"
# shellcheck disable=SC1090
source "$CONF"
[ -n "$NAME" ]    || die "$CONF: не задано NAME"
[ -n "$SOURCES" ] || die "$CONF: не задано SOURCES"
[[ "$MAP_ID" =~ ^[1-9][0-9]{3}$ ]] || die "$CONF: MAP_ID должен быть из 4 цифр и не начинаться с нуля"
[[ "$DRAW_PRIORITY" =~ ^[0-9]+$ ]] || die "$CONF: DRAW_PRIORITY должен быть целым числом"
for other in regions/*.conf; do
  [ "$other" = "$CONF" ] && continue
  if grep -q -E "^MAP_ID=\"?$MAP_ID\"?[[:space:]]*(#.*)?$" "$other"; then
    die "MAP_ID=$MAP_ID уже занят в $other"
  fi
done

# ---------- инструменты ----------
JAVA="${JAVA:-$(find_tool java tools/env/lib/jvm/bin/java tools/env/bin/java /opt/homebrew/opt/openjdk/bin/java /usr/local/opt/openjdk/bin/java)}" \
  || die "не найдена Java (ожидается tools/env или java в PATH)"
OSMIUM="${OSMIUM:-$(find_tool osmium tools/env/bin/osmium)}" \
  || die "не найден osmium (ожидается tools/env/bin/osmium или osmium в PATH)"
[ -f "$MKGMAP_JAR" ]   || die "нет tools/mkgmap-r*/mkgmap.jar"
[ -f "$SPLITTER_JAR" ] || die "нет tools/splitter-r*/splitter.jar"
for f in options lines polygons points relations version; do
  [ -f "style/$f" ] || die "нет style/$f"
done

WORK="build/$REGION"
mkdir -p data out "$WORK"
STEPS=5
[ "$EDGE1060" = 1 ] && STEPS=2          # дальше у варианта для Edge 1050/1060 свои шаги

# Итог: размер готовой карты и предупреждение о пределе Edge.
report() {
  local size
  size=$(stat -f %z "$1" 2>/dev/null || stat -c %s "$1")
  echo
  echo "Готово: $1 ($((size / 1024 / 1024)) МБ)"
  if [ "$size" -ge 4294967296 ]; then
    echo "ВНИМАНИЕ: файл больше 4 ГБ, Edge его не откроет. Разделите регион на части."
  fi
}

echo "Регион:  $REGION ($NAME), id $MAP_ID, cp$CODE_PAGE"
echo "mkgmap:  $MKGMAP_JAR"
echo "Java:    $("$JAVA" -version 2>&1 | head -1)"

# ---------- 1. исходные выгрузки ----------
step "1/$STEPS Исходные данные"
SRC_FILES=()
for url in $SOURCES; do
  file="data/$(basename "$url")"
  if [ ! -e "$file" ] || [ "$UPDATE" = 1 ]; then
    echo "Скачиваю $url"
    curl -L --fail --retry 3 -o "$file.part" "$url"
    mv "$file.part" "$file"
  else
    echo "Есть $file ($(du -hL "$file" | cut -f1))"
  fi
  SRC_FILES+=("$file")
done

# ---------- 2. вырезка ----------
step "2/$STEPS Вырезка области"
EXTRACT="$WORK/$REGION.osm.pbf"
need_extract=$FORCE
[ -f "$EXTRACT" ] || need_extract=1
for f in "${SRC_FILES[@]}" "$CONF"; do
  [ "$f" -nt "$EXTRACT" ] && need_extract=1
done

if [ "$need_extract" = 1 ]; then
  cut_args=()
  if [ -n "$POLY" ]; then
    [ -f "$POLY" ] || die "нет файла $POLY"
    cut_args=(--polygon "$POLY")
  elif [ -n "$BBOX" ]; then
    cut_args=(--bbox "$BBOX")
  fi
  parts=()
  i=0
  for f in "${SRC_FILES[@]}"; do
    i=$((i + 1))
    if [ ${#cut_args[@]} -gt 0 ]; then
      part="$WORK/part-$i.osm.pbf"
      # smart: дороги и мультиполигоны на границе области остаются целыми
      "$OSMIUM" extract "${cut_args[@]}" --strategy smart --overwrite -o "$part" "$f"
      parts+=("$part")
    else
      parts+=("$f")
    fi
  done
  if [ ${#parts[@]} -gt 1 ]; then
    "$OSMIUM" merge --overwrite -o "$EXTRACT" "${parts[@]}"
    rm -f "$WORK"/part-*.osm.pbf
  elif [ ${#cut_args[@]} -gt 0 ]; then
    mv "${parts[0]}" "$EXTRACT"
  else
    ln -sf "$ROOT/${parts[0]}" "$EXTRACT"
  fi
else
  echo "Вырезка актуальна, пропускаю (--force, чтобы вырезать заново)"
fi
echo "Вырезка: $EXTRACT ($(du -hL "$EXTRACT" | cut -f1))"

# ---------- вариант для Edge 1050/1060 ----------
# Вид, принятый на приборе, задан по умолчанию в самой цепочке; рабочие файлы — в build/edge1060.
if [ "$EDGE1060" = 1 ]; then
  absolute() { case "$1" in /*) echo "$1" ;; *) echo "$ROOT/$1" ;; esac; }
  JAVA="$(absolute "$JAVA")" OSMIUM="$(absolute "$OSMIUM")" \
  EDGE1060_WORK="${EDGE1060_WORK:-$ROOT/build/edge1060}" \
    experiments/edge1060/build.sh "$REGION" default "$ROOT/out/$REGION-1060.img" "$ROOT"
  report "out/$REGION-1060.img"
  exit 0
fi

# ---------- 3. нарезка на тайлы ----------
step "3/5 Splitter"
rm -rf "$WORK/split"
mkdir -p "$WORK/split"
"$JAVA" "-Xmx$JAVA_HEAP" -jar "$SPLITTER_JAR" \
  --output-dir="$WORK/split" \
  --mapid="${MAP_ID}0001" \
  --max-nodes=1200000 \
  --keep-complete=true \
  --description="$NAME" \
  "$EXTRACT" > "$WORK/splitter.log" 2>&1 || { tail -30 "$WORK/splitter.log"; die "splitter упал, см. $WORK/splitter.log"; }
echo "Тайлов: $(ls "$WORK/split"/*.osm.pbf | wc -l | tr -d ' ')"

# ---------- 4. TYP ----------
step "4/5 TYP"
# Стиль один на все регионы; family id и кодовая страница подставляются из конфига.
TYP_TXT="$WORK/$REGION-typ.txt"
python3 typ/make_typ.py style/typ.txt
sed -e "s/@FID@/$MAP_ID/" -e "s/@CODEPAGE@/$CODE_PAGE/" style/typ.txt > "$TYP_TXT"
echo "$TYP_TXT"

# ---------- 5. mkgmap ----------
step "5/5 mkgmap"
rm -rf "$WORK/img"
mkdir -p "$WORK/img"
"$JAVA" "-Xmx$JAVA_HEAP" -jar "$MKGMAP_JAR" \
  --output-dir="$WORK/img" \
  --style-file=style \
  --family-id="$MAP_ID" \
  --product-id=1 \
  --family-name="$NAME" \
  --series-name="$NAME" \
  --area-name="$NAME" \
  --code-page="$CODE_PAGE" \
  --lower-case \
  --order-by-decreasing-area \
  --add-pois-to-areas \
  --reduce-point-density-polygon=3 \
  --draw-priority="$DRAW_PRIORITY" \
  --gmapsupp \
  -c "$WORK/split/template.args" \
  "$TYP_TXT" > "$WORK/mkgmap.log" 2>&1 || { tail -40 "$WORK/mkgmap.log"; die "mkgmap упал, см. $WORK/mkgmap.log"; }

# mkgmap может завершиться с кодом 0, даже если часть тайлов не собралась
ERR_RE='^SEVERE|^ERROR|Error in style|Exception in thread|^java\.|Number of (MapFailed|Exit)Exceptions: [1-9]'
if grep -q -E "$ERR_RE" "$WORK/mkgmap.log"; then
  grep -E -A3 "$ERR_RE" "$WORK/mkgmap.log" | head -40
  die "mkgmap сообщил об ошибках, см. $WORK/mkgmap.log"
fi
warnings=$(grep -E "^WARNING" "$WORK/mkgmap.log" | grep -c -v "Setting max-jobs" | tr -d ' ' || true)
[ "$warnings" = 0 ] || echo "Предупреждений mkgmap: $warnings (см. $WORK/mkgmap.log)"

[ -f "$WORK/img/gmapsupp.img" ] || die "mkgmap не создал gmapsupp.img, см. $WORK/mkgmap.log"
cp "$WORK/img/gmapsupp.img" "out/$REGION.img"
report "out/$REGION.img"
