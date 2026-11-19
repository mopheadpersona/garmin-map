# Edge 1050/1060

The map variant for the Edge 1050 and 1060, and the test maps it grew from. Tried on one Edge 1060 (firmware 5.27).

```bash
./build.sh prague --edge1060
```

run in the repository root builds `out/prague-1060.img` with the look accepted on the device: the layout `less` (for Map Detail Less), lines 1.5 times thicker, the night colours of `night-palette.json`, a ground layer. The colours page offers these maps for the Edge 1050 and 1060 (`scripts/make_site.py`).

## What the device does

Found with the test maps below, on the device:

- It draws extended line types only up to `0x120xx`. `0x13000` and above are not drawn. An Edge 830 draws them all. The style now keeps its line types in `0x10cSS`–`0x11cSS` (`typ/make_typ.py`).
- It ignores bitmaps of TYP lines in every form the format has: two colours, colour and transparent, `UseOrientation`, day and night colours. The line is filled with the first colour over the whole height of the bitmap. Standard line types without a TYP entry are solid too.
- It does draw bitmaps of TYP polygons, and it draws dashes that are real short separate lines.
- A line and its casing (`LineWidth` and `BorderWidth`) are drawn as given, widths 1–12 and casings 1–2 all come out, with round ends and no smoothing: every slanted edge is a staircase of single pixels.
- All casings are drawn first, all fills after. Roads of different types merge cleanly at a junction and no casing crosses a fill, so a separate casing layer gives nothing.
- Which fill ends up on top is not decided by the type number alone, nor by the order in the file (mkgmap keeps the order of the input). In `build_chart3.py` two crossing lines of types `0x11110` and `0x11114` came out with the north–south one on top in both arrangements. White dashes on a dark line are on top with either numbering.
- Of the types `0x10cSS` only `0x10c00`–`0x10c07` are drawn (`build_chart4.py`). `0x10d00`–`0x1200f` are all drawn; for the low bytes `0x10`–`0x1f` the photo covers only `0x10dSS`–`0x10fSS`, the rest of that panel is still to be photographed. The tunnel layer of the closest look sits on `0x10cSS`; `profile1060.py` moves its six types that are not drawn (`0x10c10`–`0x10c16`) to free places among `0x10dSS`.
- In night mode (Color Mode Night) a TYP with day colours only keeps its colours, except that some areas come out black: industrial areas and quarries (type `0x0c`) for certain.
- Night colours written in the TYP are used: areas, lines and labels came out in the dark palette. The exception is the map background, polygon `0x4b`: at night the device paints it its own dark blue whatever the TYP says. So `cut1060.py` lays a ground of ordinary polygons (squares of 0.04°, tag `gm:ground`, type `0x03`) over every place that has data, and the TYP gives it the ground colour for day and night. Seen on the device: with the ground the night background is the dark grey of the palette.
- A line gets a round end at its first point and a flat end at its last point.
- On `build_chart5.py` every way of building a T-junction came out clean: the wider road lies over the street that ends on it. On the real map (same types, same widths, same level) the fill of the street lies over the road up to its axis. The stored data were decoded for one such place: the road and the streets are in the same subdivision, and the street is stored before the road at one junction and after it at the next, so neither the subdivision nor the order in the file explains it. Open.
- Coordinates snap to the lattice of the map level on screen. A line cut into pieces bends at every cut point that is off the lattice.
- Which level is shown depends on the zoom and on Map Detail (Menu > Activity Profiles > profile > Navigation > Map > Appearance). Read from the level marks of the Prague map:

  | Map Detail | 80 m | 120 m | 200 m | 300 m | 500 m |
  |---|---|---|---|---|---|
  | Less | 24 | 23 | 22 | 22 | 21 |
  | Normal | 24 | 24 | 23 | 23 | 22 |
  | More | 24 | 24 | 24 | 24 | 23 |

  Most showed 24 at 80, 120 and 200 m. The nearly empty `build_chart3.py` map gave the same at 200 m (22, 23, 24). One earlier state of the device, its Map Detail not recorded, was coarser than any of these: 24 at 30 m, 23 at 50 and 80 m, 22 at 120 m.
- A level shown too early makes the map look hand-drawn: with 23 at 50–80 m the lattice is 4–7 screen pixels, a small roundabout becomes a square and every vertex is a kink. At 30 m on level 24 the same roundabout is round. On Less, Normal and More the lattice stays at 1–3 pixels.

## The approach

Patterned lines are cut into ready-made pieces before mkgmap runs, one set per map level, and each piece is a plain solid line.

- `cut1060.py` reads the candidate ways in a stream (first the route relations, then way by way) and writes the pieces (tags `gm:lv`, `gm:ab`) and the marks for the original ways (`gm:cut`). Cut points are lattice points that lie almost on the drawn line. Cycle and MTB routes become dashes on a parallel line. A twin track keeps its uncut line and the pieces add the casing on top. A railway is dark pieces and white cased pieces taking turns: with a dark line under white dashes the device drew the line over the dashes in places.
- `profile1060.py` writes the style and the TYP for these pieces from `style/` and `typ/make_typ.py`.
- `build_region.py` runs mkgmap with that style on tiles from splitter.
- `build.sh` runs the whole chain for a region.

