"""Reproduce ColorGate Productionserver PRN output.

Bundles: bundle_gunsjet (GUNSJET 2513, CMYK TIF, 720x1200, CMYK+Lc+Lm+W, Speed Screen) and
bundle_flora (Flora XTRA2512UV via the 'POD F2' hot folder, RGB PNG, 720x1800, CMYK+Lc+Lm, error diffusion).
"""
from .cgsetup import ColorGateSetup
from .generator import Job, container_layout, generate_prn, job_size, load_layout, side_by_side
from .prn_format import read_prn
from .screening import Screen

__all__ = ["ColorGateSetup", "Job", "generate_prn", "job_size", "load_layout", "side_by_side", "container_layout",
           "read_prn", "Screen"]
