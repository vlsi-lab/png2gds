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
# along with this program.  If not, see <https:#www.gnu.org/licenses/>.

import sys, os, math
from typing import Tuple

# ---------------- Configuration ----------------
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

# ---------------- Backend selection ----------------
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

# ---------------- Grid helpers ----------------
def snap(x_um: float) -> float:
    """Snap a coordinate/length (in µm) to the technology grid."""
    step = GRID_STEP_UM
    return round(x_um / step) * step

# ---------------- Image helpers ----------------
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
    img_w, img_h,
    target_w_um, target_h_um,
    pitch_um, side_um, margin_um,
    max_cells=500_000,
    verbose=True
) -> Tuple[int,int]:
    r = (img_h / img_w) if img_w > 0 else 1.0  # aspect = H/W
    s = float(side_um)
    p = float(pitch_um)
    margin = float(margin_um)

    def nx_max_from_width(draw_w):
        return max(1, int(math.floor((draw_w - s) / p)) + 1)

    def ny_max_from_height(draw_h):
        return max(1, int(math.floor((draw_h - s) / p)) + 1)

    draw_w = None if target_w_um is None else max(target_w_um - 2.0 * margin, s)
    draw_h = None if target_h_um is None else max(target_h_um - 2.0 * margin, s)

    if draw_w is not None and draw_h is not None:
        nx_w = nx_max_from_width(draw_w)
        ny_h = ny_max_from_height(draw_h)

        if FIT_MODE == "fit_width":
            nx = nx_w
            ny = min(ny_h, max(1, int(math.floor(r * nx))))
        elif FIT_MODE == "fit_height":
            ny = ny_h
            nx = min(nx_w, max(1, int(math.floor(ny / r)))) if r > 0 else nx_w
        else:  # "contain"
            nx_h_cap = max(1, int(math.floor(ny_h / r))) if r > 0 else nx_w
            nx = max(1, min(nx_w, nx_h_cap))
            ny = max(1, min(ny_h, int(math.floor(r * nx))))
    elif draw_w is not None:
        nx = nx_max_from_width(draw_w)
        ny = max(1, int(math.floor(r * nx)))
    elif draw_h is not None:
        ny = ny_max_from_height(draw_h)
        nx = max(1, int(math.floor(ny / r))) if r > 0 else ny
    else:
        nx, ny = int(img_w), int(img_h)

    total = nx * ny
    if total > max_cells:
        scale = math.sqrt(max_cells / total)
        nx_before, ny_before = nx, ny
        nx = max(1, int(math.floor(nx * scale)))
        ny = max(1, int(math.floor(ny * scale)))
        if verbose:
            print(f"[WARN] Downscaled for MAX_CELLS={max_cells}: {nx_before}x{ny_before} -> {nx}x{ny}")

    return nx, ny

# ---------------- Size constraints helpers ----------------
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

# ---------------- PNG → GDS ----------------
def png_to_gds(input_path: str, output_path: str, verbose: bool = True):
    cell_um = float(CELL_UM)
    gap_um  = float(GAP_UM)
    margin  = float(MARGIN_UM)
    pitch_um = cell_um + gap_um

    side_min, side_max = _compute_size_bounds(pitch_um)

    img_gray = _load_png_grayscale(input_path)
    img_proc = _prepare_image(img_gray, MODE)

    nx, ny = _compute_grid_dims_inclusive(
        img_gray.width, img_gray.height,
        TARGET_WIDTH_UM, TARGET_HEIGHT_UM,
        pitch_um, cell_um, margin, max_cells=int(MAX_CELLS),
        verbose=verbose
    )

    img_grid = img_proc.resize((nx, ny), resample=_resample_mode(RESAMPLE))
    pixels = img_grid.load()

    # GDS lib/cell
    if GDSPY:
        lib = gds.GdsLibrary(unit=GDS_UNIT_M, precision=GDS_PREC_M)
        cell = lib.new_cell("LOGO")
    else:
        lib = gds.Library(unit=GDS_UNIT_M, precision=GDS_PREC_M)
        cell = lib.new_cell("LOGO")

    rects = []
    pitch = float(pitch_um)

    # Flip Y: image (top→bottom) → GDS (bottom→top)
    for j_img in range(ny):
        j = ny - 1 - j_img
        y0_row = margin + j * pitch
        for i in range(nx):
            x0_col = margin + i * pitch

            if MODE == "binary":
                on = (pixels[i, j_img] == 255)
                if not on:
                    continue
                side = cell_um 
            else:  # grayscale
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

    width_um  = (nx - 1) * pitch + side_max + 2 * margin
    height_um = (ny - 1) * pitch + side_max + 2 * margin

    if verbose:
        print(f"[INFO] Mode: {MODE}")
        print(f"[INFO] Cells: {nx} x {ny}  -> squares {len(rects)}")
        print(f"[INFO] Base Side={cell_um} µm, Base Gap={gap_um} µm, Pitch={pitch} µm")
        print(f"[INFO] Safety: MIN_SIDE={side_min} µm, MIN_GAP={MIN_GAP_UM} µm, side_max={side_max} µm")
        print(f"[INFO] Margin per side={margin} µm")
        print(f"[INFO] GDS precision={GDS_PREC_M*1e9:.0f} nm, snap grid={GRID_STEP_UM} µm")
        print(f"[INFO] Bounding box ~ {width_um:.3f} µm x {height_um:.3f} µm (inclusive of margins)")
        if TARGET_WIDTH_UM is not None or TARGET_HEIGHT_UM is not None:
            print(f"[INFO] Targets (inclusive): W={TARGET_WIDTH_UM} µm, H={TARGET_HEIGHT_UM} µm")

    lib.write_gds(output_path)
    if verbose:
        print(f"[OK] Saved: {output_path}")

# ---------------- Main ----------------
def main():
    if len(sys.argv) < 3:
        print("Usage: python3 img2gds.py <input.png> <output.gds>", file=sys.stderr)
        sys.exit(1)

    input_path  = sys.argv[1]
    output_path = sys.argv[2]
    verbose = True if "-v" in sys.argv or "--verbose" in sys.argv else False

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input not found: {input_path}")

    png_to_gds(input_path, output_path, verbose)

if __name__ == "__main__":
    main()
