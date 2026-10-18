# -*- coding: utf-8 -*-
"""
.prn generavimas be ColorGATE: stalo dizainai išdėstomi pagal modelio koordinates
ir sudedami į vieną spausdintuvo failą (colorgate_prn paketas).

Koordinatės (kaip ColorGATE konteineryje), centimetrais:
  container_x / container_y – žingsnis tarp gretimų lizdų (atstumas tarp dizainų pradžių),
  print_x / print_y         – kur ant stalo prasideda pirmas dizainas,
  height                    – spausdinimo aukštis (tik informacija operatoriui).
Pirmas dizainas visada kairėje apačioje: vieta i → stulpelis i % cols (iš kairės),
eilė i // cols (iš apačios).

Modulis be Qt – testuojamas be PySide6. numpy/tifffile importuojami tik generuojant.
"""
import os
import time
import threading
from datetime import datetime

import podbase_core as core
from podbase_core import log, BLANK_TOKEN

PRN_DEFAULTS = {
    "container_x": 0.0, "container_y": 0.0,
    "print_x": 0.0, "print_y": 0.0,
    "height": 0.0,
    "include_print_offset": True,
}

PRN_CONFIG_DEFAULTS = {
    "output_dir": "",          # tuščia → Darbalaukis\Konteineriai\PRN
    "bundle_dir": "",          # tuščia → programos colorgate_prn\bundle_gunsjet
    "table_width_mm": 2500,
    "table_height_mm": 1300,
    "schedule_enabled": False,
    "schedule_times": [],      # ["07:00", "13:30"]
}

PRN_EXTENSIONS = {".tif", ".tiff"}


def model_prn_settings(model):
    """Modelio .prn nustatymai su numatytomis reikšmėmis (models.json → "prn")."""
    out = dict(PRN_DEFAULTS)
    for k, v in ((model or {}).get("prn") or {}).items():
        if k in out:
            out[k] = v
    for k in ("container_x", "container_y", "print_x", "print_y", "height"):
        try:
            out[k] = float(out[k])
        except (TypeError, ValueError):
            out[k] = 0.0
    out["include_print_offset"] = bool(out["include_print_offset"])
    return out


def prn_config():
    """Bendri .prn nustatymai iš config.json → "prn"."""
    cfg = dict(PRN_CONFIG_DEFAULTS)
    cfg.update((core.load_app_config().get("prn") or {}))
    cfg["schedule_times"] = normalize_times(cfg.get("schedule_times"))
    return cfg


def save_prn_config(prn_cfg):
    cfg = core.load_app_config()
    cfg["prn"] = prn_cfg
    core.save_app_config(cfg)


def default_output_dir():
    return os.path.join(core.DESKTOP_DIR, "PRN")


def default_bundle_dir():
    return core.get_res_path(os.path.join("colorgate_prn", "bundle_gunsjet"))


def normalize_times(times):
    """["7:5", " 13:30", "blogai", "13:30"] → ["07:05", "13:30"] (surūšiuota, be pasikartojimų)."""
    out = set()
    for t in times or []:
        try:
            h, m = str(t).strip().split(":")
            h, m = int(h), int(m)
        except ValueError:
            continue
        if 0 <= h < 24 and 0 <= m < 60:
            out.add(f"{h:02d}:{m:02d}")
    return sorted(out)


def due_schedule_time(times, now, last_runs):
    """
    Grąžina tvarkaraščio laiką ("HH:MM"), kurį reikia vykdyti dabar, arba None.
    Laikas vykdomas, kai jau atėjo (iki 30 min. pavėlavus – pvz. programa buvo užimta),
    ir šiandien dar nebuvo vykdytas. last_runs: {"HH:MM": "YYYY-MM-DD"}.
    """
    today = now.strftime("%Y-%m-%d")
    minutes_now = now.hour * 60 + now.minute
    for t in normalize_times(times):
        h, m = map(int, t.split(":"))
        late = minutes_now - (h * 60 + m)
        if 0 <= late <= 30 and last_runs.get(t) != today:
            return t
    return None


