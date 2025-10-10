# SPDX-License-Identifier: GPL-3.0-or-later
#
# Copyright © 2025 Alessandro Varaldi
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the Licence, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import sys, os, math
from typing import Tuple

# ================================================================
#                        USER-TUNABLE SETTINGS
# ================================================================
# Target outer bounding box (inclusive). No geometry is ever drawn outside.
TARGET_WIDTH_UM   = 3000.0
TARGET_HEIGHT_UM  = 2000.0

# Inner margins that reserve space for pads, keep-out, etc.
MARGIN_X_UM       = 150.0
MARGIN_Y_UM       = 150.0

# How to place the content inside the drawable box if it does not fully fill it.
ALIGN             = "center"       # "center" | "topleft"

# Rendering
MODE              = "binary"       # "binary" | "grayscale"
INVERT            = False
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

# ================================================================
#                        ADVANCED SETTINGS
# ================================================================
GDS_UNIT_M        = 1e-6           # 1 user unit = 1 µm
GRID_STEP_UM      = 0.005          # snapping step [µm]
GDS_PREC_M        = 1e-9

# Constraints
MIN_SIDE_UM       = 3.0            # min square side [µm]
MIN_GAP_UM        = 2.0            # min edge-to-edge gap [µm]

# ================================================================
#                        BACKEND SELECTION
# ================================================================
try:
    import gdspy as gds
    GDSPY = True
except Exception:
    try:
        import gdstk as gds
        GDSPY = False
    except Exception:
        print("Error: install gdspy (or gdstk): pip install gdspy", file=sys.stderr)
        raise

from PIL import Image

LAYER_KW = {"layer": LAYER_NUM, "datatype": DATATYPE_NUM}

# ================================================================
#                           HELPERS
# ================================================================
def snap(x_um: float) -> float:
    """Snap a coordinate/length (in µm) to the technology grid."""
    step = GRID_STEP_UM
    return round(x_um / step) * step

def _load_png_grayscale(path: str) -> Image.Image:
    ext = os.path.splitext(path)[1].lower()
    if ext != ".png":
        raise ValueError("Only PNG input is accepted. Please provide a .png file.")
    return Image.open(path).convert("L")

def _prepare_image(img: Image.Image, mode: str) -> Image.Image:
    if mode == "binary":
        if INVERT:
            img = Image.eval(img, lambda x: 255 - x)
        return img.point(lambda x: 255 if x >= THRESHOLD else 0, mode="1")
    elif mode == "grayscale":
        return img
    else:
        raise ValueError('MODE must be "binary" or "grayscale"')

def _resample_mode(name: str):
    m = {"nearest": Image.NEAREST, "lanczos": Image.LANCZOS, "bilinear": Image.BILINEAR}
    n = name.lower()
    if n not in m:
        raise ValueError("RESAMPLE must be one of: nearest | lanczos | bilinear")
    return m[n]

def _compute_grid_dims_inclusive(
    img_w: int, img_h: int,
    box_w_um: float, box_h_um: float,
    pitch_um: float, side_um: float,
    max_cells: int = 500_000,
    verbose: bool = True
) -> Tuple[int, int]:

    r = (img_h / img_w) if img_w > 0 else 1.0
    s = float(side_um)
    p = float(pitch_um)

    def nx_max_from_width(draw_w):  return max(1, int(math.floor((draw_w - s) / p)) + 1)
    def ny_max_from_height(draw_h): return max(1, int(math.floor((draw_h - s) / p)) + 1)

    draw_w = max(box_w_um, s)
    draw_h = max(box_h_um, s)

    if FIT_MODE == "fit_width":
        nx = nx_max_from_width(draw_w)
        ny = max(1, int(math.floor(r * nx)))
        ny = min(ny, ny_max_from_height(draw_h))
    elif FIT_MODE == "fit_height":
        ny = ny_max_from_height(draw_h)
        nx = max(1, int(math.floor(ny / r))) if r > 0 else ny
        nx = min(nx, nx_max_from_width(draw_w))
    else:  # "contain"
        nx_w = nx_max_from_width(draw_w)
        ny_h = ny_max_from_height(draw_h)
        nx_h_cap = max(1, int(math.floor(ny_h / r))) if r > 0 else nx_w
        nx = max(1, min(nx_w, nx_h_cap))
        ny = max(1, min(ny_h, int(math.floor(r * nx))))

    total = nx * ny
    if total > max_cells:
        scale = math.sqrt(max_cells / total)
        nx_before, ny_before = nx, ny
        nx = max(1, int(math.floor(nx * scale)))
        ny = max(1, int(math.floor(ny * scale)))
        if verbose:
            print(f"[WARN] Downscaled for MAX_CELLS={max_cells}: {nx_before}x{ny_before} -> {nx}x{ny}")

    return nx, ny

