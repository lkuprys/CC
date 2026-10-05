# -*- coding: utf-8 -*-
import sys
import os
import re
import json
import time
import math
import copy
import shutil
import threading
from pathlib import Path
from datetime import datetime

# Enable explicit AppUserModelID on Windows so taskbar displays the custom transparent icon
if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('podbase.containercreator.studio.v1')
    except Exception:
        pass

from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer, QSize, QUrl, QByteArray, QMimeData, QPoint
from PySide6.QtGui import QIcon, QPixmap, QFont, QColor, QPainter, QImage, QDrag, QCursor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QSizePolicy, QFileDialog, QSpacerItem, QTableWidgetItem,
    QLabel, QSpinBox, QSplitter, QScrollArea, QStackedWidget, QHeaderView
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, NavigationWidget,
    SubtitleLabel, TitleLabel, BodyLabel, CaptionLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton, ToolButton, TransparentToolButton,
    ComboBox, EditableComboBox, LineEdit, SearchLineEdit, SpinBox,
    CardWidget, SimpleCardWidget, ElevatedCardWidget, CheckBox,
    InfoBar, InfoBarPosition, ProgressBar, ProgressRing,
    FluentIcon as FIF, setTheme, Theme, isDarkTheme,
    SmoothScrollArea, PillPushButton, TableWidget, SegmentedWidget,
    RadioButton
)
from flask import Flask, request, jsonify
from werkzeug.serving import make_server

# Import auto-updater module
from updater import AppUpdater, CURRENT_VERSION, DEFAULT_GITHUB_REPO, PERIODIC_CHECK_INTERVAL_MS

def get_res_path(filename):
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            p_mei = os.path.join(sys._MEIPASS, filename)
            if os.path.exists(p_mei):
                return p_mei
        exe_dir = os.path.dirname(sys.executable)
        p_exe = os.path.join(exe_dir, filename)
        if os.path.exists(p_exe):
            return p_exe
        p_internal = os.path.join(exe_dir, "_internal", filename)
        if os.path.exists(p_internal):
            return p_internal
    p_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if os.path.exists(p_src):
        return p_src
    return filename

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODELS_FILE = os.path.join(BASE_DIR, "models.json")
JIGS_FILE = os.path.join(BASE_DIR, "jigs.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
LOGO_FILE = get_res_path("podbase_logo.png")
ICON_FILE = get_res_path("podbase_icon.png")
DESKTOP_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "Konteineriai")
os.makedirs(DESKTOP_DIR, exist_ok=True)


def ensure_local_data_files():
    """
    Naujoje instaliacijoje nukopijuoja pradinius models.json / jigs.json / config.json
    iš sukompiliuoto paketo (_internal) šalia exe. Esamų failų NIEKADA neperrašo,
    todėl kiekvieno kompiuterio nustatymai išlieka ir po atnaujinimų.
    """
    if not getattr(sys, 'frozen', False):
        return
    bundle_dir = getattr(sys, '_MEIPASS', os.path.join(BASE_DIR, "_internal"))
    for target in (MODELS_FILE, JIGS_FILE, CONFIG_FILE):
        if os.path.exists(target):
            continue
        bundled = os.path.join(bundle_dir, os.path.basename(target))
        if os.path.exists(bundled):
            try:
                shutil.copy2(bundled, target)
            except Exception as e:
                print(f"[ensure_local_data_files]: {e}")


ensure_local_data_files()

# Common shared network hotfolder roots
NETWORK_HOTFOLDER_DEFAULT = r"\\192.168.1.143\podbase-hotfolder\BENDRAS_PODBASE_HOTFOLDER"
AUTO_CLEANUP_EXPIRY_SECONDS = 600  # 10 minutes

# ----------------- CONFIG & THEME STORAGE -----------------
def load_app_config():
    default_config = {
        "theme": "LIGHT",
        "auto_cleanup_minutes": 10,
        "github_repo": DEFAULT_GITHUB_REPO,
        "auto_check_updates": True,
        "reject_folder": ""
    }
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2)
        return default_config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "github_repo" not in data:
                data["github_repo"] = DEFAULT_GITHUB_REPO
            if "auto_check_updates" not in data:
                data["auto_check_updates"] = True
            return data
    except Exception:
        return default_config

def save_app_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

# ----------------- HISTORY STORAGE -----------------
def load_history_data():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_history_data(history_list):
    if len(history_list) > 150:
        history_list = history_list[:150]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history_list, f, ensure_ascii=False, indent=2)

def add_history_entry(entry):
    h = load_history_data()
    h.insert(0, entry)
    save_history_data(h)

# ----------------- TEMPORARY FOLDER 10-MIN AUTO-CLEANUP -----------------
def perform_temp_folders_cleanup(tracked_dirs=None):
    now = time.time()
    dirs_to_check = [DESKTOP_DIR]
    if tracked_dirs:
        for d in tracked_dirs:
            if d and os.path.exists(d) and d not in dirs_to_check:
                dirs_to_check.append(d)

    for base in dirs_to_check:
        if not os.path.exists(base):
            continue
        try:
            for item_name in os.listdir(base):
                item_path = os.path.join(base, item_name)
                if os.path.isdir(item_path):
                    try:
                        mtime = os.path.getmtime(item_path)
                        age = now - mtime
                        if age >= AUTO_CLEANUP_EXPIRY_SECONDS:
                            shutil.rmtree(item_path, ignore_errors=True)
                            print(f"[AutoCleanup] Ištrintas pasenęs laikinas aplankas (>10 min): {item_path}")
                    except Exception as err:
                        print(f"[AutoCleanup klaida]: {err}")
        except Exception as e:
            print(f"[AutoCleanup listing error]: {e}")

# ----------------- DRAG & DROP MIME PARSER -----------------
def parse_dropped_items(mime_data):
    items = []
    if mime_data.hasUrls():
        for url in mime_data.urls():
            if url.isLocalFile():
                local_path = url.toLocalFile()
                stem = Path(local_path).stem
                items.append({
                    "name": stem,
                    "url": local_path
                })
            else:
                raw_url = url.toString()
                filename = raw_url.split("?")[0].split("/")[-1]
                stem = os.path.splitext(filename)[0] or "Dizainas"
                items.append({
                    "name": stem,
                    "url": raw_url
                })
    elif mime_data.hasHtml():
        html = mime_data.html()
        src_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        alt_matches = re.findall(r'<img[^>]+alt=["\']([^"\']+)["\']', html, re.IGNORECASE)
        for i, src in enumerate(src_matches):
            alt = alt_matches[i] if i < len(alt_matches) else ""
            filename = src.split("?")[0].split("/")[-1]
            stem = alt.strip() or os.path.splitext(filename)[0] or "Dizainas"
            items.append({
                "name": stem,
                "url": src
            })
    elif mime_data.hasText():
        txt = mime_data.text().strip()
        if not txt.startswith("uv-slot:"):
            for line in txt.splitlines():
                line = line.strip()
                if line.startswith("http://") or line.startswith("https://") or os.path.exists(line):
                    is_loc = os.path.exists(line)
                    stem = Path(line).stem if is_loc else os.path.splitext(line.split("?")[0].split("/")[-1])[0]
                    items.append({
                        "name": stem or "Dizainas",
                        "url": line
                    })
                elif line:
                    items.append({
                        "name": line,
                        "url": ""
                    })
    return items

# ----------------- RECURSIVE MULTI-ROOT PRINT FILE SCANNER -----------------
SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff'}
IGNORED_FOLDER_NAMES = {'batch sheet', 'batchsheet', 'trash', 'done', 'archived', 'temp', 'tmp', '__pycache__'}
IGNORED_FILE_KEYWORDS = {'batch sheet', 'batchsheet', 'thumbs.db', '.ds_store'}

def is_file_ready(file_path, wait_interval=0.25, max_attempts=4):
    if not os.path.exists(file_path):
        return False
    try:
        initial_size = os.path.getsize(file_path)
        for _ in range(max_attempts):
            time.sleep(wait_interval)
            current_size = os.path.getsize(file_path)
            if current_size == initial_size and current_size > 0:
                try:
                    with open(file_path, 'rb') as f:
                        f.read(1024)
                    return True
                except (IOError, OSError):
                    pass
            initial_size = current_size
        return False
    except Exception as e:
        print(f"[is_file_ready klaida]: {e}")
        return False

def build_search_roots(source_dir):
    """
    Aplankai, kuriuose ieškoma spaudos failų:
    1) modelio šaltinio aplankas, 2) bendras tinklo HotFolder, 3) brokų (rejected) aplankas iš nustatymų.
    """
    source_dir = (source_dir or "").strip()
    reject_dir = (load_app_config().get("reject_folder") or "").strip()

    search_roots = []
    for d in (source_dir, NETWORK_HOTFOLDER_DEFAULT, reject_dir):
        if d and d not in search_roots and os.path.exists(d):
            search_roots.append(d)

    if not search_roots and source_dir:
        search_roots.append(source_dir)
    return search_roots

def scan_print_files_recursive(search_roots):
    if isinstance(search_roots, str):
        search_roots = [search_roots]

    scanned_files = []
    visited_roots = set()

    for root_dir in search_roots:
        if not root_dir or not os.path.exists(root_dir):
            continue
        norm_root = os.path.normpath(root_dir)
        if norm_root in visited_roots:
            continue
        visited_roots.add(norm_root)

        try:
            for dirpath, dirnames, filenames in os.walk(norm_root):
                dirnames[:] = [
                    d for d in dirnames
                    if not d.startswith(('.', '~', '$'))
                    and d.lower().strip() not in IGNORED_FOLDER_NAMES
                    and 'batch sheet' not in d.lower()
                    and 'batchsheet' not in d.lower()
                    and 'trash' not in d.lower()
                    and 'done' not in d.lower()
                ]

                for fname in filenames:
                    fname_lower = fname.lower()
                    if fname.startswith(('.', '~', '$')):
                        continue
                    if any(kw in fname_lower for kw in IGNORED_FILE_KEYWORDS):
                        continue
                    ext = os.path.splitext(fname_lower)[1]
                    if ext not in SUPPORTED_IMAGE_EXTENSIONS:
                        continue

                    stem = os.path.splitext(fname)[0]
                    stem_lower = stem.lower()
                    full_path = os.path.join(dirpath, fname)
                    
                    try:
                        mtime = os.path.getmtime(full_path)
                    except Exception:
                        mtime = 0

                    scanned_files.append({
                        "filename": fname,
                        "fname_lower": fname_lower,
                        "stem": stem,
                        "stem_lower": stem_lower,
                        "path": full_path,
                        "mtime": mtime
                    })
        except Exception as e:
            print(f"[scan_print_files_recursive klaida ties {root_dir}]: {e}")

    return scanned_files

def find_matching_file_for_design(design_name, scanned_files):
    d_clean = design_name.lower().strip()
    d_num_match = re.search(r'PID[-_:\s]*(\d+)', design_name, re.IGNORECASE)
    pid_digits = d_num_match.group(1) if d_num_match else "".join(c for c in d_clean if c.isdigit())

    matches_with_score = []

    for f_info in scanned_files:
        stem_l = f_info["stem_lower"]
        mtime = f_info["mtime"]
        f_path = f_info["path"]

        if pid_digits and len(pid_digits) >= 3:
            if stem_l.startswith(pid_digits + "_") or stem_l.startswith(pid_digits + "-") or stem_l == pid_digits:
                matches_with_score.append((100, mtime, f_path))
                continue
            
            if re.search(r'(^|[_\-\s])' + re.escape(pid_digits) + r'([_\-\s]|$)', stem_l):
                matches_with_score.append((90, mtime, f_path))
                continue

            if pid_digits in stem_l:
                matches_with_score.append((70, mtime, f_path))
                continue

        if d_clean == stem_l or d_clean == f_info["fname_lower"]:
            matches_with_score.append((85, mtime, f_path))
            continue

        if len(d_clean) >= 3 and (d_clean in stem_l or stem_l in d_clean):
            matches_with_score.append((50, mtime, f_path))
            continue

    if matches_with_score:
        matches_with_score.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return matches_with_score[0][2]

    return None

# ----------------- STRICT PID & SEQUENTIAL OUTPUT FILENAME FORMATTER -----------------
def format_output_filename(num_prefix, design_name, source_filepath, custom_name=None):
    ext = os.path.splitext(source_filepath)[1]
    stem_file = os.path.splitext(os.path.basename(source_filepath))[0]
    
    if custom_name:
        clean_name = re.sub(r'[\\/*?:"<>|]', "", custom_name).strip()
        if clean_name:
            return f"{num_prefix}_{clean_name}{ext}"
            
    pid_match = re.search(r'PID[-_:\s]*(\d+)', design_name, re.IGNORECASE)
    if pid_match:
        base_name = f"PID-{pid_match.group(1)}"
    elif re.match(r'^\d{3,}$', design_name.strip()):
        base_name = f"PID-{design_name.strip()}"
    else:
        stem_pid = re.search(r'PID[-_:\s]*(\d+)', stem_file, re.IGNORECASE)
        if stem_pid:
            base_name = f"PID-{stem_pid.group(1)}"
        else:
            num_lead = re.match(r'^(\d{3,9})[_\-\s]', stem_file)
            if num_lead:
                base_name = f"PID-{num_lead.group(1)}"
            else:
                base_name = design_name.strip()

    return f"{num_prefix}_{base_name}{ext}"

# ----------------- KONTEINERIO GENERAVIMAS FONE (be užstrigimo) -----------------
# Tinklo aplankų skenavimas gali užtrukti, todėl rezultatas trumpam įsimenamas.
# Jei su įsimintu sąrašu kurio nors failo nerandama, sąrašas automatiškai perskenuojamas.
SCAN_CACHE_TTL_SECONDS = 300
_scan_cache = {}
_scan_cache_lock = threading.Lock()


