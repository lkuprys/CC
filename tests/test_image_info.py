# -*- coding: utf-8 -*-
"""Dydžio ir DPI nuskaitymas iš failo antraštės (TIF / PNG / JPG)."""
import pytest

QtGui = pytest.importorskip("PySide6.QtGui")


@pytest.mark.parametrize("ext,dpi", [("tif", 300), ("png", 360), ("jpg", 150)])
def test_read_image_info(core, tmp_path, ext, dpi):
    img = QtGui.QImage(321, 123, QtGui.QImage.Format_ARGB32)
    img.fill(QtGui.QColor(10, 20, 30))
    img.setDotsPerMeterX(round(dpi / 0.0254))
    img.setDotsPerMeterY(round(dpi / 0.0254))
    p = str(tmp_path / f"x.{ext}")
    assert img.save(p)
    w, h, dx, dy = core.read_image_info(p)
    assert (w, h) == (321, 123)
    assert abs(dx - dpi) < 0.5 and abs(dy - dpi) < 0.5


def test_blank_png_is_fully_transparent(core, tmp_path):
    p = str(tmp_path / "b.png")
    core.write_blank_png(p, 64, 32, 300, 300)
    img = QtGui.QImage(p)
    assert (img.width(), img.height()) == (64, 32)
    assert img.hasAlphaChannel()
    assert all(img.pixelColor(x, y).alpha() == 0 for x in (0, 31, 63) for y in (0, 15, 31))
