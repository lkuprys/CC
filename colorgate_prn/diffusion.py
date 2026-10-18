"""Multi-level error diffusion ("Error Diffusion" / "Smooth" raster in ColorGate).

Fitted on ColorGate's own output (uniform white area of the calibration chart, Flora XTRA2512UV):
* Floyd-Steinberg weights 7/16, 3/16, 5/16, 1/16, threshold 0.5 between drop levels, error starts at 0
  at the job's top-left corner: the first dot row appears exactly where ColorGate's does
  (Lc row 16, Lm row 21, K row 25 for white) with the same 5 px dot spacing;
* serpentine scan (even rows left to right) matches ColorGate's later rows best.
Dot positions still differ near the job edges and after the first rows (ColorGate's exact tone values
and edge handling are unknown), so this is an approximation: the average drop level is right.

level = nearest allowed level to (t + error) on drop tones t in 0..3 (see color.drop_tone).
Default allowed levels 0, 1, 2, 3 = ColorGate.  "High gap" mode (print head far from the media) allows
only 0, 2, 3: no small drops, the same ink volume is laid down with fewer medium/large drops, which fly
straighter and mist less.  The error diffusion keeps the mean level (= ink volume) unchanged.
Tested on safian sleeves at 3-4 mm: ~1.5-2 mm more usable gap.  The very light background tint
(ColorGate's ~1-2 % K/Lc/Lm on white) must be kept; small_below lets it keep its small drops.
One state per job carries the error row between strips (create it with new_state()).
"""
from __future__ import annotations

import sys

import numpy as np

try:
    import numba
except ImportError:  # pragma: no cover
    numba = None

W_RIGHT, W_DL, W_D, W_DR = 7 / 16, 3 / 16, 5 / 16, 1 / 16


def _diffuse(t, carry, row0, serpentine, levels, light_levels, light_below):
    """t: (n, w, c) float32; carry: (w + 2, c) float64 error for the first row; row0: job line of t[0];
    levels: ascending float64 array of allowed drop levels (must contain 0);
    light_levels / light_below: pixels whose tone is below light_below use light_levels instead."""
    n, w, c = t.shape
    out = np.empty((n, w, c), np.uint8)
    cur = carry.copy()
    nxt = np.zeros_like(carry)
    for y in range(n):
        rtl = serpentine and ((row0 + y) % 2 == 1)
        d = -1 if rtl else 1
        for k in range(w):
            x = w - 1 - k if rtl else k
            for ch in range(c):
                v = t[y, x, ch] + cur[x + 1, ch]
                lv = light_levels if t[y, x, ch] < light_below else levels
                q = lv[0]
                for j in range(1, lv.shape[0]):   # nearest allowed level (ties go up, like round())
                    if v >= (lv[j - 1] + lv[j]) * 0.5:
                        q = lv[j]
                out[y, x, ch] = np.uint8(q)
                e = v - q
                cur[x + 1 + d, ch] += e * W_RIGHT
                nxt[x + 1 - d, ch] += e * W_DL
                nxt[x + 1, ch] += e * W_D
                nxt[x + 1 + d, ch] += e * W_DR
        cur = nxt
        nxt = np.zeros_like(carry)
    return out, cur


if numba is not None:
    # PyInstaller programoje .py šaltinio nėra, todėl numba talpyklos (cache) naudoti negalima
    _diffuse = numba.njit(cache=not getattr(sys, "frozen", False))(_diffuse)


class ErrorDiffusion:
    levels = 3

    def __init__(self, serpentine: bool = True, allowed_levels=(0, 1, 2, 3), floor: float = 0.0,
                 small_below: float = 0.0):
        """allowed_levels: drop levels that may be printed (0 must be included).
        floor: drop tones below this (level units) are set to 0; 0 = keep everything (ColorGate).
            Careful: the ~0.01-0.02 ink ColorGate lays on white is the profile's light background tint.
        small_below: pixels with a tone below this may still use small drops (all levels 0..3), e.g. 0.05
            keeps that light tint exactly as ColorGate prints it while the rest uses allowed_levels."""
        if numba is None:
            raise ImportError("error diffusion needs numba: pip install --user numba")
        self.serpentine = serpentine
        self.allowed = np.array(sorted(set(allowed_levels)), np.float64)
        if self.allowed[0] != 0:
            raise ValueError("allowed_levels must contain 0")
        self.floor = floor
        self.small_below = small_below

    def new_state(self):
        return {"row": 0, "carry": None}

    def apply_all(self, t: np.ndarray, state: dict) -> np.ndarray:
        """t: (n, w, C) drop tones for consecutive job lines (all channels) -> (n, w, C) uint8 levels."""
        n, w, c = t.shape
        carry = state["carry"]
        if carry is None or carry.shape != (w + 2, c):
            carry = np.zeros((w + 2, c), np.float64)
        t = np.ascontiguousarray(t, np.float32)
        if self.floor > 0:
            t = np.where(t < self.floor, np.float32(0), t)
        out, state["carry"] = _diffuse(t, carry, state["row"], self.serpentine, self.allowed,
                                       np.array([0.0, 1.0, 2.0, 3.0]), float(self.small_below))
        state["row"] += n
        return out
