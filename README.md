# A cycling map for Garmin Edge from OpenStreetMap

A vector map made for riding rather than planning: at a glance it should be clear where to go, what the road surface is and which roads to stay away from. It is built from OpenStreetMap with mkgmap.

**Pick your own colours and download the map:** <https://mopheadpersona.github.io/garmin-map/>. The page recolours the map in your browser; nothing is uploaded. Czechia only for now.

The style is described in `SPEC.md`, in Russian. The author's working notes (`NOTES.md`) are not part of the repository; comments in the code that mention that file refer to them.

## Build a region

```bash
./build.sh prague
```

The finished map is `out/prague.img`. Prague with the Brdy hills takes about a minute.

The script downloads the Geofabrik extract into `data/` (if it is not there yet), cuts out the area, splits it into tiles (splitter), generates the TYP file from `typ/make_typ.py` and runs mkgmap. Intermediate files and logs go to `build/<region>/`.

Options:

- `--update` downloads the source extract again;
- `--force` cuts the area out again.

## View it on a Mac

```bash
./view.sh prague
```

Opens the map in QMapShack and leaves the window open. Run it again after a new build and the window restarts with the new map. Position and zoom are kept if you quit QMapShack with Cmd+Q.

QMapShack picks the level of detail differently from an Edge, and a P3 display shows the colours more saturated.

## Take screenshots

```bash
python3 scripts/screenshots.py 5f prague
```

Four places at the four zoom levels from `SPEC.md` go to `screenshots/5f/`, plus overview sheets. The places are listed at the top of the script (`PLACES`). A one-off check of a single point: `--at=latitude,longitude`.

## Pick colours in the browser

```bash
python3 scripts/serve_site.py
```

The page at `http://127.0.0.1:8765` shows the legend and map views that are recoloured on the fly. “Download .img” writes the chosen colours into the finished map right in the browser; the server only hands out the files in `site/`.

`scripts/make_site.py` prepares the data for the page:

- `typ` finds where each colour sits in the map file (seconds). Run it after any change to `typ/make_typ.py`.
- `maps` lists the maps in `out/` that the page offers for download. Run it after `./build.sh`.
- `frames` captures the recolourable views in QMapShack, about two and a half minutes per view. Run it after style changes that alter how the map is drawn. `frames interchange` or `frames center_3-150m` captures one place or one view.
- `titles` writes the place names from `SCENES` into views that are already captured, without capturing again.

The places and zoom levels of the views and the legend names are the `SCENES` and `LEGEND` tables at the top of `scripts/make_site.py`. Ready-made colour sets are in `site/data/presets.json`, edited by hand.

The page comes in three languages: English (default), Czech and Russian. The choice is remembered in the browser; a link with `?lang=cs` or `?lang=ru` opens the page in that language. Interface texts are in `site/i18n.js`. Names of colours, places and maps are given in all three languages in `scripts/make_site.py` (`tr("English", "Česky", "По-русски")`), names of colour sets in `site/data/presets.json`.

“Save set to a file” gives you `palette.json`. To make those colours the default, copy them into the palette at the top of `typ/make_typ.py` and rebuild the map.

## Publish the page

The page is served by GitHub Pages from the `gh-pages` branch of this repository. That branch holds only the built page with the maps; the project source is in `main`.

```bash
python3 scripts/publish_site.py dist
```

```bash
python3 scripts/publish_site.py push
```

`dist` assembles `build/pages`: the page, the views and the maps cut into 40 MB parts (git rejects files over 100 MB; the page joins the parts itself). To look at it before publishing: `python3 scripts/serve_site.py 8766 build/pages`.

`push` sends that folder to `gh-pages` as a single commit that replaces the previous one. History is not kept on purpose: every map rebuild would otherwise add 230 MB to the repository. The upload takes a few minutes and the page updates a minute or two later.

After a map rebuild the order is: `./build.sh <region>`, `python3 scripts/make_site.py maps`, then `dist` and `push`.

## Add a region

One file, `regions/<name>.conf`, modelled on `regions/prague.conf`:

```bash
NAME="Bayern"
SOURCES="https://download.geofabrik.de/europe/germany/bayern-latest.osm.pbf"
MAP_ID=7002          # 4 digits, unique per region
CODE_PAGE=1252       # 1252 only: an Edge shows a 1250 map as "?" in diamonds
```

