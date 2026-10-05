# -*- coding: utf-8 -*-
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import podbase_core  # noqa: E402


@pytest.fixture
def core(tmp_path, monkeypatch):
    """podbase_core, kurio visi failai nukreipti į laikiną aplanką (tikri nustatymai neliečiami)."""
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(podbase_core, "CONFIG_FILE", str(data / "config.json"))
    monkeypatch.setattr(podbase_core, "HISTORY_FILE", str(data / "history.json"))
    monkeypatch.setattr(podbase_core, "MODELS_FILE", str(data / "models.json"))
    monkeypatch.setattr(podbase_core, "JIGS_FILE", str(data / "jigs.json"))
    monkeypatch.setattr(podbase_core, "TEMP_FOLDERS_FILE", str(data / "temp_folders.json"))
    monkeypatch.setattr(podbase_core, "DESKTOP_DIR", str(tmp_path / "Konteineriai"))
    monkeypatch.setattr(podbase_core, "NETWORK_HOTFOLDER_DEFAULT", str(tmp_path / "nera_tinklo"))
    monkeypatch.setattr(podbase_core, "_corrupt_backed_up", set())
    podbase_core._scan_cache.clear()
    yield podbase_core
    podbase_core._scan_cache.clear()


@pytest.fixture
def make_file():
    """Sukuria failą su nurodytu turiniu ir (nebūtinai) modifikavimo laiku."""
    def _make(path, content=b"img", mtime=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path
    return _make


@pytest.fixture
def now():
    return time.time()
