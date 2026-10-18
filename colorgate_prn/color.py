"""CMYK -> ink tones (C, M, Y, K, Lc, Lm) as done by ColorGate, see cgsetup.py for the pipeline."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageCms

from .cgsetup import ColorGateSetup

INKS = ("C", "M", "Y", "K", "Lc", "Lm")


def _curve(table: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.interp(x, np.linspace(0, 1, len(table)), table)


class ColorPipeline:
    def __init__(self, setup: ColorGateSetup):
        self.s = setup
        flags = ImageCms.Flags.BLACKPOINTCOMPENSATION if setup.bpc else ImageCms.Flags.NONE
        self.xform = ImageCms.buildTransform(setup.input_profile, setup.output_profile, "CMYK", "CMYK",
                                             renderingIntent=setup.intent, flags=flags)
        # everything after the ICC step is per channel -> precompute 8 bit device value -> ink tone LUTs
        dev = np.arange(256) / 255.0
        self.lut = {}
        for ch in "CMYK":
            v = _curve(setup.transfer[ch], dev) if ch in setup.transfer else dev
            v = _curve(setup.lin2[ch], v)
            if ch in ("C", "M"):
                dark = np.interp(v, *setup.split[f"{ch}_dark"].T)
                light = np.interp(v, *setup.split[f"{ch}_light"].T)
                self.lut[ch] = _curve(setup.lin1[ch], dark)
                self.lut["L" + ch.lower()] = _curve(setup.lin1["L" + ch.lower()], light)
            else:
                self.lut[ch] = _curve(setup.lin1[ch], v)

    def device_cmyk(self, cmyk: np.ndarray) -> np.ndarray:
        """(H, W, 4) uint8 -> (H, W, 4) uint8 device CMYK via ICC (LittleCMS)."""
        h, w, _ = cmyk.shape
        img = Image.frombytes("CMYK", (w, h), np.ascontiguousarray(cmyk, np.uint8).tobytes())
        out = ImageCms.applyTransform(img, self.xform)
        return np.frombuffer(out.tobytes(), np.uint8).reshape(h, w, 4)

    def inks(self, cmyk: np.ndarray) -> np.ndarray:
        """(H, W, 4) uint8 input CMYK -> (H, W, 6) float32 ink tones 0..1 in INKS order."""
        dev = self.device_cmyk(cmyk)
        out = np.empty(dev.shape[:2] + (6,), np.float32)
        src = {"C": 0, "M": 1, "Y": 2, "K": 3, "Lc": 0, "Lm": 1}
        for i, ink in enumerate(INKS):
            out[..., i] = self.lut[ink].astype(np.float32)[dev[..., src[ink]]]
        return out


def drop_tone(x: np.ndarray, droplet=(0.33, 0.66)) -> np.ndarray:
    """Ink tone 0..1 -> drop tone t in 0..3: band = drop level reached by every pixel, frac = coverage of next level."""
    b1, b2 = droplet
    return np.where(x <= b1, x / b1, np.where(x <= b2, 1 + (x - b1) / (b2 - b1), 2 + (x - b2) / (1 - b2)))
