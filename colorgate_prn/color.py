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
        self.xform_rgb = None
        if setup.rgb_input_profile:
            self.xform_rgb = ImageCms.buildTransform(setup.rgb_input_profile, setup.output_profile, "RGB", "CMYK",
                                                     renderingIntent=setup.rgb_intent, flags=flags)
        # everything after the ICC step is per channel -> precompute 8 bit device value -> ink tone LUTs
        self.lut = self._ink_curves(np.arange(256) / 255.0)
        # fine float version (device value -> drop tone), used with measured RGB LUTs
        self.fine_x = np.linspace(0, 1, 4097)
        self.fine = {k: drop_tone(v, setup.droplet) for k, v in self._ink_curves(self.fine_x).items()}
        self.rgb_interp = None
        if setup.rgb_lut:
            g = np.array(setup.rgb_lut["grid"], float)
            if "residual" in setup.rgb_lut:    # ICC shape + measured residual (+ dark grey axis correction)
                lut = setup.rgb_lut
                res = np.stack([np.array(lut["residual"][c], np.float32) for c in "CMYK"], -1)
                self._base_xf = self._rgb_xform(lut["base_intent"], lut.get("base_bpc", False))
                gc = lut.get("grey_corr")

                def interp(rgb, res=res, gc=gc):
                    dev = self.icc_device_rgb(rgb) + tetrahedral(g, res, rgb)
                    if gc:
                        dev += grey_axis_correction(rgb, gc)
                    return self.device_to_tones(np.clip(dev, 0, 1))
                self.rgb_interp = interp
            elif "device" in setup.rgb_lut:    # measured device CMYK: interpolate before the C/M ink split
                vals = np.stack([np.array(setup.rgb_lut["device"][c], np.float32) for c in "CMYK"], -1)
                self.rgb_interp = lambda x: self.device_to_tones(tetrahedral(g, vals, x))
            else:
                vals = np.stack([np.array(setup.rgb_lut["tones"][ink], np.float32) for ink in INKS], -1)
                self.rgb_interp = lambda x: tetrahedral(g, vals, x)

    def _rgb_xform(self, intent: int, bpc: bool):
        flags = ImageCms.Flags.BLACKPOINTCOMPENSATION if bpc else ImageCms.Flags.NONE
        return ImageCms.buildTransform(self.s.rgb_input_profile, self.s.output_profile, "RGB", "CMYK",
                                       renderingIntent=intent, flags=flags)

    def icc_device_rgb(self, rgb: np.ndarray, xform=None) -> np.ndarray:
        """(N, 3) RGB 0..255 -> (N, 4) device CMYK 0..1 through LittleCMS (base shape of the measured model)."""
        xf = xform or self._base_xf
        u = np.clip(np.rint(rgb), 0, 255).astype(np.uint8).reshape(1, -1, 3)
        out = np.asarray(ImageCms.applyTransform(Image.fromarray(u, "RGB"), xf)).reshape(-1, 4)
        return out.astype(np.float32) / 255.0

    def _ink_curves(self, dev: np.ndarray) -> dict:
        s, out = self.s, {}
        for ch in "CMYK":
            v = _curve(s.transfer[ch], dev) if ch in s.transfer else dev
            v = _curve(s.lin2[ch], v)
            if ch in ("C", "M"):
                dark = np.interp(v, *s.split[f"{ch}_dark"].T)
                light = np.interp(v, *s.split[f"{ch}_light"].T)
                out[ch] = _curve(s.lin1[ch], dark)
                out["L" + ch.lower()] = _curve(s.lin1["L" + ch.lower()], light)
            else:
                out[ch] = _curve(s.lin1[ch], v)
        return out

    _SRC = {"C": 0, "M": 1, "Y": 2, "K": 3, "Lc": 0, "Lm": 1}

    def device_to_tones(self, dev: np.ndarray) -> np.ndarray:
        """(N, 4) float device CMYK 0..1 -> (N, 6) drop tones (INKS order)."""
        return np.stack([np.interp(dev[:, self._SRC[ink]], self.fine_x, self.fine[ink]) for ink in INKS], -1).astype(np.float32)

    def tones_to_device(self, tones: np.ndarray) -> np.ndarray:
        """Inverse of device_to_tones for measured tones (N, 6): least squares over the device value per channel."""
        out = np.empty((len(tones), 4))
        for c, inks in (("C", ("C", "Lc")), ("M", ("M", "Lm")), ("Y", ("Y",)), ("K", ("K",))):
            err = sum((tones[:, INKS.index(i)][:, None] - self.fine[i][None, :]) ** 2 for i in inks)
            out[:, "CMYK".index(c)] = self.fine_x[np.argmin(err, axis=1)]
        return out

    def device_cmyk(self, cmyk: np.ndarray) -> np.ndarray:
        """(H, W, 4) uint8 -> (H, W, 4) uint8 device CMYK via ICC (LittleCMS)."""
        h, w, _ = cmyk.shape
        img = Image.frombytes("CMYK", (w, h), np.ascontiguousarray(cmyk, np.uint8).tobytes())
        out = ImageCms.applyTransform(img, self.xform)
        return np.frombuffer(out.tobytes(), np.uint8).reshape(h, w, 4)

    def inks(self, cmyk: np.ndarray) -> np.ndarray:
        """(H, W, 4) uint8 input CMYK -> (H, W, 6) float32 ink tones 0..1 in INKS order."""
        return self._dev_to_inks(self.device_cmyk(cmyk))

    def _dev_to_inks(self, dev: np.ndarray) -> np.ndarray:
        out = np.empty(dev.shape[:2] + (6,), np.float32)
        src = {"C": 0, "M": 1, "Y": 2, "K": 3, "Lc": 0, "Lm": 1}
        for i, ink in enumerate(INKS):
            out[..., i] = self.lut[ink].astype(np.float32)[dev[..., src[ink]]]
        return out

    def drop_tones(self, px: np.ndarray, space: str) -> np.ndarray:
        """Resampled job pixels (H, W, 3|4) float 0..255 -> (H, W, 6) drop tones 0..3 (INKS order).

        RGB with a measured chart LUT: tones are interpolated directly from ColorGate's own output.
        Otherwise ICC (LittleCMS) + curves; the bundle's tone_correction (estimated) is applied on top.
        """
        u8 = np.rint(px).astype(np.uint8)
        if space == "RGB" and self.rgb_interp is not None:
            h, w, _ = px.shape
            key = (u8[..., 0].astype(np.int32) << 16) | (u8[..., 1].astype(np.int32) << 8) | u8[..., 2]
            uniq, inv = np.unique(key.ravel(), return_inverse=True)       # colour per unique 8-bit RGB only
            rgb = np.stack([uniq >> 16, (uniq >> 8) & 255, uniq & 255], -1).astype(np.float64)
            return self.rgb_interp(rgb)[inv].reshape(h, w, 6)
        if space == "RGB":
            h, w, _ = u8.shape
            img = Image.frombytes("RGB", (w, h), np.ascontiguousarray(u8).tobytes())
            dev = np.frombuffer(ImageCms.applyTransform(img, self.xform_rgb).tobytes(), np.uint8).reshape(h, w, 4)
            inks = self._dev_to_inks(dev)
        else:
            inks = self.inks(u8)
        t = drop_tone(inks, self.s.droplet).astype(np.float32)
        for i, ink in enumerate(INKS):
            if ink in self.s.tone_correction:
                a, b = self.s.tone_correction[ink]
                t[..., i] = np.clip(a * t[..., i] + b, 0, 3)
        return t


