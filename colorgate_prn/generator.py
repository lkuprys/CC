"""TIF jobs -> PRN (+ BMP thumbnail), reproducing ColorGate Productionserver output for the GUNSJET 2513."""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import tifffile
from PIL import Image

from .cgsetup import ColorGateSetup
from .color import INKS, ColorPipeline, drop_tone
from .prn_format import CHANNELS, PrnWriter
from .resample import Resampler, output_size
from .screening import Screen


@dataclass
class Job:
    tif: str
    x: int = 0  # position of the job's top-left corner on the page, device pixels
    y: int = 0

    @classmethod
    def mm(cls, tif: str, x_mm: float, y_mm: float, xdpi: int = 720, ydpi: int = 1200) -> "Job":
        """Position given in millimetres from the page's top-left corner."""
        return cls(tif, int(round(x_mm / 25.4 * xdpi)), int(round(y_mm / 25.4 * ydpi)))


def job_size(tif: str, setup: ColorGateSetup) -> tuple:
    """Device-pixel size (w, h) a TIF will occupy on the page."""
    w, h, dpi = read_tif_header(tif)
    return output_size(w, dpi, setup.xdpi), output_size(h, dpi, setup.ydpi)


def side_by_side(tifs, setup: ColorGateSetup, gap_px: int = 1195, x0: int = 0, y0: int = 0) -> list:
    """Place jobs left to right with a fixed gap (default 1195 px = 42.2 mm, as in the ColorGate sample)."""
    jobs, x = [], x0
    for t in tifs:
        jobs.append(Job(t, x, y0))
        x += job_size(t, setup)[0] + gap_px
    return jobs


def load_layout(path: str, setup: ColorGateSetup) -> tuple:
    """Layout JSON -> (jobs, page_width, page_height).

    {
      "units": "px" | "mm",                 (default px)
      "page_width": 18769, "page_height": 10392,   (optional, same units; default = fit jobs)
      "jobs": [ {"tif": "a.tif", "x": 0, "y": 0}, {"tif": "b.tif", "x": 9982, "y": 0} ]
    }
    Relative tif paths are resolved against the JSON's folder.
    """
    import json
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    base = os.path.dirname(os.path.abspath(path))
    mm = d.get("units", "px") == "mm"
    cx = (lambda v: int(round(v / 25.4 * setup.xdpi))) if mm else int
    cy = (lambda v: int(round(v / 25.4 * setup.ydpi))) if mm else int
    jobs = [Job(os.path.join(base, j["tif"]), cx(j.get("x", 0)), cy(j.get("y", 0))) for j in d["jobs"]]
    pw = cx(d["page_width"]) if "page_width" in d else None
    ph = cy(d["page_height"]) if "page_height" in d else None
    return jobs, pw, ph


def read_tif_header(path: str):
    """(width, height, dpi) without decoding pixels."""
    with tifffile.TiffFile(path) as tf:
        page = tf.pages[0]
        tags = page.tags
        res = tags["XResolution"].value if "XResolution" in tags else (300, 1)
        dpi = res[0] / res[1] if res[1] else 300.0
        if dpi < 1:
            dpi = res[1] / res[0]
        if "ResolutionUnit" in tags and int(tags["ResolutionUnit"].value) == 3:
            dpi *= 2.54
        return page.shape[1], page.shape[0], dpi


def read_tif(path: str):
    """-> (cmyk uint8 (H, W, 4), spot dict name -> uint8 (H, W), dpi)."""
    with tifffile.TiffFile(path) as tf:
        page = tf.pages[0]
        data = page.asarray()
        tags = page.tags
        names = []
        if "InkNames" in tags:
            names = [n for n in str(tags["InkNames"].value).split("\x00") if n]
        res = tags["XResolution"].value if "XResolution" in tags else (300, 1)
        dpi = res[0] / res[1] if res[1] else 300.0
        if dpi < 1:  # tifffile writes (1, 300) for 300 dpi; ColorGate reads it as 300
            dpi = res[1] / res[0]
        unit = tags["ResolutionUnit"].value if "ResolutionUnit" in tags else 2
        if int(unit) == 3:
            dpi *= 2.54
    if data.dtype == np.uint16:
        data = (data >> 8).astype(np.uint8)  # ColorGate: DITHER16TO8 = false
    if data.ndim == 2:
        data = data[..., None]
    spots = {}
    for i in range(4, data.shape[2]):
        name = names[i] if i < len(names) else f"spot{i - 4}"
        spots[name] = data[..., i]
    return np.ascontiguousarray(data[..., :4]), spots, dpi


