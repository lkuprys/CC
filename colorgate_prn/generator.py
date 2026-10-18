"""TIF / PNG jobs -> PRN (+ BMP thumbnail), reproducing ColorGate Productionserver output.

Printer specifics come from the bundle (ColorGateSetup): channels, resolution, job size on the media
(dest_mm), rotation, colour chain and screening (threshold screen or error diffusion).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import tifffile
from PIL import Image

from .cgsetup import ColorGateSetup
from .color import INKS, ColorPipeline, drop_tone
from .prn_format import PrnWriter
from .resample import Resampler, output_size
from .screening import Screen

IMAGE_EXT = (".tif", ".tiff")


@dataclass
class Job:
    tif: str          # image path (TIF or PNG; name kept for compatibility)
    x: int = 0        # position of the job's top-left corner on the page, device pixels
    y: int = 0

    @classmethod
    def mm(cls, tif: str, x_mm: float, y_mm: float, xdpi: int = 720, ydpi: int = 1200) -> "Job":
        """Position given in millimetres from the page's top-left corner."""
        return cls(tif, int(round(x_mm / 25.4 * xdpi)), int(round(y_mm / 25.4 * ydpi)))


def mm_to_px(mm: float, dpi: float) -> int:
    return int(round(mm / 25.4 * dpi))


def device_size(w: int, h: int, dpi: float, setup: ColorGateSetup) -> tuple:
    """Device-pixel size (w, h) of a job: fixed media size from the hot folder (dest_mm) or image size at its dpi."""
    if setup.dest_mm:
        return mm_to_px(setup.dest_mm[0], setup.xdpi), mm_to_px(setup.dest_mm[1], setup.ydpi)
    return output_size(w, dpi, setup.xdpi), output_size(h, dpi, setup.ydpi)


def job_size(path: str, setup: ColorGateSetup) -> tuple:
    w, h, dpi = read_image_header(path)
    return device_size(w, h, dpi, setup)


def side_by_side(images, setup: ColorGateSetup, gap_px: int = 1195, x0: int = 0, y0: int = 0) -> list:
    """Place jobs left to right with a fixed gap in device pixels."""
    jobs, x = [], x0
    for t in images:
        jobs.append(Job(t, x, y0))
        x += job_size(t, setup)[0] + gap_px
    return jobs


def container_layout(images, setup: ColorGateSetup, gap_mm: float, top_mm: float = 0.0, left_mm: float = 0.0) -> list:
    """ColorGate container ('ORDERED', ContainerJobDistance): x advances by round(job) + round(gap) pixels.

    Flora sample: gap 221.2 mm, top margin 26.5 mm -> jobs at x = 0 and 11939, y = 1878.
    """
    return side_by_side(images, setup, mm_to_px(gap_mm, setup.xdpi),
                        mm_to_px(left_mm, setup.xdpi), mm_to_px(top_mm, setup.ydpi))


def load_layout(path: str, setup: ColorGateSetup) -> tuple:
    """Layout JSON -> (jobs, page_width, page_height).

    {
      "units": "px" | "mm",                 (default px)
      "page_width": 18769, "page_height": 10392,   (optional, same units; default = fit jobs)
      "jobs": [ {"tif": "a.tif", "x": 0, "y": 0}, {"tif": "b.png", "x": 9982, "y": 0} ]
    }
    or a ColorGate-style container (mm):
    {
      "container": {"gap_mm": 221.2, "top_mm": 26.5, "page_width_mm": 850.2},
      "jobs": [ {"image": "a.png"}, {"image": "b.png"} ]
    }
    Relative image paths are resolved against the JSON's folder.
    """
    import json
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    base = os.path.dirname(os.path.abspath(path))
    img = lambda j: os.path.join(base, j.get("image") or j["tif"])
    if "container" in d:
        c = d["container"]
        jobs = container_layout([img(j) for j in d["jobs"]], setup, c.get("gap_mm", 0.0), c.get("top_mm", 0.0),
                                c.get("left_mm", 0.0))
        pw = mm_to_px(c["page_width_mm"], setup.xdpi) if "page_width_mm" in c else None
        ph = mm_to_px(c["page_height_mm"], setup.ydpi) if "page_height_mm" in c else None
        return jobs, pw, ph
    mm = d.get("units", "px") == "mm"
    cx = (lambda v: mm_to_px(v, setup.xdpi)) if mm else int
    cy = (lambda v: mm_to_px(v, setup.ydpi)) if mm else int
    jobs = [Job(img(j), cx(j.get("x", 0)), cy(j.get("y", 0))) for j in d["jobs"]]
    pw = cx(d["page_width"]) if "page_width" in d else None
    ph = cy(d["page_height"]) if "page_height" in d else None
    return jobs, pw, ph


