"""Everything the pipeline needs from a ColorGate Productionserver installation, plus a portable bundle.

ColorGate pipeline for the GUNSJET 2513 job (reverse engineered and verified against PRN output):

  1. TIF CMYK (8 bit)  --input ICC (USWebCoatedSWOP) -> output ICC (Kingt 720x1200 M+ 300.icm)
     relative colorimetric + black point compensation          -> device CMYK
  2. per channel transfer curves from the job (settings.xml <ExtraColorTransfer>, cubic Bezier)
  3. Lin2  (.ccx Linearization Id=2, CMYK DeviceLink = 4 separable 1D curves, ink limits)
  4. ink split (.ccx <ColorTransfer>): C -> C (curve Id 2) + Lc (curve Id 0), M -> M + Lm
  5. Lin1  (.ccx Linearization Id=1, 6CLR DeviceLink = 6 separable 1D curves, max ink per channel)
  6. drop split (.ccx <DropletCurves>): x in [0,b1] small 0..100 %, [b1,b2] small->medium, [b2,1] medium->large
  7. spot "W" -> DeviceWhite (ColorTable w.cct), amount = 1 - W/255 (Photoshop spot convention), no ICC

Flora XTRA2512UV ('POD F2' hot folder, same ColorGate queue name, Productionserver 23): RGB PNG input.
Steps 3-6 are the same (.ccx 2026.ccx), but ColorGate's RGB -> device CMYK step is NOT reproducible with
LittleCMS (sRGB white gets ~3.5 % C/M/K), so it is measured with the RGB chart (rgb_chart.py) and stored
as rgb_lut["device"].  Job size comes from the hot folder (DestWidth/HeightSinglePage, aspect not kept),
TURN2 = 180 degree rotation, raster = error diffusion (diffusion.py).
"""
from __future__ import annotations

import base64
import glob
import json
import os
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import numpy as np

from .icc import load_link

NS_LIN = {"l": "urn:schemas-colorgate-com:linearization"}
NS_JOB = {"j": "urn:schemas-colorgate-com:jobsettings"}
# ColorGate channel ids in settings.xml / .ccx
CG_ID = {"K": 0, "C": 1, "M": 2, "Y": 3}


def _install_dirs(job_settings_xml: str | None = None) -> list:
    """Profiles folders of the Productionserver the job belongs to (ProgramData first), any version."""
    m = re.search(r"(Productionserver\d+)", job_settings_xml or "")
    names = [m.group(1)] if m else sorted({os.path.basename(p) for p in glob.glob(
        r"C:\ProgramData\ColorGATE Software\Productionserver*")}, reverse=True)
    out = []
    for n in names:
        out += [rf"C:\ProgramData\ColorGATE Software\{n}\Profiles",
                rf"C:\Program Files (x86)\ColorGATE Software\{n}\Profiles"]
    return out


_PROFILE_DIRS: list = []


def _find_profile(rel: str) -> str:
    for base in _PROFILE_DIRS or _install_dirs():
        for cand in (os.path.join(base, rel), os.path.join(base, "OutputProfiles", rel)):
            if os.path.exists(cand):
                return cand
    raise FileNotFoundError(rel)


def bezier_path_lut(segments: list, n: int = 4096) -> np.ndarray:
    """ColorGate ColorTansfer path -> LUT of n samples on 0..1.

    segments: list of (code, [(x, y), ...]); code 1 = moveto, 2 = lineto, 3 = cubic Bezier (c1, c2, end).
    """
    pts, cur = [], None
    t = np.linspace(0, 1, 1025)[:, None]
    for code, toks in segments:
        toks = [np.array(p, float) for p in toks]
        if code == 1:
            cur = toks[-1]; pts.append(cur[None])
        elif code == 2:
            for p in toks:
                pts.append(np.stack([cur, p])); cur = p
        elif code == 3:
            for i in range(0, len(toks), 3):
                c1, c2, e = toks[i:i + 3]
                pts.append((1 - t) ** 3 * cur + 3 * (1 - t) ** 2 * t * c1 + 3 * (1 - t) * t ** 2 * c2 + t ** 3 * e)
                cur = e
    p = np.concatenate(pts)
    order = np.argsort(p[:, 0], kind="stable")
    return np.interp(np.linspace(0, 1, n), p[order, 0], p[order, 1])


