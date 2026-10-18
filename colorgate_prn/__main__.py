"""Command line:

  python -m colorgate_prn bundle    --job-settings <...CJB\\settings.xml> --out bundle_dir
  python -m colorgate_prn generate  --bundle bundle_dir --layout layout.json --out page.prn
  python -m colorgate_prn generate  --bundle bundle_dir --tif a.tif --tif b.tif --gap-mm 42.2 --out page.prn
  python -m colorgate_prn compare   reference.prn mine.prn
  python -m colorgate_prn info      file.prn
  python -m colorgate_prn chart     --out chart.tif
  python -m colorgate_prn calibrate --prn chart_from_colorgate.prn --chart chart.json [--name SpeedScreen_256x448px]
"""
from __future__ import annotations

import argparse
import sys
import time

from .cgsetup import ColorGateSetup
from .generator import generate_prn, load_layout, side_by_side
from .screening import Screen


def main(argv=None):
    ap = argparse.ArgumentParser(prog="colorgate_prn")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bundle", help="collect profiles/curves from a ColorGate job into a portable folder")
    b.add_argument("--job-settings", required=True)
    b.add_argument("--out", required=True)

    g = sub.add_parser("generate", help="TIF(s) -> PRN + BMP")
    g.add_argument("--bundle", required=True)
    g.add_argument("--layout", help="layout JSON with job positions (see generator.load_layout)")
    g.add_argument("--tif", action="append", help="TIF file(s), placed left to right")
    g.add_argument("--gap-mm", type=float, default=None, help="gap between --tif jobs (default 1195 px = 42.2 mm)")
    g.add_argument("--x", type=float, default=0, help="x of first --tif job")
    g.add_argument("--y", type=float, default=0, help="y of first --tif job")
    g.add_argument("--units", choices=("px", "mm"), default="px", help="units of --x/--y/--page-*")
    g.add_argument("--page-width", type=float)
    g.add_argument("--page-height", type=float)
    g.add_argument("--screen", help="screen name in colorgate_prn/data (default from bundle)")
    g.add_argument("--no-bmp", action="store_true")
    g.add_argument("--out", required=True)

    c = sub.add_parser("compare"); c.add_argument("a"); c.add_argument("b")
    i = sub.add_parser("info"); i.add_argument("prn")

    ch = sub.add_parser("chart", help="write the screen calibration chart TIF")
    ch.add_argument("--out", required=True)

    ca = sub.add_parser("calibrate", help="extract the exact screen from ColorGate's PRN of the chart")
    ca.add_argument("--prn", required=True)
    ca.add_argument("--chart", required=True, help="chart .json written by 'chart'")
    ca.add_argument("--name", default="SpeedScreen_256x448px")
    ca.add_argument("--job-x", type=int); ca.add_argument("--job-y", type=int)

    a = ap.parse_args(argv)
    if a.cmd == "bundle":
        s = ColorGateSetup.from_colorgate(a.job_settings)
        s.save_bundle(a.out)
        print(f"bundle written to {a.out}: {s.input_profile} -> {s.output_profile}, transfer curves {list(s.transfer)}")
    elif a.cmd == "generate":
        s = ColorGateSetup.load_bundle(a.bundle)
        tox = (lambda v: int(round(v / 25.4 * s.xdpi))) if a.units == "mm" else (lambda v: int(round(v)))
        toy = (lambda v: int(round(v / 25.4 * s.ydpi))) if a.units == "mm" else (lambda v: int(round(v)))
        if a.layout:
            jobs, pw, ph = load_layout(a.layout, s)
        else:
            gap = 1195 if a.gap_mm is None else int(round(a.gap_mm / 25.4 * s.xdpi))
            jobs = side_by_side(a.tif, s, gap, tox(a.x), toy(a.y))
            pw = ph = None
        pw = tox(a.page_width) if a.page_width else pw
        ph = toy(a.page_height) if a.page_height else ph
        screen = Screen.load(a.screen or s.screen)
        t0 = time.time()
        info = generate_prn(jobs, a.out, s, screen, pw, ph, bmp_path=None if a.no_bmp else "auto",
                            progress=lambda y, h: print(f"\r{y}/{h} lines", end="", file=sys.stderr))
        print(f"\n{a.out}: {info['width']} x {info['height']} px, {time.time() - t0:.1f}s")
        for tif, x, y, w, h in info["jobs"]:
            print(f"  {tif}: x={x} y={y} size {w}x{h}")
    elif a.cmd == "compare":
        from .compare import compare_prn
        print(compare_prn(a.a, a.b))
    elif a.cmd == "info":
        from .prn_format import read_prn
        hdr, _ = read_prn(a.prn, unpack=False)
        print(hdr)
    elif a.cmd == "chart":
        from .calibrate import make_chart
        js = make_chart(a.out)
        print(f"chart: {a.out}\nlayout: {js}\nRIP it in ColorGate with the production settings (output to file), then run 'calibrate'.")
    elif a.cmd == "calibrate":
        from .calibrate import extract_screen
        try:
            prior = Screen.load(a.name)
        except FileNotFoundError:
            prior = None
        scr, rep = extract_screen(a.prn, a.chart, prior=prior, job_x=a.job_x, job_y=a.job_y)
        print(rep)
        scr.save(a.name, note=f"extracted from {a.prn}")
        print(f"saved screen '{a.name}'")


if __name__ == "__main__":
    main()
