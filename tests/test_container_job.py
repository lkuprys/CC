# -*- coding: utf-8 -*-
"""Konteinerio generavimas nuo paieškos iki nukopijuotų failų."""
import os


def plan(src, dest, beds, hotfolder=False):
    return {"source_dir": str(src), "dest_dir": str(dest), "hotfolder": hotfolder,
            "beds": [{"bed_idx": i, "title": t, "items": items} for i, (t, items) in enumerate(beds)]}


def test_scan_skips_ignored_folders_and_types(core, tmp_path, make_file):
    src = tmp_path / "src"
    make_file(src / "a" / "1001_x.png")
    make_file(src / "DONE" / "1002_x.png")
    make_file(src / "Batch Sheet 5" / "1003_x.png")
    make_file(src / "1004_x.pdf")
    make_file(src / "~1005_x.png")
    names = sorted(f["filename"] for f in core.scan_print_files_recursive([str(src)]))
    assert names == ["1001_x.png"]


def test_temp_folder_job(core, tmp_path, make_file):
    src, out = tmp_path / "src", tmp_path / "out"
    make_file(src / "1001_front.png", b"A")
    make_file(src / "sub" / "1002_x.png", b"B")
    res = core.run_container_job(plan(src, out, [("BID-77", ["PID-1001", "PID-1002", "PID-9999"])]))

    folder = out / "BID-77"
    assert sorted(os.listdir(folder)) == ["01_BID-77.png", "02_PID-1002.png", "03_PID-9999_TRUKSTA.txt"]
    assert (folder / "01_BID-77.png").read_bytes() == b"A"
    assert res["copied"] == 2
    assert res["missing"] == [(0, 2, "PID-9999")]
    assert [(f[0], f[1]) for f in res["found"]] == [(0, 0), (0, 1)]
    assert os.path.normpath(str(folder)) in core._load_temp_folders()


def test_dangerous_title_cannot_escape(core, tmp_path, make_file):
    src, out = tmp_path / "src", tmp_path / "out"
    make_file(src / "1001_a.png")
    keep = out / "kita.txt"
    make_file(keep)
    core.run_container_job(plan(src, out, [("..", ["PID-1001"])]))
    assert keep.exists()
    assert os.listdir(out / "Stalas_1") == ["01_Stalas_1.png"]


def test_duplicate_titles_get_suffix(core, tmp_path, make_file):
    src, out = tmp_path / "src", tmp_path / "out"
    make_file(src / "1001_a.png")
    make_file(src / "1002_a.png")
    res = core.run_container_job(plan(src, out, [("X", ["PID-1001"]), ("X", ["PID-1002"])]))
    assert sorted(os.listdir(out)) == ["X", "X_2"]
    assert res["copied"] == 2


def test_hotfolder_does_not_overwrite(core, tmp_path, make_file):
    src, hot = tmp_path / "src", tmp_path / "hot"
    make_file(src / "1001_a.png", b"NEW")
    make_file(hot / "01_T.png", b"OLD")
    core.run_container_job(plan(src, hot, [("T", ["PID-1001"])], hotfolder=True))
    assert (hot / "01_T.png").read_bytes() == b"OLD"
    assert (hot / "01_T_2.png").read_bytes() == b"NEW"
    assert not any(n.endswith("TRUKSTA.txt") for n in os.listdir(hot))


def test_ambiguous_match_warns_and_takes_newest(core, tmp_path, make_file, now):
    src, rejected, out = tmp_path / "src", tmp_path / "rejected", tmp_path / "out"
    make_file(src / "1001_a.png", b"OLD", mtime=now - 1000)
    make_file(rejected / "1001_a.png", b"NEW", mtime=now - 10)
    core.save_app_config({"reject_folder": str(rejected)})
    res = core.run_container_job(plan(src, out, [("T", ["PID-1001"])]))
    assert (out / "T" / "01_T.png").read_bytes() == b"NEW"
    assert res["ambiguous"] == [(0, 0)]
    assert len(res["warnings"]) == 1 and "PID-1001" in res["warnings"][0]