@dataclass
class ColorGateSetup:
    input_profile: str = ""            # path to CMYK input ICC
    output_profile: str = ""           # path to output (device CMYK) ICC
    intent: int = 1                    # ICC intent used for CMYK bitmaps (ColorGate code 7 == rel. colorimetric + BPC)
    bpc: bool = True
    rgb_input_profile: str = ""        # path to RGB input ICC (PNG / RGB TIF jobs)
    rgb_intent: int = 2
    transfer: dict = field(default_factory=dict)   # {"C"|"M"|"Y"|"K": LUT(4096)} applied on device CMYK
    lin2: dict = field(default_factory=dict)       # {"C","M","Y","K": 256-entry curve}
    split: dict = field(default_factory=dict)      # {"C_dark","C_light","M_dark","M_light": (x, y) points}
    lin1: dict = field(default_factory=dict)       # {"C","M","Y","K","Lc","Lm": 256-entry curve}
    droplet: tuple = (0.33, 0.66)                  # tone where small resp. medium drops reach 100 %
    xdpi: int = 720
    ydpi: int = 1200
    white_spot_names: tuple = ("W", "w", "White", "white")
    screen: str = "SpeedScreen_256x448px"
    screen_type: str = "speedscreen"               # "speedscreen" (threshold matrix) | "error_diffusion"
    channels: tuple = ("C", "M", "Y", "K", "Lc", "Lm", "W")   # PRN channel order
    dest_mm: tuple | None = None                   # job size on the media (w, h) mm; None = image size at its dpi
    rotate: int = 0                                # job rotation in degrees (TURN2 = 180)
    tone_correction: dict = field(default_factory=dict)  # ink -> (a, b): tone' = a * tone + b (estimated fit)
    rgb_lut: dict | None = None                    # measured RGB colour model (see rgb_chart.build_rgb_lut)
    rgb_measurements: list = field(default_factory=list)  # chart patches the model was built from

    # ------------------------------------------------------------------ loading from ColorGate
    @classmethod
    def from_colorgate(cls, job_settings_xml: str) -> "ColorGateSetup":
        """Read profiles/linearisation/curves named in a job's settings.xml (JobDir/<printer>/<job>.CJB/settings.xml)."""
        _PROFILE_DIRS[:] = _install_dirs(job_settings_xml)
        root = ET.parse(job_settings_xml).getroot()
        txt = lambda tag: (root.find(f".//j:{tag}", NS_JOB).text or "").strip()
        s = cls()
        s.input_profile = _find_profile(txt("InputProfileName_CMYKBitmap"))
        s.output_profile = _find_profile(os.path.join("OutputProfiles", txt("OutputProfileName")))
        cg_intent = int(txt("Intent_CMYKBitmap"))
        s.intent = {0: 0, 1: 1, 2: 2, 3: 3}.get(cg_intent, 1)  # 7 (seen in job) behaves as relative colorimetric
        try:
            s.rgb_input_profile = _find_profile(txt("InputProfileName_RGBBitmap"))
            s.rgb_intent = {0: 0, 1: 1, 2: 2, 3: 3}.get(int(txt("Intent_RGBBitmap")), 2)
        except (FileNotFoundError, AttributeError):
            pass
        flags = root.find(".//j:Qual/j:ExtraFlags[@BLACKPOINTCOMPENSATION]", NS_JOB)
        if flags is None:
            flags = root.find(".//j:ExtraFlags[@BLACKPOINTCOMPENSATION]", NS_JOB)
        s.bpc = flags is None or flags.get("BLACKPOINTCOMPENSATION") == "true"
        s.xdpi = int(txt("ResolutionX")); s.ydpi = int(txt("ResolutionY"))
        spot = root.find(".//j:SpotName", NS_JOB)
        if spot is not None and spot.text:
            s.screen = os.path.splitext(spot.text.strip())[0]
        raster = root.find(".//j:RasterName", NS_JOB)
        if raster is not None and "diffusion" in (raster.text or "").lower():
            s.screen_type = "error_diffusion"
        job = root.find("j:Job", NS_JOB)
        if job is not None:
            jf = job.find("j:Flags", NS_JOB)
            if jf is not None and jf.get("TURN2") == "true":
                s.rotate = 180
            dw, dh = job.find("j:DestWidthSinglePage", NS_JOB), job.find("j:DestHeightSinglePage", NS_JOB)
            sw, sh = job.find("j:SourceWidth", NS_JOB), job.find("j:SourceHeight", NS_JOB)
            if dw is not None and dh is not None and sw is not None and \
                    (abs(float(dw.text) - float(sw.text)) > 0.01 or abs(float(dh.text) - float(sh.text)) > 0.01):
                s.dest_mm = (float(dw.text), float(dh.text))
        # per-channel transfer curves (device CMYK, before linearisation)
        ext = root.find(".//j:ExtraColorTransfer", NS_JOB)
        if ext is not None:
            inv = {v: k for k, v in CG_ID.items()}
            for ct in ext.findall("j:ColorTansfer", NS_JOB):
                cid = int(ct.find("j:ChannelID", NS_JOB).text)
                segs = []
                for pt in ct.findall("j:ColorTansferPoint", NS_JOB):
                    code = int(pt.find("j:Code", NS_JOB).text)
                    toks = [(float(t.find("j:X", NS_JOB).text), float(t.find("j:Y", NS_JOB).text))
                            for t in pt.findall("j:Tokens/j:Token", NS_JOB)]
                    segs.append((code, toks))
                lut = bezier_path_lut(segs)
                if np.abs(lut - np.linspace(0, 1, len(lut))).max() < 1e-6:
                    continue  # identity
                if cid == -1:
                    for ch in "CMYK":
                        s.transfer[ch] = lut if ch not in s.transfer else np.interp(lut, np.linspace(0, 1, len(lut)), s.transfer[ch])
                elif cid in inv:
                    s.transfer[inv[cid]] = lut
        s._load_ccx(_find_profile(os.path.join("Linearisation", txt("OutputLinName"))))
        # PRN channels: ink set from the .ccx, plus W when the job maps a spot colour (ColorTable) to it
        ctab = root.find("j:ColorTable", NS_JOB)
        has_spot_table = ctab is not None and any(e.tag.split("}")[1] not in ("Flags", "AutoReplace") for e in ctab)
        s.channels = tuple(s.lin1) + (("W",) if has_spot_table else ())
        return s

    def _load_ccx(self, path: str) -> None:
        root = ET.parse(path).getroot()
        for lin in root.iterfind(".//l:Linearizations/l:Linearization", NS_LIN):
            lut = load_link(base64.b64decode(lin.find("l:TrafoData", NS_LIN).text))
            assert np.allclose(lut.in_tables, np.linspace(0, 1, lut.in_tables.shape[1])), "non-identity input tables"
            names = [c.get("Name") for c in lin.iterfind("l:Channels/l:Channel", NS_LIN)]
            short = {"Cyan": "C", "Magenta": "M", "Yellow": "Y", "Black": "K", "CyanLight": "Lc", "MagentaLight": "Lm"}
            curves = {short[n]: lut.out_tables[i].copy() for i, n in enumerate(names)}
            if lin.get("Id") == "2":
                self.lin2 = curves
            else:
                self.lin1 = curves
        for ch in root.iterfind(".//l:ColorTransfer/l:Channel", NS_LIN):
            name = {"1": "C", "2": "M"}[ch.get("Id")]
            for cv in ch.iterfind("l:ColorTransferCurve", NS_LIN):
                pts = np.array([(float(p.get("X")), float(p.get("Y"))) for p in cv.iterfind("l:CurvePoint", NS_LIN)])
                self.split[f"{name}_{'light' if cv.get('Id') == '0' else 'dark'}"] = pts
        b1 = b2 = None
        for dc in root.iterfind(".//l:DropletCurves/l:Channel/l:DropletCurve", NS_LIN):
            pts = [(float(p.get("X")), float(p.get("Y"))) for p in dc.iterfind("l:CurvePoint", NS_LIN)]
            peak = max(pts, key=lambda p: p[1])[0]
            if dc.get("DotSize") == "2":
                b1 = peak
            elif dc.get("DotSize") == "1":
                b2 = peak
        if b1 is not None and b2 is not None:
            self.droplet = (b1, b2)

    # ------------------------------------------------------------------ portable bundle
    def save_bundle(self, folder: str) -> None:
        """Copy profiles and write setup.json so the generator runs without ColorGate installed."""
        os.makedirs(folder, exist_ok=True)
        for attr in ("input_profile", "output_profile", "rgb_input_profile"):
            src = getattr(self, attr)
            if not src:
                continue
            dst = os.path.join(folder, os.path.basename(src))
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.copyfile(src, dst)
        d = {
            "input_profile": os.path.basename(self.input_profile),
            "output_profile": os.path.basename(self.output_profile),
            "rgb_input_profile": os.path.basename(self.rgb_input_profile),
            "intent": self.intent, "bpc": self.bpc, "rgb_intent": self.rgb_intent,
            "xdpi": self.xdpi, "ydpi": self.ydpi,
            "droplet": list(self.droplet), "screen": self.screen, "screen_type": self.screen_type,
            "channels": list(self.channels), "dest_mm": list(self.dest_mm) if self.dest_mm else None,
            "rotate": self.rotate,
            "white_spot_names": list(self.white_spot_names),
            "transfer": {k: v.tolist() for k, v in self.transfer.items()},
            "lin2": {k: v.tolist() for k, v in self.lin2.items()},
            "lin1": {k: v.tolist() for k, v in self.lin1.items()},
            "split": {k: v.tolist() for k, v in self.split.items()},
            "tone_correction": {k: list(v) for k, v in self.tone_correction.items()},
            "rgb_lut": self.rgb_lut,
            "rgb_measurements": self.rgb_measurements,
        }
        with open(os.path.join(folder, "setup.json"), "w") as f:
            json.dump(d, f)

    @classmethod
    def load_bundle(cls, folder: str) -> "ColorGateSetup":
        with open(os.path.join(folder, "setup.json")) as f:
            d = json.load(f)
        s = cls()
        s.input_profile = os.path.join(folder, d["input_profile"])
        s.output_profile = os.path.join(folder, d["output_profile"])
        if d.get("rgb_input_profile"):
            s.rgb_input_profile = os.path.join(folder, d["rgb_input_profile"])
        s.intent, s.bpc, s.xdpi, s.ydpi = d["intent"], d["bpc"], d["xdpi"], d["ydpi"]
        s.rgb_intent = d.get("rgb_intent", 2)
        s.droplet, s.screen = tuple(d["droplet"]), d["screen"]
        s.screen_type = d.get("screen_type", "speedscreen")
        s.channels = tuple(d.get("channels", s.channels))
        s.dest_mm = tuple(d["dest_mm"]) if d.get("dest_mm") else None
        s.rotate = d.get("rotate", 0)
        s.white_spot_names = tuple(d["white_spot_names"])
        s.transfer = {k: np.array(v) for k, v in d["transfer"].items()}
        s.lin2 = {k: np.array(v) for k, v in d["lin2"].items()}
        s.lin1 = {k: np.array(v) for k, v in d["lin1"].items()}
        s.split = {k: np.array(v) for k, v in d["split"].items()}
        s.tone_correction = {k: tuple(v) for k, v in d.get("tone_correction", {}).items()}
        s.rgb_lut = d.get("rgb_lut")
        s.rgb_measurements = d.get("rgb_measurements", [])
        return s
