"""Exact screen extraction by measuring ColorGate's own output (no access to the encoded screen file needed).

1. make_chart()   -> chart TIF (+ .json layout): flat patches 0..255 per channel, a K frame for detection.
2. RIP the chart TIF in ColorGate with the production settings, output to file (PRN).
3. extract_screen(prn, chart.json) -> exact 8-bit threshold matrix + per-channel offsets.

Every patch is flat, so it is screened at one known k (k = round(count_on * 255 / N)).  A cell that is
on at k has threshold < k, a cell that is off has threshold >= k; with patches covering all k the
threshold of every cell is pinned down exactly.  Channels share one matrix with per-channel offsets,
which are found by aligning each channel's partial result to the reference channel.
"""
from __future__ import annotations

import json
import os

import numpy as np
import tifffile

from .prn_format import CHANNELS, read_prn
from .screening import Screen

PATCH_W, PATCH_H, MARGIN = 118, 122, 3        # input px @300 dpi; interior >= 256 x 448 device px
FRAME = 8                                      # K frame width (input px)


def make_chart(out_tif: str, channels=("Y", "K", "C", "M", "W", "CM", "MY", "CY", "CMY"), values=range(1, 256),
               cols: int = 32, dpi: int = 300) -> str:
    """Write the calibration chart; returns path of the layout json.

    channels: "C", "M", "Y", "K", "W" or combinations like "CM" (all listed channels at the same value);
    the ICC conversion mixes channels, so combinations hit k values single channels miss.
    """
    patches = [(ch, v) for ch in channels for v in values]
    rows = (len(patches) + cols - 1) // cols
    W = cols * PATCH_W + 2 * FRAME
    H = rows * PATCH_H + 2 * FRAME
    img = np.zeros((H, W, 6), np.uint8)
    img[..., 4] = 255                       # Transparency: opaque
    img[..., 5] = 255                       # W spot (Photoshop convention): 255 = no white
    img[:FRAME, :, 3] = img[-FRAME:, :, 3] = 255
    img[:, :FRAME, 3] = img[:, -FRAME:, 3] = 255
    idx = {"C": 0, "M": 1, "Y": 2, "K": 3}
    layout = []
    for i, (ch, v) in enumerate(patches):
        r, c = divmod(i, cols)
        x0, y0 = FRAME + c * PATCH_W, FRAME + r * PATCH_H
        if ch == "W":
            img[y0:y0 + PATCH_H, x0:x0 + PATCH_W, 5] = 255 - v
        else:
            for c1 in ch:
                img[y0:y0 + PATCH_H, x0:x0 + PATCH_W, idx[c1]] = v
        layout.append({"channel": ch, "value": v, "x": x0, "y": y0, "w": PATCH_W, "h": PATCH_H})
    tifffile.imwrite(out_tif, img, photometric="separated", planarconfig="contig", compression="lzw",
                     extrasamples=(1, 0), resolution=(dpi, dpi), resolutionunit="INCH",
                     extratags=[(332, "H", 1, 1, False),  # InkSet = CMYK, like the production TIFs
                                (333, "s", 0, "Cyan\0Magenta\0Yellow\0Black\0Transparency\0W\0", False)])
    js = os.path.splitext(out_tif)[0] + ".json"
    with open(js, "w") as f:
        json.dump({"dpi": dpi, "width": W, "height": H, "frame": FRAME, "margin": MARGIN, "patches": layout}, f)
    return js


def _locate_job(levels_k: np.ndarray) -> tuple:
    ys, xs = np.nonzero(levels_k)
    return int(xs.min()), int(ys.min())


