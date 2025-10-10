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
* **Snaps** all coordinates and sizes to a technology **grid step**.

---

## Configuration (edit constants in `img2gds.py`)

```python
# ========================= USER-TUNABLE =========================
# Target outer bounding box (inclusive). No geometry is drawn outside.
TARGET_WIDTH_UM   = 3000.0
TARGET_HEIGHT_UM  = 2000.0

# Inner margins that reserve space for pads, keep-out, etc.
MARGIN_X_UM       = 150.0
MARGIN_Y_UM       = 150.0

# How to place the content inside the drawable box if it does not fully fill it.
ALIGN             = "center"       # "center" | "topleft"

# Rendering
MODE              = "binary"       # "binary" | "grayscale"
INVERT            = True
THRESHOLD         = 0
RESAMPLE          = "nearest"      # "nearest" | "lanczos" | "bilinear"
FIT_MODE          = "contain"      # "contain" | "fit_width" | "fit_height"

# Grid (logical pixel grid)
CELL_UM           = 10.0           # base side for binary [µm]
GAP_UM            = 5.0            # edge-to-edge gap [µm]
MAX_CELLS         = 500_000        # cap for Nx*Ny

# Content layer/datatype (where the squares go)
LAYER_NUM         = 0
DATATYPE_NUM      = 0

# =========================== ADVANCED ===========================
GDS_UNIT_M        = 1e-6           # 1 user unit = 1 µm
GRID_STEP_UM      = 0.005          # snapping step [µm]
GDS_PREC_M        = 1e-9           # file precision in meters

# Constraints
MIN_SIDE_UM       = 3.0            # min square side [µm]
MIN_GAP_UM        = 2.0            # min edge-to-edge gap [µm]
```

---

## Modes

### Binary

* After optional invert, pixels are thresholded at `THRESHOLD` and converted to a 1-bit mask.
* **White** pixels (`255`) → one square of side `CELL_UM` (fixed).
* **Black** pixels (`0`) → empty.

### Grayscale

* Pixels are first filtered by `THRESHOLD` (after optional invert):

  * With `INVERT=True`: pixels **below** `THRESHOLD` are active; brighter pixels are empty.
  * With `INVERT=False`: pixels **above** `THRESHOLD` are active; darker pixels are empty.

* Each **active** pixel maps to a side length in `[side_min, side_max]`, where

  * `side_min = max(0, MIN_SIDE_UM)`
  * `side_max = min(CELL_UM, CELL_UM + GAP_UM - MIN_GAP_UM)`, then **snapped** to `GRID_STEP_UM`.

* Darker (or lighter, depending on `INVERT`) → **larger** squares. Inactive pixels produce no geometry.

> If `MIN_SIDE_UM > side_max`, the script aborts with a clear hint to increase pitch or relax constraints.

---

## Sizing & placement (inclusive of margins)

Let `pitch = CELL_UM + GAP_UM`. The script computes `Nx, Ny` from the input aspect ratio and `FIT_MODE`, constrained by:

* available **drawable** area (`TARGET_WIDTH_UM - 2*MARGIN_X_UM` by `TARGET_HEIGHT_UM - 2*MARGIN_Y_UM`),
* and **MAX_CELLS** (automatic downscale with a `[WARN]`).

A conservative upper bound for content extent (excluding margins) uses the largest possible square:

```
content_w ≈ (Nx - 1)*pitch + side_max
content_h ≈ (Ny - 1)*pitch + side_max
```

Final bounding box (including margins) therefore fits within:

```
width_um  ≤ content_w  + 2*MARGIN_X_UM
height_um ≤ content_h + 2*MARGIN_Y_UM
```

**Alignment:** If the content doesn’t fill the drawable box, it is placed according to `ALIGN` (`"center"` or `"topleft"`).
All coordinates and side lengths are **snapped** to `GRID_STEP_UM`.

---

## Coordinate system

* Image origin (top-left) maps to **bottom-left** in GDS: **Y is flipped**.
* **GDS units**: unit = `1 µm` (`1e-6 m`), precision = `1 nm` (`1e-9 m`).

---

## Notes & tips

* **Backends:** uses **gdspy** if available; otherwise falls back to **gdstk** automatically.
* **Resampling:** for pixel-sharp masks use `"nearest"`; for smoother downsampling try `"lanczos"` or `"bilinear"`.
* **Safety:** `MAX_CELLS` prevents pathological geometries; the script prints a `[WARN]` when it downsamples.
* **Layers:** geometry is emitted only to `(LAYER_NUM, DATATYPE_NUM)`.
* **Verbose:** pass `-v` / `--verbose` to print grid size, constraints, placement, and final bounds.

---

## CLI

```bash
python3 img2gds.py <input.png> <output.gds> [-v|--verbose]
```

Errors are reported with actionable messages (e.g., missing file, non-PNG input, or conflicting size constraints).

---

## License

This project is licensed under **GPL-3.0-or-later**. See `LICENSE` for details.