# ---------------------------------------------------------------------------------------------- image input
def _tif_dpi(tags) -> float:
    res = tags["XResolution"].value if "XResolution" in tags else (300, 1)
    dpi = res[0] / res[1] if res[1] else 300.0
    if dpi < 1:  # tifffile writes (1, 300) for 300 dpi; ColorGate reads it as 300
        dpi = res[1] / res[0]
    if "ResolutionUnit" in tags and int(tags["ResolutionUnit"].value) == 3:
        dpi *= 2.54
    return dpi


def read_image_header(path: str):
    """(width, height, dpi) without decoding pixels."""
    if path.lower().endswith(IMAGE_EXT):
        with tifffile.TiffFile(path) as tf:
            page = tf.pages[0]
            return page.shape[1], page.shape[0], _tif_dpi(page.tags)
    with Image.open(path) as im:
        return im.size[0], im.size[1], float(im.info.get("dpi", (72, 72))[0])


def read_tif_header(path: str):
    return read_image_header(path)


def read_tif(path: str):
    """-> (cmyk uint8 (H, W, 4), spot dict name -> uint8 (H, W), dpi)."""
    with tifffile.TiffFile(path) as tf:
        page = tf.pages[0]
        data = page.asarray()
        tags = page.tags
        names = []
        if "InkNames" in tags:
            names = [n for n in str(tags["InkNames"].value).split("\x00") if n]
        dpi = _tif_dpi(tags)
    if data.dtype == np.uint16:
        data = (data >> 8).astype(np.uint8)  # ColorGate: DITHER16TO8 = false
    if data.ndim == 2:
        data = data[..., None]
    spots = {}
    for i in range(4, data.shape[2]):
        name = names[i] if i < len(names) else f"spot{i - 4}"
        spots[name] = data[..., i]
    return np.ascontiguousarray(data[..., :4]), spots, dpi


def read_image(path: str):
    """-> (pixels uint8 (H, W, 3|4), colour space "RGB"|"CMYK", spots, dpi)."""
    if path.lower().endswith(IMAGE_EXT):
        with tifffile.TiffFile(path) as tf:
            photometric = int(tf.pages[0].photometric)
        if photometric == 2:  # RGB TIF
            with Image.open(path) as im:
                dpi = float(im.info.get("dpi", (300, 300))[0])
                return np.asarray(im.convert("RGB")), "RGB", {}, dpi
        cmyk, spots, dpi = read_tif(path)
        return cmyk, "CMYK", spots, dpi
    with Image.open(path) as im:
        dpi = float(im.info.get("dpi", (72, 72))[0])
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))   # transparency over white media
            im = Image.alpha_composite(bg, im)
        return np.asarray(im.convert("RGB")), "RGB", {}, dpi


# ---------------------------------------------------------------------------------------------- job raster
class JobRaster:
    """Per-job drop tones at device resolution, delivered in line strips on demand."""

    def __init__(self, job: Job, setup: ColorGateSetup, pipe: ColorPipeline, screen):
        self.job, self.s, self.pipe, self.screen = job, setup, pipe, screen
        px, self.space, spots, dpi = read_image(job.tif)
        h, w = px.shape[:2]
        self.w, self.h = device_size(w, h, dpi, setup)
        white = next((spots[n] for n in setup.white_spot_names if n in spots), None)
        planes = px.astype(np.float32)
        self.has_white = white is not None and "W" in setup.channels
        if self.has_white:
            planes = np.concatenate([planes, (255.0 - white.astype(np.float32))[..., None]], axis=2)
        if setup.rotate == 180:
            planes = planes[::-1, ::-1]
        elif setup.rotate:
            raise NotImplementedError(f"rotation {setup.rotate}")
        self.rs = Resampler(np.ascontiguousarray(planes), self.w, self.h, 0.0, 255.0)
        self.state = screen.new_state()

    def tones(self, y0: int, y1: int) -> np.ndarray:
        """Drop tones (0..3) for job lines y0..y1-1 as (n, w, channels) in setup.channels order."""
        p = self.rs.lines(y0, y1)
        nc = 3 if self.space == "RGB" else 4
        t = self.pipe.drop_tones(p[..., :nc], self.space)
        out = np.zeros(t.shape[:2] + (len(self.s.channels),), np.float32)
        for ci, ch in enumerate(self.s.channels):
            if ch in INKS:
                out[..., ci] = t[..., INKS.index(ch)]
            elif ch == "W" and self.has_white:
                out[..., ci] = drop_tone(p[..., nc] / 255.0, self.s.droplet)
        return out

    def levels(self, y0: int, y1: int) -> np.ndarray:
        """Screened drop levels (n, w, channels) uint8 for job lines y0..y1-1 (call in increasing order)."""
        t = self.tones(y0, y1)
        if hasattr(self.screen, "apply_all"):
            return self.screen.apply_all(t, self.state)
        return np.stack([self.screen.apply(t[..., ci], ch, 0, y0) for ci, ch in enumerate(self.s.channels)], -1)