class JobRaster:
    """Per-job ink tones resampled to device resolution, delivered line strips on demand."""

    def __init__(self, job: Job, setup: ColorGateSetup, pipe: ColorPipeline, order: str = "resample_then_separate"):
        self.job, self.s, self.pipe, self.order = job, setup, pipe, order
        cmyk, spots, dpi = read_tif(job.tif)
        h, w, _ = cmyk.shape
        self.w = output_size(w, dpi, setup.xdpi)
        self.h = output_size(h, dpi, setup.ydpi)
        white = next((spots[n] for n in setup.white_spot_names if n in spots), None)
        if order == "separate_then_resample":
            amount_w = None if white is None else (1.0 - white.astype(np.float32) / 255.0)
            planes = pipe.inks(cmyk)                                 # (h, w, 6) 0..1
            if amount_w is not None:
                planes = np.concatenate([planes, amount_w[..., None]], axis=2)
            self.rs = Resampler(planes, self.w, self.h, 0.0, 1.0)
        else:  # resample CMYK (and W) first, colour per device pixel
            planes = cmyk  # uint8; the resampler converts per chunk
            if white is not None:
                planes = np.concatenate([planes, (255 - white)[..., None]], axis=2)
            self.rs = Resampler(planes, self.w, self.h, 0.0, 255.0)
        self.has_white = white is not None

    def tones(self, y0: int, y1: int) -> dict:
        """Drop tones (0..3) for job lines y0..y1-1, dict channel -> (n, w)."""
        p = self.rs.lines(y0, y1)
        if self.order != "separate_then_resample":
            cm = np.rint(p[..., :4]).astype(np.uint8)
            inks = self.pipe.inks(cm)
            w = p[..., 4] / 255.0 if self.has_white else None
        else:
            inks = p[..., :6]
            w = p[..., 6] if self.has_white else None
        out = {ink: drop_tone(inks[..., i], self.s.droplet) for i, ink in enumerate(INKS)}
        out["W"] = drop_tone(w, self.s.droplet) if w is not None else np.zeros(inks.shape[:2], np.float32)
        return out


def generate_prn(jobs, out_path: str, setup: ColorGateSetup, screen: Screen | None = None,
                 page_width: int | None = None, page_height: int | None = None,
                 bmp_path: str | None = "auto", strip: int = 448, order: str = "resample_then_separate",
                 progress=None) -> dict:
    """Render jobs onto one page and write PRN (+ BMP thumbnail next to it when bmp_path == 'auto')."""
    screen = screen or Screen.load(setup.screen)
    pipe = ColorPipeline(setup)
    # Job sizes come from the TIF headers; rasters (decoded TIF + resampler) exist only while
    # the strips cross the job, so memory does not grow with the number of jobs on the table.
    sizes = [job_size(j.tif, setup) for j in jobs]
    W = page_width or max(j.x + w for j, (w, h) in zip(jobs, sizes))
    H = page_height or max(j.y + h for j, (w, h) in zip(jobs, sizes))
    live = {}
    thumb_w = 500
    thumb_h = max(1, int(round(thumb_w * (H / setup.ydpi) / (W / setup.xdpi))))
    thumb = np.zeros((thumb_h, thumb_w, 3), np.float64); thumb_n = np.zeros((thumb_h, 1), np.float64)
    with PrnWriter(out_path, W, H, len(CHANNELS), setup.xdpi, setup.ydpi) as wr:
        for y0 in range(0, H, strip):
            y1 = min(H, y0 + strip)
            block = np.zeros((y1 - y0, len(CHANNELS), W), np.uint8)
            for k, (job, (jw, jh)) in enumerate(zip(jobs, sizes)):
                if y0 >= job.y + jh:
                    live.pop(k, None)
                    continue
                if y1 <= job.y:
                    continue
                if k not in live:
                    live[k] = JobRaster(job, setup, pipe, order)
                r = live[k]
                jy0, jy1 = max(y0, r.job.y), min(y1, r.job.y + r.h)
                if jy0 >= jy1:
                    continue
                tones = r.tones(jy0 - r.job.y, jy1 - r.job.y)
                xa, xb = max(0, r.job.x), min(W, r.job.x + r.w)
                for ci, ch in enumerate(CHANNELS):
                    lv = screen.apply(tones[ch][:, xa - r.job.x:xb - r.job.x], ch, xa - r.job.x, jy0 - r.job.y)
                    block[jy0 - y0:jy1 - y0, ci, xa:xb] = np.maximum(block[jy0 - y0:jy1 - y0, ci, xa:xb], lv)
            wr.write_lines(block)
            _accumulate_thumb(block, thumb, thumb_n, y0, H, W)
            if progress:
                progress(y1, H)
    if bmp_path == "auto":
        bmp_path = os.path.splitext(out_path)[0] + ".bmp"
    if bmp_path:
        rgb = np.where(thumb_n[:, :, None] > 0, thumb / np.maximum(thumb_n[:, :, None], 1), 255)
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)
        Image.fromarray(rgb, "RGB").save(bmp_path, format="BMP")
    return {"width": W, "height": H, "jobs": [(j.tif, j.x, j.y, w, h) for j, (w, h) in zip(jobs, sizes)]}


# rough RGB appearance of each ink at full coverage (for the thumbnail only)
_INK_RGB = {"C": (0, 160, 230), "M": (230, 0, 125), "Y": (255, 235, 0), "K": (20, 20, 20),
            "Lc": (130, 210, 240), "Lm": (240, 140, 190)}


def _accumulate_thumb(block, thumb, thumb_n, y0, H, W):
    th, tw, _ = thumb.shape
    cov = block[:, :6, :].astype(np.float32) / 3.0                       # (n, 6, W)
    xs = (np.arange(W) * tw // W)
    ty = ((y0 + np.arange(block.shape[0])) * th // H)
    for row in np.unique(ty):
        sel = cov[ty == row]                                              # (k, 6, W)
        m = sel.mean(0)                                                   # (6, W)
        col = np.ones((W, 3)) * 255.0
        for i, ink in enumerate(("C", "M", "Y", "K", "Lc", "Lm")):
            a = m[i][:, None]
            col = col * (1 - a) + col * a * (np.array(_INK_RGB[ink]) / 255.0)
        sums = np.zeros((tw, 3)); np.add.at(sums, xs, col)
        cnt = np.bincount(xs, minlength=tw)[:, None]
        thumb[row] += sums / np.maximum(cnt, 1) * len(sel)
        thumb_n[row] += len(sel)