def get_scanned_files(search_roots, force=False):
    """Grąžina (failų sąrašas, ar paimta iš atminties)."""
    key = tuple(os.path.normcase(os.path.normpath(r)) for r in search_roots)
    if not force:
        with _scan_cache_lock:
            hit = _scan_cache.get(key)
        if hit and time.time() - hit[0] < SCAN_CACHE_TTL_SECONDS:
            return hit[1], True
    files = scan_print_files_recursive(search_roots)
    with _scan_cache_lock:
        _scan_cache[key] = (time.time(), files)
    return files, False


def safe_copy_file(src, dst):
    """
    Kopijuoja laikinu pavadinimu (.part) ir tik pabaigus pervadina.
    Taip ColorGATE niekada nepaima pusiau nukopijuoto failo.
    """
    tmp = dst + ".part"
    if os.path.exists(tmp):
        os.remove(tmp)
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def safe_folder_name(name, fallback):
    """Aplanko pavadinimas be kelio dalių: be \\ / : * ? " < > |, ir ne „.“ / „..“."""
    clean = re.sub(r'[\\/*?:"<>|]', "", str(name or "")).strip().rstrip(". ")
    if not clean or set(clean) <= {"."}:
        return fallback
    return clean


def is_inside_dir(path, base):
    """True, jei path yra base aplanko viduje (ne pats base ir ne aukščiau jo)."""
    try:
        real_path = os.path.normcase(os.path.realpath(path))
        real_base = os.path.normcase(os.path.realpath(base))
        return real_path != real_base and os.path.commonpath([real_path, real_base]) == real_base
    except ValueError:
        return False


def run_container_job(plan, progress=None):
    """
    Suranda ir nukopijuoja spaudos failus pagal planą. Vykdoma fono gijoje.

    plan = {
        "source_dir": str, "dest_dir": str, "hotfolder": bool,
        "beds": [{"bed_idx": int, "title": str, "items": [dizaino pavadinimas, ...]}]
    }
    Grąžina {"copied", "missing": [(bed_idx, item_idx, name)], "errors", "folders", "search_roots"}.
    """
    def report(text, done=0, total=0):
        if progress:
            progress(done, total, text)

    result = {"copied": 0, "missing": [], "errors": [], "folders": [], "search_roots": []}

    report("Tikrinami paieškos aplankai...")
    search_roots = build_search_roots(plan.get("source_dir", ""))
    result["search_roots"] = search_roots

    def match_all(scanned):
        return {
            (b["bed_idx"], i): find_matching_file_for_design(name, scanned)
            for b in plan["beds"] for i, name in enumerate(b["items"])
        }

    report("Ieškoma spaudos failų...")
    scanned, from_cache = get_scanned_files(search_roots)
    matches = match_all(scanned)
    if from_cache and any(v is None or not os.path.exists(v) for v in matches.values()):
        report("Atnaujinamas failų sąrašas...")
        scanned, _ = get_scanned_files(search_roots, force=True)
        matches = match_all(scanned)

    is_hot = plan.get("hotfolder", False)
    dest_dir = plan.get("dest_dir", "")
    if is_hot:
        os.makedirs(dest_dir, exist_ok=True)

    total = len(matches)
    done = 0
    for b in plan["beds"]:
        title = safe_folder_name(b["title"], f"Stalas_{b['bed_idx'] + 1}")
        if is_hot:
            target_dir = dest_dir
        else:
            base_out = dest_dir or DESKTOP_DIR
            try:
                os.makedirs(base_out, exist_ok=True)
            except Exception:
                base_out = DESKTOP_DIR
                os.makedirs(base_out, exist_ok=True)
            target_dir = os.path.join(base_out, title)
            if not is_inside_dir(target_dir, base_out):
                result["errors"].append(f"Netinkamas stalo pavadinimas: {title}")
                continue
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir, ignore_errors=True)
            os.makedirs(target_dir, exist_ok=True)
        if target_dir not in result["folders"]:
            result["folders"].append(target_dir)

        for i, name in enumerate(b["items"]):
            done += 1
            report(f"Kopijuojama {done} iš {total}...", done, total)
            num_prefix = f"{i + 1:02d}"
            custom_name = title if i == 0 and title else None
            found = matches.get((b["bed_idx"], i))

            if found:
                try:
                    dst_name = format_output_filename(num_prefix, name, found, custom_name=custom_name)
                    safe_copy_file(found, os.path.join(target_dir, dst_name))
                    result["copied"] += 1
                    continue
                except Exception as e:
                    result["errors"].append(f"{name}: {e}")

            result["missing"].append((b["bed_idx"], i, name))

            # Laikiname aplanke paliekame žymą; į HotFolderį nieko pašalinio nerašome
            if not is_hot:
                pid_m = re.search(r'PID[-_:\s]*(\d+)', name, re.IGNORECASE)
                label = custom_name or (f"PID-{pid_m.group(1)}" if pid_m else name)
                clean_lbl = re.sub(r'[\\/*?:"<>|]', "", label).strip()
                try:
                    with open(os.path.join(target_dir, f"{num_prefix}_{clean_lbl}_TRUKSTA.txt"), "w", encoding="utf-8") as df:
                        df.write("Dizainas nerastas tarp nuskaitytu failu aplankuose:\n" + "\n".join(search_roots))
                except Exception:
                    pass

    return result


class ContainerJobWorker(QThread):
    progress = Signal(int, int, str)   # (atlikta, iš viso, tekstas)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self.plan = plan

    def run(self):
        try:
            res = run_container_job(self.plan, lambda d, t, txt: self.progress.emit(d, t, txt))
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(res)


def missing_label(name):
    pid_m = re.search(r'PID[-_:\s]*(\d+)', name or "", re.IGNORECASE)
    return f"PID-{pid_m.group(1)}" if pid_m else (name or "?")


