# img2gds (PNG → GDS)

Convert a **PNG** image into a **GDSII** cell made of a grid of rectangles on a single layer. PNG input only. Supports **binary** and **grayscale** rendering.

---

## Quick start

```bash
# optional: isolated environment
python3 -m venv .venv && source .venv/bin/activate

# dependencies (gdspy preferred; gdstk works too)
pip install -r requirements.txt
# or: pip install pillow gdspy   # (or: pillow gdstk)

# run
python3 img2gds.py input.png output.gds
```

Open `output.gds` in KLayout (or any GDS viewer).

---

## What it does

* Loads the PNG as **8-bit grayscale**.
* Optional **invert**, then:

  * **binary** mode: **threshold** to on/off squares.
  * **grayscale** mode: map pixel intensity → **square side** (continuous sizing).
* Resamples to an `Nx × Ny` grid (respecting **aspect ratio** and **fit mode**).
* Emits one **rectangle per active pixel** on the configured **GDS layer/datatype**.
* Places the grid with **margins**; flips **Y** so image top maps to positive GDS Y.
* Enforces **minimum square side** and **minimum edge-to-edge gap** globally.
* Caps total tiles with **MAX_CELLS** (auto downscales with a warning).

---

## Configuration (edit constants in `# img2gds.py`)

```python
# GDS units
GDS_UNIT_M       = 1e-6        # 1 µm = 1e-6 m
GRID_STEP_UM     = 0.005
GDS_PREC_M       = GRID_STEP_UM * 1e-6  # precision in meters, aligned to GRID_STEP_UM

# Grid parameters
MAX_CELLS        = 500_000     # safety cap for Nx*Ny
CELL_UM          = 10.0        # base side for binary [µm]
GAP_UM           = 2.0         # base edge-to-edge gap [µm]

# Sizing constraints (enforced in any mode)
MIN_SIDE_UM      = 3.0         # minimum allowed square side [µm]
MIN_GAP_UM       = 2.0         # minimum safety edge-to-edge gap [µm]

# Sizing targets (inclusive of margins; optional)
TARGET_WIDTH_UM  = 3000.0
TARGET_HEIGHT_UM = 2000.0
MARGIN_UM        = 150.0

# Rendering mode
MODE             = "binary"    # "binary" | "grayscale"

# PNG processing
INVERT           = True        # invert before threshold/intensity use
THRESHOLD        = 250         # only used in "binary" (also as cutoff in grayscale)

# Image processing
RESAMPLE         = "nearest"   # "nearest" | "lanczos" | "bilinear"
FIT_MODE         = "contain"   # "contain" | "fit_width" | "fit_height"

# Numeric GDS layer/datatype
LAYER_NUM        = 0
DATATYPE_NUM     = 0
```

---

## Modes

### Binary

* After optional invert, pixels are thresholded at `THRESHOLD`.
* **White** pixels → one square of side `CELL_UM` (fixed).
* **Black** pixels → empty.

### Grayscale

* After optional invert, pixels are filtered by `THRESHOLD`:

  * With `INVERT=True`: pixels **below** `THRESHOLD` are active; brighter pixels are empty.
  * With `INVERT=False`: pixels **above** `THRESHOLD` are active; darker pixels are empty.
* Active pixels map to a side length in **[side_min, side_max]**:

  * `side_min = max(MIN_SIDE_UM, 0)`
  * `side_max = min(CELL_UM, CELL_UM + GAP_UM - MIN_GAP_UM)`
* Darker (or lighter, depending on `INVERT`) → **larger** squares. Empty pixels produce no geometry.

> If `MIN_SIDE_UM > side_max`, the script aborts with a clear hint to increase pitch or relax constraints.

---

## Sizing (inclusive of margins)

Let:

* `pitch = CELL_UM + GAP_UM`
* `margin = MARGIN_UM`

Grid size (`Nx, Ny`) is chosen from the input image aspect ratio and `FIT_MODE`, constrained by:

* available **drawable** area (`TARGET_WIDTH_UM / TARGET_HEIGHT_UM`, inclusive of margins),
* and **MAX_CELLS** (automatic downscale when exceeded).

Model extent (excluding margins) uses the **grid pitch** and a **conservative** square size:

```
model_w ≈ (Nx - 1)*pitch + side_max
model_h ≈ (Ny - 1)*pitch + side_max
```

Final bounding box (including margins):

```
width_um  = (Nx - 1)*pitch + side_max + 2*margin
height_um = (Ny - 1)*pitch + side_max + 2*margin
```

> `side_max` is used for bounding since it is the largest possible square; actual content may be smaller (especially in grayscale).

---

## Coordinate system

* Image origin (top-left) maps to **bottom-left** in GDS: **Y is flipped**.
* **GDS units**: unit = `1e-6 m` (µm), precision = `1e-9 m`.

---

## Notes & tips

* **Backends**: uses **gdspy** if available; otherwise falls back to **gdstk** automatically.
* **Resampling**: for pixel-sharp masks use `"nearest"`; for smoother downsampling try `"lanczos"` or `"bilinear"`.
* **Safety**: `MAX_CELLS` prevents pathological geometries; the script will print a `[WARN]` if it must downscale.
* **Layers**: geometry is emitted to `(LAYER_NUM, DATATYPE_NUM)` only.
* **Verbose**: pass `-v`/`--verbose` to print grid size, safety constraints, and final bounding box.

---

## CLI

```bash
python3 img2gds.py <input.png> <output.gds> [-v|--verbose]
```

Errors are reported with actionable messages (e.g., missing file, non-PNG input, or conflicting size constraints).
