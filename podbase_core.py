# -*- coding: utf-8 -*-
"""
Podbase Container Studio – programos logika be sąsajos (Qt):
keliai ir nustatymai, JSON saugojimas, laikinų aplankų valymas,
spaudos failų paieška ir konteinerio generavimas.

Šį modulį galima importuoti ir testuoti be PySide6.
"""
import sys
import os
import re
import json
import time
import shutil
import struct
import zlib
import logging
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler


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

DEFAULT_GITHUB_REPO = "lkuprys/CC"  # toks pat kaip updater.py

# ----------------- ŽURNALAS (podbase.log šalia programos) -----------------
# .exe neturi konsolės, todėl klaidos rašomos į failą. Failas ribojamas iki 3 x 1 MB.
LOG_FILE = os.path.join(BASE_DIR, "podbase.log")
log = logging.getLogger("podbase")
if not log.handlers:
    log.setLevel(logging.INFO)
    try:
        _fh = RotatingFileHandler(LOG_FILE, maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
        _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(threadName)s: %(message)s"))
        log.addHandler(_fh)
    except Exception:
        pass
    if sys.stderr:
        log.addHandler(logging.StreamHandler())


def install_exception_logging():
    """Nepagautos klaidos (ir fono gijose) įrašomos į žurnalą, o ne dingsta."""
    def _hook(exc_type, exc, tb):
        log.critical("Nepagauta klaida", exc_info=(exc_type, exc, tb))
    sys.excepthook = _hook

    def _thread_hook(args):
        log.critical("Nepagauta klaida gijoje %s", getattr(args.thread, "name", "?"),
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    threading.excepthook = _thread_hook


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
                log.warning(f"[ensure_local_data_files]: {e}")


ensure_local_data_files()

# Common shared network hotfolder roots
NETWORK_HOTFOLDER_DEFAULT = r"\\192.168.1.143\podbase-hotfolder\BENDRAS_PODBASE_HOTFOLDER"

# ----------------- SAUGUS JSON RAŠYMAS / SKAITYMAS -----------------
_json_write_lock = threading.Lock()


def write_json_atomic(path, data, **dump_kwargs):
    """Rašo į laikiną failą ir tik tada pakeičia originalą – nutrūkus rašymui failas nesugadinamas."""
    tmp = f"{path}.tmp"
    with _json_write_lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, **dump_kwargs)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)


_corrupt_backed_up = set()


def backup_corrupt_file(path, err):
    """Sugadintą JSON failą išsaugo atsarginei kopijai, kad kitas išsaugojimas jo negalutinai neperrašytų."""
    if path in _corrupt_backed_up or not os.path.exists(path):
        return
    _corrupt_backed_up.add(path)
    try:
        backup = f"{path}.sugadintas_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(path, backup)
        log.warning(f"[JSON klaida] {path}: {err}. Kopija: {backup}")
    except Exception as e:
        log.warning(f"[JSON klaida] {path}: {err}. Kopijos padaryti nepavyko: {e}")


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
        write_json_atomic(CONFIG_FILE, default_config, indent=2)
        return default_config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "github_repo" not in data:
                data["github_repo"] = DEFAULT_GITHUB_REPO
            if "auto_check_updates" not in data:
                data["auto_check_updates"] = True
            return data
    except Exception as e:
        backup_corrupt_file(CONFIG_FILE, e)
        return default_config

def save_app_config(cfg):
    write_json_atomic(CONFIG_FILE, cfg, indent=2)

# ----------------- HISTORY STORAGE -----------------
def load_history_data():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        backup_corrupt_file(HISTORY_FILE, e)
        return []

def save_history_data(history_list):
    if len(history_list) > 150:
        history_list = history_list[:150]
    write_json_atomic(HISTORY_FILE, history_list, ensure_ascii=False, indent=2)

_history_lock = threading.Lock()

