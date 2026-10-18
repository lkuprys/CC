# -*- coding: utf-8 -*-
"""Spausdinimo (.prn) failo išdėstymas pagal modelio koordinates ir generavimas."""
import os
from datetime import datetime

import pytest

import prn_job

S = dict(prn_job.PRN_DEFAULTS, container_x=100.0, container_y=50.0, print_x=20.0, print_y=10.0)


def px(mm, dpi):
    return prn_job.mm_to_px(mm, dpi)


def test_first_design_bottom_left_and_rows_go_up():
    # 2 x 2 rėmas, 100 x 50 px dizainai, dpi 254 → 1 mm = 10 px; konteineris = tarpas tarp dizainų
    slots = [(0, 100, 50), (1, 100, 50), (2, 100, 50)]
    pos, w, h, warns = prn_job.layout_bed(slots, 2, S, 254, 254)
    assert w == 200 + 100 + 1000 + 100                  # print X + dizainas + tarpas X + dizainas
    assert h == 100 + 50 + 500 + 50                     # print Y + dizainas + tarpas Y + dizainas
    assert pos[0] == (200, h - (100 + 50))              # apatinė eilė, kairėje
    assert pos[1] == (200 + 100 + 1000, h - (100 + 50))  # apatinė eilė, dešinėje
    assert pos[2] == (200, h - (100 + 50 + 500 + 50))   # viršutinė eilė
    assert warns == []


def test_without_print_offset_first_design_at_page_corner():
    s = dict(S, include_print_offset=False)
    pos, w, h, _ = prn_job.layout_bed([(0, 100, 50), (1, 100, 50)], 2, s, 254, 254)
    assert pos[0] == (0, 0) and w == 100 + 1000 + 100 and h == 50


def test_empty_slot_keeps_its_place():
    pos, _, _, _ = prn_job.layout_bed([(1, 100, 50)], 2, S, 254, 254)
    assert pos[1][0] == 200 + 100 + 1000


def test_overlap_and_table_warnings():
    s = dict(S, container_x=-5.0)
    _, _, _, warns = prn_job.layout_bed([(0, 100, 50), (1, 100, 50)], 2, s, 254, 254, table_mm=(10, 10))
    assert any("persidengia" in w for w in warns)
    assert any("netelpa" in w for w in warns)


def test_model_settings_defaults_and_bad_values():
    s = prn_job.model_prn_settings({"prn": {"container_x": "242.5", "print_y": "x", "nežinomas": 1, "units": "mm"}})
    assert s["container_x"] == 242.5 and s["print_y"] == 0.0 and "nežinomas" not in s
    # v1.3.0 išsaugotos reikšmės centimetrais (be "units") → milimetrai
    old = prn_job.model_prn_settings({"prn": {"container_x": 24.25, "print_y": 3.1, "height": 9}})
    assert (old["container_x"], old["print_y"], old["height"], old["units"]) == (242.5, 31.0, 90.0, "mm")
    assert prn_job.model_prn_settings({"prn": {"output_dir": " D:/PRN "}})["output_dir"] == "D:/PRN"
    assert prn_job.model_prn_settings(None) == prn_job.PRN_DEFAULTS


def test_normalize_and_due_times():
    assert prn_job.normalize_times(["7:5", " 13:30", "blogai", "13:30", "25:00"]) == ["07:05", "13:30"]
    now = datetime(2026, 10, 18, 7, 20)
    assert prn_job.due_schedule_time(["07:05"], now, {}) == "07:05"
    assert prn_job.due_schedule_time(["07:05"], now, {"07:05": "2026-10-18"}) is None
    assert prn_job.due_schedule_time(["06:00"], now, {}) is None     # per seniai praleistas
    assert prn_job.due_schedule_time(["08:00"], now, {}) is None     # dar neatėjo


def test_generate_prn_for_bed(core, tmp_path):
    np = pytest.importorskip("numpy")
    tifffile = pytest.importorskip("tifffile")
    pytest.importorskip("PIL.ImageCms")
    from colorgate_prn.prn_format import read_prn

    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    img = np.full((30, 40, 4), 128, np.uint8)
    for pid in (1001, 1002):
        tifffile.imwrite(str(src / f"{pid}_macbook.tif"), img, photometric="separated",
                         resolution=(300, 300), resolutionunit=2)
    (src / "1003_macbook.png").write_bytes(b"png")
    plan = {
        "source_dir": str(src), "search_network": False, "out_dir": str(out), "cols": 2,
        "prn": dict(prn_job.PRN_DEFAULTS, container_x=10.0, container_y=10.0, print_x=5.0, print_y=2.0),
        "beds": [{"bed_idx": 0, "title": "BID-7", "items": ["PID-1001", None, "PID-1002", "PID-1003", "PID-9"]}],
    }
    plan["prn"]["output_dir"] = str(tmp_path / "modelio")   # modelio aplankas svarbesnis už bendrą
    res = prn_job.run_prn_job(plan)
    out = tmp_path / "modelio"
    assert len(res["files"]) == 1 and res["placed"] == 2
    f = res["files"][0]
    assert os.path.basename(f["path"]).startswith("BID-7_") and os.path.exists(f["bmp"])
    assert not [n for n in os.listdir(out) if n.endswith(".part")]
    hdr, _ = read_prn(f["path"], unpack=False)
    # 40x30 px @300 → 96x120 px; vieta 2 = 0 stulpelis, 1 eilė; poslinkis 5/2 mm, tarpas 10 mm
    assert hdr.width == px(5, 720) + 96
    assert hdr.height == px(2, 1200) + 120 + px(10, 1200) + 120
    assert sorted(m[2] for m in res["missing"]) == ["PID-1003", "PID-9"]
    assert any("TIF" in e for e in res["errors"])
