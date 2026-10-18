"""Resampling as done by ColorGate (fitted on edge profiles of the sample job).

* Target size is rounded up to whole device pixels: out_w = ceil(in_w * xdpi / in_dpi),
  out_h = ceil(in_h * ydpi / in_dpi)  (3661 px @300dpi -> 8787 px @720dpi), scale = out/in exactly.
* Separable Mitchell-Netravali cubic (B = C = 1/3), centre aligned:
  src = (dst + 0.5) * in/out - 0.5, edge pixels replicated, result clipped to the input range.
"""
from __future__ import annotations

import numpy as np


def mitchell(x: np.ndarray, B: float = 1 / 3, C: float = 1 / 3) -> np.ndarray:
    x = np.abs(x)
    out = np.zeros_like(x)
    m1 = x < 1
    m2 = (x >= 1) & (x < 2)
    x1, x2 = x[m1], x[m2]
    out[m1] = ((12 - 9 * B - 6 * C) * x1**3 + (-18 + 12 * B + 6 * C) * x1**2 + (6 - 2 * B)) / 6
    out[m2] = ((-B - 6 * C) * x2**3 + (6 * B + 30 * C) * x2**2 + (-12 * B - 48 * C) * x2 + (8 * B + 24 * C)) / 6
    return out


def output_size(n_in: int, dpi_in: float, dpi_out: float) -> int:
    """ColorGate rounds the device size up: 3661 px @300 -> 8786.4 -> 8787 px @720."""
    return int(np.ceil(n_in * dpi_out / dpi_in - 1e-6))


def taps(n_in: int, n_out: int):
    """(idx, w) arrays of shape (n_out, 4): out[j] = sum_k w[j,k] * in[idx[j,k]]."""
    src = (np.arange(n_out) + 0.5) * (n_in / n_out) - 0.5
    i0 = np.floor(src).astype(np.int64)
    idx = i0[:, None] + np.arange(-1, 3)[None, :]
    w = mitchell(src[:, None] - idx)
    w /= w.sum(1, keepdims=True)
    return np.clip(idx, 0, n_in - 1), w.astype(np.float32)


class Resampler:
    """Upsamples an (H, W, C) image; x pass done once, y pass streamed in strips of output lines."""

    def __init__(self, img: np.ndarray, out_w: int, out_h: int, lo: float = 0.0, hi: float = 255.0):
        img = img.astype(np.float32)
        if img.ndim == 2:
            img = img[..., None]
        self.in_h, in_w, _ = img.shape
        self.out_w, self.out_h, self.lo, self.hi = out_w, out_h, lo, hi
        ix, wx = taps(in_w, out_w)
        self.xpass = np.empty((self.in_h, out_w, img.shape[2]), np.float32)
        for r in range(0, self.in_h, 256):  # chunked to keep the (rows, out_w, 4, C) gather small
            self.xpass[r:r + 256] = np.einsum("hjkc,jk->hjc", img[r:r + 256][:, ix, :], wx, optimize=True)
        self.iy, self.wy = taps(self.in_h, out_h)

    def lines(self, y0: int, y1: int) -> np.ndarray:
        """Output lines y0..y1-1 as (n, out_w, C) float32, clipped to [lo, hi]."""
        rows = self.xpass[self.iy[y0:y1]]  # (n, 4, out_w, C)
        out = np.einsum("nkwc,nk->nwc", rows, self.wy[y0:y1], optimize=True)
        return np.clip(out, self.lo, self.hi)