Three layouts of levels:

- `fine`: the levels of the style as they are. Fits Map Detail Normal: the closest look up to 120 m, the next one at 200–300 m, the third at 500 m.
- `less`: for Map Detail Less. As `fine`, and level 21 carries the look of level 22, so the looks change at 120 m, at 200 m and stay to 500 m. Paths and bad tracks are then on screen only up to 120 m.
- `coarse`: the first attempt, for the coarse state described above. The four looks move to coarser levels (24 → 24 and 23, 23 → 22 and 21, 22 → 20, 18–21 → 19 and 18). Kept for reference.

On More and Most the closest look stays on screen up to 300 m and further, which is too heavy there.

The device rounds the start of every line. A plain dash therefore comes out longer than cut and the gap shorter, so `cut1060.py` cuts the gaps of plain dashes wide, and steps are a row of dots. A way that is drawn as a cycleway gets no cycle route dashes beside it.

```bash
experiments/edge1060/build.sh prague less /tmp/praha-less.img /path/to/folder/with/tools
```

runs the chain by hand: another layout, another output file, tools from another folder. The extract `build/prague/prague.osm.pbf` must exist there.

Options of `build.sh`, set through the environment. The values shown are the defaults, which make the accepted look; a variable set to an empty value switches its option off:

- `EDGE1060_BOLD=1.5`: every line width and casing times this factor, for the dense screen (267 ppi). Dashes get longer and route overlays move away from the road by the same factor.
- `EDGE1060_BOLD_FAR=1.25`: another factor for the two far looks; empty: as `EDGE1060_BOLD`.
- `EDGE1060_DASH=2`: factor for plain dashes (paths, bad tracks) and route overlays; empty: as `EDGE1060_BOLD`.
- `EDGE1060_CYCLEWAY=wide`: the cycleway line about twice as wide.
- `EDGE1060_NOACCESS=plain`: roads closed to bicycles are drawn as ordinary roads of their kind, without the red dots (`hide`: not drawn at all; empty: red dots).
- `EDGE1060_NIGHT=/full/path/night-palette.json`: night colours from a file with the names of the palette in `typ/make_typ.py`. `night-palette.json` here is the dark theme: dark ground, grey streets, dimmed main roads, bright routes and paths. Tunnels get the night colour of their road half-way to the ground colour; the tunnel of a white road keeps the colour of the road. A night colour belongs to the name of the colour, so it stays when the day colours change.
- `EDGE1060_NIGHT=same`: night colours written out for every area and line, equal to the day colours.
- `EDGE1060_HEAP=6g`: Java heap for splitter and mkgmap; a whole country needs more than 4g.
- `EDGE1060_KEEP=1`: keep the tiles after the build (they are deleted by default).

Off unless set:

- `EDGE1060_CASING=layer`: a road becomes two lines, a dark one of the full width in the lowest layer and a plain fill above, so that every casing lies under every fill. Without it a road is one line with `BorderWidth`.
- `EDGE1060_MARKS="lat,lon lat,lon"`: level marks (`marks.py`). At each place the map carries the number of its own level (Garmin resolution 24–18), drawn on that level only, so a photo of the device tells which level is on screen.
- `EDGE1060_NAME`, `EDGE1060_FID`: map name and family id. Two maps on one device need different ids.
- `TYP_PALETTE=colours.json`: colour overrides, as in `typ/make_typ.py`.

## Test maps

- `build_chart.py`: a grid of extended line types and, for every map level, a tint and the number of its resolution in block digits. Shows which types are drawn and which level the device shows at a zoom.
- `build_chart2.py`: the same dashed line written in every way the TYP format allows, dashes as real geometry, and polygon patterns.
- `build_chart5.py`: a street ending on a wider road, built in 36 ways (order in the file, direction of the street, the road split at the junction, the fill of the road drawn once more in another layer, the street stopping short). All of them came out clean on the device, see above.
- `build_chart4.py`: one short line per extended type `0x1TTSS`, TT `0x0c`–`0x20`, in two panels, with red marks beside every row and column so that a type that is not drawn shows as a hole.
- `build_chart3.py`: stacking order and widths. Crossing and overlapping lines with different type numbers, with a casing from the TYP and with the casing as a separate line, the railway and twin track overlays, and a ladder of `LineWidth` 1–12 with `BorderWidth` 0–2. The list of cells is at the top of the script.

## Other tools

- `mtp.py`: list, copy, fetch and delete files on the device over MTP from the shell, through the library that ships with OpenMTP. OpenMTP must be closed.
- `shoot.py`: QMapShack frames of a map at chosen zooms and map levels, glued into one sheet. Uses `scripts/screenshots.py`. The zoom is in metres of the Mercator projection per screen point; at 50° north zoom 1.5 is about 1 m per point, the scale of the 80 m zoom on the Edge 1060.

## Known gaps

- No labels on the pieces, so the S0–S6 grades on paths are missing.
- Ferries and the state border are solid lines.
- Parallel railway tracks a few metres apart cover each other's white pieces.
- A road in a tunnel (cased pieces with gaps) comes out as a chain of capsules.
- Prague grows from 23 MB to 57–88 MB, depending on the layout.
