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
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import numpy as np

from .icc import load_link

CG_PROGRAMDATA = r"C:\ProgramData\ColorGATE Software\Productionserver10"
CG_PROGRAMFILES = r"C:\Program Files (x86)\ColorGATE Software\Productionserver10"
NS_LIN = {"l": "urn:schemas-colorgate-com:linearization"}
NS_JOB = {"j": "urn:schemas-colorgate-com:jobsettings"}
# ColorGate channel ids in settings.xml / .ccx
CG_ID = {"K": 0, "C": 1, "M": 2, "Y": 3}


def _find_profile(rel: str) -> str:
    for base in (os.path.join(CG_PROGRAMDATA, "Profiles"), os.path.join(CG_PROGRAMFILES, "Profiles")):
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
    transfer: dict = field(default_factory=dict)   # {"C"|"M"|"Y"|"K": LUT(4096)} applied on device CMYK
    lin2: dict = field(default_factory=dict)       # {"C","M","Y","K": 256-entry curve}
    split: dict = field(default_factory=dict)      # {"C_dark","C_light","M_dark","M_light": (x, y) points}
    lin1: dict = field(default_factory=dict)       # {"C","M","Y","K","Lc","Lm": 256-entry curve}
    droplet: tuple = (0.33, 0.66)                  # tone where small resp. medium drops reach 100 %
    xdpi: int = 720
    ydpi: int = 1200
    white_spot_names: tuple = ("W", "w", "White", "white")
    screen: str = "SpeedScreen_256x448px"

    # ------------------------------------------------------------------ loading from ColorGate
    @classmethod
    def from_colorgate(cls, job_settings_xml: str) -> "ColorGateSetup":
        """Read profiles/linearisation/curves named in a job's settings.xml (JobDir/<printer>/<job>.CJB/settings.xml)."""
        root = ET.parse(job_settings_xml).getroot()
        txt = lambda tag: (root.find(f".//j:{tag}", NS_JOB).text or "").strip()
        s = cls()
        s.input_profile = _find_profile(txt("InputProfileName_CMYKBitmap"))
        s.output_profile = _find_profile(os.path.join("OutputProfiles", txt("OutputProfileName")))
        cg_intent = int(txt("Intent_CMYKBitmap"))
        s.intent = {0: 0, 1: 1, 2: 2, 3: 3}.get(cg_intent, 1)  # 7 (seen in job) behaves as relative colorimetric
        flags = root.find(".//j:ExtraFlags[@BLACKPOINTCOMPENSATION]", NS_JOB)
        s.bpc = flags is None or flags.get("BLACKPOINTCOMPENSATION") == "true"
        s.xdpi = int(txt("ResolutionX")); s.ydpi = int(txt("ResolutionY"))
        spot = root.find(".//j:SpotName", NS_JOB)
        if spot is not None and spot.text:
            s.screen = os.path.splitext(spot.text.strip())[0]
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
        for attr in ("input_profile", "output_profile"):
            src = getattr(self, attr)
            dst = os.path.join(folder, os.path.basename(src))
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.copyfile(src, dst)
        d = {
            "input_profile": os.path.basename(self.input_profile),
            "output_profile": os.path.basename(self.output_profile),
            "intent": self.intent, "bpc": self.bpc, "xdpi": self.xdpi, "ydpi": self.ydpi,
            "droplet": list(self.droplet), "screen": self.screen,
            "white_spot_names": list(self.white_spot_names),
            "transfer": {k: v.tolist() for k, v in self.transfer.items()},
            "lin2": {k: v.tolist() for k, v in self.lin2.items()},
            "lin1": {k: v.tolist() for k, v in self.lin1.items()},
            "split": {k: v.tolist() for k, v in self.split.items()},
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
        s.intent, s.bpc, s.xdpi, s.ydpi = d["intent"], d["bpc"], d["xdpi"], d["ydpi"]
        s.droplet, s.screen = tuple(d["droplet"]), d["screen"]
        s.white_spot_names = tuple(d["white_spot_names"])
        s.transfer = {k: np.array(v) for k, v in d["transfer"].items()}
        s.lin2 = {k: np.array(v) for k, v in d["lin2"].items()}
        s.lin1 = {k: np.array(v) for k, v in d["lin1"].items()}
        s.split = {k: np.array(v) for k, v in d["split"].items()}
        return s
