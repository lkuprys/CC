"""Compare two PRN files channel by channel."""
from __future__ import annotations

import numpy as np

from .prn_format import CHANNELS, read_prn, unpack_levels


def compare_prn(path_a: str, path_b: str, block: int = 48, strip: int = 1024) -> str:
    ha, ra = read_prn(path_a, unpack=False)
    hb, rb = read_prn(path_b, unpack=False)
    lines = [f"A: {ha}", f"B: {hb}"]
    if (ha.width, ha.height, ha.channels) != (hb.width, hb.height, hb.channels):
        lines.append("DIFFERENT GEOMETRY - comparing the overlapping area")
    W, H, C = min(ha.width, hb.width), min(ha.height, hb.height), min(ha.channels, hb.channels)
    eq = np.zeros(C); nz = np.zeros(C); eq_nz = np.zeros(C); sa = np.zeros(C); sb = np.zeros(C)
    tone_err = [[] for _ in range(C)]
    for y in range(0, H, strip):
        a = unpack_levels(np.asarray(ra[y:y + strip, :C]), ha.width)[..., :W].astype(np.int16)
        b = unpack_levels(np.asarray(rb[y:y + strip, :C]), hb.width)[..., :W].astype(np.int16)
        n = a.shape[0]
        for c in range(C):
            ac, bc = a[:, c], b[:, c]
            same = ac == bc; anyink = (ac > 0) | (bc > 0)
            eq[c] += same.sum(); nz[c] += anyink.sum(); eq_nz[c] += (same & anyink).sum()
            sa[c] += ac.sum(); sb[c] += bc.sum()
            nb = n // block
            if nb:
                wb = W // block
                ta = ac[:nb * block, :wb * block].reshape(nb, block, wb, block).mean((1, 3))
                tb = bc[:nb * block, :wb * block].reshape(nb, block, wb, block).mean((1, 3))
                tone_err[c].append((ta - tb).ravel())
    total = W * H
    lines.append(f"{'ch':4s} {'identical px':>13s} {'identical where ink':>20s} {'mean lvl A':>11s} {'mean lvl B':>11s} {'block tone |err| p50/p99/max':>30s}")
    for c in range(C):
        te = np.abs(np.concatenate(tone_err[c])) if tone_err[c] else np.zeros(1)
        lines.append(f"{CHANNELS[c]:4s} {eq[c] / total:13.4%} {eq_nz[c] / max(nz[c], 1):20.4%} {sa[c] / total:11.4f} {sb[c] / total:11.4f}"
                     f"   {np.percentile(te, 50):.4f}/{np.percentile(te, 99):.4f}/{te.max():.4f}")
    return "\n".join(lines)
