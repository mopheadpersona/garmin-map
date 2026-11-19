# Edge 1050/1060 experiments

Work in progress, not part of the regular build. Tried on one Edge 1060 (firmware 5.27).

## What the device does

Found with the test maps below, on the device:

- It draws extended line types only up to `0x120xx`. `0x13000` and above are not drawn. An Edge 830 draws them all. The style now keeps its line types in `0x10cSS`–`0x11cSS` (`typ/make_typ.py`).
- It ignores bitmaps of TYP lines in every form the format has: two colours, colour and transparent, `UseOrientation`, day and night colours. The line is filled with the first colour over the whole height of the bitmap. Standard line types without a TYP entry are solid too.
- It does draw bitmaps of TYP polygons, and it draws dashes that are real short separate lines.
- A line and its casing (`LineWidth` and `BorderWidth`) are drawn as given.
- Coordinates snap to the lattice of the map level on screen. A line cut into pieces bends at every cut point that is off the lattice.
- Which level is shown depends on the zoom and on Map Detail (Menu > Activity Profiles > profile > Navigation > Map > Appearance). With a nearly empty map at Map Detail Normal: resolution 24 at 20–30 m, 23 at 50–80 m, 22 at 120–200 m, 21 at 300 m, 20 at 500 m–1.2 km, 18 at 2 km. A dense map leaves the detailed levels sooner. A higher Map Detail gave 23 at 200 m and 22 at 500 m.

## The approach

Patterned lines are cut into ready-made pieces before mkgmap runs, one set per map level, and each piece is a plain solid line.

- `cut1060.py` reads the candidate ways and writes the pieces (tags `gm:lv`, `gm:ab`) and the marks for the original ways (`gm:cut`). Cut points are lattice points that lie almost on the drawn line. Cycle and MTB routes become dashes on a parallel line. Railways and twin tracks keep their uncut line; the pieces add the white dashes or the casing on top.
- `profile1060.py` writes the style and the TYP for these pieces from `style/` and `typ/make_typ.py`.
- `build_region.py` runs mkgmap with that style on tiles from splitter.
- `build.sh` runs the whole chain for a region.

Two layouts of levels:

- `normal`: for Map Detail Normal. The four looks of the style move to the levels the device shows then (24 → 24 and 23, 23 → 22 and 21, 22 → 20, 18–21 → 19 and 18).
- `fine`: the levels of the style as they are. The device has to be set to the higher Map Detail.

```bash
experiments/edge1060/build.sh prague fine /tmp/praha-fine.img /path/to/folder/with/tools
```

## Test maps

- `build_chart.py`: a grid of extended line types and, for every map level, a tint and the number of its resolution in block digits. Shows which types are drawn and which level the device shows at a zoom.
- `build_chart2.py`: the same dashed line written in every way the TYP format allows, dashes as real geometry, and polygon patterns.

## Other tools

- `mtp.py`: list, copy, fetch and delete files on the device over MTP from the shell, through the library that ships with OpenMTP. OpenMTP must be closed.
- `shoot.py`: QMapShack frames of a map at chosen zooms and map levels, glued into one sheet. Uses `scripts/screenshots.py`.

## Known gaps

- No labels on the pieces, so the S0–S6 grades on paths are missing.
- Ferries and the state border are solid lines.
- Whether the device draws the white railway dashes above the dark line has not been seen yet.
- Prague grows from 23 MB to 57–88 MB, depending on the layout.
