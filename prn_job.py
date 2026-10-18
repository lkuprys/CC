# -*- coding: utf-8 -*-
"""
.prn generavimas be ColorGATE: stalo dizainai išdėstomi pagal modelio koordinates
ir sudedami į vieną spausdintuvo failą (colorgate_prn paketas).

Koordinatės (kaip ColorGATE konteineryje), milimetrais:
  container_x / container_y – tarpas tarp gretimų dizainų (nuo vieno krašto iki kito krašto),
  print_x / print_y         – kiek visas išdėstymas atitrauktas nuo atskaitos kampo (origin),
  height                    – spausdinimo aukštis (tik informacija operatoriui).
Atskaitos kampas (origin, numatyta kairė apačia) – nuo jo matuojamas Print X/Y; eilės skaičiuojamos
nuo jo (i // cols), o eilėje dizainai dedami iš dešinės į kairę (kaip Container Studio) arba atvirkščiai.
Modelio stalo dydis (table_width/height) nurodo plotą, į kurį dizainai turi sutilpti.

Modulis be Qt – testuojamas be PySide6. numpy/tifffile importuojami tik generuojant.
"""
import os
import time
import threading
from datetime import datetime

import podbase_core as core
from podbase_core import log, BLANK_TOKEN

DEFAULT_PRINTER = "gunsjet"
CUSTOM_PRINTER = "custom"

PRN_DEFAULTS = {
    "container_x": 0.0, "container_y": 0.0,
    "print_x": 0.0, "print_y": 0.0,
    "height": 0.0,
    "include_print_offset": True,
    "output_dir": "",          # tuščia → bendras aplankas (config.json → prn.output_dir)
    "units": "mm",
    "printer": DEFAULT_PRINTER,
    "origin": "bottom_left",
    "row_direction": "right_to_left",   # kaip Container Studio; arba "left_to_right"
    "table_width": 0.0,        # mm; 0 → stulpelių tiek, kiek rėme
    "table_height": 0.0,       # mm; 0 → eilių neribojama
}

PRN_ROW_DIRECTIONS = {
    "right_to_left": "Iš dešinės į kairę (kaip Studijoje)",
    "left_to_right": "Iš kairės į dešinę",
}

PRN_ORIGINS = {
    "bottom_left": "Kairė apačia",
    "top_left": "Kairė viršus",
    "bottom_right": "Dešinė apačia",
    "top_right": "Dešinė viršus",
}

PRN_LENGTH_KEYS = ("container_x", "container_y", "print_x", "print_y", "height", "table_width", "table_height")

PRN_CONFIG_DEFAULTS = {
    "output_dir": "",          # tuščia → Darbalaukis\Konteineriai\PRN
    "bundle_dir": "",          # papildomas spausdintuvas (bundle aplankas) – modeliuose pasirenkamas kaip „custom“
    "table_width_mm": 2500,
    "table_height_mm": 1300,
    "schedule_enabled": False,
    "schedule_times": [],      # ["07:00", "13:30"]
}

CMYK_EXTENSIONS = {".tif", ".tiff"}
RGB_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}

# Žinomi spausdintuvai (colorgate_prn/bundle_<id>); kiti bundle_* aplankai rodomi pagal pavadinimą
KNOWN_PRINTERS = {
    "gunsjet": "GUNSJET 2513 – CMYK TIF + baltas (Productionserver 10)",
    "flora": "Flora XTRA2512UV – RGB PNG, „POD F2“ (Productionserver 23)",
}



def model_prn_settings(model):
    """
    Modelio .prn nustatymai su numatytomis reikšmėmis (models.json → "prn"), ilgiai milimetrais.
    v1.3.0 reikšmės buvo saugomos centimetrais be "units" – jos paverčiamos milimetrais.
    """
    raw = (model or {}).get("prn") or {}
    scale = 1.0 if raw.get("units") == "mm" else 10.0
    out = dict(PRN_DEFAULTS)
    for k, v in raw.items():
        if k in out:
            out[k] = v
    for k in PRN_LENGTH_KEYS:
        try:
            out[k] = round(float(raw.get(k, 0.0)) * scale, 3)
        except (TypeError, ValueError):
            out[k] = 0.0
    out["units"] = "mm"
    if out.get("origin") not in PRN_ORIGINS:
        out["origin"] = "bottom_left"
    out["printer"] = str(out.get("printer") or DEFAULT_PRINTER)
    if out.get("row_direction") not in PRN_ROW_DIRECTIONS:
        out["row_direction"] = "right_to_left"
    out["include_print_offset"] = bool(out["include_print_offset"])
    out["output_dir"] = str(out.get("output_dir") or "").strip()
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


