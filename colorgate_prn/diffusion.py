"""Multi-level error diffusion ("Error Diffusion" / "Smooth" raster in ColorGate).

Fitted on ColorGate's own output (uniform white area of the calibration chart, Flora XTRA2512UV):
* Floyd-Steinberg weights 7/16, 3/16, 5/16, 1/16, threshold 0.5 between drop levels, error starts at 0
  at the job's top-left corner: the first dot row appears exactly where ColorGate's does
  (Lc row 16, Lm row 21, K row 25 for white) with the same 5 px dot spacing;
* serpentine scan (even rows left to right) matches ColorGate's later rows best.
Dot positions still differ near the job edges and after the first rows (ColorGate's exact tone values
and edge handling are unknown), so this is an approximation: the average drop level is right.

level = clip(round(t + error), 0, 3) on drop tones t in 0..3 (see color.drop_tone).
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


def _diffuse(t, carry, row0, serpentine):
    """t: (n, w, c) float32; carry: (w + 2, c) float64 error for the first row; row0: job line of t[0]."""
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
                q = np.floor(v + 0.5)
                if q < 0.0:
                    q = 0.0
                elif q > 3.0:
                    q = 3.0
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

    def __init__(self, serpentine: bool = True):
        if numba is None:
            raise ImportError("error diffusion needs numba: pip install --user numba")
        self.serpentine = serpentine

    def new_state(self):
        return {"row": 0, "carry": None}

    def apply_all(self, t: np.ndarray, state: dict) -> np.ndarray:
        """t: (n, w, C) drop tones for consecutive job lines (all channels) -> (n, w, C) uint8 levels."""
        n, w, c = t.shape
        carry = state["carry"]
        if carry is None or carry.shape != (w + 2, c):
            carry = np.zeros((w + 2, c), np.float64)
        out, state["carry"] = _diffuse(np.ascontiguousarray(t, np.float32), carry, state["row"], self.serpentine)
        state["row"] += n
        return out
