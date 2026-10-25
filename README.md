# 🖨️ Podbase Container Studio

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6%20%2F%20QFluentWidgets-green.svg)](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
[![Platform Windows](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-lightgrey.svg)]()
[![Release](https://img.shields.io/badge/release-v1.1.1-emerald.svg)]()

**Podbase Container Studio** – profesionali UV spaudos stalų (rėmų / jigs) išdėstymo ir automatizuoto spaudos failų paruošimo sistema, skirta UV spausdintuvams (pvz., Roland, Mimaki, ColorGATE RIP).

---

## 🌟 Pagrindinės Funkcijos

- **📐 Dinaminis UV Stalų Išdėstymas (Jigs):**
  - Palaiko įvairių konfigūracijų rėmus (pvz., `1x7` Sleeve, `2x5` iPad/MacBook, `3x6` Dėklai, `2x2` Deskmats).
  - Automatinis elementų numeravimas ir užpildymas pagal operatoriaus nustatytą gamybos tvarką.
- **🖱️ Interaktyvus Drag & Drop:**
  - Lizdų sukeitimas vietomis (Swap) velkant vieną elementą ant kito.
  - Išorinių failų ar nuotraukų įkėlimas nutempiant tiesiai iš darbalaukio arba naršyklės.
  - Lizdų dubliavimas ir greitas išvalymas.
- **🌐 Naršyklės Plėtinio Integracija (Chrome Extension):**
  - Integruotas vietinis `Flask` API serveris (`localhost:5000`), kuris akimirksniu priima užsakymo dizainus iš valdymo sistemos vienu paspaudimu.
- **🔍 Pažangus Spaudos Failų Paieškos Variklis:**
  - Rekursyviai skenuoja tinklo (`\\192.168.1.143\...`) ir vietinius aplankus pagal PID numerius ir failų pavadinimus.
  - Papildomai galima nurodyti brokų (rejected) aplanką: *Nustatymai → 📂 Paieškos Aplankai*.
  - Automatinis nerastų failų aptikimas su **mirksinčiu raudonu indikatoriumi** ekrane.
- **⏳ Saugus 10 Minučių Laikinas Aplankas (Auto-Cleanup):**
  - Sukuria paruoštus spaudos konteinerius darbalaukyje su automatiniu pasenusių aplankų išvalymu.
  - Galimybė nustatyti tiesioginį siuntimą į *ColorGATE HotFolder*.
- **🖨️ Spausdinimo failas (.prn) be ColorGATE:**
  - Mygtukas *Generuoti .prn* sudeda stalo TIF failus pagal modelio koordinates (konteinerio X/Y – tarpai tarp dizainų, print X/Y – atitraukimas nuo pasirinkto atskaitos kampo, kuriame stovi ir pirmas dizainas; numatyta kairė apačia) į vieną GUNSJET 2513 `.prn` failą (+ `.bmp` peržiūra).
  - Generavimas pagal tvarkaraštį: *Nustatymai → Automatinis .prn*. Koordinatės – *Nustatymai → Modeliai → Spausdinimo failas (.prn)*.
  - Spausdintuvas parenkamas kiekvienam modeliui (`prn.printer`): `gunsjet` – GUNSJET 2513 (CMYK TIF + W), `flora` – Flora XTRA2512UV (RGB PNG, klaidų difuzija, reikia `numba`). Papildomas bundle aplankas (`prn.bundle_dir` nustatymuose) rodomas kaip „Kitas“. `prn.high_gap` – HighGap režimas (be mažų lašų, tik klaidų difuzijos spausdintuvams; failo pavadinime `_HG`).
  - Rastravimo variklis – `colorgate_prn/` (žr. jo `README.md`). Senas būdas (HotFolderis / laikinas aplankas) veikia kaip anksčiau.
- **🧽 Rėmo paruošimas:**
  - Skirtukas *Rėmo paruošimas*: švarus rėmas užpildomas paruošimo dizainu (`remo_paruosimas/f1.png` → rėmas „F1…“, `f2.png` → „F2“, `f3.png` → „F3“) ir visos vietos siunčiamos į pasirinktą HotFolderį (`01_F2_PARUOSIMAS.png` …). Failai įdiegiami kartu su programa; naują rėmą galima pridėti įdėjus `f4.png`.
- **📜 Užsakymų Istorija ir Greitas Atkūrimas:**
  - Išsaugo visų atliktų generavimų istoriją su galimybe bet kada atkurti ar pergeneruoti užsakymą.
- **🚀 Automatinis Atnaujinimų Tikrinimas (Auto-Updater):**
  - Fone asinchroniškai tikrina naujausias „GitHub Releases“ versijas.
  - Tikrina paleidus programą ir kas 30 min., kol programa atidaryta.
  - Fluent UI iššokantis langas su pakeitimų sąrašu (*Changelog*), siuntimo progreso juosta ir automatiniu programos persikrovimu.
  - Atsisiųstas ZIP patikrinamas (dydis, SHA-256, struktūra). Nepavykus atnaujinimui, atstatoma senoji versija ir programa vis tiek paleidžiama.
  - Vietiniai `models.json`, `jigs.json`, `config.json`, `history.json` atnaujinimo metu neliečiami.

---

## 🚀 Paleidimas ir Diegimas

### 1. Reikalavimai
- Python 3.10 ar naujesnė versija.
- Windows 10 arba Windows 11.

### 2. Įdiegimas
```bash
# Klonuokite repozitoriją
git clone https://github.com/lkuprys/CC.git
cd CC

# Įdiekite reikalingas bibliotekas
pip install -r requirements.txt

# Paleiskite programą
python app_gui.py
```

### 3. Kompiliavimas į savarankišką `.exe` failą
Norėdami sukompiliuoti programą į atskirą vykdomąjį `.exe` failą:
```bash
build.bat
```
Sukompiliuota programa bus sugeneruota aplanke `dist/Podbase_Konteineriai/`.

### 4. Naujos versijos išleidimas (atnaujinimas visiems kompiuteriams)
Viskas daroma GitHub svetainėje, nieko nereikia diegti ar kompiliuoti savo kompiuteryje:

1. Atidarykite https://github.com/lkuprys/CC/actions/workflows/release.yml
2. Spauskite **„Run workflow“**, įrašykite, kas pasikeitė, ir dar kartą **„Run workflow“**.
3. Po ~5 min. atsiras naujas leidimas skiltyje *Releases*. Atidarytos programos pasiūlys atnaujinimą per 30 min. arba kito paleidimo metu.

Versijos numeris padidinamas automatiškai. Atnaujinimo žurnalas kompiuteryje: `%TEMP%\podbase_updater.log`.

---

## 🧩 Naršyklės Plėtinio Įdiegimas

1. Atidarykite **Google Chrome** (arba Edge/Brave) ir eikite į `chrome://extensions/`.
2. Viršuje dešinėje įjunkite **„Developer mode“** (Kūrėjo režimas).
3. Spustelėkite **„Load unpacked“** (Įkelti neišpakuotą).
4. Pasirinkite aplanką **`Extension/`** iš šios repozitorijos.

---

## 🧪 Testai

Programos logika (paieška, failų pavadinimai, generavimas, valymas, API) tikrinama automatiškai:

```bash
pip install pytest
python -m pytest -q
```

GitHub'e testai paleidžiami po kiekvieno pakeitimo (*Actions → Testai*) ir prieš kiekvieną išleidimą – jei testai nepraeina, nauja versija neišleidžiama.

Kodo struktūra: `podbase_core.py` – logika be sąsajos, `prn_job.py` – .prn išdėstymas ir generavimas, `colorgate_prn/` – TIF → .prn rastravimas, `api_server.py` – naršyklės plėtinio API, `app_gui.py` – sąsaja, `ui_kit.py` – išvaizda (Podbase WORK spalvos, šriftai, mygtukai, laukai, pranešimai), `updater.py` – atnaujinimai.

Išvaizdos pavyzdžiai prieš ir po: `docs/dizainas/`. Šriftas Inter (OFL licencija, `fonts/`) įtraukiamas į programos paketą.

## 🩺 Klaidų žurnalas

Programa rašo žurnalą `podbase.log` šalia `.exe` (*Nustatymai → Atnaujinimai ir Versija → Atidaryti žurnalą*). Ten matyti kiekvieno generavimo santrauka, nerasti failai, įspėjimai ir klaidos.

## ⚙️ Nustatymai (`config.json`)

```json
{
  "theme": "LIGHT",
  "auto_cleanup_minutes": 10,
  "github_repo": "lkuprys/CC",
  "auto_check_updates": true,
  "reject_folder": "",
  "api_host": "127.0.0.1",
  "prn": {
    "output_dir": "",
    "bundle_dir": "",
    "table_width_mm": 2500,
    "table_height_mm": 1300,
    "show_button": true,
    "schedule_enabled": false,
    "schedule_times": ["07:00", "13:30"]
  }
}
```

- `auto_cleanup_minutes` – po kiek minučių ištrinami programos sukurti laikini aplankai. Trinami **tik** programos sukurti aplankai (jie įsimenami faile `temp_folders.json`), jūsų pačių aplankai neliečiami.
- `api_host` – kur klauso naršyklės plėtinio serveris (5000 prievadas). Numatyta `127.0.0.1` – pasiekiamas tik iš to paties kompiuterio. Jei plėtinys siunčia iš **kito** kompiuterio, įrašykite `"0.0.0.0"` ir plėtinio nustatymuose nurodykite šio kompiuterio IP.
- `reject_folder` – papildomas brokų aplankas paieškai.
- `prn` – `.prn` generavimas: `output_dir` (tuščia → `Darbalaukis\Konteineriai\PRN`), `bundle_dir` (tuščia → su programa įdiegti GUNSJET profiliai), stalo dydis ir tvarkaraštis. Modelio koordinatės saugomos `models.json` → `"prn": {"container_x", "container_y", "print_x", "print_y", "height", "include_print_offset", "output_dir", "printer", "high_gap", "origin", "mirror_x", "row_direction", "table_width", "table_height", "units": "mm"}` (`origin`: `bottom_left` | `top_left` | `bottom_right` | `top_right`; `row_direction`: `right_to_left` (numatyta, kaip Studijoje) | `left_to_right`; `table_width/height` – plotas, į kurį turi sutilpti dizainai, 0 – pagal rėmą) (milimetrais; senos reikšmės be `units` laikomos centimetrais ir perskaičiuojamos; `output_dir` – modelio .prn aplankas, tuščia → bendras).

---

## 📄 Licencija
Sukurta vidiniam naudojimui gamybos procesų optimizavimui. Visos teisės saugomos.
