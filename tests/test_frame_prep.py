# -*- coding: utf-8 -*-
"""Rėmo paruošimas: paruošimo failai su programa ir pilno rėmo siuntimas į HotFolderį."""
import os


def test_bundled_prep_files_present(core):
    keys = [k for k, _ in core.frame_prep_files()]
    assert keys[:3] == ["F1", "F2", "F3"]


def test_match_prep_jig_by_name(core):
    jigs = [{"name": "F2", "rows": 3, "cols": 6}, {"name": "F1 (Kindle)", "rows": 3, "cols": 7},
            {"name": "F10", "rows": 1, "cols": 1}, {"name": "MB 9x2", "rows": 2, "cols": 9}]
    assert core.match_prep_jig("F1", jigs)["name"] == "F1 (Kindle)"
    assert core.match_prep_jig("F2", jigs)["name"] == "F2"
    assert core.match_prep_jig("F3", jigs) is None
    assert core.jig_capacity(jigs[1]) == 21


def test_send_frame_prep_fills_whole_frame(core, tmp_path, make_file):
    src = tmp_path / "f2.png"
    make_file(src, b"PNG")
    hot = tmp_path / "hot"
    make_file(hot / "01_F2_PARUOSIMAS.png", b"OLD")
    written = core.send_frame_prep(str(src), 18, str(hot), "F2")
    assert len(written) == 18
    names = sorted(os.listdir(hot))
    assert "01_F2_PARUOSIMAS_2.png" in names and "18_F2_PARUOSIMAS.png" in names
    assert (hot / "01_F2_PARUOSIMAS.png").read_bytes() == b"OLD"      # esamas neperrašytas
    assert not [n for n in names if n.endswith(".part")]
