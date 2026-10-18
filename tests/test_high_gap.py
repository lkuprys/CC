"""HighGap priėmimo testas (iš github_HighGap): python -m pytest tests/test_high_gap.py

Synthetic job: white background + mid grey square + dark square.  Checks that HighGap
* prints no small drops (level 1) where the tone is >= 0.05 (grey / dark squares),
* keeps the light background tint exactly like normal mode (small drops, same amount),
* keeps the ink volume (mean drop level per channel) within 2 % of normal mode.
"""
import os
import sys
import tempfile

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pytest = __import__("pytest")
pytest.importorskip("numba")
sys.path.insert(0, ROOT)

from colorgate_prn import ColorGateSetup, Job, generate_prn, read_prn  # noqa: E402


def _make_job(folder):
    img = np.full((300, 240, 3), 255, np.uint8)
    img[60:140, 40:200] = (150, 150, 160)        # mid grey (bluish)
    img[180:260, 40:200] = (60, 45, 35)          # dark brown
    path = os.path.join(folder, "job.png")
    Image.fromarray(img).save(path, dpi=(300, 300))
    return path


def _render(path, out, high_gap):
    s = ColorGateSetup.load_bundle(os.path.join(ROOT, "colorgate_prn", "bundle_flora"))
    s.dest_mm = None                              # small native size keeps the test fast
    generate_prn([Job(path, 0, 0)], out, s, bmp_path=None, high_gap=high_gap)
    return read_prn(out)[1]                       # (h, channels, w) drop levels


def test_high_gap():
    with tempfile.TemporaryDirectory() as d:
        job = _make_job(d)
        normal = _render(job, os.path.join(d, "normal.prn"), False)
        high = _render(job, os.path.join(d, "high.prn"), True)
        h, c, w = normal.shape
        sy, sx = h / 300, w / 240

        def rect(y0, y1, x0, x1):          # image rect -> device rect (the Flora bundle rotates jobs 180 deg)
            y0, y1, x0, x1 = 300 - y1, 300 - y0, 240 - x1, 240 - x0
            return slice(int(y0 * sy), int(y1 * sy)), slice(None), slice(int(x0 * sx), int(x1 * sx))
        grey, dark, bg = rect(70, 130, 50, 190), rect(190, 250, 50, 190), rect(5, 50, 5, 235)
        for region, name in ((grey, "grey"), (dark, "dark")):
            m_n = normal[region].mean(axis=(0, 2)); m_h = high[region].mean(axis=(0, 2))
            for ch in np.nonzero(m_n >= 0.06)[0]:   # channels below 0.05 may keep small drops by design
                assert (high[region][:, ch] == 1).sum() == 0, f"small drops in {name} square, channel {ch}"
            assert np.all(np.abs(m_h - m_n) <= 0.02 * np.maximum(m_n, 0.05)), f"{name}: {m_n} vs {m_h}"
        bn, bh = normal[bg].mean(axis=(0, 2)), high[bg].mean(axis=(0, 2))
        assert bn.max() > 0.005, "normal mode should print the light background tint"
        assert np.allclose(bn, bh, atol=0.002), f"background tint changed: {bn} vs {bh}"
        assert (high[bg] >= 2).sum() == 0, "background tint must stay in small drops"


if __name__ == "__main__":
    test_high_gap()
    print("HighGap test OK")