def grey_axis_correction(rgb: np.ndarray, gc: dict) -> np.ndarray:
    """Device CMYK correction measured on the 256-step grey ramp, for dark near-neutral colours only.

    The 13-level grid is coarse in the shadows (0, 32, 64) where K rises steeply; the grey ramp is not.
    Weight: exp(-(chroma / sigma)^2), faded out between fade[0] and fade[1] of the grey level.
    """
    l = rgb.mean(1)
    corr = np.array(gc["corr"], np.float32)
    c = np.stack([np.interp(l, gc["level"], corr[:, k]) for k in range(4)], -1)
    chroma = rgb.max(1) - rgb.min(1)
    f0, f1 = gc["fade"]
    w = np.exp(-(chroma / gc["sigma"]) ** 2) * np.clip((f1 - l) / (f1 - f0), 0, 1)
    return (w[:, None] * c).astype(np.float32)


def tetrahedral(grid: np.ndarray, vals: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Tetrahedral interpolation in a 3D LUT with the same (non-uniform) grid on every axis.

    grid: (g,) ascending; vals: (g, g, g, k); x: (N, 3) -> (N, k).
    """
    g = len(grid)
    x = np.clip(x, grid[0], grid[-1])
    i = np.clip(np.searchsorted(grid, x, side="right") - 1, 0, g - 2)
    f = (x - grid[i]) / (grid[i + 1] - grid[i])
    # sort the three fractions: the tetrahedron walks from corner 000 along the axes in decreasing order
    order = np.argsort(-f, axis=1, kind="stable")                       # (N, 3) axis indices
    fs = np.take_along_axis(f, order, 1)                                 # descending fractions
    flat = vals.reshape(-1, vals.shape[-1])
    strides = np.array([g * g, g, 1])
    idx = (i * strides).sum(1)
    out = flat[idx] * (1 - fs[:, 0:1])
    step = np.zeros(len(x), np.int64)
    w_next = np.concatenate([fs[:, :1] - fs[:, 1:2], fs[:, 1:2] - fs[:, 2:3], fs[:, 2:3]], 1)
    for k in range(3):
        step += strides[order[:, k]]
        out += flat[idx + step] * w_next[:, k:k + 1]
    return out.astype(np.float32)


def drop_tone(x: np.ndarray, droplet=(0.33, 0.66)) -> np.ndarray:
    """Ink tone 0..1 -> drop tone t in 0..3: band = drop level reached by every pixel, frac = coverage of next level."""
    b1, b2 = droplet
    return np.where(x <= b1, x / b1, np.where(x <= b2, 1 + (x - b1) / (b2 - b1), 2 + (x - b2) / (1 - b2)))
