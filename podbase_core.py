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
            log.warning(f"[scan_print_files_recursive klaida ties {root_dir}]: {e}")

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
                base_name = safe_folder_name(design_name, stem_file or "Dizainas")

    return f"{num_prefix}_{base_name}{ext}"

# ----------------- KONTEINERIO GENERAVIMAS FONE (be užstrigimo) -----------------
# Tinklo aplankų skenavimas gali užtrukti, todėl rezultatas trumpam įsimenamas.
# Jei su įsimintu sąrašu kurio nors failo nerandama, sąrašas automatiškai perskenuojamas.
SCAN_CACHE_TTL_SECONDS = 120
_scan_cache = {}
_scan_cache_lock = threading.Lock()


def get_scanned_files(search_roots, force=False):
    """Grąžina (failų sąrašas, ar paimta iš atminties)."""
    key = tuple(os.path.normcase(os.path.normpath(r)) for r in search_roots)
    roots_mtime = _roots_mtime(search_roots)
    if not force:
        with _scan_cache_lock:
            hit = _scan_cache.get(key)
        # Jei pagrindiniame aplanke atsirado / dingo failas, sąrašas nebeaktualus
        if hit and time.time() - hit[0] < SCAN_CACHE_TTL_SECONDS and hit[2] == roots_mtime:
            return hit[1], True
    files = scan_print_files_recursive(search_roots)
    with _scan_cache_lock:
        _scan_cache[key] = (time.time(), files, roots_mtime)
    return files, False


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
            found = matches.get((b["bed_idx"], i))

            if found:
                try:
                    dst_name = format_output_filename(num_prefix, name, found, custom_name=custom_name)
                    dst_path = os.path.join(target_dir, dst_name)
                    if is_hot:
                        dst_path = unique_destination(dst_path)
                    safe_copy_file(found, dst_path)
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
