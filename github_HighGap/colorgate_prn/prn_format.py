"""PRN file format used by ColorGate output for this printer (reverse engineered).

Layout
------
48-byte header, 12 little-endian uint32:

  idx  offset  value (example)  meaning
  0    0x00    0x52590000       magic, bytes 00 00 'Y' 'R'
  1    0x04    720              X resolution (dpi)
  2    0x08    1200             Y resolution (dpi)
  3    0x0C    18769            width in pixels
  4    0x10    10392            height in lines
  5    0x14    4696             bytes per line per channel
  6    0x18    7                number of channels
  7    0x1C    0                unknown (always 0 in sample)
  8    0x20    0                unknown (always 0 in sample)
  9    0x24    2                bits per pixel
  10   0x28    3                number of drop sizes (max level)
  11   0x2C    0                unknown (always 0 in sample)

Raster data follows immediately, uncompressed, top line first:
  for y in range(height):
      for ch in range(channels):          # line interleaved
          bytes_per_line bytes, 4 pixels per byte, MSB first:
          pixel0 = (b >> 6) & 3, pixel1 = (b >> 4) & 3, pixel2 = (b >> 2) & 3, pixel3 = b & 3

Pixel values: 0 = no drop, 1 = small, 2 = medium, 3 = large drop.
Channel order: 0=C 1=M 2=Y 3=K 4=Lc 5=Lm 6=W
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

MAGIC = 0x52590000
HEADER_SIZE = 48
CHANNELS = ("C", "M", "Y", "K", "Lc", "Lm", "W")


def bytes_per_line(width: int, bits: int = 2) -> int:
    """ceil(width*bits/8) rounded up to a multiple of 4 bytes (4693 -> 4696, 6025 -> 6028, 3041 -> 3044)."""
    raw = (width * bits + 7) // 8
    return (raw + 3) // 4 * 4


@dataclass
class PrnHeader:
    xdpi: int = 720
    ydpi: int = 1200
    width: int = 0
    height: int = 0
    bpl: int = 0
    channels: int = 7
    bits: int = 2
    levels: int = 3
    magic: int = MAGIC
    reserved7: int = 0
    reserved8: int = 0
    reserved11: int = 0

    def pack(self) -> bytes:
        return struct.pack(
            "<12I", self.magic, self.xdpi, self.ydpi, self.width, self.height, self.bpl,
            self.channels, self.reserved7, self.reserved8, self.bits, self.levels, self.reserved11)

    @classmethod
    def unpack(cls, data: bytes) -> "PrnHeader":
        v = struct.unpack("<12I", data[:HEADER_SIZE])
        return cls(magic=v[0], xdpi=v[1], ydpi=v[2], width=v[3], height=v[4], bpl=v[5],
                   channels=v[6], reserved7=v[7], reserved8=v[8], bits=v[9], levels=v[10], reserved11=v[11])


def pack_levels(row_levels: np.ndarray, bpl: int) -> np.ndarray:
    """Pack (..., width) array of 0..3 into (..., bpl) bytes, MSB-first, 4 px per byte."""
    w = row_levels.shape[-1]
    padded = np.zeros(row_levels.shape[:-1] + (bpl * 4,), dtype=np.uint8)
    padded[..., :w] = row_levels
    p = padded.reshape(row_levels.shape[:-1] + (bpl, 4))
    return (p[..., 0] << 6) | (p[..., 1] << 4) | (p[..., 2] << 2) | p[..., 3]


def unpack_levels(row_bytes: np.ndarray, width: int) -> np.ndarray:
    """Inverse of pack_levels."""
    b = row_bytes[..., None]
    out = np.concatenate([(b >> 6) & 3, (b >> 4) & 3, (b >> 2) & 3, b & 3], axis=-1)
    return out.reshape(row_bytes.shape[:-1] + (row_bytes.shape[-1] * 4,))[..., :width].astype(np.uint8)


class PrnWriter:
    """Streaming writer: call write_lines() with blocks of (lines, channels, width) levels."""

    def __init__(self, path, width: int, height: int, channels: int = 7, xdpi: int = 720, ydpi: int = 1200):
        self.hdr = PrnHeader(xdpi=xdpi, ydpi=ydpi, width=width, height=height,
                             bpl=bytes_per_line(width), channels=channels)
        self.f = open(path, "wb")
        self.f.write(self.hdr.pack())
        self.lines = 0

    def write_lines(self, levels: np.ndarray) -> None:
        assert levels.ndim == 3 and levels.shape[1] == self.hdr.channels and levels.shape[2] == self.hdr.width
        self.f.write(np.ascontiguousarray(pack_levels(levels, self.hdr.bpl)).tobytes())
        self.lines += levels.shape[0]

    def close(self) -> None:
        if self.lines != self.hdr.height:
            raise ValueError(f"wrote {self.lines} lines, header says {self.hdr.height}")
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self.close()
        else:
            self.f.close()


def read_prn(path, unpack: bool = True):
    """Return (header, data). data is (height, channels, width) levels if unpack, else packed bytes (memmap)."""
    with open(path, "rb") as f:
        hdr = PrnHeader.unpack(f.read(HEADER_SIZE))
    raw = np.memmap(path, dtype=np.uint8, mode="r", offset=HEADER_SIZE,
                    shape=(hdr.height, hdr.channels, hdr.bpl))
    if not unpack:
        return hdr, raw
    out = np.empty((hdr.height, hdr.channels, hdr.width), dtype=np.uint8)
    step = 512
    for y in range(0, hdr.height, step):
        out[y:y + step] = unpack_levels(np.asarray(raw[y:y + step]), hdr.width)
    return hdr, out
