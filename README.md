<p align="center">
  <img src="floor_generator.png" alt="Floor & Decking Generator icon" width="128">
</p>

<h1 align="center">Floor &amp; Decking Generator for IngeTrazo</h1>

<p align="center">
  Parametric plank flooring, decking and parquet for <a href="https://github.com/ingelibre/ingetrazo">IngeTrazo</a> –
  select a face, pick a pattern, get a ready-made floor with border, skirting boards and a material &amp; cut report.
</p>

<p align="center">
  <b>English</b> · <a href="README.pl.md">Polski</a>
</p>

---

## What is it?

`floor_generator.py` is a single-file **plugin (extension) for IngeTrazo**. It turns any flat face of your model
(a room floor, a terrace, a balcony…) into a real 3D floor made of individual planks:

- every plank is a separate solid with the chosen thickness and gap,
- planks are trimmed exactly to the room outline, around columns and openings,
- you can add a mitered perimeter border (frieze) and skirting boards,
- the plugin calculates how much material to buy (with waste allowance) and exports it to CSV.

The floor stays **parametric**: select it later and change the pattern, plank size, wood or angle – it is rebuilt
in place. Everything is a single Undo step (`Ctrl+Z`).

## Features

| | |
|---|---|
| 🪵 **11 laying patterns** | running bond, 1/3 step, random, stack bond, herringbone (1×/2×/3×), French chevron, basketweave, Versailles panels, mixed widths |
| 📐 **Any outline** | concave / L-shaped rooms, any layout angle, multiple faces at once |
| 🕳️ **Columns & openings** | holes in the face and smaller coplanar faces selected inside the room are cut out automatically |
| 🖼️ **Mitered border** | 1–10 border planks along the walls and (optionally) around columns |
| 🧱 **Skirting boards** | mitered at corners, along walls and around columns; wood-matched or white (RAL 9003) |
| 🎨 **Wood species & shade variation** | oak, pine, walnut, ash, teak; random ±% shade per plank for a natural look |
| 📊 **Material & cut report** | areas, full / cut / border plank counts, linear metres, skirting length, recommended purchase area; CSV export |
| ✏️ **Editable** | select a generated floor and run the tool again to change any parameter |
| ⚡ **Fast & light** | identical planks are shared **component instances** – thousands of planks stay smooth to orbit and select |
| 🏗️ **BIM ready** | the floor is tagged as `IfcCovering` (FLOORING) |
| ↩️ **Undo / Redo** | creating and editing a floor is one history step |
| 🌐 **English / Polski** | language switch directly in the dialog |

## Installation

1. Download `floor_generator.py` (optionally also `floor_generator.svg` / `floor_generator.png` – the icon is
   embedded in the script anyway, the files are only an override).