# ----------------- IŠDĖSTYMAS -----------------
def cm_to_px(cm, dpi):
    return int(round(float(cm) * 10.0 / 25.4 * dpi))


def layout_bed(slots, cols, settings, xdpi, ydpi, table_mm=None):
    """
    slots: [(vieta, plotis_px, aukštis_px)] – tik užpildyti lizdai, vieta = indeksas stale.
    Grąžina (pozicijos {vieta: (x, y)} – kairysis viršutinis kampas puslapio pikseliais,
             puslapio plotis, aukštis, įspėjimai).
    """
    cols = max(1, int(cols or 1))
    off_x = settings["print_x"] if settings["include_print_offset"] else 0.0
    off_y = settings["print_y"] if settings["include_print_offset"] else 0.0
    placed = []  # (vieta, x kairė, apačia nuo stalo apačios, w, h) pikseliais
    for idx, w, h in slots:
        col, row = idx % cols, idx // cols
        x = cm_to_px(off_x + col * settings["container_x"], xdpi)
        bottom = cm_to_px(off_y + row * settings["container_y"], ydpi)
        placed.append((idx, x, bottom, w, h))
    if not placed:
        return {}, 0, 0, []
    page_w = max(x + w for _, x, _, w, _ in placed)
    page_h = max(b + h for _, _, b, _, h in placed)
    positions = {idx: (x, page_h - (b + h)) for idx, x, b, w, h in placed}

    warnings = []
    by_idx = sorted(placed)
    for a in range(len(by_idx)):
        for b in range(a + 1, len(by_idx)):
            ia, xa, ba, wa, ha = by_idx[a]
            ib, xb, bb, wb, hb = by_idx[b]
            if xa < xb + wb and xb < xa + wa and ba < bb + hb and bb < ba + ha:
                warnings.append(f"Dizainai {ia + 1} ir {ib + 1} persidengia – padidinkite konteinerio X/Y žingsnį.")
    if table_mm:
        tw, th = table_mm
        full_w = page_w / xdpi * 25.4 + (0 if settings["include_print_offset"] else settings["print_x"] * 10)
        full_h = page_h / ydpi * 25.4 + (0 if settings["include_print_offset"] else settings["print_y"] * 10)
        if full_w > tw + 0.5 or full_h > th + 0.5:
            warnings.append(f"Išdėstymas ({full_w:.0f} × {full_h:.0f} mm) netelpa ant stalo ({tw:.0f} × {th:.0f} mm).")
    return positions, page_w, page_h, warnings


# ----------------- GENERAVIMAS -----------------
_prn_job_lock = threading.Lock()


def run_prn_job(plan, progress=None):
    """
    plan = {
        "source_dir", "file_types", "search_network",      – kaip konteinerio plane
        "out_dir": str, "bundle_dir": str (nebūtina),
        "cols": int, "prn": modelio nustatymai (model_prn_settings), "table_mm": (2500, 1300),
        "beds": [{"bed_idx", "title", "items": [pavadinimas | BLANK_TOKEN | None, ...]}]  – eilės tvarka nuo 01; BLANK_TOKEN/None – praleista vieta
    }
    Grąžina {"files", "missing", "errors", "warnings", "found", "ambiguous", "search_roots", "search_seconds", "placed"}.
    """
    if not _prn_job_lock.acquire(blocking=False):
        if progress:
            progress(0, 0, "Laukiama, kol baigsis kitas .prn generavimas...")
        _prn_job_lock.acquire()
    try:
        started = time.time()
        res = _run_prn_job(plan, progress)
        log.info(
            f".prn: {len(plan.get('beds', []))} stal., failų {len(res['files'])}, nerasta {len(res['missing'])}, "
            f"klaidų {len(res['errors'])} → {plan.get('out_dir')} ({time.time() - started:.1f} s, "
            f"paieška {res.get('search_seconds', 0):.1f} s)"
        )
        for err in res["errors"]:
            log.warning(f"  .prn klaida: {err}")
        for warn in res["warnings"]:
            log.warning(f"  .prn dėmesio: {warn}")
        return res
    except Exception:
        log.exception(".prn generavimas nepavyko")
        raise
    finally:
        _prn_job_lock.release()


