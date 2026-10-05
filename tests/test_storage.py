# -*- coding: utf-8 -*-
"""Nustatymų / istorijos saugojimas ir laikinų aplankų valymas."""
import json
import os


def test_write_json_atomic_leaves_no_tmp(core, tmp_path):
    p = tmp_path / "x.json"
    core.write_json_atomic(str(p), {"a": 1}, indent=2)
    assert json.loads(p.read_text()) == {"a": 1}
    assert not (tmp_path / "x.json.tmp").exists()


def test_corrupt_models_backed_up_once(core):
    with open(core.MODELS_FILE, "w", encoding="utf-8") as f:
        f.write("{sugadinta")
    assert core.load_models_data() == []
    assert core.load_models_data() == []
    backups = [n for n in os.listdir(os.path.dirname(core.MODELS_FILE)) if ".sugadintas_" in n]
    assert len(backups) == 1


def test_config_created_with_defaults(core):
    cfg = core.load_app_config()
    assert cfg["auto_cleanup_minutes"] == 10
    assert os.path.exists(core.CONFIG_FILE)


def test_cleanup_minutes_from_config(core):
    core.save_app_config({"auto_cleanup_minutes": 3})
    assert core.get_cleanup_expiry_seconds() == 180
    core.save_app_config({"auto_cleanup_minutes": "blogai"})
    assert core.get_cleanup_expiry_seconds() == 600


def test_history_keeps_newest_first_and_limit(core):
    for i in range(155):
        core.add_history_entry({"n": i})
    h = core.load_history_data()
    assert len(h) == 150 and h[0]["n"] == 154


def test_cleanup_only_removes_registered_old_folders(core, tmp_path, now):
    old, new, user = tmp_path / "old", tmp_path / "new", tmp_path / "mano"
    for d in (old, new, user):
        d.mkdir()
    os.utime(user, (now - 99999, now - 99999))
    core.register_temp_folder(str(old))
    core.register_temp_folder(str(new))
    reg = json.loads(open(core.TEMP_FOLDERS_FILE).read())
    reg[os.path.normpath(str(old))] -= 700
    core.write_json_atomic(core.TEMP_FOLDERS_FILE, reg)

    core.perform_temp_folders_cleanup()

    assert not old.exists()
    assert new.exists() and user.exists()
    assert list(json.loads(open(core.TEMP_FOLDERS_FILE).read())) == [os.path.normpath(str(new))]


def test_is_inside_dir(core, tmp_path):
    base = str(tmp_path / "b")
    assert core.is_inside_dir(os.path.join(base, "x"), base)
    assert not core.is_inside_dir(os.path.join(base, ".."), base)
    assert not core.is_inside_dir(base, base)


def test_unique_destination(core, tmp_path):
    p = tmp_path / "01_x.png"
    assert core.unique_destination(str(p)) == str(p)
    p.write_bytes(b"1")
    (tmp_path / "01_x_2.png").write_bytes(b"2")
    assert core.unique_destination(str(p)) == str(tmp_path / "01_x_3.png")