2. Copy the file(s) to your IngeTrazo plugins folder:
   - **Windows:** `%APPDATA%\ingetrazo\plugins\`
   - **Linux:** `~/.local/share/ingetrazo/plugins/`

   Tip: in IngeTrazo use **Extensions → Open plugins folder**.
3. **Restart IngeTrazo** (plugins are loaded only at startup).

After the restart you will find:

- a **“Floor & Decking”** toolbar at the top with the plugin icon
  (click = generate / edit, small arrow = menu with the material report),
- **Extensions → Floor & Decking Generator** (shortcut `Ctrl+Shift+F`, if not taken by another tool),
- **Extensions → Floor & Decking (Podłoga)** submenu with *Generate / Edit Floor…* and *Material & Cut Report…*,
- right-click (context menu) entries on selected faces and on generated floors.

### Requirements

- IngeTrazo with the Extension API v2 (any current release).
- No extra Python packages. 2D clipping uses `manifold3d`, which ships with IngeTrazo;
  `shapely` is used if `manifold3d` is not available.

## How to use

### Create a floor

1. Select the **face** of the floor (one or more faces; each separate outline gets its own floor).
2. *Optional:* also select smaller faces lying on the same plane inside the room – they are treated as
   **columns / openings** and cut out. Holes already present in the face are detected automatically.
3. Click the toolbar icon (or use the menu / `Ctrl+Shift+F` / right-click → *Generate Floor…*).
4. Set the parameters and confirm with **OK**.
5. Optionally open the **material report** offered after generation.

The floor is created as a group named *Plank Floor* placed on top of the selected face.

### Edit a floor

Select the generated floor group and run the tool again (or right-click → *Edit Floor…*).
The dialog opens with the floor's saved parameters; after **OK** the floor is rebuilt in place
(its position, name and any move/rotation you applied are kept).

### Material report

Toolbar arrow → *Material & Cut Report…* (or right-click on a floor → *Material Report…*).
The report can also be opened from the dialog with the *Material & Cut Report…* button.

## Options

| Option | Default | Range | Description |
|---|---|---|---|
| **Floor pattern** | 1/2 running bond | 11 patterns | Laying pattern – see below. |
| **Layout angle** | 0° | 0–360° | Rotation of the whole pattern relative to the face. |
| **Plank width** | 14 cm | 3–100 cm | Width of a single plank. |
| **Plank length** | 120 cm | 0–1000 cm | Length of a single plank. **0 = continuous** (one board from wall to wall). |
| **Thickness (height)** | 20 mm | 2–100 mm | Plank thickness. |
| **Gap / joint** | 3 mm | 0–20 mm | Gap between planks (decking joint). |
| **Add perimeter border** | off | – | Mitered frieze along the walls. |
| **Border around holes/columns** | on | – | Also frame columns and openings with the border. |
| **Plank count in border** | 1 | 1–10 | Number of border rows. |
| **Border plank width** | 14 cm | 3–100 cm | Width of border planks. |
| **Add skirting boards** | off | – | Skirting boards along the walls, mitered at corners. |
| **Skirting around holes/columns** | on | – | Also put skirting around columns. |
| **Skirting height** | 8 cm | 3–25 cm | |
| **Skirting thickness** | 15 mm | 5–35 mm | |
| **Skirting finish** | match floor wood | wood / white RAL 9003 | |
| **Wood species** | natural oak | oak, pine, walnut, ash, teak | Base colour of the planks. |
| **Shade variation** | 6 % | 0–25 % | Random brightness variation per plank (0 = all planks identical). |
| **Create planks as components** | on | – | Identical planks share one geometry (strongly recommended – see *Performance*). |
| **Language** | English | English / Polski | Language of the dialog, report and element names. |

The last used settings are remembered in the document and offered for the next floor.

### Patterns

| Pattern | Description |
|---|---|
| **1/2 (running bond)** | Classic staggered rows, joints shifted by half a plank. |
| **1/3 (staggered step)** | Joints shifted by a third of a plank – a “stair-step” look. |
| **Random stagger** | Random joint offsets, natural plank-floor look. |
| **Stack bond (straight grid)** | No offset – all joints in line. |
| **Classic herringbone (1×)** | Single planks at 90° to each other. |
| **Double herringbone (2×)** | Pairs of planks in a herringbone. |
| **Triple herringbone (3×)** | Triplets of planks in a herringbone. |
| **French chevron (45°)** | Planks with 45° cut ends meeting in a V. |
| **Basketweave / parquet squares** | Squares made of planks, alternately rotated 90°. |
| **Versailles parquet** | Classic square palace panels made of short slats. |
| **Mixed widths (rustic)** | Rows of different plank widths, rustic style. |

**Tip:** for herringbone patterns use a short plank (e.g. 60 × 10 cm); with *Plank length = 0* the plugin picks
a sensible length automatically.

## Material & cut report

| Section | Content |
|---|---|
| Project & geometry | net room area, area covered by planks, pattern, wood, plank size |
| Openings & columns | number and area of the deducted openings |
| Planks | full (uncut) planks, cut planks, border planks (walls / around holes), total count, total linear metres, components (instances / definitions) |
| Skirting | number of segments, total length |
| Order recommendation | waste allowance and **recommended purchase area** |

Waste allowance by pattern: straight / 1/2 / 1/3 – **7 %**, random / mixed widths – **8 %**,
Versailles – **10 %**, herringbone – **12 %**, chevron – **15 %**; **+3 %** when the layout angle is not 0°.

**Export to CSV…** saves the report as UTF-8 CSV (opens directly in Excel / LibreOffice).

## Performance

With *Create planks as components* enabled, every plank shape that occurs at least twice becomes **one component
definition** and all such planks are its **instances** – including rotated planks (herringbone, chevron,
Versailles) and identical offcuts. The plank colour is stored on the instance, so planks with the same size but
a different shade still share one geometry. Only unique pieces (typically individual offcuts at walls) remain
ordinary groups.

In a typical 8 × 6 m herringbone room this means ~50 geometries instead of ~500 and ~10× fewer faces to draw,
so the model stays responsive even with thousands of planks.

Turn the option off only if you need the whole floor as one plain mesh (e.g. for further modelling of the
floor surface).

## Tips & troubleshooting

- **The toolbar / menu entry does not appear** – make sure the file is in the plugins folder and restart IngeTrazo.
  If the plugin fails to load, IngeTrazo shows it in the *Extensions* menu with a ⚠ warning and the error in the tooltip.
- **“Select a floor face…” message** – nothing usable is selected: select a face (to create) or a generated floor group (to edit).
- **“No planks generated”** – the outline is too small for the chosen plank / border sizes.
- **A column is not cut out** – select its face together with the room face; it must lie on the same plane and inside the room outline.
- **Older IngeTrazo versions** – per-instance colour requires a recent IngeTrazo (`Group.material`). Older versions
  work too, the shade is then stored in the component geometry, so you get somewhat fewer shared components
  (set *Shade variation* to 0 % to get the maximum).

## License

GPL-3.0-or-later – the same license as IngeTrazo.