def test_cache_rescans_when_file_appears(core, tmp_path, make_file):
    src, out = tmp_path / "src", tmp_path / "out"
    make_file(src / "1001_a.png")
    core.run_container_job(plan(src, out, [("T", ["PID-1001"])]))
    make_file(src / "deep" / "er" / "1002_a.png")
    res = core.run_container_job(plan(src, out, [("T", ["PID-1002"])]))
    assert res["copied"] == 1 and res["missing"] == []


def test_forced_rescan_ignores_scan_started_before_request(core, tmp_path, make_file, now):
    src = tmp_path / "src"
    make_file(src / "1001_a.png")
    roots = [str(src)]
    key = tuple(os.path.normcase(os.path.normpath(r)) for r in roots)
    # Kito skenavimo rezultatas: baigtas „ateityje“, bet pradėtas prieš užklausą – be naujo failo
    core._scan_cache[key] = (now + 60, [], core._roots_mtime(roots), now - 5)
    files, from_cache = core.get_scanned_files(roots, force=True)
    assert [f["filename"] for f in files] == ["1001_a.png"] and from_cache is False


def test_prefetch_does_not_wait_for_running_scan(core, tmp_path):
    roots = [str(tmp_path)]
    key = tuple(os.path.normcase(os.path.normpath(r)) for r in roots)
    lock = core._scan_lock_for(key)
    with lock:
        assert core.get_scanned_files(roots, wait=False) == (None, False)


def test_model_file_types_limit_search(core, tmp_path, make_file, now):
    src, out = tmp_path / "src", tmp_path / "out"
    make_file(src / "a" / "89911_macbook.png", b"PNG", mtime=now)
    make_file(src / "b" / "89911_macbook.tif", b"TIF", mtime=now - 100)
    p = plan(src, out, [("T", ["PID-89911"])])
    p["file_types"] = ["tif"]
    res = core.run_container_job(p)
    assert (out / "T" / "01_T.tif").read_bytes() == b"TIF"
    assert res["warnings"] == [] and res["ambiguous"] == []
    # Be apribojimo – du kandidatai ir įspėjimas
    p.pop("file_types")
    res = core.run_container_job(p)
    assert len(res["warnings"]) == 1


def test_extensions_for_types(core):
    assert core.extensions_for_types(["tif"]) == {".tif", ".tiff"}
    assert core.extensions_for_types(["JPG", ".png"]) == {".jpg", ".jpeg", ".png"}
    assert core.extensions_for_types([]) == core.SUPPORTED_IMAGE_EXTENSIONS


def test_blank_slot_gets_size_and_dpi_of_bed_file(core, tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    # „Spaudos failai“: tikri PNG su žinomu dydžiu ir DPI
    core.write_blank_png(str(src / "1001_a.png"), 120, 80, 300, 300)
    core.write_blank_png(str(src / "1002_a.png"), 120, 80, 300, 300)
    res = core.run_container_job(plan(src, out, [("T", ["PID-1001", core.BLANK_TOKEN, "PID-1002"])]))
    files = sorted(os.listdir(out / "T"))
    assert files == ["01_T.png", "02_TUSCIAS.png", "03_PID-1002.png"]
    w, h, dx, dy = core.read_image_info(str(out / "T" / "02_TUSCIAS.png"))
    assert (w, h) == (120, 80) and round(dx) == 300 and round(dy) == 300
    assert res["missing"] == [] and res["copied"] == 3 and len(res["blanks"]) == 1


def test_blank_slot_without_reference_is_reported(core, tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    res = core.run_container_job(plan(src, out, [("T", [core.BLANK_TOKEN])]))
    assert res["missing"] == [(0, 0, core.BLANK_LABEL)]
    assert any("Tuščias lizdas" in e for e in res["errors"])


def test_plan_item_name(core):
    assert core.plan_item_name({"name": "Tuščias lizdas", "blank": True}) == core.BLANK_TOKEN
    assert core.plan_item_name({"name": "PID-1"}) == "PID-1"