def _bundles_root():
    return core.get_res_path("colorgate_prn")


def available_printers(cfg=None):
    """{id: pavadinimas} – su programa įdiegti spausdintuvai (bundle_*) ir, jei nurodytas, papildomas aplankas."""
    out = {}
    root = _bundles_root()
    try:
        names = sorted(os.listdir(root))
    except OSError:
        names = []
    for n in names:
        if n.startswith("bundle_") and os.path.exists(os.path.join(root, n, "setup.json")):
            pid = n[len("bundle_"):]
            out[pid] = KNOWN_PRINTERS.get(pid, pid)
    custom = (cfg if cfg is not None else prn_config()).get("bundle_dir")
    if custom:
        out[CUSTOM_PRINTER] = f"Kitas: {custom}"
    return out


def printer_bundle_dir(printer, cfg=None):
    """Spausdintuvo bundle aplankas: custom → nustatymų aplankas, kitaip colorgate_prn/bundle_<id>."""
    if printer == CUSTOM_PRINTER:
        custom = (cfg if cfg is not None else prn_config()).get("bundle_dir")
        if custom:
            return custom
        printer = DEFAULT_PRINTER
    return os.path.join(_bundles_root(), f"bundle_{printer or DEFAULT_PRINTER}")


def default_bundle_dir():
    return printer_bundle_dir(DEFAULT_PRINTER, {})


def printer_name(printer, cfg=None):
    return available_printers(cfg).get(printer) or KNOWN_PRINTERS.get(printer) or str(printer)


def _prepare_numba():
    """Klaidų difuzijos (Flora) numba talpykla – rašomame programos aplanke (ne įdiegtame _internal)."""
    os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(core.BASE_DIR, "numba_cache"))


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
def mm_to_px(mm, dpi):
    return int(round(float(mm) / 25.4 * dpi))