def _run_prn_job(plan, progress=None):
    def report(text, done=0, total=0):
        if progress:
            progress(done, total, text)

    result = {"files": [], "missing": [], "errors": [], "warnings": [], "found": [], "ambiguous": [],
              "search_roots": [], "placed": 0}
    _, matches = core.resolve_plan_files(plan, result, report)

    report("Ruošiamas spausdinimo failas...")
    from colorgate_prn import ColorGateSetup, Job, generate_prn, job_size, Screen

    bundle = plan.get("bundle_dir") or default_bundle_dir()
    setup = ColorGateSetup.load_bundle(bundle)
    screen = Screen.load(setup.screen)
    settings = plan["prn"]
    out_dir = plan.get("out_dir") or default_output_dir()
    os.makedirs(out_dir, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    used = set()
    for b in plan["beds"]:
        bed_no = b["bed_idx"] + 1
        slots, jobs_by_idx = [], {}
        for i, name in enumerate(b["items"]):
            if not name or name == BLANK_TOKEN:
                continue
            found = matches.get((b["bed_idx"], i))
            if not found:
                result["missing"].append((b["bed_idx"], i, name))
                continue
            if os.path.splitext(found)[1].lower() not in PRN_EXTENSIONS:
                result["errors"].append(f"{core.missing_label(name)} (stalas {bed_no}, vieta {i + 1}): "
                                        f".prn galima sudaryti tik iš TIF failų – rastas {os.path.basename(found)}")
                result["missing"].append((b["bed_idx"], i, name))
                continue
            try:
                w, h = job_size(found, setup)
            except Exception as e:
                result["errors"].append(f"{core.missing_label(name)}: nepavyko perskaityti TIF – {e}")
                result["missing"].append((b["bed_idx"], i, name))
                continue
            slots.append((i, w, h))
            jobs_by_idx[i] = found
            try:
                mtime = os.path.getmtime(found)
            except OSError:
                mtime = 0
            result["found"].append((b["bed_idx"], i, name, found, mtime))

        if not slots:
            result["errors"].append(f"Stalas {bed_no}: nėra nei vieno TIF failo – .prn nesukurtas.")
            continue

        positions, page_w, page_h, warns = layout_bed(slots, plan.get("cols", 1), settings,
                                                      setup.xdpi, setup.ydpi, plan.get("table_mm"))
        result["warnings"].extend(f"Stalas {bed_no}: {w}" for w in warns)
        jobs = [Job(jobs_by_idx[i], *positions[i]) for i, _, _ in slots]

        title = core.safe_folder_name(b.get("title") or "", f"Stalas_{bed_no}")
        base = f"{title}_{stamp}"
        n = 2
        while base.lower() in used:
            base = f"{title}_{stamp}_{n}"
            n += 1
        used.add(base.lower())
        final = core.unique_destination(os.path.join(out_dir, base + ".prn"))
        part = final + ".part"
        bmp = os.path.splitext(final)[0] + ".bmp"

        def on_lines(y, total, _bed=bed_no):
            report(f"Stalas {_bed}: generuojama {y * 100 // max(1, total)} %", y, total)

        try:
            generate_prn(jobs, part, setup, screen, page_w, page_h, bmp_path=bmp, progress=on_lines)
            os.replace(part, final)
        except Exception as e:
            result["errors"].append(f"Stalas {bed_no}: .prn sukurti nepavyko – {e}")
            for p in (part,):
                try:
                    os.remove(p)
                except OSError:
                    pass
            continue
        result["placed"] += len(jobs)
        result["files"].append({
            "bed_idx": b["bed_idx"], "path": final, "bmp": bmp, "designs": len(jobs),
            "width_mm": round(page_w / setup.xdpi * 25.4, 1), "height_mm": round(page_h / setup.ydpi * 25.4, 1),
        })
    return result
