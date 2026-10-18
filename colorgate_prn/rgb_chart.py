"""RGB calibration chart for printers whose ColorGate queue takes RGB PNG input (Flora XTRA2512UV).

ColorGate's RGB -> device conversion on this queue cannot be reproduced from the ICC profiles alone
(sRGB white comes out with ~1-2 % C/M/K ink), so the colour chain is measured instead:

1. make_rgb_chart()  -> PNG of the same pixel size as production jobs (2339 x 3059 @ 300 dpi), so the hot
   folder scales and rotates it exactly like a real job, plus a .json with patch positions.
2. RIP it in ColorGate through the same hot folder (POD F2), output to file.
3. measure_rgb_chart(prn, json) -> per patch mean drop level for every channel -> 3D LUT RGB -> tone.

Top band: large flat grey squares used to study the error diffusion.
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

GRID = (0, 32, 64, 96, 128, 150, 172, 192, 210, 226, 240, 250, 255)   # 13 levels per channel
DARK = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96)                     # shadows, where K/GCR change fast
FLATS = (255, 250, 240, 220, 192, 128)                                  # big squares for ED analysis


def make_rgb_chart(out_png: str, kind: str = "main", width: int = 2339, height: int = 3059, patch: int = 42,
                   flat: int = 360, dpi: int = 300) -> str:
    """kind "main": 13^3 grid + 256 greys + flats; kind "dark": 11^3 grid of shadow colours (0..96)."""
    img = np.full((height, width, 3), 255, np.uint8)
    patches = []
    if kind == "main":
        grid = GRID
        gap = (width - len(FLATS) * flat) // (len(FLATS) + 1)
        for i, v in enumerate(FLATS):
            x0 = gap + i * (flat + gap)
            img[20:20 + flat, x0:x0 + flat] = v
            patches.append({"kind": "flat", "rgb": [v, v, v], "x": x0, "y": 20, "w": flat, "h": flat})
        colours = [(r, g, b) for r in grid for g in grid for b in grid] + [(v, v, v) for v in range(256)]
        top = 20 + flat + 30
    elif kind == "dark":
        grid = DARK
        colours = [(r, g, b) for r in grid for g in grid for b in grid]
        top = 60
        patch = 64                       # 11^3 colours fit with larger (more precisely measured) patches
    else:
        raise ValueError(kind)
    cols = width // patch
    rows_needed = (len(colours) + cols - 1) // cols
    if top + rows_needed * patch > height:
        raise ValueError("chart does not fit")
    x_off = (width - cols * patch) // 2
    for i, c in enumerate(colours):
        r, k = divmod(i, cols)
        x0, y0 = x_off + k * patch, top + r * patch
        img[y0:y0 + patch, x0:x0 + patch] = c
        patches.append({"kind": "patch", "rgb": list(c), "x": x0, "y": y0, "w": patch, "h": patch})
    Image.fromarray(img, "RGB").save(out_png, dpi=(dpi, dpi))
    js = os.path.splitext(out_png)[0] + ".json"
    with open(js, "w") as f:
        json.dump({"width": width, "height": height, "dpi": dpi, "kind": kind, "grid": list(grid),
                   "patches": patches}, f)
    return js


def locate_job(prn_path: str, sizes) -> tuple:
    """(x, y, w, h) of the single job in a PRN, choosing the candidate size that fits the ink bounding box.

    White prints a light ink floor, so the bbox is the job; error diffusion leaves the first rows of a
    light job empty, so the job is anchored on the bottom/right edges.
    """
    from .prn_format import read_prn, unpack_levels
    hdr, raw = read_prn(prn_path, unpack=False)
    cols = np.zeros(hdr.width, bool); rows = np.zeros(hdr.height, bool)
    for y in range(0, hdr.height, 1024):
        blk = unpack_levels(np.asarray(raw[y:y + 1024]), hdr.width) > 0
        cols |= blk.any((0, 1)); rows[y:y + blk.shape[0]] = blk.any((1, 2))
    xs, ys = np.nonzero(cols)[0], np.nonzero(rows)[0]
    bw, bh = int(xs[-1]) + 1 - int(xs[0]), int(ys[-1]) + 1 - int(ys[0])
    w, h = min(sizes, key=lambda s: abs(s[0] - bw) + abs(s[1] - bh) + (1e9 if s[1] < bh else 0))
    if abs(w - bw) > 2:
        print(f"warning: ink bbox {bw}x{bh} does not match job size {w}x{h}")
    return int(xs[-1]) + 1 - w, int(ys[-1]) + 1 - h, w, h


def measure_rgb_chart(prn_path: str, chart_json: str, image_path: str, setup, margin: float = 2.5) -> list:
    """Per patch: actual mean RGB in the image ColorGate received, and mean drop level per PRN channel.

    image_path: the PNG exactly as ColorGate RIPped it (JobDir\\<job>.CJB\\EPS-Data\\*.png); it may be a
    rescaled copy of the chart, patch positions are scaled accordingly.
    """
    from .prn_format import read_prn, unpack_levels
    from .generator import device_size, read_image_header
    from .resample import output_size
    with open(chart_json) as f:
        chart = json.load(f)
    img = np.asarray(Image.open(image_path).convert("RGB")).astype(np.float64)
    ih, iw, _ = img.shape
    s = iw / chart["width"]
    # job size: stretched by the hot folder (dest_mm) or, when RIPped by hand, the image size at its dpi
    dpi = read_image_header(image_path)[2]
    sizes = [device_size(iw, ih, dpi, setup), (output_size(iw, dpi, setup.xdpi), output_size(ih, dpi, setup.ydpi))]
    jx, jy, jw, jh = locate_job(prn_path, sizes)
    sx, sy = jw / iw, jh / ih
    hdr, raw = read_prn(prn_path, unpack=False)
    out = []
    for p in chart["patches"]:
        x0, x1 = p["x"] * s + margin, (p["x"] + p["w"]) * s - margin
        y0, y1 = p["y"] * s + margin, (p["y"] + p["h"]) * s - margin
        rgb = img[int(np.ceil(y0)):int(y1), int(np.ceil(x0)):int(x1)].reshape(-1, 3)
        if setup.rotate == 180:                                # image rect -> device rect of the rotated job
            x0, x1, y0, y1 = iw - x1, iw - x0, ih - y1, ih - y0
        dx0, dx1 = jx + int(np.ceil(x0 * sx)), jx + int(x1 * sx)
        dy0, dy1 = jy + int(np.ceil(y0 * sy)), jy + int(y1 * sy)
        lv = unpack_levels(np.asarray(raw[dy0:dy1]), hdr.width)[:, :, dx0:dx1].astype(np.float64)
        out.append({"kind": p["kind"], "rgb": rgb.mean(0).tolist(), "rgb_std": float(rgb.std(0).max()),
                    "tones": lv.mean((0, 2)).tolist(), "n": int(lv.shape[0] * lv.shape[2]),
                    "grid": chart.get("grid", list(GRID))})
    return out


def _grid_points(measured: list, garr: np.ndarray, channels) -> dict:
    """Measured grid colours -> tones; a patch counts when every channel is within 2 of a grid level."""
    best = {}
    for m in measured:
        if m["kind"] != "patch":
            continue
        idx = tuple(int(np.argmin(np.abs(garr - v))) for v in m["rgb"])
        d = max(abs(garr[i] - v) for i, v in zip(idx, m["rgb"]))
        if d <= 2.0 and (idx not in best or d < best[idx][0]):      # closest patch wins
            best[idx] = (d, m["tones"][:len(channels)])
    return {k: v[1] for k, v in best.items()}


def build_rgb_lut(measured: list, channels, pipe) -> dict:
    """Measured patches (one or more charts) -> colour model stored in setup.json["rgb_lut"].

    Model: device CMYK = LittleCMS perceptual(rgb) + residual(rgb) [+ dark grey axis correction].
    The perceptual transform gives the fine shape between grid points (GCR, K start); the residual,
    measured at the grid points, makes it match ColorGate there.  Fitted on the Flora sample jobs:
    perceptual beat relative/saturation and the plain LUT (croc K error 0.023 -> 0.011).
    The main chart (13^3, GRID) must be complete; further charts (e.g. "dark") refine the residual on
    the union of all grid levels, unmeasured points of the finer grid are interpolated from the coarse one.
    """
    from .color import INKS, tetrahedral
    ci = [list(channels).index(i) for i in INKS]
    coarse = np.array(GRID, float)
    cpts = _grid_points(measured, coarse, channels)
    g = len(coarse)
    if len(cpts) < g ** 3:
        raise ValueError(f"{g ** 3 - len(cpts)} colours of the main chart grid not measured")
    base_xf = pipe._rgb_xform(0, False)

    def residual_at(levels, pts):
        rgb = np.array([[levels[i] for i in k] for k in pts], float)
        dev = pipe.tones_to_device(np.array([[v[c] for c in ci] for v in pts.values()]))
        return rgb, dev - pipe.icc_device_rgb(rgb, base_xf)

    rgb_c, res_c = residual_at(coarse, cpts)
    res = np.zeros((g, g, g, 4), np.float32)
    for k, r in zip(cpts, res_c):
        res[k] = r
    levels = sorted({float(v) for m in measured if m["kind"] == "patch" for v in m.get("grid", GRID)})
    fine = np.array(levels)
    if len(fine) > g:   # refine on the union grid
        G = len(fine)
        allpts = np.stack(np.meshgrid(fine, fine, fine, indexing="ij"), -1).reshape(-1, 3)
        res_f = tetrahedral(coarse, res, allpts).reshape(G, G, G, 4)
        fpts = _grid_points(measured, fine, channels)
        if fpts:
            _, r = residual_at(fine, fpts)
            for k, v in zip(fpts, r):
                res_f[k] = v
        res, grid, g = res_f, fine, G
    else:
        grid = coarse
    lut = {"grid": [float(v) for v in grid], "base_intent": 0, "base_bpc": False,
           "residual": {c: res[..., k].tolist() for k, c in enumerate("CMYK")}}
    grey = [m for m in measured if m["kind"] == "patch" and max(m["rgb"]) - min(m["rgb"]) < 1.0]
    if grey and len(grid) == len(coarse):   # with a measured dark chart the dense grid already covers shadows
        grey.sort(key=lambda m: np.mean(m["rgb"]))
        grgb = np.array([m["rgb"] for m in grey])
        gdev = pipe.tones_to_device(np.array([[m["tones"][c] for c in ci] for m in grey]))
        model = pipe.icc_device_rgb(grgb, base_xf) + tetrahedral(np.array(grid), res, grgb)
        lut["grey_corr"] = {"level": grgb.mean(1).tolist(), "corr": (gdev - model).tolist(),
                            "sigma": 24.0, "fade": [40.0, 72.0]}
    return lut