# ----------------- DATA HELPERS FOR JIGS AND MODELS -----------------
def load_jigs_data():
    if not os.path.exists(JIGS_FILE):
        default_jigs = [
            {"id": "jig_1x7", "name": "SLEEVE RĖMAS (1x7 - 7 vnt.)", "rows": 1, "cols": 7, "total_slots": 7},
            {"id": "jig_2x2", "name": "Rėmas 2x2 (4 vnt. - Sleeves / Deskmats)", "rows": 2, "cols": 2, "total_slots": 4},
            {"id": "jig_2x5", "name": "Rėmas 2x5 (10 vnt. - iPad / MacBook)", "rows": 2, "cols": 5, "total_slots": 10},
            {"id": "jig_3x6", "name": "Rėmas 3x6 (18 vnt. - Dėklai)", "rows": 3, "cols": 6, "total_slots": 18},
            {"id": "jig_2x4", "name": "Rėmas 2x4 (8 vnt.)", "rows": 2, "cols": 4, "total_slots": 8}
        ]
        with open(JIGS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_jigs, f, ensure_ascii=False, indent=2)
        return default_jigs
    try:
        with open(JIGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_jigs_data(jigs_list):
    with open(JIGS_FILE, "w", encoding="utf-8") as f:
        json.dump(jigs_list, f, ensure_ascii=False, indent=2)

def load_models_data():
    try:
        with open(MODELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_models_data(models_list):
    with open(MODELS_FILE, "w", encoding="utf-8") as f:
        json.dump(models_list, f, ensure_ascii=False, indent=2)

# ----------------- FLASK API SERVER (QThread) -----------------
class FlaskServerThread(QThread):
    designs_received = Signal(dict)

    def __init__(self, port=5000, host="127.0.0.1"):
        super().__init__()
        self.port = port
        self.host = host
        self.app = Flask(__name__)
        self.server = None
        self.setup_routes()

    def setup_routes(self):
        @self.app.route("/api/health", methods=["GET"])
        def health():
            return jsonify({"status": "ok", "app": "Podbase UV Studio"})

        @self.app.route("/api/models", methods=["GET"])
        def get_models():
            return jsonify(load_models_data())

        @self.app.route("/api/jigs", methods=["GET"])
        def get_jigs():
            return jsonify(load_jigs_data())

        @self.app.before_request
        def check_host():
            # Apsauga nuo DNS rebinding: priimame tik užklausas, adresuotas šiam kompiuteriui
            if self.host in ("127.0.0.1", "localhost"):
                host = (request.host or "").rsplit(":", 1)[0].strip("[]").lower()
                if host not in ("127.0.0.1", "localhost"):
                    return jsonify({"success": False, "error": "Forbidden host"}), 403

        @self.app.route("/api/add_designs", methods=["POST"])
        def add_designs():
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify({"success": False, "error": "Netinkamas JSON"}), 400
            designs = []
            for d in data.get("designs") or []:
                if not isinstance(d, dict):
                    continue
                d = dict(d)
                d["name"] = str(d.get("name") or "").strip()
                url = str(d.get("url") or "").strip()
                # Tik http(s): vietiniai ir UNC keliai (\\serveris\...) iš išorės neleidžiami,
                # kitaip Windows prisijungtų prie svetimo serverio ir atskleistų NTLM duomenis
                d["url"] = url if url.lower().startswith(("http://", "https://")) else ""
                designs.append(d)
            model = data.get("model")
            model = str(model) if isinstance(model, (str, int)) else None
            job_name = data.get("jobName") or data.get("bidNumber")
            job_name = str(job_name) if isinstance(job_name, (str, int)) else None
            
            self.designs_received.emit({
                "designs": designs,
                "model": model,
                "jobName": job_name
            })
            return jsonify({"success": True, "count": len(designs)})

    def run(self):
        try:
            self.server = make_server(self.host, self.port, self.app, threaded=True)
            self.server.serve_forever()
        except Exception as e:
            print(f"[Flask server error]: {e}")

    def stop(self):
        if self.server:
            self.server.shutdown()

# ----------------- RESPONSIVE UV SLOT CARD WITH FLUID DRAG & DROP & ANIMATION -----------------
class UVSlotWidget(ElevatedCardWidget):
    slot_cleared = Signal(int)
    slot_swapped = Signal(int, int)
    slot_duplicated = Signal(int)
    external_items_dropped = Signal(int, list)
    slot_clicked = Signal(int)

    def __init__(self, row, col, parent=None, is_single_row=False):
        super().__init__(parent)
        self.grid_r = row
        self.grid_c = col
        self.item_idx = None
        self.is_single_row = is_single_row
        self.design_name = ""
        self.design_url = ""
        self.current_reply = None
        self.net_mgr = QNetworkAccessManager(self)
        self.drag_start_pos = None

        self.is_blinking = False
        self.blink_state = False
        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(400)
        self.blink_timer.timeout.connect(self._on_blink_step)

        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        if self.is_single_row:
            self.setMinimumHeight(180)
            self.setMaximumHeight(320)
        else:
            self.setMinimumHeight(90)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(2)
        self.badge = QLabel("--", self)
        self.badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        top_bar.addWidget(self.badge)
        top_bar.addStretch(1)

        self.btn_dup = TransparentToolButton(FIF.ADD, self)
        self.btn_dup.setFixedSize(20, 20)
        self.btn_dup.setToolTip("Dublikuoti")
        self.btn_dup.clicked.connect(self.on_dup_clicked)
        self.btn_dup.hide()
        top_bar.addWidget(self.btn_dup)

        self.btn_clear = TransparentToolButton(FIF.DELETE, self)
        self.btn_clear.setFixedSize(20, 20)
        self.btn_clear.setToolTip("Išvalyti")
        self.btn_clear.clicked.connect(self.on_clear_clicked)
        self.btn_clear.hide()
        top_bar.addWidget(self.btn_clear)
        layout.addLayout(top_bar)

        self.thumb_label = QLabel(self)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet("border-radius: 4px; background: transparent;")
        self.thumb_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.thumb_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.thumb_label, 1)

        self.title_label = CaptionLabel("Laisvas", self)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.title_label)

        self.set_empty()

    def start_blinking(self):
        self.is_blinking = True
        self.blink_state = True
        self._apply_blink_style(True)
        if not self.blink_timer.isActive():
            self.blink_timer.start()

    def stop_blinking(self):
        self.is_blinking = False
        if self.blink_timer.isActive():
            self.blink_timer.stop()
        self.refresh_style()

    def _on_blink_step(self):
        if not self.is_blinking:
            self.blink_timer.stop()
            return
        self.blink_state = not self.blink_state
        self._apply_blink_style(self.blink_state)

    def _apply_blink_style(self, highlight_on):
        dark = isDarkTheme()
        if highlight_on:
            self.badge.setStyleSheet("""
                background: #ef4444;
                color: #ffffff;
                font-weight: 900;
                font-size: 11px;
                padding: 1px 6px;
                border-radius: 4px;
            """)
            self.title_label.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 11px;")
            self.setStyleSheet(f"""
                UVSlotWidget {{
                    border: 3px solid #ef4444;
                    border-radius: 8px;
                    background: {'#450a0a' if dark else '#fee2e2'};
                }}
            """)
        else:
            self.badge.setStyleSheet(f"""
                background: {'#991b1b' if dark else '#fca5a5'};
                color: #ffffff;
                font-weight: 800;
                font-size: 11px;
                padding: 1px 6px;
                border-radius: 4px;
            """)
            self.title_label.setStyleSheet(f"color: {'#f87171' if dark else '#dc2626'}; font-size: 11px;")
            self.setStyleSheet(f"""
                UVSlotWidget {{
                    border: 2px dashed #ef4444;
                    border-radius: 8px;
                    background: {'#1e293b' if dark else '#ffffff'};
                }}
            """)

    def on_dup_clicked(self):
        self.stop_blinking()
        if self.item_idx is not None:
            self.slot_duplicated.emit(self.item_idx)

    def on_clear_clicked(self):
        self.stop_blinking()
        if self.item_idx is not None:
            self.slot_cleared.emit(self.item_idx)

    def refresh_style(self):
        if self.is_blinking:
            self._apply_blink_style(self.blink_state)
            return

        dark = isDarkTheme()
        if self.is_occupied():
            self.badge.setStyleSheet("""
                background: linear-gradient(135deg, #10b981, #059669);
                color: #ffffff;
                font-weight: 800;
                font-size: 11px;
                padding: 1px 6px;
                border-radius: 4px;
            """)
            self.title_label.setStyleSheet(f"color: {'#f1f5f9' if dark else '#0f172a'}; font-weight: bold; font-size: 11px;")
            self.setStyleSheet(f"""
                UVSlotWidget {{
                    border: 2px solid #10b981;
                    border-radius: 8px;
                    background: {'#1e293b' if dark else '#ffffff'};
                }}
            """)
        else:
            self.badge.setStyleSheet(f"""
                background: {'#334155' if dark else '#e2e8f0'};
                color: {'#94a3b8' if dark else '#64748b'};
                font-weight: 800;
                font-size: 11px;
                padding: 1px 6px;
                border-radius: 4px;
            """)
            self.thumb_label.setStyleSheet(f"font-size: 24px; color: {'#475569' if dark else '#cbd5e1'}; font-weight: 300;")
            self.title_label.setStyleSheet(f"color: {'#64748b' if dark else '#94a3b8'}; font-size: 11px;")
            self.setStyleSheet(f"""
                UVSlotWidget {{
                    border: 1.5px dashed {'#475569' if dark else '#cbd5e1'};
                    border-radius: 8px;
                    background: {'#0f172a' if dark else '#f8fafc'};
                }}
                UVSlotWidget:hover {{
                    border-color: #10b981;
                    background: {'#1e293b' if dark else '#f1f5f9'};
                }}
            """)

    def set_data(self, name, url="", item_idx=None):
        self.stop_blinking()
        if self.current_reply:
            try:
                self.current_reply.abort()
                self.current_reply.deleteLater()
            except Exception:
                pass
            self.current_reply = None

        self.item_idx = item_idx
        self.design_name = name.strip()
        self.design_url = url.strip()
        self.btn_dup.show()
        self.btn_clear.show()
        self.title_label.setText(self.design_name)
        if item_idx is not None:
            self.badge.setText(f"{item_idx + 1:02d}")
        self.refresh_style()

        thumb_dim = 95 if self.is_single_row else 75
        self.thumb_label.clear()
        self.thumb_label.setPixmap(QPixmap())

        if self.design_url:
            if os.path.exists(self.design_url):
                pix = QPixmap(self.design_url).scaled(thumb_dim, thumb_dim, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.thumb_label.setPixmap(pix)
                self.thumb_label.setText("")
            else:
                self.load_thumbnail(self.design_url)
        else:
            self.thumb_label.setText("🎨")
            self.thumb_label.setStyleSheet("font-size: 22px; color: #10b981;")

    def set_empty(self, placeholder_num=None):
        self.stop_blinking()
        if self.current_reply:
            try:
                self.current_reply.abort()
                self.current_reply.deleteLater()
            except Exception:
                pass
            self.current_reply = None

        self.item_idx = None
        self.design_name = ""
        self.design_url = ""
        self.btn_dup.hide()
        self.btn_clear.hide()
        self.thumb_label.clear()
        self.thumb_label.setPixmap(QPixmap())
        self.thumb_label.setText("+")
        self.title_label.setText("Laisvas")
        if placeholder_num is not None:
            self.badge.setText(f"{placeholder_num:02d}")
        else:
            self.badge.setText("--")
        self.refresh_style()

    def is_occupied(self):
        return bool(self.design_name)

    def load_thumbnail(self, url):
        if self.current_reply:
            try:
                self.current_reply.abort()
                self.current_reply.deleteLater()
            except Exception:
                pass
            self.current_reply = None

        req = QNetworkRequest(QUrl(url))
        self.current_reply = self.net_mgr.get(req)
        self.current_reply.finished.connect(lambda reply=self.current_reply, target_url=url: self.on_thumbnail_loaded(reply, target_url))

    def on_thumbnail_loaded(self, reply, target_url):
        if not self.is_occupied() or self.design_url != target_url:
            try:
                reply.deleteLater()
            except Exception:
                pass
            if self.current_reply == reply:
                self.current_reply = None
            return

        if reply.error() == QNetworkReply.NoError:
            data = reply.readAll()
            img = QImage()
            if img.loadFromData(data):
                thumb_dim = 95 if self.is_single_row else 75
                pix = QPixmap.fromImage(img).scaled(thumb_dim, thumb_dim, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.thumb_label.setPixmap(pix)
                self.thumb_label.setText("")
        
        try:
            reply.deleteLater()
        except Exception:
            pass
        if self.current_reply == reply:
            self.current_reply = None

    def mousePressEvent(self, event):
        self.stop_blinking()
        if event.button() == Qt.LeftButton and self.is_occupied():
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton) or not self.drag_start_pos:
            return
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"uv-slot:{self.item_idx if self.item_idx is not None else -1}")
        drag.setMimeData(mime_data)

        pixmap = self.grab()
        drag.setPixmap(pixmap.scaled(80, 85, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        drag.setHotSpot(QPoint(40, 42))
        drag.exec_(Qt.MoveAction)
        self.drag_start_pos = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasUrls() or event.mimeData().hasHtml() or event.mimeData().hasImage():
            event.acceptProposedAction()
            dark = isDarkTheme()
            self.setStyleSheet(f"UVSlotWidget {{ border: 2.5px solid #3b82f6; background: {'#1e3a8a' if dark else '#eff6ff'}; border-radius: 8px; }}")

    def dragMoveEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasUrls() or event.mimeData().hasHtml() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.refresh_style()

    def dropEvent(self, event):
        self.stop_blinking()
        mime = event.mimeData()
        if mime.hasText() and mime.text().startswith("uv-slot:"):
            try:
                src_idx = int(mime.text().split(":")[1])
                target_idx = self.item_idx if self.item_idx is not None else -1
                if src_idx != -1 and src_idx != target_idx:
                    self.slot_swapped.emit(src_idx, target_idx)
            except Exception as e:
                print(f"dropEvent swap error: {e}")
            event.acceptProposedAction()
        else:
            items = parse_dropped_items(mime)
            if items:
                self.external_items_dropped.emit(self.item_idx if self.item_idx is not None else -1, items)
                event.acceptProposedAction()
        self.refresh_style()


# ----------------- MAIN STUDIO INTERFACE -----------------
class ContainerStudioInterface(QWidget):
    container_generated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.models_data = []
        self.jigs_data = []
        self.active_jig = None
        self.grid_slots = []

        self.beds = [[]]
        self.bed_names = [""]
        self.current_bed_index = 0
        self.missing_items_by_bed = {}
        self._job_worker = None
        self._job_context = None

        self.setAcceptDrops(True)
        self.load_data()
        self.init_ui()

    def load_data(self):
        self.models_data = load_models_data()
        self.jigs_data = load_jigs_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(6)

        # 1. Unified Compact Control Card (Single Row)
        top_card = CardWidget(self)
        top_layout = QHBoxLayout(top_card)
        top_layout.setContentsMargins(12, 6, 12, 6)
        top_layout.setSpacing(8)

        if os.path.exists(ICON_FILE):
            self.lbl_brand_icon = QLabel(self)
            pix = QPixmap(ICON_FILE).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_brand_icon.setPixmap(pix)
            top_layout.addWidget(self.lbl_brand_icon)

        title_brand = StrongBodyLabel("Podbase", self)
        title_brand.setStyleSheet("font-weight: 900; font-size: 15px; color: #10b981;")
        top_layout.addWidget(title_brand)

        sep0 = QFrame(self)
        sep0.setFrameShape(QFrame.VLine)
        sep0.setStyleSheet("color: #cbd5e1;")
        top_layout.addWidget(sep0)

        # Container / Job Name
        top_layout.addWidget(StrongBodyLabel("Konteinerio Pavadinimas:", self))
        self.job_edit = LineEdit(self)
        self.job_edit.setPlaceholderText("pvz. BID-6363")
        self.job_edit.setFixedHeight(30)
        self.job_edit.setMinimumWidth(160)
        self.job_edit.textChanged.connect(self.on_job_name_changed)
        top_layout.addWidget(self.job_edit, 1)

        # Model Selector
        top_layout.addWidget(StrongBodyLabel("Modelis:", self))
        self.model_combo = ComboBox(self)
        self.model_combo.setFixedHeight(30)
        self.model_combo.setMinimumWidth(220)
        self.populate_models_combo()
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        top_layout.addWidget(self.model_combo, 1)

        # Server Pill
        self.status_pill = PillPushButton("🟢 Port 5000", self)
        self.status_pill.setEnabled(False)
        self.status_pill.setFixedHeight(26)
        top_layout.addWidget(self.status_pill)

        main_layout.addWidget(top_card)

        # 2. Compact Bed Navigation & Actions Bar
        bed_nav_card = SimpleCardWidget(self)
        bed_nav_layout = QHBoxLayout(bed_nav_card)
        bed_nav_layout.setContentsMargins(10, 4, 10, 4)
        bed_nav_layout.setSpacing(8)

        self.lbl_jig_name = StrongBodyLabel("📐 Rėmas: Nėra", self)
        self.lbl_jig_name.setStyleSheet("font-size: 12px;")
        bed_nav_layout.addWidget(self.lbl_jig_name)

        sep = QFrame(self)
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #cbd5e1;")
        bed_nav_layout.addWidget(sep)

        self.btn_prev_bed = ToolButton(FIF.LEFT_ARROW, self)
        self.btn_prev_bed.setFixedSize(26, 26)
        self.btn_prev_bed.setToolTip("Ankstesnis stalas")
        self.btn_prev_bed.clicked.connect(self.prev_bed)
        bed_nav_layout.addWidget(self.btn_prev_bed)

        self.lbl_bed_page = StrongBodyLabel("Stalas 1 / 1", self)
        self.lbl_bed_page.setStyleSheet("font-size: 12px; color: #10b981; font-weight: 800; padding: 0 4px;")
        bed_nav_layout.addWidget(self.lbl_bed_page)

        self.btn_next_bed = ToolButton(FIF.RIGHT_ARROW, self)
        self.btn_next_bed.setFixedSize(26, 26)
        self.btn_next_bed.setToolTip("Kitas stalas")
        self.btn_next_bed.clicked.connect(self.next_bed)
        bed_nav_layout.addWidget(self.btn_next_bed)

        self.btn_add_bed = PushButton(FIF.ADD, "Naujas Stalas", self)
        self.btn_add_bed.setFixedHeight(26)
        self.btn_add_bed.clicked.connect(self.add_new_bed)
        bed_nav_layout.addWidget(self.btn_add_bed)

        self.capacity_bar = ProgressBar(self)
        self.capacity_bar.setFixedWidth(110)
        self.capacity_bar.setFixedHeight(12)
        bed_nav_layout.addWidget(self.capacity_bar)

        self.lbl_capacity_text = CaptionLabel("0/0 lizdų (0%)", self)
        self.lbl_capacity_text.setStyleSheet("font-weight: bold; color: #10b981; font-size: 11px;")
        bed_nav_layout.addWidget(self.lbl_capacity_text)

        bed_nav_layout.addStretch(1)

        self.lbl_mode_badge = QLabel("⚡ Tiesioginis HotFolderis", self)
        self.lbl_mode_badge.setStyleSheet("""
            background: #dbeafe;
            color: #1e40af;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
        """)
        bed_nav_layout.addWidget(self.lbl_mode_badge)

        self.btn_add_slot = PushButton(FIF.ADD, "Pridėti", self)
        self.btn_add_slot.setFixedHeight(26)
        self.btn_add_slot.clicked.connect(self.add_manual_design)
        bed_nav_layout.addWidget(self.btn_add_slot)

        self.btn_reverse = PushButton(FIF.SYNC, "Apversti", self)
        self.btn_reverse.setFixedHeight(26)
        self.btn_reverse.clicked.connect(self.reverse_slots_order)
        bed_nav_layout.addWidget(self.btn_reverse)

        self.btn_clear_all = PushButton(FIF.DELETE, "Išvalyti", self)
        self.btn_clear_all.setFixedHeight(26)
        self.btn_clear_all.clicked.connect(self.clear_current_bed)
        bed_nav_layout.addWidget(self.btn_clear_all)

        main_layout.addWidget(bed_nav_card)

        # 3. UV Printer Bed Grid Area (Full Screen Responsive Fill)
        self.grid_widget = CardWidget(self)
        self.grid_widget.setObjectName("uvTableBedGrid")
        self.grid_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.grid_widget.setAcceptDrops(True)
        self.update_bed_container_style()

        self.table_grid_layout = QGridLayout(self.grid_widget)
        self.table_grid_layout.setContentsMargins(10, 10, 10, 10)
        self.table_grid_layout.setSpacing(8)

        main_layout.addWidget(self.grid_widget, 1)

        # 4. Compact Bottom Action Bar
        bottom_card = ElevatedCardWidget(self)
        bottom_card.setFixedHeight(52)
        bot_layout = QHBoxLayout(bottom_card)
        bot_layout.setContentsMargins(14, 6, 14, 6)

        self.btn_open_folder = PushButton(FIF.FOLDER, "📁 Atidaryti aplanką", self)
        self.btn_open_folder.setFixedHeight(36)
        self.btn_open_folder.clicked.connect(self.open_current_output_folder)
        bot_layout.addWidget(self.btn_open_folder)

        bot_layout.addStretch(1)

        self.btn_generate = PushButton(self)
        self.btn_generate.setText("🚀  SUKURTI KONTEINERĮ")
        self.btn_generate.setFixedHeight(38)
        self.btn_generate.setCursor(Qt.PointingHandCursor)
        self.btn_generate.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #059669);
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 800;
                padding: 0 30px;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #047857);
            }
            QPushButton:pressed {
                background: #047857;
            }
        """)
        self.btn_generate.clicked.connect(self.generate_container)
        bot_layout.addWidget(self.btn_generate)

        main_layout.addWidget(bottom_card)

        self.on_model_changed()

    def on_job_name_changed(self, text):
        if 0 <= self.current_bed_index < len(self.bed_names):
            self.bed_names[self.current_bed_index] = text.strip()

    def open_current_output_folder(self):
        m_data = self.get_selected_model_data()
        dest = m_data.get("destination", "") if m_data else ""
        output_mode = m_data.get("output_mode", "temp_folder") if m_data else "temp_folder"
        
        if output_mode == "direct_hotfolder" and dest:
            try:
                os.makedirs(dest, exist_ok=True)
            except Exception:
                pass
            if os.path.exists(dest):
                os.startfile(dest)
                return

        if dest and os.path.exists(dest):
            os.startfile(dest)
            return

        if os.path.exists(DESKTOP_DIR):
            os.startfile(DESKTOP_DIR)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasHtml() or event.mimeData().hasText() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dropEvent(self, event):
        items = parse_dropped_items(event.mimeData())
        if items:
            self.place_dropped_items(items)
            event.acceptProposedAction()

    def update_bed_container_style(self):
        dark = isDarkTheme()
        self.grid_widget.setStyleSheet(f"""
            CardWidget#uvTableBedGrid {{
                background: {'#0f172a' if dark else '#f1f5f9'};
                border: 2px solid {'#334155' if dark else '#cbd5e1'};
                border-radius: 8px;
            }}
        """)
        for row in self.grid_slots:
            for s in row:
                s.refresh_style()

    def populate_models_combo(self):
        self.model_combo.clear()
        for m in self.models_data:
            self.model_combo.addItem(m.get("name", ""))

    def get_selected_model_data(self):
        name = self.model_combo.currentText()
        return next((m for m in self.models_data if m.get("name") == name), None)

    def get_active_jig_capacity(self):
        if self.active_jig:
            return self.active_jig.get("rows", 2) * self.active_jig.get("cols", 5)
        return 10

    def on_model_changed(self):
        m_data = self.get_selected_model_data()
        if not m_data:
            return

        jig_id = m_data.get("jig_id", "jig_2x5")
        jig = next((j for j in self.jigs_data if j.get("id") == jig_id), None)
        if not jig:
            jig = self.jigs_data[0] if self.jigs_data else {"rows": 2, "cols": 5, "name": "Standartinis 2x5"}

        self.active_jig = jig
        self.lbl_jig_name.setText(f"📐 Rėmas: <b>{jig.get('name', 'Standartinis')}</b> ({jig.get('rows', 2)}x{jig.get('cols', 5)})")
        
        output_mode = m_data.get("output_mode", "temp_folder")
        dark = isDarkTheme()

        if output_mode == "direct_hotfolder":
            self.btn_generate.setText("🚀  SIŲSTI TIESIAI Į HOTFOLDERĮ")
            self.btn_open_folder.setText("📁 Atidaryti HotFolderį")
            self.lbl_mode_badge.setText("⚡ Tiesioginis HotFolderis")
            self.lbl_mode_badge.setStyleSheet(f"""
                background: {'#1e3a8a' if dark else '#dbeafe'};
                color: {'#93c5fd' if dark else '#1e40af'};
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 700;
            """)
        else:
            self.btn_generate.setText("🚀  SUKURTI KONTEINERĮ (10 min. laikinas)")
            self.btn_open_folder.setText("📁 Atidaryti aplanką")
            self.lbl_mode_badge.setText("⏳ 10 min. Laikinas aplankas")
            self.lbl_mode_badge.setStyleSheet(f"""
                background: {'#374151' if dark else '#f1f5f9'};
                color: {'#9ca3af' if dark else '#475569'};
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 700;
            """)

        self.build_grid_layout()
        self.render_current_bed()

    def build_grid_layout(self):
        if not self.active_jig:
            return
        rows = self.active_jig.get("rows", 2)
        cols = self.active_jig.get("cols", 5)
        is_single_row = (rows == 1)

        while self.table_grid_layout.count():
            item = self.table_grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for r in range(25):
            self.table_grid_layout.setRowStretch(r, 0)
        for c in range(35):
            self.table_grid_layout.setColumnStretch(c, 0)

        self.grid_slots = []

        if is_single_row:
            self.table_grid_layout.setRowStretch(0, 1)
            self.table_grid_layout.setRowStretch(1, 0)
            self.table_grid_layout.setRowStretch(2, 1)

            row_slots = []
            for c in range(cols):
                self.table_grid_layout.setColumnStretch(c, 1)
                slot = UVSlotWidget(0, c, self.grid_widget, is_single_row=True)
                slot.slot_cleared.connect(self.on_slot_cleared)
                slot.slot_swapped.connect(self.on_slots_swapped)
                slot.slot_duplicated.connect(self.on_slot_duplicated)
                slot.external_items_dropped.connect(self.on_external_items_dropped)
                self.table_grid_layout.addWidget(slot, 1, c)
                row_slots.append(slot)
            self.grid_slots.append(row_slots)
        else:
            for r in range(rows):
                self.table_grid_layout.setRowStretch(r, 1)
            for c in range(cols):
                self.table_grid_layout.setColumnStretch(c, 1)

            for r in range(rows):
                row_slots = []
                for c in range(cols):
                    slot = UVSlotWidget(r, c, self.grid_widget, is_single_row=False)
                    slot.slot_cleared.connect(self.on_slot_cleared)
                    slot.slot_swapped.connect(self.on_slots_swapped)
                    slot.slot_duplicated.connect(self.on_slot_duplicated)
                    slot.external_items_dropped.connect(self.on_external_items_dropped)
                    self.table_grid_layout.addWidget(slot, r, c)
                    row_slots.append(slot)
                self.grid_slots.append(row_slots)

    def render_current_bed(self):
        if not self.active_jig:
            return

        rows = self.active_jig.get("rows", 2)
        cols = self.active_jig.get("cols", 5)

        if self.current_bed_index >= len(self.beds):
            self.current_bed_index = max(0, len(self.beds) - 1)

        while len(self.bed_names) < len(self.beds):
            idx = len(self.bed_names)
            base_name = self.bed_names[0] if self.bed_names and self.bed_names[0] else ""
            new_name = f"{base_name}_{idx + 1}" if base_name else f"Stalas_{idx + 1}"
            self.bed_names.append(new_name)

        current_name = self.bed_names[self.current_bed_index] if self.current_bed_index < len(self.bed_names) else ""
        self.job_edit.blockSignals(True)
        self.job_edit.setText(current_name)
        self.job_edit.blockSignals(False)

        current_items = [it for it in self.beds[self.current_bed_index] if it and it.get("name")]
        num_items = len(current_items)
        missing_indices = self.missing_items_by_bed.get(self.current_bed_index, set())

        # 1. Reset all slots to completely empty
        for r in range(rows):
            for c in range(cols):
                if r < len(self.grid_slots) and c < len(self.grid_slots[r]):
                    self.grid_slots[r][c].set_empty()

        # 2. Map items dynamically to grid coordinates
        k_bottom = min(num_items, cols)
        for i in range(num_items):
            it = current_items[i]
            if i < cols:
                r = rows - 1
                c = (k_bottom - 1) - i
            else:
                row_from_bottom = i // cols
                r = (rows - 1) - row_from_bottom
                c = (cols - 1) - (i % cols)

            if 0 <= r < len(self.grid_slots) and 0 <= c < len(self.grid_slots[r]):
                slot_w = self.grid_slots[r][c]
                slot_w.set_data(it.get("name", ""), it.get("url", ""), item_idx=i)
                if i in missing_indices:
                    slot_w.start_blinking()
                else:
                    slot_w.stop_blinking()

        self.update_bed_navigation()

    def save_current_bed_state(self):
        while len(self.bed_names) < len(self.beds):
            self.bed_names.append("")
        if self.current_bed_index < len(self.bed_names):
            self.bed_names[self.current_bed_index] = self.job_edit.text().strip()

    def update_bed_navigation(self):
        total_beds = len(self.beds)
        curr_page = self.current_bed_index + 1

        self.lbl_bed_page.setText(f"Stalas {curr_page} iš {total_beds}")
        self.btn_prev_bed.setEnabled(self.current_bed_index > 0)
        self.btn_next_bed.setEnabled(self.current_bed_index < total_beds - 1)

        capacity = self.get_active_jig_capacity()
        occupied = len([it for it in self.beds[self.current_bed_index] if it and it.get("name")])
        pct = int((occupied / capacity) * 100) if capacity > 0 else 0

        self.capacity_bar.setValue(pct)
        self.lbl_capacity_text.setText(f"{occupied}/{capacity} ({pct}%)")

    def prev_bed(self):
        self.save_current_bed_state()
        if self.current_bed_index > 0:
            self.current_bed_index -= 1
            self.render_current_bed()

    def next_bed(self):
        self.save_current_bed_state()
        if self.current_bed_index < len(self.beds) - 1:
            self.current_bed_index += 1
            self.render_current_bed()

    def add_new_bed(self):
        self.save_current_bed_state()
        self.beds.append([])

        base_name = self.bed_names[0] if self.bed_names and self.bed_names[0] else ""
        new_bed_num = len(self.beds)
        new_name = f"{base_name}_{new_bed_num}" if base_name else f"Stalas_{new_bed_num}"
        self.bed_names.append(new_name)

        self.current_bed_index = len(self.beds) - 1
        self.render_current_bed()
        InfoBar.success(
            title="Pridėtas naujas stalas",
            content=f"Sukurtas papildomas stalas #{self.current_bed_index + 1} ({new_name})!",
            orient=Qt.Horizontal,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self
        )

    def on_slot_cleared(self, item_idx):
        self.missing_items_by_bed.clear()
        if 0 <= self.current_bed_index < len(self.beds):
            curr_items = self.beds[self.current_bed_index]
            if 0 <= item_idx < len(curr_items):
                del curr_items[item_idx]
                self.render_current_bed()

    def on_slots_swapped(self, src_idx, target_idx):
        self.missing_items_by_bed.clear()
        if 0 <= self.current_bed_index < len(self.beds):
            curr_items = self.beds[self.current_bed_index]
            if 0 <= src_idx < len(curr_items):
                if target_idx == -1 or target_idx >= len(curr_items):
                    item = curr_items.pop(src_idx)
                    curr_items.append(item)
                elif 0 <= target_idx < len(curr_items):
                    curr_items[src_idx], curr_items[target_idx] = curr_items[target_idx], curr_items[src_idx]
                self.render_current_bed()

    def on_slot_duplicated(self, item_idx):
        self.missing_items_by_bed.clear()
        if 0 <= self.current_bed_index < len(self.beds):
            curr_items = self.beds[self.current_bed_index]
            if 0 <= item_idx < len(curr_items):
                dup_item = dict(curr_items[item_idx])
                capacity = self.get_active_jig_capacity()

                if len(curr_items) < capacity:
                    curr_items.append(dup_item)
                    self.render_current_bed()
                    InfoBar.success(
                        title="Dizainas dublikuotas",
                        content=f"Dizainas sėkmingai pridėtas į stalo sąrašą!",
                        position=InfoBarPosition.TOP_RIGHT,
                        duration=2500,
                        parent=self
                    )
                else:
                    self.save_current_bed_state()
                    next_bed_idx = self.current_bed_index + 1
                    if next_bed_idx >= len(self.beds):
                        self.beds.append([])
                        base_name = self.bed_names[0] if self.bed_names and self.bed_names[0] else ""
                        self.bed_names.append(f"{base_name}_{len(self.beds)}" if base_name else f"Stalas_{len(self.beds)}")

                    self.current_bed_index = next_bed_idx
                    self.beds[self.current_bed_index].append(dup_item)
                    self.render_current_bed()
                    InfoBar.info(
                        title="Rėmas buvo pilnas",
                        content=f"Dublikuota į naują stalą #{self.current_bed_index + 1}!",
                        position=InfoBarPosition.TOP_RIGHT,
                        duration=3000,
                        parent=self
                    )

    def on_external_items_dropped(self, target_idx, items):
        self.missing_items_by_bed.clear()
        if not items:
            return

        curr_items = self.beds[self.current_bed_index]
        if len(items) == 1 and target_idx != -1 and 0 <= target_idx < len(curr_items):
            curr_items[target_idx] = items[0]
            self.render_current_bed()
            InfoBar.success(
                title="Dizainas pakeistas",
                content=f"Lizdas #{target_idx + 1} sėkmingai pakeistas nauju dizainu!",
                position=InfoBarPosition.TOP_RIGHT,
                duration=2500,
                parent=self
            )
        else:
            self.place_dropped_items(items)

    def place_dropped_items(self, items):
        if not items:
            return

        self.missing_items_by_bed.clear()
        self.save_current_bed_state()
        capacity = self.get_active_jig_capacity()

        for it in items:
            curr_items = self.beds[self.current_bed_index]
            if len(curr_items) < capacity:
                curr_items.append(it)
            else:
                self.save_current_bed_state()
                next_bed_idx = self.current_bed_index + 1
                if next_bed_idx >= len(self.beds):
                    self.beds.append([])
                    base_name = self.bed_names[0] if self.bed_names and self.bed_names[0] else ""
                    self.bed_names.append(f"{base_name}_{len(self.beds)}" if base_name else f"Stalas_{len(self.beds)}")
                self.current_bed_index = next_bed_idx
                self.beds[self.current_bed_index].append(it)

        self.render_current_bed()
        InfoBar.success(
            title="Dizainai įkelti",
            content=f"Sėkmingai įkelta {len(items)} vnt. dizainų!",
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self
        )

    def add_manual_design(self):
        self.missing_items_by_bed.clear()
        capacity = self.get_active_jig_capacity()
        curr_items = self.beds[self.current_bed_index]

        if len(curr_items) < capacity:
            curr_items.append({"name": f"PID-{1000 + len(curr_items) + 1:04d}", "url": ""})
            self.render_current_bed()
        else:
            self.add_new_bed()
            self.beds[self.current_bed_index].append({"name": "PID-1001", "url": ""})
            self.render_current_bed()

    def clear_current_bed(self):
        self.missing_items_by_bed.clear()
        self.beds[self.current_bed_index] = []
        self.render_current_bed()

    def reverse_slots_order(self):
        self.missing_items_by_bed.clear()
        self.beds[self.current_bed_index].reverse()
        self.render_current_bed()

    def set_data_from_extension(self, payload):
        self.missing_items_by_bed.clear()
        designs = payload.get("designs", [])
        model = payload.get("model", None)
        job_name = payload.get("jobName", None) or ""

        matched_idx = -1
        if model:
            for idx, m in enumerate(self.models_data):
                m_name = m.get("name", "")
                aliases = m.get("aliases", [])
                if model.lower() == m_name.lower() or any(model.lower() == a.lower() for a in aliases) or any(a.lower() in model.lower() for a in aliases):
                    matched_idx = idx
                    break

        current_idx = self.model_combo.currentIndex()
        is_same_model = (matched_idx != -1 and matched_idx == current_idx)

        capacity = self.get_active_jig_capacity()

        if is_same_model:
            self.save_current_bed_state()

            for d in designs:
                placed = False
                for b_idx in range(len(self.beds)):
                    bed_items = self.beds[b_idx]
                    if len(bed_items) < capacity:
                        bed_items.append(d)
                        placed = True
                        break

                if not placed:
                    new_b_num = len(self.beds) + 1
                    self.beds.append([d])
                    new_b_name = f"{job_name}_{new_b_num}" if job_name else f"Stalas_{new_b_num}"
                    self.bed_names.append(new_b_name)

            self.render_current_bed()
            InfoBar.info(
                title="Pridėta prie esamo užsakymo",
                content=f"Pridėta {len(designs)} naujų dizainų! Iš viso stalų: {len(self.beds)}.",
                orient=Qt.Horizontal,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3500,
                parent=self
            )
        else:
            if matched_idx != -1:
                self.model_combo.setCurrentIndex(matched_idx)

            capacity = self.get_active_jig_capacity()

            self.beds = []
            self.bed_names = []
            num_beds = max(1, math.ceil(len(designs) / capacity)) if capacity > 0 else 1

            for b in range(num_beds):
                start_i = b * capacity
                end_i = start_i + capacity
                chunk = designs[start_i:end_i]
                self.beds.append(chunk)

                if num_beds == 1:
                    self.bed_names.append(job_name)
                else:
                    self.bed_names.append(f"{job_name}_{b+1}" if job_name else f"Stalas_{b+1}")

            self.current_bed_index = 0
            self.render_current_bed()

            msg = f"Įkelta {len(designs)} dizainų užsakymui {job_name or ''}!"
            if len(self.beds) > 1:
                msg += f" ({len(self.beds)} stalai)."

            InfoBar.success(
                title="Gauti duomenys iš naršyklės",
                content=msg,
                orient=Qt.Horizontal,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3500,
                parent=self
            )

    def load_from_history_entry(self, entry):
        self.missing_items_by_bed.clear()
        job_name = entry.get("job_name", "")
        model_name = entry.get("model_name", "")
        beds = entry.get("beds", [[]])
        bed_names = entry.get("bed_names", [])

        idx = self.model_combo.findText(model_name)
        if idx != -1:
            self.model_combo.setCurrentIndex(idx)

        self.beds = beds if beds else [[]]
        if bed_names and len(bed_names) == len(self.beds):
            self.bed_names = bed_names
        else:
            self.bed_names = []
            for i in range(len(self.beds)):
                if len(self.beds) == 1:
                    self.bed_names.append(job_name)
                else:
                    self.bed_names.append(f"{job_name}_{i+1}" if job_name else f"Stalas_{i+1}")

        self.current_bed_index = 0
        self.render_current_bed()

        InfoBar.success(
            title="Istorijos užsakymas įkeltas",
            content=f"Užsakymas '{job_name}' sėkmingai atkurtas redagavimui ir pergeneravimui!",
            position=InfoBarPosition.TOP_RIGHT,
            duration=3500,
            parent=self
        )

    def generate_container(self):
        if self._job_worker is not None and self._job_worker.isRunning():
            return

        self.save_current_bed_state()
        self.missing_items_by_bed.clear()

        valid_beds = []
        for idx, bed_items in enumerate(self.beds):
            occupied = [it for it in bed_items if it is not None and it.get("name")]
            if occupied:
                valid_beds.append((idx + 1, occupied))

        if not valid_beds:
            InfoBar.warning(
                title="Tuščias stalas",
                content="Prieš generuodami, pridėkite bent vieną dizainą į stalo lizdą!",
                position=InfoBarPosition.TOP,
                parent=self
            )
            return

        m_data = self.get_selected_model_data()
        if not m_data:
            InfoBar.error(
                title="Klaida",
                content="Nepasirinktas joks modelis!",
                position=InfoBarPosition.TOP,
                parent=self
            )
            return

        source_dir = m_data.get("source", "").strip()
        dest_dir = m_data.get("destination", "").strip()
        output_mode = m_data.get("output_mode", "temp_folder")
        is_direct_hotfolder = (output_mode == "direct_hotfolder")

        if is_direct_hotfolder and not dest_dir:
            InfoBar.error(
                title="Nenurodytas HotFolderio kelias!",
                content="Šiam modeliui nustatymuose nenurodytas 'Paskirtis (HotFolderis)' kelias.\nNustatykite jį Nustatymų skirtuke.",
                orient=Qt.Horizontal,
                position=InfoBarPosition.TOP_RIGHT,
                duration=6000,
                parent=self
            )
            return

        beds_plan = []
        for bed_num, occupied_items in valid_beds:
            real_bed_idx = bed_num - 1
            if real_bed_idx < len(self.bed_names) and self.bed_names[real_bed_idx]:
                bed_title = self.bed_names[real_bed_idx]
            else:
                bed_title = f"Stalas_{bed_num}"
            clean_bed_title = safe_folder_name(bed_title, f"Stalas_{bed_num}")
            beds_plan.append({
                "bed_idx": real_bed_idx,
                "title": clean_bed_title,
                "items": [it.get("name", "") for it in occupied_items]
            })

        plan = {
            "source_dir": source_dir,
            "dest_dir": dest_dir,
            "hotfolder": is_direct_hotfolder,
            "beds": beds_plan
        }

        main_job_name = self.bed_names[0] if self.bed_names and self.bed_names[0] else m_data.get("name", "Job")
        self._job_context = {
            "is_hot": is_direct_hotfolder,
            "dest_dir": dest_dir,
            "bed_count": len(valid_beds),
            "beds_snapshot": [[(it or {}).get("name") for it in bed] for bed in self.beds],
            "history": {
                "id": f"hist_{int(time.time())}",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "job_name": main_job_name,
                "bed_names": list(self.bed_names),
                "model_name": m_data.get("name", ""),
                "jig_name": self.active_jig.get("name", "") if self.active_jig else "",
                "output_mode": output_mode,
                "total_beds": len(valid_beds),
                "total_designs": sum(len(items) for _, items in valid_beds),
                "beds": copy.deepcopy(self.beds),
                "source_dir": source_dir,
                "dest_dir": dest_dir
            }
        }

        self._set_generate_busy(True)
        worker = ContainerJobWorker(plan, self)
        worker.progress.connect(self._on_job_progress)
        worker.finished_ok.connect(self._on_job_finished)
        worker.failed.connect(self._on_job_failed)
        self._job_worker = worker
        worker.start()

    def _set_generate_busy(self, busy):
        self.btn_generate.setEnabled(not busy)
        if busy:
            self.btn_generate.setText("⏳  Ieškoma spaudos failų...")
            return
        m_data = self.get_selected_model_data() or {}
        if m_data.get("output_mode", "temp_folder") == "direct_hotfolder":
            self.btn_generate.setText("🚀  SIŲSTI TIESIAI Į HOTFOLDERĮ")
        else:
            self.btn_generate.setText("🚀  SUKURTI KONTEINERĮ (10 min. laikinas)")

    def _on_job_progress(self, done, total, text):
        self.btn_generate.setText(f"⏳  {text}")

    def _on_job_failed(self, err_msg):
        self._set_generate_busy(False)
        InfoBar.error(
            title="Klaida kuriant konteinerį!",
            content=err_msg,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=-1,
            parent=self
        )

    def _on_job_finished(self, res):
        self._set_generate_busy(False)
        ctx = self._job_context or {}
        is_hot = ctx.get("is_hot", False)

        history_entry = dict(ctx.get("history", {}))
        history_entry["folders"] = res.get("folders", [])
        try:
            add_history_entry(history_entry)
        except Exception as e:
            print(f"[history klaida]: {e}")
        self.container_generated.emit()

        missing = res.get("missing", [])
        errors = res.get("errors", [])

        # Mirksintys lizdai – tik jei stalas nepasikeitė, kol vyko kopijavimas
        current_snapshot = [[(it or {}).get("name") for it in bed] for bed in self.beds]
        if missing and current_snapshot == ctx.get("beds_snapshot"):
            self.missing_items_by_bed.clear()
            for bed_idx, item_idx, _name in missing:
                self.missing_items_by_bed.setdefault(bed_idx, set()).add(item_idx)
            self.current_bed_index = min(self.missing_items_by_bed.keys())
        self.render_current_bed()

        if not is_hot:
            for fold in res.get("folders", []):
                try:
                    if os.path.exists(fold):
                        os.startfile(fold)
                except Exception as e:
                    print(f"startfile error: {e}")

        if missing:
            names = ", ".join(missing_label(n) for _, _, n in missing)
            content = f"Nerasti {len(missing)} failai: {names}\nNukopijuota: {res.get('copied', 0)}. Trūkstami lizdai mirksi raudonai."
            if errors:
                content += "\nKopijavimo klaidos: " + "; ".join(errors[:3])
            InfoBar.error(
                title="⚠️ DĖMESIO: Ne visi failai išsiųsti!",
                content=content,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=-1,
                parent=self
            )
            return

        if is_hot:
            msg = f"Failai ({res.get('copied', 0)} vnt.) sėkmingai nusiųsti tiesiai į HotFolderį!\n📁 {ctx.get('dest_dir', '')}"
        else:
            msg = f"Konteinerio aplankas sukurtas ({ctx.get('bed_count', 0)} stalai, {res.get('copied', 0)} failų).\n⏳ Po 10 min. laikinas aplankas automatiškai išsivalys!"
        InfoBar.success(
            title="Konteineris sukurtas!",
            content=msg,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=4500,
            parent=self
        )

# ----------------- HISTORY INTERFACE -----------------
class HistoryInterface(QWidget):
    load_order_to_studio = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.history_items = []
        self.filtered_items = []
        self.selected_item = None
        self._job_worker = None
        self._regen_btn_text = "⚡ Greitas nusiuntimas į aplanką"
        self.init_ui()
        self.reload_history()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        top_bar = QHBoxLayout()
        top_bar.addWidget(TitleLabel("📜 Generavimo Istorija", self))
        top_bar.addStretch(1)

        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("🔍 Ieškoti pagal užsakymą, modelį...")
        self.search_edit.setFixedWidth(260)
        self.search_edit.textChanged.connect(self.filter_history)
        top_bar.addWidget(self.search_edit)

        self.btn_refresh = PushButton(FIF.SYNC, "Atnaujinti", self)
        self.btn_refresh.clicked.connect(self.reload_history)
        top_bar.addWidget(self.btn_refresh)

        self.btn_clear_history = PushButton(FIF.DELETE, "Išvalyti istoriją", self)
        self.btn_clear_history.clicked.connect(self.clear_all_history)
        top_bar.addWidget(self.btn_clear_history)

        main_layout.addLayout(top_bar)

        splitter = QSplitter(Qt.Horizontal, self)

        table_card = CardWidget(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(8, 8, 8, 8)

        self.table = TableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Data ir Laikas", "Užsakymas", "Modelis", "Stalai", "Dizainai"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.cellClicked.connect(self.on_row_selected)
        table_layout.addWidget(self.table)

        splitter.addWidget(table_card)

        self.detail_card = ElevatedCardWidget(self)
        self.detail_card.setMinimumWidth(340)
        detail_layout = QVBoxLayout(self.detail_card)
        detail_layout.setContentsMargins(16, 14, 16, 14)
        detail_layout.setSpacing(10)

        self.lbl_detail_title = SubtitleLabel("Pasirinkite įrašą", self)
        detail_layout.addWidget(self.lbl_detail_title)

        self.lbl_detail_info = BodyLabel("Pasirinkite istorinį užsakymą kairėje lentelėje, kad pamatytumėte detales ir pergeneruotumėte.", self)
        self.lbl_detail_info.setWordWrap(True)
        detail_layout.addWidget(self.lbl_detail_info)

        self.preview_scroll = SmoothScrollArea(self)
        self.preview_scroll.setWidgetResizable(True)
        self.preview_container = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(4, 4, 4, 4)
        self.preview_layout.setSpacing(4)
        self.preview_scroll.setWidget(self.preview_container)
        detail_layout.addWidget(self.preview_scroll, 1)

        actions_box = QVBoxLayout()
        actions_box.setSpacing(6)

        self.btn_load_to_studio = PrimaryPushButton(FIF.EDIT, "🔄 Įkelti į redaktorių ir pergeneruoti", self)
        self.btn_load_to_studio.setFixedHeight(36)
        self.btn_load_to_studio.clicked.connect(self.load_selected_to_studio)
        self.btn_load_to_studio.setEnabled(False)
        actions_box.addWidget(self.btn_load_to_studio)

        self.btn_quick_regenerate = PushButton(FIF.SYNC, "⚡ Greitas nusiuntimas į aplanką", self)
        self.btn_quick_regenerate.setFixedHeight(34)
        self.btn_quick_regenerate.clicked.connect(self.quick_regenerate_selected)
        self.btn_quick_regenerate.setEnabled(False)
        actions_box.addWidget(self.btn_quick_regenerate)

        self.btn_open_saved_folder = PushButton(FIF.FOLDER, "📁 Atidaryti aplanką", self)
        self.btn_open_saved_folder.setFixedHeight(34)
        self.btn_open_saved_folder.clicked.connect(self.open_selected_folder)
        self.btn_open_saved_folder.setEnabled(False)
        actions_box.addWidget(self.btn_open_saved_folder)

        self.btn_del_entry = PushButton(FIF.DELETE, "Ištrinti šį įrašą", self)
        self.btn_del_entry.setFixedHeight(30)
        self.btn_del_entry.clicked.connect(self.delete_selected_entry)
        self.btn_del_entry.setEnabled(False)
        actions_box.addWidget(self.btn_del_entry)

        detail_layout.addLayout(actions_box)
        splitter.addWidget(self.detail_card)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter, 1)

    def reload_history(self):
        self.history_items = load_history_data()
        self.filter_history(self.search_edit.text().strip())

    def filter_history(self, search_text=""):
        s = search_text.lower()
        if not s:
            self.filtered_items = list(self.history_items)
        else:
            self.filtered_items = [
                it for it in self.history_items
                if s in it.get("job_name", "").lower()
                or s in it.get("model_name", "").lower()
                or s in it.get("timestamp", "").lower()
            ]

        self.table.setRowCount(len(self.filtered_items))
        for row, it in enumerate(self.filtered_items):
            self.table.setItem(row, 0, QTableWidgetItem(it.get("timestamp", "")))
            self.table.setItem(row, 1, QTableWidgetItem(it.get("job_name", "")))
            self.table.setItem(row, 2, QTableWidgetItem(it.get("model_name", "")))
            self.table.setItem(row, 3, QTableWidgetItem(f"{it.get('total_beds', 1)} st."))
            self.table.setItem(row, 4, QTableWidgetItem(f"{it.get('total_designs', 0)} vnt."))

        if self.filtered_items:
            self.table.selectRow(0)
            self.on_row_selected(0, 0)
        else:
            self.selected_item = None
            self.lbl_detail_title.setText("Istorija tuščia")
            self.lbl_detail_info.setText("Nėra atliktų konteinerių generavimų.")
            self.clear_preview_layout()
            self.btn_load_to_studio.setEnabled(False)
            self.btn_quick_regenerate.setEnabled(False)
            self.btn_open_saved_folder.setEnabled(False)
            self.btn_del_entry.setEnabled(False)

    def clear_preview_layout(self):
        while self.preview_layout.count():
            item = self.preview_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def on_row_selected(self, row, col):
        if 0 <= row < len(self.filtered_items):
            self.selected_item = self.filtered_items[row]
            it = self.selected_item

            self.lbl_detail_title.setText(f"🏷️ {it.get('job_name', 'Užsakymas')}")
            info_str = f"<b>Data:</b> {it.get('timestamp')}<br>" \
                       f"<b>Modelis:</b> {it.get('model_name')}<br>" \
                       f"<b>Rėmas:</b> {it.get('jig_name')}<br>" \
                       f"<b>Stalai:</b> {it.get('total_beds')} st. | <b>Dizainai:</b> {it.get('total_designs')} vnt."
            self.lbl_detail_info.setText(info_str)

            self.clear_preview_layout()
            beds = it.get("beds", [])
            bed_names = it.get("bed_names", [])
            for b_idx, bed_items in enumerate(beds):
                b_name = bed_names[b_idx] if b_idx < len(bed_names) and bed_names[b_idx] else f"Stalas #{b_idx + 1}"
                b_lbl = StrongBodyLabel(f"{b_name}:", self.preview_container)
                b_lbl.setStyleSheet("color: #10b981; font-weight: bold; margin-top: 4px;")
                self.preview_layout.addWidget(b_lbl)

                for s_idx, d in enumerate(bed_items):
                    if d:
                        row_lbl = BodyLabel(f"  {s_idx + 1:02d}. {d.get('name')}", self.preview_container)
                        row_lbl.setStyleSheet("font-size: 11px;")
                        self.preview_layout.addWidget(row_lbl)

            self.preview_layout.addStretch(1)

            self.btn_load_to_studio.setEnabled(True)
            self.btn_quick_regenerate.setEnabled(True)
            self.btn_open_saved_folder.setEnabled(True)
            self.btn_del_entry.setEnabled(True)

    def load_selected_to_studio(self):
        if self.selected_item:
            self.load_order_to_studio.emit(self.selected_item)

    def quick_regenerate_selected(self):
        if not self.selected_item:
            return
        if self._job_worker is not None and self._job_worker.isRunning():
            return

        it = self.selected_item
        source_dir = it.get("source_dir", "").strip()
        dest_dir = it.get("dest_dir", "").strip()
        job_title = it.get("job_name", "Job")
        beds = it.get("beds", [])
        bed_names = it.get("bed_names", [])
        is_direct_hotfolder = (it.get("output_mode", "temp_folder") == "direct_hotfolder")

        if is_direct_hotfolder and not dest_dir:
            InfoBar.error(
                title="Nenurodytas HotFolderis!",
                content="Šiam modeliui nenurodytas paskirties HotFolderis.",
                position=InfoBarPosition.TOP_RIGHT,
                parent=self
            )
            return

        valid_beds = []
        for idx, bed_items in enumerate(beds):
            occupied = [x for x in bed_items if x and x.get("name")]
            if occupied:
                valid_beds.append((idx + 1, occupied))

        beds_plan = []
        for bed_num, occupied_items in valid_beds:
            real_bed_idx = bed_num - 1
            if real_bed_idx < len(bed_names) and bed_names[real_bed_idx]:
                bed_title = bed_names[real_bed_idx]
            else:
                bed_title = f"{job_title}_{bed_num}" if len(valid_beds) > 1 else job_title
            clean_bed_title = safe_folder_name(bed_title, f"Stalas_{bed_num}")
            beds_plan.append({
                "bed_idx": real_bed_idx,
                "title": clean_bed_title,
                "items": [x.get("name", "") for x in occupied_items]
            })

        plan = {
            "source_dir": source_dir,
            "dest_dir": dest_dir,
            "hotfolder": is_direct_hotfolder,
            "beds": beds_plan
        }

        self.btn_quick_regenerate.setEnabled(False)
        self.btn_quick_regenerate.setText("⏳ Siunčiama...")
        worker = ContainerJobWorker(plan, self)
        worker.progress.connect(lambda d, t, txt: self.btn_quick_regenerate.setText(f"⏳ {txt}"))
        worker.finished_ok.connect(lambda res: self._on_regenerate_finished(res, job_title, is_direct_hotfolder))
        worker.failed.connect(self._on_regenerate_failed)
        self._job_worker = worker
        worker.start()

    def _restore_regenerate_button(self):
        self.btn_quick_regenerate.setText(self._regen_btn_text)
        self.btn_quick_regenerate.setEnabled(self.selected_item is not None)

    def _on_regenerate_failed(self, err_msg):
        self._restore_regenerate_button()
        InfoBar.error(
            title="Klaida pergeneruojant!",
            content=err_msg,
            position=InfoBarPosition.TOP_RIGHT,
            duration=-1,
            parent=self
        )

    def _on_regenerate_finished(self, res, job_title, is_direct_hotfolder):
        self._restore_regenerate_button()

        if not is_direct_hotfolder:
            for fold in res.get("folders", []):
                try:
                    if os.path.exists(fold):
                        os.startfile(fold)
                except Exception:
                    pass

        missing = res.get("missing", [])
        if missing:
            names = ", ".join(missing_label(n) for _, _, n in missing)
            InfoBar.error(
                title="⚠️ Ne visi failai rasti!",
                content=f"Užsakymas '{job_title}': nukopijuota {res.get('copied', 0)}, nerasta {len(missing)}: {names}",
                position=InfoBarPosition.TOP_RIGHT,
                duration=-1,
                parent=self
            )
            return

        if is_direct_hotfolder:
            msg = f"Užsakymas '{job_title}' nukopijuotas tiesiai į HotFolderį ({res.get('copied', 0)} failų)."
        else:
            msg = f"Užsakymas '{job_title}' nukopijuotas į laikiną aplanką ({res.get('copied', 0)} failų)."
        InfoBar.success(
            title="Sėkmingai atkurta!",
            content=msg,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3500,
            parent=self
        )

    def open_selected_folder(self):
        if not self.selected_item:
            return
        dest_dir = self.selected_item.get("dest_dir", "").strip()
        output_mode = self.selected_item.get("output_mode", "temp_folder")

        if output_mode == "direct_hotfolder" and dest_dir and os.path.exists(dest_dir):
            os.startfile(dest_dir)
            return

        folders = self.selected_item.get("folders", [])
        opened = False
        for f in folders:
            if os.path.exists(f):
                os.startfile(f)
                opened = True
        if not opened:
            if os.path.exists(DESKTOP_DIR):
                os.startfile(DESKTOP_DIR)

    def delete_selected_entry(self):
        if not self.selected_item:
            return
        target_id = self.selected_item.get("id")
        self.history_items = [it for it in self.history_items if it.get("id") != target_id]
        save_history_data(self.history_items)
        self.filter_history(self.search_edit.text().strip())

    def clear_all_history(self):
        self.history_items = []
        save_history_data([])
        self.filter_history("")
        InfoBar.info(
            title="Istorija išvalyta",
            content="Visi istoriniai generavimo įrašai sėkmingai išvalyti.",
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500,
            parent=self
        )


# ----------------- ADVANCED SETTINGS INTERFACE -----------------
class ModelsSettingsInterface(QWidget):
    settings_updated = Signal()
    theme_changed = Signal(str)

    def __init__(self, updater=None, parent=None):
        super().__init__(parent)
        self.updater = updater
        self.models_list = []
        self.jigs_list = []
        self.current_model_idx = -1
        self.current_jig_idx = -1
        self.load_all_data()
        self.init_ui()

    def load_all_data(self):
        self.models_list = load_models_data()
        self.jigs_list = load_jigs_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        top_box = QHBoxLayout()
        top_box.addWidget(TitleLabel("Nustatymai", self))
        top_box.addStretch(1)

        top_box.addWidget(StrongBodyLabel("🎨 Tema:", self))
        self.theme_segment = SegmentedWidget(self)
        self.theme_segment.addItem("light", "☀️ Šviesi", lambda: self.on_theme_selected("LIGHT"))
        self.theme_segment.addItem("dark", "🌙 Tamsi", lambda: self.on_theme_selected("DARK"))

        cfg = load_app_config()
        curr_th = cfg.get("theme", "LIGHT").lower()
        self.theme_segment.setCurrentItem(curr_th if curr_th in ("light", "dark") else "light")
        top_box.addWidget(self.theme_segment)

        top_box.addSpacing(14)

        self.btn_save_all = PrimaryPushButton(FIF.SAVE, "💾 Išsaugoti nustatymus", self)
        self.btn_save_all.setFixedHeight(34)
        self.btn_save_all.clicked.connect(self.save_all_data)
        top_box.addWidget(self.btn_save_all)
        main_layout.addLayout(top_box)

        self.segmented_nav = SegmentedWidget(self)
        self.stack = QStackedWidget(self)

        self.models_tab = QWidget()
        self.init_models_tab(self.models_tab)
        self.stack.addWidget(self.models_tab)

        self.jigs_tab = QWidget()
        self.init_jigs_tab(self.jigs_tab)
        self.stack.addWidget(self.jigs_tab)

        self.updates_tab = QWidget()
        self.init_updates_tab(self.updates_tab)
        self.stack.addWidget(self.updates_tab)

        self.search_tab = QWidget()
        self.init_search_tab(self.search_tab)
        self.stack.addWidget(self.search_tab)

        self.segmented_nav.addItem("modelsTab", "📱 Modelių ir Žaliavų Nustatymai", lambda: self.stack.setCurrentIndex(0))
        self.segmented_nav.addItem("jigsTab", "📐 Rėmų (Jigs / Stalo) Valdymas", lambda: self.stack.setCurrentIndex(1))
        self.segmented_nav.addItem("updatesTab", "🚀 Atnaujinimai ir Versija", lambda: self.stack.setCurrentIndex(2))
        self.segmented_nav.addItem("searchTab", "📂 Paieškos Aplankai", lambda: self.stack.setCurrentIndex(3))
        self.segmented_nav.setCurrentItem("modelsTab")

        main_layout.addWidget(self.segmented_nav)
        main_layout.addWidget(self.stack, 1)

    def on_theme_selected(self, theme_mode):
        cfg = load_app_config()
        cfg["theme"] = theme_mode
        save_app_config(cfg)
        self.theme_changed.emit(theme_mode)

    def init_models_tab(self, parent_widget):
        layout = QHBoxLayout(parent_widget)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)

        left_card = CardWidget(parent_widget)
        left_card.setFixedWidth(300)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        self.search_model_edit = SearchLineEdit(parent_widget)
        self.search_model_edit.setPlaceholderText("🔍 Ieškoti modelio...")
        self.search_model_edit.textChanged.connect(self.filter_models_table)
        left_layout.addWidget(self.search_model_edit)

        self.models_table = TableWidget(parent_widget)
        self.models_table.setColumnCount(1)
        self.models_table.setHorizontalHeaderLabels(["Modelių Sąrašas"])
        self.models_table.horizontalHeader().setStretchLastSection(True)
        self.models_table.cellClicked.connect(self.on_model_selected)
        left_layout.addWidget(self.models_table, 1)

        btn_box = QHBoxLayout()
        self.btn_add_model = PushButton(FIF.ADD, "Naujas", parent_widget)
        self.btn_add_model.clicked.connect(self.add_model)
        btn_box.addWidget(self.btn_add_model)

        self.btn_del_model = PushButton(FIF.DELETE, "Trinti", parent_widget)
        self.btn_del_model.clicked.connect(self.delete_model)
        btn_box.addWidget(self.btn_del_model)
        left_layout.addLayout(btn_box)

        layout.addWidget(left_card)

        self.model_detail_card = ElevatedCardWidget(parent_widget)
        detail_layout = QVBoxLayout(self.model_detail_card)
        detail_layout.setContentsMargins(16, 14, 16, 14)
        detail_layout.setSpacing(12)

        self.model_detail_title = SubtitleLabel("Pasirinkite modelį", parent_widget)
        detail_layout.addWidget(self.model_detail_title)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        form.addWidget(StrongBodyLabel("Modelio Pavadinimas:", parent_widget), 0, 0)
        self.edit_m_name = LineEdit(parent_widget)
        self.edit_m_name.textChanged.connect(self.on_model_edited)
        form.addWidget(self.edit_m_name, 0, 1, 1, 2)

        form.addWidget(StrongBodyLabel("Priskirtas Rėmas (Jig):", parent_widget), 1, 0)
        self.combo_m_jig = ComboBox(parent_widget)
        self.combo_m_jig.currentIndexChanged.connect(self.on_model_edited)
        form.addWidget(self.combo_m_jig, 1, 1, 1, 2)

        form.addWidget(StrongBodyLabel("Išvesties Tipas:", parent_widget), 2, 0)
        self.combo_m_output_mode = ComboBox(parent_widget)
        self.combo_m_output_mode.addItem("📁 Laikinas aplankas (Išsivalo po 10 min.)", userData="temp_folder")
        self.combo_m_output_mode.addItem("⚡ Tiesiogiai į ColorGATE HotFolderį", userData="direct_hotfolder")
        self.combo_m_output_mode.currentIndexChanged.connect(self.on_model_edited)
        form.addWidget(self.combo_m_output_mode, 2, 1, 1, 2)

        form.addWidget(StrongBodyLabel("Šaltinis (Spaudos failų aplankas):", parent_widget), 3, 0)
        self.edit_m_source = LineEdit(parent_widget)
        self.edit_m_source.setPlaceholderText(r"pvz. \\192.168.1.143\podbase-hotfolder\MacBook...")
        self.edit_m_source.textChanged.connect(self.on_model_edited)
        form.addWidget(self.edit_m_source, 3, 1)

        self.btn_browse_source = PushButton(FIF.FOLDER, "Naršyti...", parent_widget)
        self.btn_browse_source.clicked.connect(self.browse_source)
        form.addWidget(self.btn_browse_source, 3, 2)

        form.addWidget(StrongBodyLabel("Paskirtis (HotFolderis arba Aplankas):", parent_widget), 4, 0)
        self.edit_m_dest = LineEdit(parent_widget)
        self.edit_m_dest.setPlaceholderText(r"pvz. C:/ProgramData/ColorGATE Software/Productionserver25/HotDir/IPAD...")
        self.edit_m_dest.textChanged.connect(self.on_model_edited)
        form.addWidget(self.edit_m_dest, 4, 1)

        self.btn_browse_dest = PushButton(FIF.FOLDER, "Naršyti...", parent_widget)
        self.btn_browse_dest.clicked.connect(self.browse_dest)
        form.addWidget(self.btn_browse_dest, 4, 2)

        form.addWidget(StrongBodyLabel("Alijasai / Raktažodžiai:", parent_widget), 5, 0)
        self.edit_m_aliases = LineEdit(parent_widget)
        self.edit_m_aliases.setPlaceholderText("Atskirti kableliais: pvz. MacBook Air 13, A1932, A2179")
        self.edit_m_aliases.textChanged.connect(self.on_model_edited)
        form.addWidget(self.edit_m_aliases, 5, 1, 1, 2)

        detail_layout.addLayout(form)
        detail_layout.addStretch(1)

        layout.addWidget(self.model_detail_card, 1)

        self.update_jig_combos()
        self.populate_models_table()
        if self.models_list:
            self.select_model_row(0)

    def init_jigs_tab(self, parent_widget):
        layout = QHBoxLayout(parent_widget)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)

        left_card = CardWidget(parent_widget)
        left_card.setFixedWidth(300)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        left_layout.addWidget(StrongBodyLabel("Sukurti Rėmai (Jigs):", parent_widget))
        self.jigs_table = TableWidget(parent_widget)
        self.jigs_table.setColumnCount(1)
        self.jigs_table.setHorizontalHeaderLabels(["Rėmo Pavadinimas"])
        self.jigs_table.horizontalHeader().setStretchLastSection(True)
        self.jigs_table.cellClicked.connect(self.on_jig_selected)
        left_layout.addWidget(self.jigs_table, 1)

        btn_box = QHBoxLayout()
        self.btn_add_jig = PushButton(FIF.ADD, "Naujas Rėmas", parent_widget)
        self.btn_add_jig.clicked.connect(self.add_jig)
        btn_box.addWidget(self.btn_add_jig)

        self.btn_del_jig = PushButton(FIF.DELETE, "Trinti Rėmą", parent_widget)
        self.btn_del_jig.clicked.connect(self.delete_jig)
        btn_box.addWidget(self.btn_del_jig)
        left_layout.addLayout(btn_box)

        layout.addWidget(left_card)

        self.jig_detail_card = ElevatedCardWidget(parent_widget)
        detail_layout = QVBoxLayout(self.jig_detail_card)
        detail_layout.setContentsMargins(16, 14, 16, 14)
        detail_layout.setSpacing(12)

        self.jig_detail_title = SubtitleLabel("Rėmo konfigūracija", parent_widget)
        detail_layout.addWidget(self.jig_detail_title)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        form.addWidget(StrongBodyLabel("Rėmo Pavadinimas:", parent_widget), 0, 0)
        self.edit_j_name = LineEdit(parent_widget)
        self.edit_j_name.setPlaceholderText("pvz. Rėmas 2x5 (10 vnt. - iPad)")
        self.edit_j_name.textChanged.connect(self.on_jig_edited)
        form.addWidget(self.edit_j_name, 0, 1, 1, 2)

        form.addWidget(StrongBodyLabel("Eilučių skaičius (Rows):", parent_widget), 1, 0)
        self.spin_j_rows = SpinBox(parent_widget)
        self.spin_j_rows.setRange(1, 20)
        self.spin_j_rows.setValue(2)
        self.spin_j_rows.valueChanged.connect(self.on_jig_edited)
        form.addWidget(self.spin_j_rows, 1, 1, 1, 2)

        form.addWidget(StrongBodyLabel("Stulpelių skaičius (Cols):", parent_widget), 2, 0)
        self.spin_j_cols = SpinBox(parent_widget)
        self.spin_j_cols.setRange(1, 30)
        self.spin_j_cols.setValue(5)
        self.spin_j_cols.valueChanged.connect(self.on_jig_edited)
        form.addWidget(self.spin_j_cols, 2, 1, 1, 2)

        form.addWidget(StrongBodyLabel("Bendras lizdų skaičius:", parent_widget), 3, 0)
        self.lbl_j_total = BodyLabel("10 lizdų", parent_widget)
        self.lbl_j_total.setStyleSheet("font-weight: bold; color: #10b981; font-size: 13px;")
        form.addWidget(self.lbl_j_total, 3, 1, 1, 2)

        form.addWidget(StrongBodyLabel("Aprašymas / Pastaba:", parent_widget), 4, 0)
        self.edit_j_desc = LineEdit(parent_widget)
        self.edit_j_desc.setPlaceholderText("pvz. Skirtas iPad / MacBook")
        self.edit_j_desc.textChanged.connect(self.on_jig_edited)
        form.addWidget(self.edit_j_desc, 4, 1, 1, 2)

        detail_layout.addLayout(form)
        detail_layout.addStretch(1)

        layout.addWidget(self.jig_detail_card, 1)

        self.populate_jigs_table()
        if self.jigs_list:
            self.select_jig_row(0)

    def init_updates_tab(self, parent_widget):
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(14)

        # Version Info Card
        ver_card = ElevatedCardWidget(parent_widget)
        v_layout = QHBoxLayout(ver_card)
        v_layout.setContentsMargins(16, 16, 16, 16)
        v_layout.setSpacing(14)

        lbl_app_logo = QLabel(ver_card)
        if os.path.exists(ICON_FILE):
            lbl_app_logo.setPixmap(QPixmap(ICON_FILE).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        v_layout.addWidget(lbl_app_logo)

        v_info_box = QVBoxLayout()
        v_info_box.setSpacing(3)
        v_title = TitleLabel("Podbase Container Studio", ver_card)
        v_title.setStyleSheet("font-size: 20px; font-weight: 800; color: #10b981;")
        v_info_box.addWidget(v_title)

        v_ver_lbl = BodyLabel(f"Dabartinė įdiegta versija: <b>v{CURRENT_VERSION}</b>", ver_card)
        v_info_box.addWidget(v_ver_lbl)
        v_layout.addLayout(v_info_box)

        v_layout.addStretch(1)

        self.btn_check_updates = PrimaryPushButton(FIF.SYNC, "🔍 Tikrinti atnaujinimus dabar", ver_card)
        self.btn_check_updates.setFixedHeight(38)
        self.btn_check_updates.clicked.connect(self.on_manual_check_updates)
        v_layout.addWidget(self.btn_check_updates)

        layout.addWidget(ver_card)

        # GitHub Repo & Settings Card
        repo_card = CardWidget(parent_widget)
        r_layout = QVBoxLayout(repo_card)
        r_layout.setContentsMargins(18, 16, 18, 16)
        r_layout.setSpacing(12)

        r_title = SubtitleLabel("GitHub Atnaujinimų Nustatymai", repo_card)
        r_layout.addWidget(r_title)

        cfg = load_app_config()

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(12)

        form.addWidget(StrongBodyLabel("GitHub Repozitorija (owner/repo):", repo_card), 0, 0)
        self.edit_github_repo = LineEdit(repo_card)
        self.edit_github_repo.setText(cfg.get("github_repo", DEFAULT_GITHUB_REPO))
        self.edit_github_repo.setPlaceholderText("pvz. lkuprys/CC")
        form.addWidget(self.edit_github_repo, 0, 1)

        self.chk_auto_updates = CheckBox("Automatiškai tikrinti atnaujinimus (paleidus programą ir kas 30 min.)", repo_card)
        self.chk_auto_updates.setChecked(cfg.get("auto_check_updates", True))
        form.addWidget(self.chk_auto_updates, 1, 0, 1, 2)

        r_layout.addLayout(form)
        r_layout.addStretch(1)

        layout.addWidget(repo_card)
        layout.addStretch(1)

    def init_search_tab(self, parent_widget):
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(14)

        card = CardWidget(parent_widget)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(18, 16, 18, 16)
        c_layout.setSpacing(12)

        c_layout.addWidget(SubtitleLabel("Brokų (Rejected) Aplankas", card))
        hint = BodyLabel(
            "Papildomas aplankas, kuriame taip pat ieškoma spaudos failų pagal PID (visiems modeliams). "
            "Paieška vyksta ir jo poaplankiuose. Jei tas pats PID randamas keliuose aplankuose, "
            "imamas naujausias failas.", card)
        hint.setWordWrap(True)
        c_layout.addWidget(hint)

        cfg = load_app_config()
        row = QHBoxLayout()
        row.setSpacing(8)
        self.edit_reject_folder = LineEdit(card)
        self.edit_reject_folder.setText(cfg.get("reject_folder", ""))
        self.edit_reject_folder.setPlaceholderText(r"pvz. \\192.168.1.143\podbase-hotfolder\REJECTED")
        self.edit_reject_folder.setClearButtonEnabled(True)
        row.addWidget(self.edit_reject_folder, 1)

        btn_browse = PushButton(FIF.FOLDER, "Pasirinkti...", card)
        btn_browse.clicked.connect(self.browse_reject_folder)
        row.addWidget(btn_browse)
        c_layout.addLayout(row)

        self.lbl_reject_status = CaptionLabel("", card)
        c_layout.addWidget(self.lbl_reject_status)
        self.edit_reject_folder.textChanged.connect(self.update_reject_status)
        self.update_reject_status()

        info = CaptionLabel(
            "Visada ieškoma: modelio šaltinio aplanke ir bendrame tinklo aplanke "
            f"{NETWORK_HOTFOLDER_DEFAULT}. Nepamirškite paspausti „Išsaugoti“.", card)
        info.setWordWrap(True)
        c_layout.addWidget(info)

        layout.addWidget(card)
        layout.addStretch(1)

    def browse_reject_folder(self):
        curr = self.edit_reject_folder.text().strip() or NETWORK_HOTFOLDER_DEFAULT
        folder = QFileDialog.getExistingDirectory(self, "Pasirinkite brokų (rejected) aplanką", curr)
        if folder:
            self.edit_reject_folder.setText(os.path.normpath(folder))

    def update_reject_status(self):
        path = self.edit_reject_folder.text().strip()
        if not path:
            self.lbl_reject_status.setText("Brokų aplankas nenustatytas.")
            self.lbl_reject_status.setStyleSheet("color: #64748b;")
        elif os.path.exists(path):
            self.lbl_reject_status.setText("🟢 Aplankas pasiekiamas.")
            self.lbl_reject_status.setStyleSheet("color: #10b981;")
        else:
            self.lbl_reject_status.setText("🔴 Aplankas nerastas arba nepasiekiamas.")
            self.lbl_reject_status.setStyleSheet("color: #ef4444;")

    def on_manual_check_updates(self):
        if self.updater:
            repo_slug = self.edit_github_repo.text().strip() or DEFAULT_GITHUB_REPO
            self.updater.check_for_updates(repo_slug=repo_slug, manual=True)

    def update_jig_combos(self):
        self.combo_m_jig.blockSignals(True)
        self.combo_m_jig.clear()
        for j in self.jigs_list:
            self.combo_m_jig.addItem(j.get("name", "Rėmas"), userData=j.get("id"))
        self.combo_m_jig.blockSignals(False)

    def populate_models_table(self, filter_text=""):
        self.models_table.setRowCount(0)
        row_idx = 0
        for real_idx, m in enumerate(self.models_list):
            name = m.get("name", "")
            if not filter_text or filter_text.lower() in name.lower():
                self.models_table.insertRow(row_idx)
                item = QTableWidgetItem(name)
                item.setData(Qt.UserRole, real_idx)
                self.models_table.setItem(row_idx, 0, item)
                row_idx += 1

    def populate_jigs_table(self):
        self.jigs_table.setRowCount(len(self.jigs_list))
        for row, j in enumerate(self.jigs_list):
            self.jigs_table.setItem(row, 0, QTableWidgetItem(j.get("name", "Rėmas")))

    def filter_models_table(self, text):
        self.populate_models_table(filter_text=text)

    def on_model_selected(self, row, col):
        item = self.models_table.item(row, 0)
        if item:
            real_idx = item.data(Qt.UserRole)
            self.select_model_row(real_idx)

    def select_model_row(self, real_idx):
        if 0 <= real_idx < len(self.models_list):
            self.current_model_idx = real_idx
            m = self.models_list[real_idx]
            self.model_detail_title.setText(f"📱 {m.get('name', 'Modelis')}")

            self.edit_m_name.blockSignals(True)
            self.edit_m_source.blockSignals(True)
            self.edit_m_dest.blockSignals(True)
            self.edit_m_aliases.blockSignals(True)
            self.combo_m_jig.blockSignals(True)
            self.combo_m_output_mode.blockSignals(True)

            self.edit_m_name.setText(m.get("name", ""))
            self.edit_m_source.setText(m.get("source", ""))
            self.edit_m_dest.setText(m.get("destination", ""))
            self.edit_m_aliases.setText(", ".join(m.get("aliases", [])))

            out_mode = m.get("output_mode", "temp_folder")
            idx_mode = self.combo_m_output_mode.findData(out_mode)
            if idx_mode != -1:
                self.combo_m_output_mode.setCurrentIndex(idx_mode)
            else:
                self.combo_m_output_mode.setCurrentIndex(0)

            j_id = m.get("jig_id", "")
            idx = self.combo_m_jig.findData(j_id)
            if idx != -1:
                self.combo_m_jig.setCurrentIndex(idx)
            else:
                for j_idx, j in enumerate(self.jigs_list):
                    if j.get("id") == j_id:
                        self.combo_m_jig.setCurrentIndex(j_idx)
                        break
                else:
                    self.combo_m_jig.setCurrentIndex(0)

            self.edit_m_name.blockSignals(False)
            self.edit_m_source.blockSignals(False)
            self.edit_m_dest.blockSignals(False)
            self.edit_m_aliases.blockSignals(False)
            self.combo_m_jig.blockSignals(False)
            self.combo_m_output_mode.blockSignals(False)

    def on_model_edited(self):
        if 0 <= self.current_model_idx < len(self.models_list):
            m = self.models_list[self.current_model_idx]
            m["name"] = self.edit_m_name.text().strip()
            m["source"] = self.edit_m_source.text().strip()
            m["destination"] = self.edit_m_dest.text().strip()
            m["output_mode"] = self.combo_m_output_mode.currentData() or "temp_folder"
            
            curr_jig_id = self.combo_m_jig.currentData()
            if not curr_jig_id and 0 <= self.combo_m_jig.currentIndex() < len(self.jigs_list):
                curr_jig_id = self.jigs_list[self.combo_m_jig.currentIndex()].get("id")
            if curr_jig_id:
                m["jig_id"] = curr_jig_id

            aliases_raw = self.edit_m_aliases.text().split(",")
            m["aliases"] = [a.strip() for a in aliases_raw if a.strip()]
            self.model_detail_title.setText(f"📱 {m['name']}")

    def on_jig_selected(self, row, col):
        self.select_jig_row(row)

    def select_jig_row(self, row):
        if 0 <= row < len(self.jigs_list):
            self.current_jig_idx = row
            j = self.jigs_list[row]
            self.jig_detail_title.setText(f"📐 {j.get('name', 'Rėmas')}")

            self.edit_j_name.blockSignals(True)
            self.spin_j_rows.blockSignals(True)
            self.spin_j_cols.blockSignals(True)
            self.edit_j_desc.blockSignals(True)

            self.edit_j_name.setText(j.get("name", ""))
            rows = j.get("rows", 2)
            cols = j.get("cols", 5)
            self.spin_j_rows.setValue(rows)
            self.spin_j_cols.setValue(cols)
            self.lbl_j_total.setText(f"{rows * cols} lizdų ({rows} eil. x {cols} stulp.)")
            self.edit_j_desc.setText(j.get("description", ""))

            self.edit_j_name.blockSignals(False)
            self.spin_j_rows.blockSignals(False)
            self.spin_j_cols.blockSignals(False)
            self.edit_j_desc.blockSignals(False)

    def on_jig_edited(self):
        if 0 <= self.current_jig_idx < len(self.jigs_list):
            j = self.jigs_list[self.current_jig_idx]
            j["name"] = self.edit_j_name.text().strip()
            rows = self.spin_j_rows.value()
            cols = self.spin_j_cols.value()
            j["rows"] = rows
            j["cols"] = cols
            j["total_slots"] = rows * cols
            j["description"] = self.edit_j_desc.text().strip()

            self.lbl_j_total.setText(f"{rows * cols} lizdų ({rows} eil. x {cols} stulp.)")
            self.jig_detail_title.setText(f"📐 {j['name']}")

    def browse_source(self):
        curr = self.edit_m_source.text().strip() or "C:/"
        folder = QFileDialog.getExistingDirectory(self, "Pasirinkite spaudos failų šaltinio aplanką", curr)
        if folder:
            self.edit_m_source.setText(folder.replace("\\", "/"))
            self.on_model_edited()

    def browse_dest(self):
        curr = self.edit_m_dest.text().strip() or "C:/ProgramData/ColorGATE Software"
        folder = QFileDialog.getExistingDirectory(self, "Pasirinkite paskirties aplanką arba ColorGATE HotFolderį", curr)
        if folder:
            self.edit_m_dest.setText(folder.replace("\\", "/"))
            self.on_model_edited()

    def add_model(self):
        new_m = {
            "name": f"Naujas Modelis {len(self.models_list) + 1}",
            "jig_id": self.jigs_list[0].get("id") if self.jigs_list else "jig_2x5",
            "source": r"\\192.168.1.143\podbase-hotfolder\BENDRAS_PODBASE_HOTFOLDER",
            "destination": "",
            "output_mode": "temp_folder",
            "aliases": []
        }
        self.models_list.append(new_m)
        self.populate_models_table()
        self.select_model_row(len(self.models_list) - 1)

    def delete_model(self):
        if 0 <= self.current_model_idx < len(self.models_list):
            del self.models_list[self.current_model_idx]
            self.populate_models_table()
            if self.models_list:
                self.select_model_row(min(self.current_model_idx, len(self.models_list) - 1))

    def add_jig(self):
        new_id = f"jig_{int(time.time())}"
        new_j = {
            "id": new_id,
            "name": f"Naujas Rėmas ({len(self.jigs_list) + 1})",
            "rows": 2,
            "cols": 5,
            "total_slots": 10,
            "description": ""
        }
        self.jigs_list.append(new_j)
        self.populate_jigs_table()
        self.update_jig_combos()
        self.select_jig_row(len(self.jigs_list) - 1)

    def delete_jig(self):
        if 0 <= self.current_jig_idx < len(self.jigs_list):
            del self.jigs_list[self.current_jig_idx]
            self.populate_jigs_table()
            self.update_jig_combos()
            if self.jigs_list:
                self.select_jig_row(min(self.current_jig_idx, len(self.jigs_list) - 1))

    def save_all_data(self):
        try:
            if 0 <= self.current_model_idx < len(self.models_list):
                self.on_model_edited()
            if 0 <= self.current_jig_idx < len(self.jigs_list):
                self.on_jig_edited()

            save_models_data(self.models_list)
            save_jigs_data(self.jigs_list)

            cfg = load_app_config()
            cfg["github_repo"] = self.edit_github_repo.text().strip() or DEFAULT_GITHUB_REPO
            cfg["auto_check_updates"] = self.chk_auto_updates.isChecked()
            cfg["reject_folder"] = self.edit_reject_folder.text().strip()
            save_app_config(cfg)

            saved_model_idx = self.current_model_idx
            saved_jig_idx = self.current_jig_idx

            self.update_jig_combos()
            self.populate_models_table()
            self.populate_jigs_table()

            if 0 <= saved_model_idx < len(self.models_list):
                self.select_model_row(saved_model_idx)
            if 0 <= saved_jig_idx < len(self.jigs_list):
                self.select_jig_row(saved_jig_idx)

            self.settings_updated.emit()

            InfoBar.success(
                title="Išsaugota!",
                content="Visi nustatymai sėkmingai išsaugoti!",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self
            )
        except Exception as e:
            InfoBar.error(
                title="Klaida išsaugant",
                content=str(e),
                position=InfoBarPosition.TOP_RIGHT,
                parent=self
            )


# ----------------- MAIN FLUENT WINDOW -----------------
class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Podbase — Konteinerių Generatorius (v{CURRENT_VERSION})")
        if os.path.exists(ICON_FILE):
            app_icon = QIcon(ICON_FILE)
            self.setWindowIcon(app_icon)
            QApplication.setWindowIcon(app_icon)
            
        self.resize(1180, 760)

        cfg = load_app_config()
        if cfg.get("theme", "LIGHT") == "DARK":
            setTheme(Theme.DARK)
        else:
            setTheme(Theme.LIGHT)

        # 0. Initialize Auto-Updater
        self.updater = AppUpdater(self, current_version=CURRENT_VERSION)

        # 1. Studio Tab
        self.studio_interface = ContainerStudioInterface(self)
        self.studio_interface.setObjectName("studioInterface")

        # 2. History Tab
        self.history_interface = HistoryInterface(self)
        self.history_interface.setObjectName("historyInterface")
        self.history_interface.load_order_to_studio.connect(self.on_load_order_to_studio)
        self.studio_interface.container_generated.connect(self.history_interface.reload_history)

        # 3. Settings Tab (with Updater integration)
        self.settings_interface = ModelsSettingsInterface(updater=self.updater, parent=self)
        self.settings_interface.setObjectName("settingsInterface")
        self.settings_interface.settings_updated.connect(self.on_settings_updated)
        self.settings_interface.theme_changed.connect(self.on_theme_changed)

        self.init_navigation()

        self.server_thread = FlaskServerThread(port=5000, host=(load_app_config().get("api_host") or "127.0.0.1"))
        self.server_thread.designs_received.connect(self.on_designs_received)
        self.server_thread.start()

        # Periodic 10-minute Auto-Cleanup timer (checks every 30s)
        self.cleanup_timer = QTimer(self)
        self.cleanup_timer.setInterval(30000)
        self.cleanup_timer.timeout.connect(self.run_auto_cleanup)
        self.cleanup_timer.start()
        self.run_auto_cleanup()

        # Parodome, kaip baigėsi paskutinis atnaujinimas (jei programa ką tik persikrovė po jo)
        QTimer.singleShot(1500, self.updater.show_last_update_result)

        # Atnaujinimų tikrinimas: po 3.5 s nuo paleidimo ir toliau periodiškai
        QTimer.singleShot(3500, self.run_periodic_update_check)
        self.update_check_timer = QTimer(self)
        self.update_check_timer.setInterval(PERIODIC_CHECK_INTERVAL_MS)
        self.update_check_timer.timeout.connect(self.run_periodic_update_check)
        self.update_check_timer.start()

    def run_periodic_update_check(self):
        cfg = load_app_config()
        if cfg.get("auto_check_updates", True):
            repo_slug = cfg.get("github_repo", DEFAULT_GITHUB_REPO)
            self.updater.check_for_updates(repo_slug=repo_slug, manual=False)

    def run_auto_cleanup(self):
        try:
            perform_temp_folders_cleanup()
        except Exception as e:
            print(f"[run_auto_cleanup error]: {e}")

    def init_navigation(self):
        self.addSubInterface(
            self.studio_interface,
            FIF.DEVELOPER_TOOLS,
            "Konteinerių Kūrimas",
            NavigationItemPosition.TOP
        )
        self.addSubInterface(
            self.history_interface,
            FIF.HISTORY,
            "Generavimo Istorija",
            NavigationItemPosition.TOP
        )
        self.addSubInterface(
            self.settings_interface,
            FIF.SETTING,
            "Nustatymai ir Tema",
            NavigationItemPosition.BOTTOM
        )

    def on_load_order_to_studio(self, entry):
        self.studio_interface.load_from_history_entry(entry)
        self.switchTo(self.studio_interface)

    def on_theme_changed(self, theme_mode):
        if theme_mode == "DARK":
            setTheme(Theme.DARK)
        else:
            setTheme(Theme.LIGHT)
        self.studio_interface.update_bed_container_style()

    def on_settings_updated(self):
        self.studio_interface.load_data()
        self.studio_interface.populate_models_combo()
        self.studio_interface.on_model_changed()

    def on_designs_received(self, payload):
        self.studio_interface.set_data_from_extension(payload)
        self.switchTo(self.studio_interface)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        self.server_thread.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    if os.path.exists(ICON_FILE):
        app.setWindowIcon(QIcon(ICON_FILE))
    cfg = load_app_config()
    if cfg.get("theme", "LIGHT") == "DARK":
        setTheme(Theme.DARK)
    else:
        setTheme(Theme.LIGHT)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