def add_history_entry(entry):
    with _history_lock:
        h = load_history_data()
        h.insert(0, entry)
        save_history_data(h)

# ----------------- TEMPORARY FOLDER 10-MIN AUTO-CLEANUP -----------------
def get_cleanup_expiry_seconds():
    try:
        minutes = float(load_app_config().get("auto_cleanup_minutes", 10))
    except (TypeError, ValueError):
        minutes = 10
    return max(1.0, minutes) * 60


TEMP_FOLDERS_FILE = os.path.join(BASE_DIR, "temp_folders.json")
_temp_folders_lock = threading.Lock()


def _load_temp_folders():
    try:
        with open(TEMP_FOLDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def register_temp_folder(path):
    """Įsimena programos sukurtą laikiną aplanką – valymas trina TIK tokius aplankus."""
    with _temp_folders_lock:
        data = _load_temp_folders()
        data[os.path.normpath(path)] = time.time()
        write_json_atomic(TEMP_FOLDERS_FILE, data, ensure_ascii=False, indent=2)


def perform_temp_folders_cleanup():
    """Ištrina programos sukurtus laikinus aplankus, senesnius nei auto_cleanup_minutes.
    Vartotojo paties sukurti aplankai (net ir „Konteineriai“ viduje) neliečiami."""
    now = time.time()
    expiry = get_cleanup_expiry_seconds()
    with _temp_folders_lock:
        data = _load_temp_folders()
        if not data:
            return
        keep = {}
        for path, created in data.items():
            if not os.path.isdir(path):
                continue
            try:
                created = float(created)
            except (TypeError, ValueError):
                created = now
            if now - created < expiry:
                keep[path] = created
                continue
            shutil.rmtree(path, ignore_errors=True)
            if os.path.isdir(path):
                keep[path] = created  # dalis failų užrakinta – bandysime vėliau
            else:
                log.info(f"[AutoCleanup] Ištrintas laikinas aplankas (>{expiry / 60:.0f} min): {path}")
        if keep != data:
            try:
                write_json_atomic(TEMP_FOLDERS_FILE, keep, ensure_ascii=False, indent=2)
            except Exception as e:
                log.warning(f"[AutoCleanup klaida]: {e}")

# ----------------- RECURSIVE MULTI-ROOT PRINT FILE SCANNER -----------------
SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff'}

# Failų tipai, kuriuos galima pasirinkti modelio nustatymuose (raktas → plėtiniai)
FILE_TYPE_GROUPS = {
    "png": (".png",),
    "jpg": (".jpg", ".jpeg"),
    "webp": (".webp",),
    "tif": (".tif", ".tiff"),
}


def extensions_for_types(file_types):
    """Modelio failų tipai (pvz. ["tif"]) → plėtinių aibė. Tuščias sąrašas = visi palaikomi tipai."""
    exts = set()
    for t in file_types or []:
        exts.update(FILE_TYPE_GROUPS.get(str(t).lower().lstrip("."), ()))
    return exts or set(SUPPORTED_IMAGE_EXTENSIONS)
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
        log.warning(f"[is_file_ready klaida]: {e}")
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

def _is_ignored_dir(name):
    low = name.lower()
    return (name.startswith(('.', '~', '$'))
            or low.strip() in IGNORED_FOLDER_NAMES
            or 'batch sheet' in low or 'batchsheet' in low
            or 'trash' in low or 'done' in low)


def scan_print_files_recursive(search_roots):
    """
    Rekursyviai suranda spaudos failus. Naudojamas os.scandir: Windows'e failo data gaunama
    kartu su aplanko sąrašu, todėl tinklo diske nereikia atskiros užklausos kiekvienam failui.
    """
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

        stack = [norm_root]
        while stack:
            dirpath = stack.pop()
            try:
                with os.scandir(dirpath) as it:
                    entries = list(it)
            except OSError as e:
                log.warning(f"[scan_print_files_recursive klaida ties {dirpath}]: {e}")
                continue

            for entry in entries:
                fname = entry.name
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if not _is_ignored_dir(fname):
                            stack.append(entry.path)
                        continue
                except OSError:
                    continue

                fname_lower = fname.lower()
                if fname.startswith(('.', '~', '$')):
                    continue
                if any(kw in fname_lower for kw in IGNORED_FILE_KEYWORDS):
                    continue
                ext = os.path.splitext(fname_lower)[1]
                if ext not in SUPPORTED_IMAGE_EXTENSIONS:
                    continue

                stem = os.path.splitext(fname)[0]
                try:
                    mtime = entry.stat().st_mtime
                except OSError:
                    mtime = 0

                scanned_files.append({
                    "filename": fname,
                    "fname_lower": fname_lower,
                    "stem": stem,
                    "stem_lower": stem.lower(),
                    "path": entry.path,
                    "mtime": mtime
                })

    return scanned_files

# ----------------- TUŠČIAS (PERMATOMAS) LIZDAS -----------------
# Specialus plano elementas: vietoj spaudos failo sukuriamas visiškai permatomas PNG,
# kurio dydis ir DPI sutampa su kitu to paties stalo failu – ColorGATE tą vietą praleidžia.
BLANK_TOKEN = "__TUSCIAS_LIZDAS__"
BLANK_LABEL = "Tuščias lizdas"


def plan_item_name(item):
    """Stalo elementas (dict) → plano elemento pavadinimas (tuščiam lizdui – BLANK_TOKEN)."""
    if isinstance(item, dict) and item.get("blank"):
        return BLANK_TOKEN
    return (item or {}).get("name", "") if isinstance(item, dict) else str(item or "")


def read_image_info(path):
    """
    (plotis, aukštis, dpi_x, dpi_y) iš failo antraštės, viso failo nedekoduojant.
    DPI None, jei faile nenurodytas. Grąžina None, jei formatas neatpažintas.
    """
    with open(path, "rb") as f:
        head = f.read(32)
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            return _png_info(f)
        if head[:4] in (b"II*\x00", b"MM\x00*"):
            return _tiff_info(f, head[:2])
        if head[:2] == b"\xff\xd8":
            return _jpeg_info(f)
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            return _webp_info(head, f)
    return None


def _png_info(f):
    f.seek(8)
    w = h = None
    dpi = (None, None)
    while True:
        hdr = f.read(8)
        if len(hdr) < 8:
            break
        length, ctype = struct.unpack(">I4s", hdr)
        if ctype == b"IHDR":
            w, h = struct.unpack(">II", f.read(8))
            f.seek(length - 8 + 4, 1)
        elif ctype == b"pHYs":
            px, py, unit = struct.unpack(">IIB", f.read(9))
            if unit == 1:
                dpi = (px * 0.0254, py * 0.0254)
            f.seek(4, 1)
        elif ctype in (b"IDAT", b"IEND"):
            break
        else:
            f.seek(length + 4, 1)
    return (w, h, dpi[0], dpi[1]) if w and h else None


def _tiff_info(f, order):
    e = "<" if order == b"II" else ">"
    f.seek(4)
    (ifd,) = struct.unpack(e + "I", f.read(4))
    f.seek(ifd)
    (n,) = struct.unpack(e + "H", f.read(2))
    tags = {}
    for _ in range(n):
        tag, typ, count, value = struct.unpack(e + "HHI4s", f.read(12))
        tags[tag] = (typ, count, value)

    def num(tag):
        if tag not in tags:
            return None
        typ, _count, raw = tags[tag]
        if typ == 3:   # SHORT
            return struct.unpack(e + "H", raw[:2])[0]
        if typ == 4:   # LONG
            return struct.unpack(e + "I", raw)[0]
        if typ == 5:   # RATIONAL – reikšmė toliau faile
            pos = f.tell()
            f.seek(struct.unpack(e + "I", raw)[0])
            a, b = struct.unpack(e + "II", f.read(8))
            f.seek(pos)
            return a / b if b else None
        return None

    w, h = num(256), num(257)
    xr, yr, unit = num(282), num(283), num(296) or 2
    factor = 2.54 if unit == 3 else 1.0
    if unit == 1:   # be matavimo vieneto
        xr = yr = None
    dpi_x = xr * factor if xr else None
    dpi_y = yr * factor if yr else None
    return (w, h, dpi_x, dpi_y) if w and h else None


def _jpeg_info(f):
    f.seek(2)
    dpi = (None, None)
    while True:
        b = f.read(1)
        while b and b != b"\xff":
            b = f.read(1)
        while b == b"\xff":
            b = f.read(1)
        if not b:
            return None
        marker = b[0]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            continue
        (length,) = struct.unpack(">H", f.read(2))
        data_start = f.tell()
        if marker == 0xE0:
            data = f.read(min(length - 2, 14))
            if data[:5] == b"JFIF\x00" and len(data) >= 12:
                unit, dx, dy = struct.unpack(">BHH", data[7:12])
                if unit == 1:
                    dpi = (float(dx), float(dy))
                elif unit == 2:
                    dpi = (dx * 2.54, dy * 2.54)
        elif 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            _p, h, w = struct.unpack(">BHH", f.read(5))
            return (w, h, dpi[0], dpi[1])
        f.seek(data_start + length - 2)


def _webp_info(head, f):
    chunk = head[12:16]
    if chunk == b"VP8X":
        f.seek(24)
        d = f.read(6)
        w = 1 + int.from_bytes(d[0:3], "little")
        h = 1 + int.from_bytes(d[3:6], "little")
        return (w, h, None, None)
    if chunk == b"VP8 ":
        f.seek(26)
        w, h = struct.unpack("<HH", f.read(4))
        return (w & 0x3FFF, h & 0x3FFF, None, None)
    if chunk == b"VP8L":
        f.seek(21)
        b = f.read(4)
        bits = int.from_bytes(b, "little")
        return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1, None, None)
    return None