def layout_bed(slots, cols, settings, xdpi, ydpi, table_mm=None):
    """
    slots: [(vieta, plotis_px, aukštis_px)] – tik užpildyti lizdai, vieta = eilės numeris (0 = pirmas).
    Lizdo dydis – didžiausias stalo dizainas (to paties modelio dizainai vienodi), tarp lizdų –
    konteinerio X/Y tarpas, tad tuščia vieta užima tiek pat, kiek dizainas.
    Stulpelių skaičius: kiek telpa į modelio stalo plotį (table_width), o jei jis 0 – pagal rėmą (cols).
    Eilės pildomos iš dešinės į kairę (kaip Container Studio) arba iš kairės į dešinę (row_direction).
    Grąžina (pozicijos {vieta: (x, y)} – kairysis viršutinis kampas puslapio pikseliais,
             puslapio plotis, aukštis, įspėjimai, netilpusios vietos).
    """
    if not slots:
        return {}, 0, 0, [], []
    warnings, overflow = [], []
    off_x = settings["print_x"] if settings["include_print_offset"] else 0.0
    off_y = settings["print_y"] if settings["include_print_offset"] else 0.0
    cell_w = max(w for _, w, _ in slots)
    cell_h = max(h for _, _, h in slots)
    gap_x, gap_y = mm_to_px(settings["container_x"], xdpi), mm_to_px(settings["container_y"], ydpi)
    step_x, step_y = cell_w + gap_x, cell_h + gap_y
    x0, y0 = mm_to_px(off_x, xdpi), mm_to_px(off_y, ydpi)

    table_w, table_h = settings.get("table_width") or 0, settings.get("table_height") or 0
    if table_w > 0:
        avail = mm_to_px(table_w - settings["print_x"], xdpi)
        cols = max(0, (avail + gap_x) // step_x)
    else:
        cols = max(1, int(cols or 1))
    rows_max = None
    if table_h > 0:
        avail = mm_to_px(table_h - settings["print_y"], ydpi)
        rows_max = max(0, (avail + gap_y) // step_y)
    if cols == 0 or rows_max == 0:
        warnings.append(f"Dizainas ({cell_w / xdpi * 25.4:.0f} × {cell_h / ydpi * 25.4:.0f} mm) netelpa į modelio "
                        f"stalą ({table_w or '–'} × {table_h or '–'} mm).")
        return {}, 0, 0, warnings, [idx for idx, _, _ in slots]

    rtl = settings.get("row_direction", "right_to_left") == "right_to_left"
    n_total = max(idx for idx, _, _ in slots) + 1
    block_w = cols * cell_w + (cols - 1) * gap_x
    origin = settings.get("origin", "bottom_left")
    right, top = origin.endswith("_right"), origin.startswith("top_")

    # dx – atstumas nuo atskaitos kampo šoninio krašto, dy – nuo jo viršaus/apačios
    placed = []  # (vieta, dx, dy, w, h) pikseliais
    for idx, w, h in slots:
        row, k = idx // cols, idx % cols
        if rows_max is not None and row >= rows_max:
            overflow.append(idx)
            continue
        if not rtl:
            c = k
        elif row == 0 and n_total < cols:
            c = n_total - 1 - k          # nepilna pirma eilė – kaip Studijoje, prie kairiojo krašto
        else:
            c = cols - 1 - k
        left = c * step_x                # nuo bloko kairiojo krašto
        dx = x0 + (block_w - left - cell_w if right else left)
        placed.append((idx, dx, y0 + row * step_y, w, h))
    if overflow:
        warnings.append(f"Netilpo į modelio stalą ({table_w or '–'} × {table_h or '–'} mm): "
                        f"{len(overflow)} diz. – jie į failą neįtraukti.")
    if not placed:
        return {}, 0, 0, warnings, overflow

    page_w = max(dx + w for _, dx, _, w, _ in placed)
    page_h = max(dy + h for _, _, dy, _, h in placed)
    positions = {idx: (page_w - dx - w if right else dx, dy if top else page_h - dy - h)
                 for idx, dx, dy, w, h in placed}

    by_idx = sorted(placed)
    for a in range(len(by_idx)):
        for b in range(a + 1, len(by_idx)):
            ia, xa, ba, wa, ha = by_idx[a]
            ib, xb, bb, wb, hb = by_idx[b]
            if xa < xb + wb and xb < xa + wa and ba < bb + hb and bb < ba + ha:
                warnings.append(f"Dizainai {ia + 1} ir {ib + 1} persidengia – padidinkite konteinerio X/Y tarpą.")
    if table_mm and not (table_w > 0 and table_h > 0):
        tw, th = table_mm
        full_w = page_w / xdpi * 25.4 + (0 if settings["include_print_offset"] else settings["print_x"])
        full_h = page_h / ydpi * 25.4 + (0 if settings["include_print_offset"] else settings["print_y"])
        if full_w > tw + 0.5 or full_h > th + 0.5:
            warnings.append(f"Išdėstymas ({full_w:.0f} × {full_h:.0f} mm) netelpa ant stalo ({tw:.0f} × {th:.0f} mm).")
    return positions, page_w, page_h, warnings, overflow


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
    _prepare_numba()
    from colorgate_prn import ColorGateSetup, Job, generate_prn, job_size
    from colorgate_prn.generator import make_screen

    settings = plan["prn"]
    bundle = plan.get("bundle_dir") or printer_bundle_dir(settings.get("printer"))
    setup = ColorGateSetup.load_bundle(bundle)
    screen = make_screen(setup)
    takes_rgb = bool(setup.rgb_input_profile or setup.rgb_lut)
    allowed = RGB_EXTENSIONS if takes_rgb else CMYK_EXTENSIONS
    kinds = "PNG / JPG / TIF" if takes_rgb else "TIF"
    out_dir = settings.get("output_dir") or plan.get("out_dir") or default_output_dir()
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
            if os.path.splitext(found)[1].lower() not in allowed:
                result["errors"].append(f"{core.missing_label(name)} (stalas {bed_no}, vieta {i + 1}): "
                                        f"šiam spausdintuvui .prn sudaromas iš {kinds} failų – rastas "
                                        f"{os.path.basename(found)}")
                result["missing"].append((b["bed_idx"], i, name))
                continue
            try:
                w, h = job_size(found, setup)
            except Exception as e:
                result["errors"].append(f"{core.missing_label(name)}: nepavyko perskaityti failo – {e}")
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
            result["errors"].append(f"Stalas {bed_no}: nėra nė vieno tinkamo ({kinds}) failo – .prn nesukurtas.")
            continue

        positions, page_w, page_h, warns, overflow = layout_bed(slots, plan.get("cols", 1), settings,
                                                                setup.xdpi, setup.ydpi, plan.get("table_mm"))
        result["warnings"].extend(f"Stalas {bed_no}: {w}" for w in warns)
        for i in overflow:
            name = b["items"][i]
            result["errors"].append(f"{core.missing_label(name)} (stalas {bed_no}, vieta {i + 1}): netilpo į modelio stalą")
            result["missing"].append((b["bed_idx"], i, name))
            result["found"] = [f for f in result["found"] if (f[0], f[1]) != (b["bed_idx"], i)]
        if not positions:
            result["errors"].append(f"Stalas {bed_no}: nė vienas dizainas netilpo – .prn nesukurtas.")
            continue
        jobs = [Job(jobs_by_idx[i], *positions[i]) for i, _, _ in slots if i in positions]

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
