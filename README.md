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
  - Automatinis nerastų failų aptikimas su **mirksinčiu raudonu indikatoriumi** ekrane.
- **⏳ Saugus 10 Minučių Laikinas Aplankas (Auto-Cleanup):**
  - Sukuria paruoštus spaudos konteinerius darbalaukyje su automatiniu pasenusių aplankų išvalymu.
  - Galimybė nustatyti tiesioginį siuntimą į *ColorGATE HotFolder*.
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
1. Faile `updater.py` padidinkite `CURRENT_VERSION` (pvz. `1.1.1` → `1.1.2`).
2. Paleiskite: `py publish_release.py "Kas pasikeitė šioje versijoje"` (reikia prisijungusio `gh`).
3. Programos, kurios atidarytos, pasiūlys atnaujinimą per 30 min. arba kito paleidimo metu.

Skriptas sustos, jei tokia versija jau išleista. Atnaujinimo žurnalas kompiuteryje: `%TEMP%\podbase_updater.log`.

---

## 🧩 Naršyklės Plėtinio Įdiegimas

1. Atidarykite **Google Chrome** (arba Edge/Brave) ir eikite į `chrome://extensions/`.
2. Viršuje dešinėje įjunkite **„Developer mode“** (Kūrėjo režimas).
3. Spustelėkite **„Load unpacked“** (Įkelti neišpakuotą).
4. Pasirinkite aplanką **`Extension/`** iš šios repozitorijos.

---

## ⚙️ Nustatymai (`config.json`)

```json
{
  "theme": "LIGHT",
  "auto_cleanup_minutes": 10,
  "github_repo": "lkuprys/CC",
  "auto_check_updates": true
}
```

---

## 📄 Licencija
Sukurta vidiniam naudojimui gamybos procesų optimizavimui. Visos teisės saugomos.