def write_blank_png(path, width, height, dpi_x=None, dpi_y=None):
    """Visiškai permatomas RGBA PNG. Nuliai suspaudžiami labai gerai, todėl failas mažas net dideliems matmenims."""
    def chunk(ctype, data):
        return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)

    comp = zlib.compressobj(9)
    row = b"\x00" * (1 + 4 * width)      # filtro baitas + RGBA nuliai
    rows_per_block = max(1, (4 * 1024 * 1024) // len(row))
    idat = bytearray()
    remaining = height
    while remaining > 0:
        n = min(rows_per_block, remaining)
        idat += comp.compress(row * n)
        remaining -= n
    idat += comp.flush()

    out = bytearray(b"\x89PNG\r\n\x1a\n")
    out += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    if dpi_x and dpi_y:
        out += chunk(b"pHYs", struct.pack(">IIB", round(dpi_x / 0.0254), round(dpi_y / 0.0254), 1))
    out += chunk(b"IDAT", bytes(idat))
    out += chunk(b"IEND", b"")
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        fh.write(out)
    os.replace(tmp, path)


def find_matching_file_for_design(design_name, scanned_files):
    """Geriausiai tinkančio failo kelias arba None."""
    candidates = find_matching_candidates(design_name, scanned_files)
    return candidates[0][2] if candidates else None


def find_matching_candidates(design_name, scanned_files):
    """Visi tinkami failai [(balas, mtime, kelias)], geriausias pirmas."""
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

            # Pvz. „pid1234“ tinka, bet „51234“ ar „12345“ – ne (kitas užsakymas)
            if re.search(r'(?<!\d)' + re.escape(pid_digits) + r'(?!\d)', stem_l):
                matches_with_score.append((70, mtime, f_path))
                continue

        if d_clean == stem_l or d_clean == f_info["fname_lower"]:
            matches_with_score.append((85, mtime, f_path))
            continue

        # Kai nurodytas aiškus PID, failas be to PID negali būti laikomas atitikmeniu
        if d_num_match:
            continue

        if len(d_clean) >= 3 and len(stem_l) >= 3 and (d_clean in stem_l or stem_l in d_clean):
            matches_with_score.append((50, mtime, f_path))
            continue

    matches_with_score.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return matches_with_score


def ambiguous_alternatives(candidates):
    """Kiti failai su tokiu pat geriausiu balu (pvz., tas pats PID ir brokų, ir įprastame aplanke)."""
    if len(candidates) < 2:
        return []
    top = candidates[0][0]
    return [c[2] for c in candidates[1:] if c[0] == top]

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
                base_name = safe_folder_name(design_name, stem_file or "Dizainas")

    return f"{num_prefix}_{base_name}{ext}"

# ----------------- KONTEINERIO GENERAVIMAS FONE (be užstrigimo) -----------------
# Tinklo aplankų skenavimas gali užtrukti, todėl rezultatas trumpam įsimenamas.
# Jei su įsimintu sąrašu kurio nors failo nerandama, sąrašas automatiškai perskenuojamas.
SCAN_CACHE_TTL_SECONDS = 120
_scan_cache = {}
_scan_cache_lock = threading.Lock()


_scan_key_locks = {}


def _scan_lock_for(key):
    with _scan_cache_lock:
        return _scan_key_locks.setdefault(key, threading.Lock())


def get_scanned_files(search_roots, force=False, wait=True):
    """
    Grąžina (failų sąrašas, ar paimta iš atminties).
    wait=False: jei tie patys aplankai jau skenuojami, nelaukia ir grąžina (None, False).
    """
    key = tuple(os.path.normcase(os.path.normpath(r)) for r in search_roots)
    requested_at = time.time()
    lock = _scan_lock_for(key)
    # Tie patys aplankai skenuojami tik vieną kartą vienu metu (pvz., išankstinis skenavimas ir generavimas)
    if not lock.acquire(blocking=wait):
        return None, False
    try:
        roots_mtime = _roots_mtime(search_roots)
        with _scan_cache_lock:
            hit = _scan_cache.get(key)
        if hit and hit[2] == roots_mtime:
            scan_started = hit[3]
            # force: tinka tik sąrašas, kurio skenavimas PRASIDĖJO po šios užklausos
            if force:
                if scan_started >= requested_at:
                    return hit[1], False
            elif time.time() - scan_started < SCAN_CACHE_TTL_SECONDS:
                return hit[1], True
        scan_started = time.time()
        files = scan_print_files_recursive(search_roots)
        with _scan_cache_lock:
            _scan_cache[key] = (time.time(), files, roots_mtime, scan_started)
        return files, False
    finally:
        lock.release()


def prefetch_scanned_files(source_dir):
    """Pradeda skenuoti modelio aplankus fone, kad paspaudus „Generuoti“ sąrašas jau būtų paruoštas."""
    def _run():
        try:
            get_scanned_files(build_search_roots(source_dir), wait=False)
        except Exception as e:
            log.warning(f"[išankstinis skenavimas]: {e}")
    threading.Thread(target=_run, name="prefetch-scan", daemon=True).start()


def _roots_mtime(search_roots):
    result = []
    for r in search_roots:
        try:
            result.append(os.path.getmtime(r))
        except OSError:
            result.append(None)
    return tuple(result)


def unique_destination(dst):
    """Jei failas jau yra (pvz., HotFolderis jo dar nepaėmė), grąžina pavadinimą su _2, _3..."""
    if not os.path.exists(dst):
        return dst
    stem, ext = os.path.splitext(dst)
    n = 2
    while os.path.exists(f"{stem}_{n}{ext}"):
        n += 1
    return f"{stem}_{n}{ext}"


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


_container_job_lock = threading.Lock()


def run_container_job(plan, progress=None):
    """Vienu metu vykdomas tik vienas darbas (Studija ir Istorija rašo į tuos pačius aplankus)."""
    if not _container_job_lock.acquire(blocking=False):
        if progress:
            progress(0, 0, "Laukiama, kol baigsis kitas generavimas...")
        _container_job_lock.acquire()
    try:
        started = time.time()
        res = _run_container_job(plan, progress)
        log.info(
            f"Konteineris: {len(plan.get('beds', []))} stal., nukopijuota {res['copied']}, "
            f"nerasta {len(res['missing'])}, klaidų {len(res['errors'])}, "
            f"{'HotFolder' if plan.get('hotfolder') else 'laikinas aplankas'} → {plan.get('dest_dir') or DESKTOP_DIR} "
            f"({time.time() - started:.1f} s)"
        )
        for bed_idx, item_idx, name in res["missing"]:
            log.info(f"  nerasta: stalas {bed_idx + 1}, vieta {item_idx + 1}: {name}")
        for err in res["errors"]:
            log.warning(f"  klaida: {err}")
        for warn in res["warnings"]:
            log.warning(f"  dėmesio: {warn}")
        return res
    except Exception:
        log.exception("Konteinerio generavimas nepavyko")
        raise
    finally:
        _container_job_lock.release()


def _run_container_job(plan, progress=None):
    """
    Suranda ir nukopijuoja spaudos failus pagal planą. Vykdoma fono gijoje.

    plan = {
        "source_dir": str, "dest_dir": str, "hotfolder": bool, "file_types": ["tif", ...] (nebūtina),
        "beds": [{"bed_idx": int, "title": str, "items": [dizaino pavadinimas, ...]}]
    }
    Grąžina {"copied", "missing": [(bed_idx, item_idx, name)], "errors", "folders", "search_roots"}.
    """
    def report(text, done=0, total=0):
        if progress:
            progress(done, total, text)

    # found: [(stalas, vieta, pavadinimas, kelias, mtime)], warnings: tekstai operatoriui
    result = {"copied": 0, "missing": [], "errors": [], "folders": [], "search_roots": [],
              "found": [], "warnings": [], "ambiguous": [], "blanks": []}

    report("Tikrinami paieškos aplankai...")
    search_roots = build_search_roots(plan.get("source_dir", ""))
    result["search_roots"] = search_roots

    def match_all(scanned):
        return {
            (b["bed_idx"], i): find_matching_candidates(name, scanned)
            for b in plan["beds"] for i, name in enumerate(b["items"]) if name != BLANK_TOKEN
        }

    # Tik modeliui priskirti failų tipai (pvz. MacBook – tik TIF)
    allowed_exts = extensions_for_types(plan.get("file_types"))

    def only_allowed(files):
        return [f for f in files if os.path.splitext(f["fname_lower"])[1] in allowed_exts]

    report("Ieškoma spaudos failų...")
    scanned, from_cache = get_scanned_files(search_roots)
    candidates_by_slot = match_all(only_allowed(scanned))
    if from_cache and any(not c or not os.path.exists(c[0][2]) for c in candidates_by_slot.values()):
        report("Atnaujinamas failų sąrašas...")
        scanned, _ = get_scanned_files(search_roots, force=True)
        candidates_by_slot = match_all(only_allowed(scanned))
    matches = {k: (c[0][2] if c else None) for k, c in candidates_by_slot.items()}

    # Tuščių lizdų dydis: pirmas rastas to paties stalo failas (jei nėra – bet kurio stalo)
    blank_ref = {}
    any_found = next((p for p in matches.values() if p), None)
    for b in plan["beds"]:
        if BLANK_TOKEN in b["items"]:
            same_bed = [matches.get((b["bed_idx"], i)) for i, n in enumerate(b["items"]) if n != BLANK_TOKEN]
            blank_ref[b["bed_idx"]] = next((p for p in same_bed if p), None) or any_found

    for b in plan["beds"]:
        for i, name in enumerate(b["items"]):
            cands = candidates_by_slot.get((b["bed_idx"], i)) or []
            others = ambiguous_alternatives(cands)
            if others:
                chosen = cands[0][2]
                result["ambiguous"].append((b["bed_idx"], i))
                result["warnings"].append(
                    f"{missing_label(name)} (stalas {b['bed_idx'] + 1}, vieta {i + 1}): rasti {len(others) + 1} "
                    f"tinkami failai, paimtas naujausias – {os.path.basename(chosen)} "
                    f"({os.path.dirname(chosen)})"
                )

    is_hot = plan.get("hotfolder", False)
    dest_dir = plan.get("dest_dir", "")
    if is_hot:
        os.makedirs(dest_dir, exist_ok=True)

    total = sum(len(b["items"]) for b in plan["beds"])
    done = 0
    used_titles = set()
    for b in plan["beds"]:
        title = safe_folder_name(b["title"], f"Stalas_{b['bed_idx'] + 1}")
        # Du stalai tuo pačiu pavadinimu kitaip ištrintų vienas kito aplanką
        base_title, n = title, 2
        while title.lower() in used_titles:
            title = f"{base_title}_{n}"
            n += 1
        used_titles.add(title.lower())
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
            try:
                register_temp_folder(target_dir)
            except Exception as e:
                log.warning(f"[register_temp_folder klaida]: {e}")
        if target_dir not in result["folders"]:
            result["folders"].append(target_dir)

        for i, name in enumerate(b["items"]):
            done += 1
            report(f"Kopijuojama {done} iš {total}...", done, total)
            num_prefix = f"{i + 1:02d}"
            custom_name = title if i == 0 and title else None
            if name == BLANK_TOKEN:
                ref = blank_ref.get(b["bed_idx"])
                try:
                    info = read_image_info(ref) if ref else None
                    if not info:
                        raise ValueError("nėra rasto failo, pagal kurį nustatyti dydį")
                    w, h, dx, dy = info
                    dst_name = f"{num_prefix}_{safe_folder_name(custom_name, 'TUSCIAS') if custom_name else 'TUSCIAS'}.png"
                    dst_path = os.path.join(target_dir, dst_name)
                    if is_hot:
                        dst_path = unique_destination(dst_path)
                    write_blank_png(dst_path, w, h, dx, dy)
                    result["copied"] += 1
                    result["blanks"].append((b["bed_idx"], i, w, h, dx, dy))
                except Exception as e:
                    result["errors"].append(f"Tuščias lizdas (stalas {b['bed_idx'] + 1}, vieta {i + 1}): {e}")
                    result["missing"].append((b["bed_idx"], i, BLANK_LABEL))
                continue

            found = matches.get((b["bed_idx"], i))

            if found:
                try:
                    dst_name = format_output_filename(num_prefix, name, found, custom_name=custom_name)
                    dst_path = os.path.join(target_dir, dst_name)
                    if is_hot:
                        dst_path = unique_destination(dst_path)
                    safe_copy_file(found, dst_path)
                    result["copied"] += 1
                    try:
                        found_mtime = os.path.getmtime(found)
                    except OSError:
                        found_mtime = 0
                    result["found"].append((b["bed_idx"], i, name, found, found_mtime))
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
        write_json_atomic(JIGS_FILE, default_jigs, ensure_ascii=False, indent=2)
        return default_jigs
    try:
        with open(JIGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        backup_corrupt_file(JIGS_FILE, e)
        return []

def save_jigs_data(jigs_list):
    write_json_atomic(JIGS_FILE, jigs_list, ensure_ascii=False, indent=2)

def load_models_data():
    try:
        with open(MODELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        backup_corrupt_file(MODELS_FILE, e)
        return []

def save_models_data(models_list):
    write_json_atomic(MODELS_FILE, models_list, ensure_ascii=False, indent=2)
