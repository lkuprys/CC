# -*- coding: utf-8 -*-
"""Spaudos failų paieška pagal dizaino pavadinimą / PID."""


def files(*stems, mtime=0):
    return [{"stem_lower": s.lower(), "fname_lower": s.lower() + ".png", "path": s, "mtime": mtime}
            for s in stems]


def test_pid_exact_prefix_wins(core):
    assert core.find_matching_file_for_design("PID-1234", files("x_1234_y", "1234_front")) == "1234_front"


def test_pid_not_matched_inside_longer_number(core):
    assert core.find_matching_file_for_design("PID-1234", files("51234_x", "12345", "a12340")) is None


def test_pid_glued_to_letters_still_found(core):
    assert core.find_matching_file_for_design("PID-1234", files("pid1234")) == "pid1234"


def test_explicit_pid_never_falls_back_to_name(core):
    assert core.find_matching_file_for_design("PID-1234 Blue case", files("blue case")) is None


def test_name_substring_match_without_pid(core):
    assert core.find_matching_file_for_design("Blue case", files("blue case big")) == "blue case big"


def test_short_stems_do_not_match_everything(core):
    assert core.find_matching_file_for_design("abc design", files("1", "ab")) is None


def test_newest_file_wins_on_equal_score(core):
    cands = [{"stem_lower": "1234_a", "fname_lower": "1234_a.png", "path": "old", "mtime": 1},
             {"stem_lower": "1234_b", "fname_lower": "1234_b.png", "path": "new", "mtime": 2}]
    assert core.find_matching_file_for_design("PID 1234", cands) == "new"


def test_ambiguous_alternatives(core):
    cands = core.find_matching_candidates("PID-1234", files("1234_a", "1234_b", "x_1234"))
    assert len(core.ambiguous_alternatives(cands)) == 1  # 1234_a ir 1234_b – vienodas balas
    assert core.ambiguous_alternatives(core.find_matching_candidates("PID-1234", files("1234_a"))) == []


def test_format_output_filename(core):
    assert core.format_output_filename("02", "PID 77", "/x/f.png") == "02_PID-77.png"
    assert core.format_output_filename("01", "x", "/x/f.tif", custom_name="BID-6363") == "01_BID-6363.tif"
    assert core.format_output_filename("03", "a:b/../c", "/x/foo.png") == "03_ab..c.png"


def test_safe_folder_name(core):
    for bad in ("..", ".", "  ", "...", ""):
        assert core.safe_folder_name(bad, "FB") == "FB"
    assert core.safe_folder_name("iPad 7/8", "FB") == "iPad 78"
    assert core.safe_folder_name("abc.", "FB") == "abc"


def test_missing_label(core):
    assert core.missing_label("PID: 55 Blue") == "PID-55"
    assert core.missing_label("Blue") == "Blue"