def extract_screen(prn_path: str, chart_json: str, ref_channel: str = "Y", prior: Screen | None = None,
                   job_x: int | None = None, job_y: int | None = None, xdpi: int = 720, ydpi: int = 1200):
    """Returns (Screen, report str)."""
    with open(chart_json) as f:
        chart = json.load(f)
    hdr, data = read_prn(prn_path)
    if job_x is None or job_y is None:
        jx, jy = _locate_job(data[:, CHANNELS.index("K"), :])
        job_x = jx if job_x is None else job_x
        job_y = jy if job_y is None else job_y
    sx = int(np.ceil(chart["width"] * xdpi / chart["dpi"] - 1e-6)) / chart["width"]
    sy = int(np.ceil(chart["height"] * ydpi / chart["dpi"] - 1e-6)) / chart["height"]
    MH, MW = 448, 256
    N = MH * MW
    lo = {c: np.zeros(N, np.int32) for c in CHANNELS}            # threshold >= lo
    hi = {c: np.full(N, 254, np.int32) for c in CHANNELS}        # threshold <= hi
    seen_k = {c: set() for c in CHANNELS}
    conflicts = 0
    m = chart["margin"]
    for p in chart["patches"]:
        x0 = job_x + int(np.ceil((p["x"] + m) * sx)); x1 = job_x + int(np.floor((p["x"] + p["w"] - m) * sx))
        y0 = job_y + int(np.ceil((p["y"] + m) * sy)); y1 = job_y + int(np.floor((p["y"] + p["h"] - m) * sy))
        if x1 - x0 < MW or y1 - y0 < MH:
            raise ValueError("patch interior smaller than one screen tile")
        x1, y1 = x0 + MW, y0 + MH                                   # exactly one tile
        cols = (np.arange(x0, x1) - job_x) % MW
        rows = (np.arange(y0, y1) - job_y) % MH
        cell = (rows[:, None] * MW + cols[None, :]).ravel()
        for c in CHANNELS:
            lv = data[y0:y1, CHANNELS.index(c), x0:x1].ravel().astype(np.int32)
            band = lv.min()
            if lv.max() > band + 1:
                conflicts += 1                                     # not a flat patch for this channel
                continue
            on = lv > band
            n_on = int(on.sum())
            if n_on == 0 or band >= 3:
                continue
            k = int(round(n_on * 255 / N))
            seen_k[c].add(k)
            on_cells, off_cells = cell[on], cell[~on]
            hi[c][on_cells] = np.minimum(hi[c][on_cells], k - 1)
            lo[c][off_cells] = np.maximum(lo[c][off_cells], k)
    report = [f"job located at x={job_x} y={job_y}; non-flat channel/patches skipped: {conflicts}"]
    # align channels to the reference: channel cell u == reference cell u + (ox, oy); found by FFT
    # cross-correlation of the interval mid-points, then checked by interval consistency
    ref_lo, ref_hi = lo[ref_channel].reshape(MH, MW), hi[ref_channel].reshape(MH, MW)
    ref_mid = (ref_lo + ref_hi) / 2.0
    F_ref = np.fft.fft2(ref_mid - ref_mid.mean())
    offsets = {ref_channel: (0, 0)}
    for c in CHANNELS:
        if c == ref_channel or not seen_k[c]:
            continue
        clo, chi = lo[c].reshape(MH, MW), hi[c].reshape(MH, MW)
        mid = (clo + chi) / 2.0
        corr = np.real(np.fft.ifft2(F_ref * np.conj(np.fft.fft2(mid - mid.mean()))))
        oy, ox = np.unravel_index(np.argmax(corr), corr.shape)
        a_lo = np.roll(np.roll(ref_lo, -oy, 0), -ox, 1); a_hi = np.roll(np.roll(ref_hi, -oy, 0), -ox, 1)
        consistency = np.mean(np.maximum(a_lo, clo) <= np.minimum(a_hi, chi))
        offsets[c] = (int(ox), int(oy))
        report.append(f"{c}: offset ({ox},{oy}) vs {ref_channel}, interval consistency {consistency:.4%}, k seen {len(seen_k[c])}")
    # merge into the reference frame
    flo, fhi = ref_lo.copy(), ref_hi.copy()
    for c, (ox, oy) in offsets.items():
        if c == ref_channel:
            continue
        clo = np.roll(np.roll(lo[c].reshape(MH, MW), oy, 0), ox, 1)
        chi = np.roll(np.roll(hi[c].reshape(MH, MW), oy, 0), ox, 1)
        flo, fhi = np.maximum(flo, clo), np.minimum(fhi, chi)
    bad = flo > fhi
    exact = flo == fhi
    report.append(f"cells exact: {exact.mean():.4%}, undetermined: {(~exact & ~bad).mean():.4%}, contradictory: {bad.mean():.4%}")
    all_k = sorted(set().union(*seen_k.values()))
    missing = [k for k in range(1, 255) if k not in all_k]
    report.append(f"k values observed: {len(all_k)}; missing: {missing[:40]}{' ...' if len(missing) > 40 else ''}")
    thr = flo.copy()
    if prior is not None:  # fill undetermined cells with the prior estimate, clamped into the known interval
        pox, poy = prior.offsets[ref_channel]                    # prior expressed in the reference frame
        pr = np.roll(np.roll(prior.thr.astype(np.int32), -poy, 0), -pox, 1)
        thr = np.where(exact, flo, np.clip(pr, flo, np.maximum(flo, fhi)))
    thr = np.clip(thr, 0, 254).astype(np.uint8)
    # express offsets in the generator's convention: threshold[(y + oy) % H, (x + ox) % W] for job-local x, y
    screen = Screen(thr, {c: (ox % MW, oy % MH) for c, (ox, oy) in offsets.items()})
    return screen, "\n".join(report)
