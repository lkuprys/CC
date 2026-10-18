"""ColorGate "Speed Screen" stochastic multi-level screening.

One 8-bit threshold matrix (256 x 448 for SpeedScreen_256x448px) shared by all channels; every channel
reads it with its own (x, y) offset, and the matrix is anchored to each job's own top-left corner.

For a drop tone t in 0..3 (see color.drop_tone):  band = floor(t), k = round(frac(t) * 255)
    level = band + (k > threshold[(y + oy) % H, (x + ox) % W])
so small drops fill to 100 % before medium drops appear, medium before large.
"""
from __future__ import annotations

import json
import os

import numpy as np

DATA = os.path.join(os.path.dirname(__file__), "data")


class Screen:
    def __init__(self, thresholds: np.ndarray, offsets: dict):
        self.thr = np.asarray(thresholds, np.uint8)       # (H, W), values 0..254
        self.h, self.w = self.thr.shape
        self.offsets = offsets                             # channel name -> (ox, oy)

    @classmethod
    def load(cls, name: str = "SpeedScreen_256x448px", folder: str = DATA) -> "Screen":
        thr = np.load(os.path.join(folder, name + ".npy"))
        with open(os.path.join(folder, name + ".json")) as f:
            meta = json.load(f)
        return cls(thr, {k: tuple(v) for k, v in meta["offsets"].items()})

    def save(self, name: str, folder: str = DATA, note: str = "") -> None:
        os.makedirs(folder, exist_ok=True)
        np.save(os.path.join(folder, name + ".npy"), self.thr)
        with open(os.path.join(folder, name + ".json"), "w") as f:
            json.dump({"offsets": {k: list(v) for k, v in self.offsets.items()}, "note": note}, f, indent=1)

    def apply(self, t: np.ndarray, channel: str, x0: int, y0: int) -> np.ndarray:
        """t: (lines, width) drop tones 0..3 for job-local columns x0.. and lines y0..  -> uint8 levels 0..3."""
        ox, oy = self.offsets[channel]
        n, w = t.shape
        rows = (np.arange(y0, y0 + n) + oy) % self.h
        cols = (np.arange(x0, x0 + w) + ox) % self.w
        thr = self.thr[rows][:, cols]
        t = np.clip(t, 0, 3)
        band = np.floor(t)
        k = np.rint((t - band) * 255)
        lvl = band + (k > thr)
        return np.minimum(lvl, 3).astype(np.uint8)
