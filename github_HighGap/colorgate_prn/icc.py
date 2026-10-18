"""Minimal ICC LUT evaluator: lut8 (mft1), lut16 (mft2), lutAToB (mAB ), lutBToA (mBA ).

Used for the DeviceLink profiles embedded in ColorGate linearisation files (.ccx TrafoData)
and as a fallback CMM.  All values are handled as floats in 0..1 (device / encoded PCS).
"""
from __future__ import annotations

import struct

import numpy as np


def read_tags(data: bytes) -> dict:
    n = struct.unpack(">I", data[128:132])[0]
    tags = {}
    for i in range(n):
        sig, off, size = struct.unpack(">4sII", data[132 + 12 * i:144 + 12 * i])
        tags[sig.decode("latin1")] = data[off:off + size]
    return tags


def header(data: bytes) -> dict:
    size, cmm, ver, cls, cs, pcs = struct.unpack(">I4sI4s4s4s", data[:24])
    return {"class": cls.decode(), "space": cs.decode().strip(), "pcs": pcs.decode().strip(), "version": ver >> 24}


# ---------------------------------------------------------------- interpolation helpers
def interp_curve(table: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Linear interpolation in a 1D table sampled uniformly on 0..1."""
    n = len(table)
    if n == 1:
        return np.full_like(x, table[0])
    pos = np.clip(x, 0, 1) * (n - 1)
    i0 = np.minimum(pos.astype(np.int64), n - 2)
    f = pos - i0
    return table[i0] * (1 - f) + table[i0 + 1] * f


def interp_clut(grid: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Multilinear interpolation. grid: (g0, g1, ..., gn-1, out), x: (N, n) in 0..1."""
    nin = x.shape[1]
    dims = np.array(grid.shape[:nin])
    pos = np.clip(x, 0, 1) * (dims - 1)
    i0 = np.minimum(pos.astype(np.int64), np.maximum(dims - 2, 0))
    f = pos - i0
    flat = grid.reshape(-1, grid.shape[-1])
    strides = np.r_[np.cumprod(dims[::-1])[::-1][1:], 1]
    out = np.zeros((x.shape[0], grid.shape[-1]))
    for corner in range(1 << nin):
        bits = [(corner >> (nin - 1 - k)) & 1 for k in range(nin)]
        idx = ((i0 + bits) * strides).sum(1)
        w = np.prod(np.where(bits, f, 1 - f), axis=1)
        out += flat[idx] * w[:, None]
    return out


def parse_curve(buf: bytes, off: int):
    """Returns (callable, byte length) for 'curv' or 'para'."""
    sig = buf[off:off + 4]
    if sig == b"curv":
        n = struct.unpack(">I", buf[off + 8:off + 12])[0]
        if n == 0:
            fn = lambda x: x
        elif n == 1:
            g = struct.unpack(">H", buf[off + 12:off + 14])[0] / 256.0
            fn = lambda x, g=g: np.clip(x, 0, 1) ** g
        else:
            t = np.frombuffer(buf, ">u2", n, off + 12).astype(np.float64) / 65535
            fn = lambda x, t=t: interp_curve(t, x)
        length = 12 + 2 * n
    elif sig == b"para":
        ftype = struct.unpack(">H", buf[off + 8:off + 10])[0]
        npar = {0: 1, 1: 3, 2: 4, 3: 5, 4: 7}[ftype]
        p = np.array(struct.unpack(">" + "i" * npar, buf[off + 12:off + 12 + 4 * npar])) / 65536.0
        g, a, b, c, d, e, f = (list(p) + [1, 0, 0, 0, 0, 0])[:7] if ftype else (p[0], 1, 0, 0, 0, 0, 0)

        def fn(x, ftype=ftype, g=g, a=a, b=b, c=c, d=d, e=e, f=f):
            x = np.clip(x, 0, 1)
            if ftype == 0:
                return x ** g
            if ftype == 1:
                return np.where(x >= -b / a, np.clip(a * x + b, 0, None) ** g, 0)
            if ftype == 2:
                return np.where(x >= -b / a, np.clip(a * x + b, 0, None) ** g + c, c)
            if ftype == 3:
                return np.where(x >= d, np.clip(a * x + b, 0, None) ** g, c * x)
            return np.where(x >= d, np.clip(a * x + b, 0, None) ** g + e, c * x + f)
        length = 12 + 4 * npar
    else:
        raise ValueError(f"unsupported curve type {sig!r}")
    return fn, (length + 3) & ~3


class Lut:
    """Callable LUT transform: __call__(x (N, nin) floats 0..1) -> (N, nout)."""

    def __init__(self, buf: bytes):
        sig = buf[:4]
        self.kind = sig.decode()
        if sig in (b"mft1", b"mft2"):
            self._parse_mft(buf, sig == b"mft2")
        elif sig in (b"mAB ", b"mBA "):
            self._parse_mab(buf, sig == b"mAB ")
        else:
            raise ValueError(f"unsupported LUT type {sig!r}")

    def _parse_mft(self, b: bytes, is16: bool):
        nin, nout, g = b[8], b[9], b[10]
        self.nin, self.nout = nin, nout
        self.matrix = np.array(struct.unpack(">9i", b[12:48])).reshape(3, 3) / 65536.0
        if is16:
            n_in, n_out = struct.unpack(">HH", b[48:52]); off = 52; dt, scale = ">u2", 65535.0
        else:
            n_in = n_out = 256; off = 48; dt, scale = "u1", 255.0
        sz = 2 if is16 else 1
        self.in_tables = np.frombuffer(b, dt, nin * n_in, off).reshape(nin, n_in) / scale
        off += nin * n_in * sz
        ncl = g ** nin * nout
        self.clut = (np.frombuffer(b, dt, ncl, off) / scale).reshape((g,) * nin + (nout,))
        off += ncl * sz
        self.out_tables = np.frombuffer(b, dt, nout * n_out, off).reshape(nout, n_out) / scale
        self.use_matrix = nin == 3 and not np.allclose(self.matrix, np.eye(3))

    def _parse_mab(self, b: bytes, a2b: bool):
        nin, nout = b[8], b[9]
        self.nin, self.nout = nin, nout
        oB, oM, oCurveM, oClut, oA = struct.unpack(">5I", b[12:32])
        self.a2b = a2b

        def curves(off, n):
            fns = []
            for _ in range(n):
                fn, ln = parse_curve(b, off); fns.append(fn); off += ln
            return fns
        self.B = curves(oB, nout if a2b else nin) if oB else None
        self.Mc = curves(oCurveM, 3) if oCurveM else None
        self.mat = None
        if oM:
            v = np.array(struct.unpack(">12i", b[oM:oM + 48])) / 65536.0
            self.mat = (v[:9].reshape(3, 3), v[9:])
        self.A = curves(oA, nin if a2b else nout) if oA else None
        self.clut = None
        if oClut:
            gp = list(b[oClut:oClut + nin]); prec = b[oClut + 16]
            dt, scale = (">u2", 65535.0) if prec == 2 else ("u1", 255.0)
            ncl = int(np.prod(gp)) * nout
            self.clut = (np.frombuffer(b, dt, ncl, oClut + 20) / scale).reshape(tuple(gp) + (nout,))

    @staticmethod
    def _apply(fns, x):
        return np.stack([fn(x[:, i]) for i, fn in enumerate(fns)], axis=1)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        x = np.atleast_2d(np.asarray(x, np.float64))
        if self.kind in ("mft1", "mft2"):
            if self.use_matrix:
                x = np.clip(x @ self.matrix.T, 0, 1)
            y = np.stack([interp_curve(self.in_tables[i], x[:, i]) for i in range(self.nin)], 1)
            y = interp_clut(self.clut, y)
            return np.stack([interp_curve(self.out_tables[i], y[:, i]) for i in range(self.nout)], 1)
        if self.a2b:  # A -> CLUT -> M -> Matrix -> B
            if self.A: x = self._apply(self.A, x)
            if self.clut is not None: x = interp_clut(self.clut, x)
            if self.Mc: x = self._apply(self.Mc, x)
            if self.mat: x = np.clip(x @ self.mat[0].T + self.mat[1], 0, 1)
            if self.B: x = self._apply(self.B, x)
            return x
        # B -> Matrix -> M -> CLUT -> A
        if self.B: x = self._apply(self.B, x)
        if self.mat: x = np.clip(x @ self.mat[0].T + self.mat[1], 0, 1)
        if self.Mc: x = self._apply(self.Mc, x)
        if self.clut is not None: x = interp_clut(self.clut, x)
        if self.A: x = self._apply(self.A, x)
        return x


def load_link(data: bytes, tag: str = "A2B0") -> Lut:
    return Lut(read_tags(data)[tag])