- `BBOX="west,south,east,north"` or `POLY="regions/name.poly"` crops the extract. Without them the whole extract is used.
- `SOURCES` may list several URLs separated by spaces: each extract is cropped and the pieces are merged. That is how “Czechia plus the border areas” would be built. This path is written but has only been tried with a single extract.
- To take screenshots of a new region, add its places to `PLACES` in `scripts/screenshots.py`.

There is one style for all regions. An Edge will not open a file larger than 4 GB; the script warns about that.

## Put the map on an Edge from a Mac

So far the map has been tried on one Edge 830 (16 Nov 2026): labels, navigation and rerouting work there, and so does a map downloaded from the colours page. The steps below follow the manual and have not been tried on an Edge 1060.

1. Install [OpenMTP](https://openmtp.ganeshrvel.com). A Mac does not see an Edge 1050 as a disk, so an MTP client is needed.
2. Quit other MTP programs (Android File Transfer, Garmin Express), otherwise OpenMTP will not connect.
3. Turn the Edge on and connect it with a USB-C cable. The device storage appears on the right in OpenMTP.
4. Open the `Garmin` folder on the device.
5. Drag `out/prague.img` into it. The file name can be anything; the extension must be `.img`.
6. Unplug the cable and wait for the device to restart.
7. On the Edge, switch the map on in the profile you ride with: profile settings → Navigation → Map → Configure Maps. The map is listed under the name set in `NAME`.
8. Leave the stock Garmin Cycle Map switched on: routing and Up Ahead depend on it, because this map carries no routing data. The map is built with draw priority 31 (`DRAW_PRIORITY` in `build.sh`) so that it is drawn over the stock one; an earlier build with priority 25 was not shown at all on an Edge 830 while the stock map was on. With priority 31 the 830 shows this map, and navigation and rerouting work (reported 16 Nov 2026). If this map does not show on your device, switch the stock map off for the time being.

## What is where

| Path | What |
|---|---|
| `SPEC.md` | Style specification (Russian) |
| `build.sh` | Builds a region |
| `view.sh` | Opens a map in QMapShack |
| `regions/*.conf` | Region configs |
| `style/` | mkgmap style: `options`, `lines`, `polygons`, `points`, `relations`, `typ.txt` |
| `typ/make_typ.py` | Tables of colours and widths; generates `style/typ.txt`. Edit here, not in `typ.txt` |
| `typ/icons.py` | Icon drawings |
| `scripts/` | Screenshots and viewing; `make_site.py` and `serve_site.py` are the data and the server for the colour page, `publish_site.py` publishes it to GitHub Pages |
| `site/` | The colour page: page code, `i18n.js` (texts in three languages), `data/` (legend, views, colour slots), `maps/` (links to the maps in `out/`) |
| `tools/` | mkgmap, splitter, an environment with osmium and Java |
| `data/` | OSM source extracts |
| `build/`, `out/` | Intermediate files and finished maps |

`tools/`, `data/`, `build/`, `out/` and `screenshots/` are not in the repository: they are downloaded programs, source extracts and build results. Neither are `site/maps/` and `site/data/maps.json`; they appear after `./build.sh` and `python3 scripts/make_site.py maps`.

## Where to change what

- **Colour or width of a line**: the `SOLID` and `BITMAP` tables in `typ/make_typ.py`. Four columns for four zoom steps.
- **From which zoom an object appears**: `resolution` in the rules of `style/lines`, `style/polygons`, `style/points`. How screens map to resolutions is in `style/options`.
- **Which OSM tags turn into what**: section 1 of `style/lines` (road classes).
- **An icon**: `SYMBOLS` in `typ/icons.py`; preview in a terminal with `python3 typ/icons.py`.

## Environment

You need Java, osmium-tool, mkgmap, splitter and QMapShack. `build.sh` takes `java` and `osmium` from `tools/env` if that exists and from PATH otherwise; it looks for mkgmap and splitter in `tools/mkgmap-r*/` and `tools/splitter-r*/`.
## Licence

Code, style and documentation are under the MIT licence, see `LICENSE`. Map data © OpenStreetMap contributors, Open Database License (ODbL): <https://www.openstreetmap.org/copyright>. mkgmap and splitter are not part of this repository and have their own licence (GPL).