def _compute_size_bounds(pitch_um: float) -> Tuple[float, float]:
    side_min = max(0.0, float(MIN_SIDE_UM))
    side_max = max(0.0, min(float(CELL_UM), float(pitch_um) - float(MIN_GAP_UM)))
    if side_min > side_max:
        raise ValueError(
            f"Constraint conflict: MIN_SIDE_UM({MIN_SIDE_UM}) > allowed max side ({side_max:.3f}). "
            "Increase pitch (CELL_UM+GAP_UM) or reduce MIN_SIDE_UM/MIN_GAP_UM."
        )
    return side_min, side_max

def _intensity_to_side(t01: float, side_min: float, side_max: float) -> float:
    t = 0.0 if t01 < 0.0 else (1.0 if t01 > 1.0 else float(t01))
    return side_min + (side_max - side_min) * t

# ================================================================
#                         PNG → GDS PIPELINE
# ================================================================
def png_to_gds(input_path: str, output_path: str, verbose: bool = True):

    cell_um  = float(CELL_UM)
    gap_um   = float(GAP_UM)
    pitch_um = cell_um + gap_um

    side_min, side_max = _compute_size_bounds(pitch_um)
    side_max = snap(side_max)

    if TARGET_WIDTH_UM <= 0 or TARGET_HEIGHT_UM <= 0:
        raise ValueError("TARGET_* must be positive.")
    if MARGIN_X_UM < 0 or MARGIN_Y_UM < 0:
        raise ValueError("MARGIN_* must be non-negative.")
    drawable_w = TARGET_WIDTH_UM  - 2.0 * MARGIN_X_UM
    drawable_h = TARGET_HEIGHT_UM - 2.0 * MARGIN_Y_UM
    if drawable_w <= 0 or drawable_h <= 0:
        raise ValueError(
            f"Drawable box is non-positive: ({drawable_w:.3f} µm × {drawable_h:.3f} µm). "
            "Reduce margins or increase targets."
        )

    img_gray = _load_png_grayscale(input_path)
    img_proc = _prepare_image(img_gray, MODE)

    nx, ny = _compute_grid_dims_inclusive(
        img_gray.width, img_gray.height,
        drawable_w, drawable_h,
        pitch_um, cell_um, max_cells=int(MAX_CELLS),
        verbose=verbose
    )

    width_nom  = (nx - 1) * pitch_um + side_max
    height_nom = (ny - 1) * pitch_um + side_max

    if width_nom > drawable_w + 1e-12 or height_nom > drawable_h + 1e-12:
        raise ValueError(
            "Drawable box too small for current pitch/side/grid:\n"
            f"  need at least ~ {width_nom:.3f} µm × {height_nom:.3f} µm (no extra margins),\n"
            f"  drawable = {drawable_w:.3f} µm × {drawable_h:.3f} µm.\n"
            "Increase target size or reduce pitch/side or margins."
        )

    base_x = MARGIN_X_UM
    base_y = MARGIN_Y_UM

    slack_x = drawable_w - width_nom
    slack_y = drawable_h - height_nom
    if ALIGN.lower() == "center":
        base_x += 0.5 * slack_x
        base_y += 0.5 * slack_y
    elif ALIGN.lower() == "topleft":
        pass
    else:
        raise ValueError('ALIGN must be "center" or "topleft"')

    base_x = snap(base_x)
    base_y = snap(base_y)

    img_grid = img_proc.resize((nx, ny), resample=_resample_mode(RESAMPLE))
    pixels = img_grid.load()

    if GDSPY:
        lib = gds.GdsLibrary(unit=GDS_UNIT_M, precision=GDS_PREC_M)
        cell = lib.new_cell("LOGO")
    else:
        lib = gds.Library(unit=GDS_UNIT_M, precision=GDS_PREC_M)
        cell = lib.new_cell("LOGO")

    rects = []
    pitch = float(pitch_um)

    for j_img in range(ny):
        j = ny - 1 - j_img
        y0_row = base_y + j * pitch
        for i in range(nx):
            x0_col = base_x + i * pitch

            if MODE == "binary":
                on = (pixels[i, j_img] == 255)
                if not on:
                    continue
                side = cell_um
            else:
                val = pixels[i, j_img]
                if not INVERT:
                    if val <= THRESHOLD:
                        continue
                    t01 = (float(val) - THRESHOLD) / (255.0 - THRESHOLD)
                else:
                    if val >= THRESHOLD:
                        continue
                    t01 = (THRESHOLD - float(val)) / THRESHOLD

                side = _intensity_to_side(t01, side_min, side_max)
                if side <= 0.0:
                    continue

            x0 = snap(x0_col)
            y0 = snap(y0_row)
            side = snap(side)
            x1 = snap(x0 + side)
            y1 = snap(y0 + side)

            if GDSPY:
                rects.append(gds.Rectangle((x0, y0), (x1, y1), **LAYER_KW))
            else:
                rects.append(gds.rectangle((x0, y0), (x1, y1), **LAYER_KW))

    if rects:
        if GDSPY:
            cell.add(rects)
        else:
            for r in rects:
                cell.add(r)

    if verbose:
        content_bbox_w = width_nom
        content_bbox_h = height_nom
        print(f"[INFO] Mode: {MODE}")
        print(f"[INFO] Cells: {nx} x {ny}  -> rectangles {len(rects)}")
        print(f"[INFO] Pitch={pitch} µm, Base Side={CELL_UM} µm, side_max={side_max} µm")
        print(f"[INFO] Target box      : {TARGET_WIDTH_UM:.3f} µm × {TARGET_HEIGHT_UM:.3f} µm")
        print(f"[INFO] Drawable box    : {drawable_w:.3f} µm × {drawable_h:.3f} µm "
              f"(margins: x={MARGIN_X_UM} µm, y={MARGIN_Y_UM} µm)")
        print(f"[INFO] Placement origin: ({base_x:.3f} µm, {base_y:.3f} µm), align={ALIGN}")
        print(f"[INFO] Content bbox ≤  : {content_bbox_w:.3f} µm × {content_bbox_h:.3f} µm "
              f"(inside drawable box)")
        print(f"[INFO] Grid snap={GRID_STEP_UM} µm, GDS unit=1 µm, precision={GDS_PREC_M*1e9:.0f} nm")

    lib.write_gds(output_path)
    if verbose:
        print(f"[OK] Saved: {output_path}")

# ================================================================
#                             MAIN
# ================================================================
def main():
    if len(sys.argv) < 3:
        print("Usage: python3 img2gds.py <input.png> <output.gds> [-v|--verbose]", file=sys.stderr)
        sys.exit(1)

    input_path  = sys.argv[1]
    output_path = sys.argv[2]
    verbose = True if "-v" in sys.argv or "--verbose" in sys.argv else False

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input not found: {input_path}")

    png_to_gds(input_path, output_path, verbose)

if __name__ == "__main__":
    main()