def make_screen(setup: ColorGateSetup, screen=None):
    if screen is not None:
        return screen
    if setup.screen_type == "error_diffusion":
        from .diffusion import ErrorDiffusion
        return ErrorDiffusion()
    return Screen.load(setup.screen)


def generate_prn(jobs, out_path: str, setup: ColorGateSetup, screen=None,
                 page_width: int | None = None, page_height: int | None = None,
                 bmp_path: str | None = "auto", strip: int = 448, progress=None) -> dict:
    """Render jobs onto one page and write PRN (+ BMP thumbnail next to it when bmp_path == 'auto')."""
    screen = make_screen(setup, screen)
    pipe = ColorPipeline(setup)
    rasters = [JobRaster(j, setup, pipe, screen) for j in jobs]
    W = page_width or max(r.job.x + r.w for r in rasters)
    H = page_height or max(r.job.y + r.h for r in rasters)
    C = len(setup.channels)
    thumb_w = 500
    thumb_h = max(1, int(round(thumb_w * (H / setup.ydpi) / (W / setup.xdpi))))
    thumb = np.zeros((thumb_h, thumb_w, 3), np.float64); thumb_n = np.zeros((thumb_h, 1), np.float64)
    with PrnWriter(out_path, W, H, C, setup.xdpi, setup.ydpi) as wr:
        for y0 in range(0, H, strip):
            y1 = min(H, y0 + strip)
            block = np.zeros((y1 - y0, C, W), np.uint8)
            for r in rasters:
                jy0, jy1 = max(y0, r.job.y), min(y1, r.job.y + r.h)
                if jy0 >= jy1:
                    continue
                lv = r.levels(jy0 - r.job.y, jy1 - r.job.y)           # (n, job w, C), full job width
                xa, xb = max(0, r.job.x), min(W, r.job.x + r.w)
                if xa >= xb:
                    continue
                part = lv[:, xa - r.job.x:xb - r.job.x].transpose(0, 2, 1)
                dst = block[jy0 - y0:jy1 - y0, :, xa:xb]
                np.maximum(dst, part, out=dst)
            wr.write_lines(block)
            _accumulate_thumb(block, thumb, thumb_n, y0, H, W, setup.channels)
            if progress:
                progress(y1, H)
    if bmp_path == "auto":
        bmp_path = os.path.splitext(out_path)[0] + ".bmp"
    if bmp_path:
        rgb = np.where(thumb_n[:, :, None] > 0, thumb / np.maximum(thumb_n[:, :, None], 1), 255)
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)
        Image.fromarray(rgb, "RGB").save(bmp_path, format="BMP")
    return {"width": W, "height": H, "jobs": [(r.job.tif, r.job.x, r.job.y, r.w, r.h) for r in rasters]}


# rough RGB appearance of each ink at full coverage (for the thumbnail only)
_INK_RGB = {"C": (0, 160, 230), "M": (230, 0, 125), "Y": (255, 235, 0), "K": (20, 20, 20),
            "Lc": (130, 210, 240), "Lm": (240, 140, 190)}


def _accumulate_thumb(block, thumb, thumb_n, y0, H, W, channels):
    th, tw, _ = thumb.shape
    inks = [(i, ch) for i, ch in enumerate(channels) if ch in _INK_RGB]
    cov = block[:, [i for i, _ in inks], :].astype(np.float32) / 3.0      # (n, k, W)
    xs = (np.arange(W) * tw // W)
    ty = ((y0 + np.arange(block.shape[0])) * th // H)
    for row in np.unique(ty):
        sel = cov[ty == row]
        m = sel.mean(0)
        col = np.ones((W, 3)) * 255.0
        for k, (_, ink) in enumerate(inks):
            a = m[k][:, None]
            col = col * (1 - a) + col * a * (np.array(_INK_RGB[ink]) / 255.0)
        sums = np.zeros((tw, 3)); np.add.at(sums, xs, col)
        cnt = np.bincount(xs, minlength=tw)[:, None]
        thumb[row] += sums / np.maximum(cnt, 1) * len(sel)
        thumb_n[row] += len(sel)
