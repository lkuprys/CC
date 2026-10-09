# Atnaujinimų ir išleidimų sistema – techninė specifikacija

Dokumentas skirtas kūrėjams ir AI agentams, kurie prižiūri ar keičia **Podbase Container Studio**
atnaujinimų mechanizmą arba išleidžia naujas versijas. Jame aprašyta visa grandinė: nuo kodo pakeitimo
iki to, kai programa gamybos kompiuteryje pati atsinaujina.

Repozitorija: `lkuprys/CC`. Platforma: Windows 10/11, Python 3.11, PySide6, PyInstaller (`--onedir`).

---

## 1. Architektūra

```
 Kūrėjas / agentas                     GitHub                                  Gamybos kompiuteris
 ─────────────────                     ──────                                  ───────────────────
 šaka X.Y.Z  ──merge──▶ main ──▶ Actions „Išleisti atnaujinimą“ (rankinis)
                                   │ 1. next_version.py  → CURRENT_VERSION
                                   │ 2. testai (pytest)
                                   │ 3. PyInstaller → dist/Podbase_Konteineriai/
                                   │ 4. package_release.py → Podbase_Studio_vX.Y.Z.zip
                                   │ 5. release_notes.py ← KAS_NAUJO.md
                                   │ 6. commit „Versija vX.Y.Z“ → main, tag vX.Y.Z
                                   │ 7. gh release create (+ZIP, --latest)
                                   ▼
                          GitHub Release vX.Y.Z  ◀──── API /releases/latest ──── AppUpdater (kas 30 min.)
                                   │                                               │ dialogas → atsisiuntimas
                                   └──────── ZIP (browser_download_url) ─────────▶ │ patikra (dydis, SHA-256, struktūra)
                                                                                   │ išarchyvavimas į %TEMP%
                                                                                   │ PowerShell skriptas
                                                                                   ▼
                                                                  failų keitimas → grąžinimas klaidos atveju → paleidimas
```

Principai:
- **Viena versijos tiesa** – `CURRENT_VERSION` faile `updater.py`. Ją keičia tik workflow.
- **Išleidimas tik per GitHub Actions** (rankinis paleidimas). Vietinio išleidimo skripto nėra.
- **Atnaujinimas atominis iš vartotojo pusės**: arba visa nauja versija, arba atstatoma sena. Programa paleidžiama visada.
- **Vartotojo duomenys neliečiami**: nustatymai ir istorija gyvena šalia `.exe`, ne pakete.

---

## 2. Failai ir atsakomybės

| Failas | Paskirtis |
|---|---|
| `updater.py` | `CURRENT_VERSION`, versijos tikrinimas, atsisiuntimas, ZIP patikra, PowerShell keitimo skriptas, dialogai, `AppUpdater` valdiklis |
| `app_gui.py` | `AppUpdater` integracija: laikmačiai, rankinis tikrinimas, nustatymai, rezultato rodymas paleidus |
| `podbase_core.py` | `BASE_DIR`, `ensure_local_data_files()` (pradiniai JSON tik pirmą kartą), žurnalas `podbase.log` |
| `package_release.py` | Release ZIP sudarymas iš `dist/` |
| `.github/workflows/release.yml` | Išleidimo procesas (Windows runner) |
| `.github/workflows/tests.yml` | Testai po kiekvieno push (Linux runner) |
| `.github/scripts/next_version.py` | Naujos versijos skaičiavimas ir įrašymas į `updater.py` |
| `.github/scripts/release_notes.py` | Pakeitimų aprašas → `dist/release_notes.md`, `KAS_NAUJO.md` išvalymas |
| `KAS_NAUJO.md` | Kito išleidimo pakeitimų sąrašas (pildo kūrėjas, išvalo workflow) |
| `build.bat` | Tik vietiniam kompiliavimui / bandymams (neišleidžia) |
| `config.json` | Numatytieji nustatymai naujai instaliacijai (`github_repo`, `auto_check_updates`) |

---

## 3. Versijų numeravimas

- Formatas `MAJOR.MINOR.PATCH`, tag'as `vMAJOR.MINOR.PATCH` (pvz. `v1.2.4`).
- Release asset'o pavadinimas: `Podbase_Studio_vX.Y.Z.zip`.
- Politika:
  - `patch` – klaidų taisymai ir smulkios funkcijos (numatytasis);
  - `minor` – pastebimi pakeitimai (pvz. naujas dizainas – v1.2.0);
  - `major` – nesuderinami pakeitimai (pvz. nustatymų formato pakeitimas).

### 3.1 `next_version.py` logika

1. Nuskaito `CURRENT_VERSION` iš `updater.py` (regex `^CURRENT_VERSION\s*=\s*"([^"]+)"`).
2. Randa didžiausią tag'ą `v*` (reikia `fetch-depth: 0`).
3. Jei versija kode **didesnė** už paskutinį tag'ą, naudoja ją. Taip galima rankiniu būdu nustatyti, pvz., `2.0.0`.
4. Kitu atveju padidina paskutinį tag'ą pagal `bump` (`patch` / `minor` / `major`).
5. Įrašo naują reikšmę į `updater.py` ir išveda `version=X.Y.Z` į `$GITHUB_OUTPUT`.

Svarbu: versija įrašoma **prieš** PyInstaller, todėl sukompiliuota programa žino savo tikrąją versiją.

### 3.2 Palyginimas kliento pusėje

`parse_version_tuple()` paverčia `v1.2.3`, `1.2`, `v2.0.0-beta` į `(1,2,3)`, `(1,2,0)`, `(2,0,0)`
(priesagos `-…` ir `+…` atmetamos). Atnaujinimas siūlomas tik kai nuotolinė versija **griežtai didesnė**.
Grąžinti senesnės versijos per atnaujintoją neįmanoma: tam reikia išleisti naują, didesnę versiją su senu kodu.

---

## 4. Išleidimo procesas (`release.yml`)

Paleidimas: **GitHub → Actions → „Išleisti atnaujinimą“ → Run workflow**.

Įvestys:
- `notes` (neprivaloma) – pakeitimų aprašas. Jei tuščia, imamas `KAS_NAUJO.md`.
- `bump` – `patch` (numatyta) / `minor` / `major`.

Nustatymai: `runs-on: windows-latest`, `permissions: contents: write`, `concurrency: release`
(du išleidimai vienu metu nevyksta; antras laukia eilėje).

| # | Žingsnis | Ką daro | Nepavykus |
|---|---|---|---|
| 1 | Paimti kodą | `checkout@v4`, `fetch-depth: 0` (reikia tag'ų) | – |
| 2 | Python | 3.11, pip talpykla | – |
| 3 | Nustatyti versiją | `next_version.py` → `steps.ver.outputs.version` | Workflow sustoja |
| 4 | Įdiegti bibliotekas | `requirements.txt` | Sustoja |
| 5 | Patikrinti sintaksę | `py_compile` visiems moduliams | Sustoja, niekas neišleista |
| 6 | Testai | `pytest -q` | **Sustoja, niekas neišleista** |
| 7 | Kompiliuoti | PyInstaller `--onedir --windowed`, `--add-data` JSON, logotipai, `fonts` | Sustoja |
| 8 | Sudaryti ZIP | `package_release.py` + patikra, kad ZIP'e yra `Podbase_Konteineriai/Podbase_Konteineriai.exe` | Sustoja |
| 9 | Pakeitimų aprašas | `release_notes.py`: `NOTES` → `KAS_NAUJO.md` → commit'ų pavadinimai → „Smulkūs patobulinimai.“; `KAS_NAUJO.md` išvalomas | – |
| 10 | Įrašyti versiją | commit „Versija vX.Y.Z“ (`updater.py`, `KAS_NAUJO.md`) → `git push origin HEAD:main`; tag → push | Push į main nepavyksta → sustoja (žr. 9 sk.) |
| 11 | Sukurti Release | `gh release create vX.Y.Z <zip> --notes-file dist/release_notes.md --latest` | – |

Rezultatas: GitHub Release su vienu asset'u ir pažymėtas **Latest**.
Visi įdiegti klientai jį pamatys per ≤ 30 min. arba kito paleidimo metu.

### 4.1 Release ZIP struktūra (`package_release.py`)

```
Podbase_Studio_vX.Y.Z.zip
├── Podbase_Konteineriai/              ← PyInstaller --onedir rezultatas
│   ├── Podbase_Konteineriai.exe
│   └── _internal/                     ← Python, Qt, moduliai, --add-data failai (models.json, jigs.json, config.json, fonts/ …)
├── Chrome_Extension/                  ← Extension/ turinys
├── Paleisti_Programa.bat
└── NAUDOJIMO_INSTRUKCIJA.md
```

`_internal/` esantys JSON yra tik **pradinės reikšmės** naujai instaliacijai (žr. 6 sk.).

### 4.2 `tests.yml`

Paleidžiamas po kiekvieno push į bet kurią šaką ir PR (ne tag'ams), `ubuntu-latest`:
`py_compile` → `pyflakes` (neapibrėžti vardai = klaida) → `pytest -q`.
Tai greita apsauga prieš sujungiant į `main`. `release.yml` testus paleidžia dar kartą Windows'e.

---

## 5. Atnaujinimas kliento pusėje (`updater.py`)

### 5.1 Kada tikrinama

| Įvykis | Kada | Kodas |
|---|---|---|
| Ankstesnio atnaujinimo rezultatas | 1,5 s po paleidimo | `AppUpdater.show_last_update_result()` |
| Automatinis tikrinimas | 3,5 s po paleidimo, vėliau kas 30 min. (`PERIODIC_CHECK_INTERVAL_MS`) | `MainWindow.run_periodic_update_check()` |
| Rankinis tikrinimas | Viršutinės juostos ⟳ arba Nustatymai → Atnaujinimai → „Tikrinti atnaujinimus“ | `check_for_updates(manual=True)` |

Automatinis tikrinimas vyksta tik jei `config.json` → `auto_check_updates: true`.
Repozitorija – `config.json` → `github_repo` (numatyta `lkuprys/CC`).

### 5.2 Versijos patikra (`VersionCheckWorker`, fono gija)

`fetch_github_release_safe()` kreipiasi į `https://api.github.com/repos/<repo>/releases/latest`
trimis būdais iš eilės (pirmas sėkmingas laimi). Visais atvejais SSL sertifikatas tikrinamas.

1. `curl.exe` (Windows sistemos sertifikatų saugykla), `--max-time 12`.
2. Python `urllib` su `ssl.create_default_context()`, 10 s.
3. PowerShell `Invoke-RestMethod` (TLS 1.2), 15 s.

Toliau:
- Jei `tag_name` versija nėra didesnė už `CURRENT_VERSION` → `no_update`. Rankiniu atveju rodomas pranešimas „Naujausia versija“.
- `select_release_asset()` ima pirmą asset'ą, atitinkantį `^Podbase_Studio_v[\d.]+\.zip$`.
- SHA-256 paimamas iš asset'o lauko `digest` (`sha256:…`), jei GitHub jį pateikia.
- Signalas `update_available(dict)`: `version`, `changelog` (release body), `download_url`, `asset_size`, `asset_sha256`.

### 5.3 Sprendimas ir dialogas (`AppUpdater.on_update_available`)

- Jei asset'o nėra: rankiniu atveju įspėjimas „Nėra diegimo failo“, automatiniu – tylu.
- **Atidėjimas**: „Priminti vėliau“ tai pačiai versijai neberodomas 4 val. (`POSTPONE_SECONDS`) automatinių patikrų metu. Rankinė patikra rodo visada.
- `_busy` neleidžia atidaryti antro dialogo, kol rodomas pirmasis ar vyksta atsisiuntimas.
- `UpdateConfirmDialog`: dabartinė → nauja versija, „Kas naujo“ (release body), „Priminti vėliau“ / „Atnaujinti dabar“.

### 5.4 Atsisiuntimas (`DownloadWorker`, fono gija)

- Paskirtis: `%TEMP%\podbase_update_vX.Y.Z.zip` (senas failas pirma ištrinamas).
- 1 būdas: `curl.exe -f -L --retry 2 --connect-timeout 15`. Eiga matuojama pagal failo dydį kas 0,2 s.
- 2 būdas (jei curl nepavyko): `urllib`, 64 KB blokais, 30 s laiko limitas.
- „Atšaukti“ nutraukia procesą arba ciklą ir ištrina dalinį failą.
- **`validate_update_zip()`**, nepavykus failas ištrinamas ir rodoma klaida:
  1. dydis = `asset_size`;
  2. SHA-256 = `digest` (jei pateiktas);
  3. `zipfile.is_zipfile` + `testzip()` (CRC);
  4. ZIP'e yra `Podbase_Konteineriai/Podbase_Konteineriai.exe`.

### 5.5 Paruošimas ir perdavimas PowerShell'ui (`apply_update_and_restart`)

Vykdoma GUI gijoje praėjus 1,2 s po sėkmingo atsisiuntimo.

1. Veikia tik sukompiliuotoje programoje (`sys.frozen`). Paleidus iš šaltinio grąžinama klaida.
2. ZIP dar kartą patikrinamas (`validate_update_zip`).
3. Išarchyvuojama į `%TEMP%\podbase_update_staging` (Python `zipfile`, ne `Expand-Archive`).
4. Tikrinama, ar yra `Podbase_Konteineriai\Podbase_Konteineriai.exe` ir `_internal\`.
5. Tikrinama, ar dabartinio `.exe` pavadinimas sutampa su `PAYLOAD_EXE_NAME`. Jei ne, atnaujinimas atšaukiamas.
6. Iš `UPDATER_PS_TEMPLATE` sugeneruojamas `%TEMP%\podbase_updater.ps1`:
   - visos reikšmės įstatomos kaip PowerShell eilutės viengubose kabutėse (`_ps_quote`: `'` → `''`), todėl keliai su `$`, `` ` ``, tarpais ar lietuviškomis raidėmis saugūs;
   - failas rašomas **UTF-8 su BOM**, kitaip Windows PowerShell 5.1 sugadina ne ASCII simbolius.
7. Paleidžiama `powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File …` (`CREATE_NO_WINDOW`).
8. `QApplication.quit()` ir **`os._exit(0)`**: procesas baigiamas iškart, kad atsilaisvintų visi failai.

### 5.6 PowerShell keitimo skriptas

`$ErrorActionPreference = 'Stop'`, žurnalas `%TEMP%\podbase_updater.log`.

1. **Laukia, kol programa užsidarys**: `Wait-Process -Id <PID> -Timeout 20`. Po to priverstinai uždaro tą PID ir kitus to paties `.exe` (tas pats kelias) egzempliorius.
2. **Laukia, kol `.exe` bus atrakintas**: iki 30 bandymų kas 1 s atidaro failą su `FileShare None`. Nepavykus – klaida.
3. **Atsarginė kopija**: `_internal` pervadinamas į `_internal.old`, `.exe` nukopijuojamas į `.exe.old`.
4. **Naujas `_internal`**: `robocopy <staged>\_internal <app>\_internal /E` (švari kopija, be senų failų).
5. **Šakniniai failai**: `robocopy <staged> <app> /E /IS /IT /XD _internal _internal.old /XF models.json jigs.json config.json history.json`.
6. **Gretimi failai** (klaidos nekritinės): `Chrome_Extension\` → `<parent>\Chrome_Extension\`, `Paleisti_Programa.bat`, `NAUDOJIMO_INSTRUKCIJA.md` → `<parent>\`.
7. **Klaidos atveju – grąžinimas**: jei atsarginė kopija buvo padaryta, `_internal` grąžinamas iš `_internal.old`, `.exe` – iš `.exe.old`.
8. **`finally`** (vykdoma visada):
   - įrašomas `%TEMP%\podbase_update_result.json` (`ok`, `version`, `old_version`, `message`, `log`);
   - sėkmės atveju ištrinami `_internal.old` ir `.exe.old`;
   - ištrinami staging aplankas ir ZIP;
   - **programa paleidžiama visada** – nauja arba atstatyta sena.

`robocopy` išvestis įrašoma į žurnalą. Išėjimo kodas ≥ 8 laikomas klaida (0–7 reiškia sėkmę). Parametrai `/R:10 /W:1`.

### 5.7 Po paleidimo

`read_last_update_result()` perskaito ir ištrina `podbase_update_result.json`:
- `ok: true` → pranešimas „Programa atnaujinta, dabar naudojate vX.Y.Z“;
- `ok: false` → nuolatinis klaidos pranešimas su priežastimi ir žurnalo keliu („Palikta vX.Y.Z“).

Sąveika su vieno lango apsauga: senasis procesas baigiamas (`os._exit`) prieš paleidžiant naują,
o `QLockFile` atpažįsta nebeveikiančio proceso užraktą, todėl naujas paleidimas neužblokuojamas.

---

## 6. Vartotojo duomenų išsaugojimas

| Failas | Vieta | Atnaujinimo metu |
|---|---|---|
| `models.json`, `jigs.json`, `config.json` | šalia `.exe` (`BASE_DIR`) | **Neliečiami** (`/XF`). Naujoje instaliacijoje sukuriami iš `_internal` (`ensure_local_data_files`, tik jei failo nėra) |
| `history.json`, `temp_folders.json`, `podbase.log` | šalia `.exe` | Neliečiami (nėra pakete, `robocopy` be `/PURGE`) |
| `_internal\*.json` | pakete | Perrašomi. Tai tik pradinės reikšmės |

Pasekmė: `models.json` ar `jigs.json` pakeitimai repozitorijoje **nepasiekia** jau įdiegtų kompiuterių.
Tai sąmoningas sprendimas, kad nebūtų perrašyti vietiniai kiekvieno kompiuterio nustatymai.
Jei kada reikės sinchronizuoti modelius, tam reikės atskiros sujungimo (merge) logikos.

**Chrome plėtinys** nukopijuojamas į `Chrome_Extension\`, bet Chrome jo neperkrauna automatiškai:
kiekviename kompiuteryje reikia `chrome://extensions` → „Reload“. Versija – `Extension/manifest.json`.

---

## 7. Diagnostika

| Žurnalas / failas | Kelias | Turinys |
|---|---|---|
| Atnaujinimo žurnalas | `%TEMP%\podbase_updater.log` | PowerShell žingsniai, robocopy išvestis, klaidos, grąžinimas |
| Atnaujinimo rezultatas | `%TEMP%\podbase_update_result.json` | Paskutinio bandymo rezultatas (ištrinamas jį parodžius) |
| Programos žurnalas | `<app>\podbase.log` (3 × 1 MB) | Paleidimai, generavimai, nepagautos klaidos |
| Release būsena | GitHub → Actions / Releases | Workflow žingsnių žurnalai, asset'ai |

---

## 8. Kaip išleisti naują versiją (procedūra)

1. Darbas vyksta šakoje, pavadintoje pagal kitą versiją (pvz. `1.2.5`), sukurtoje nuo naujausio `main`.
2. Kiekvienas naudotojui matomas pakeitimas įrašomas į `KAS_NAUJO.md` (po komentaro eilute, punktais `- …`, lietuviškai, paprasta kalba). Tai bus atnaujinimo lango tekstas.
3. Vietoje: `python -m pytest -q` ir `pyflakes` turi būti švarūs.
4. Push → palaukti, kol `tests.yml` taps žalias.
5. Sujungti į `main` (fast-forward). Jei `main` pasikeitė (pvz. ankstesnio išleidimo „Versija vX.Y.Z“ commit'as), pirma sujungti `origin/main` į šaką ir išspręsti `KAS_NAUJO.md` konfliktą. Palikti tik **dar neišleistus** punktus.
6. GitHub → Actions → „Išleisti atnaujinimą“ → **Run workflow** iš `main`, nurodyti `bump`.
7. Patikrinti, ar Release turi `Podbase_Studio_vX.Y.Z.zip` ir pažymėtas **Latest**.
8. Gamybos kompiuteryje: Nustatymai → Atnaujinimai → „Tikrinti atnaujinimus“. Įsitikinti, kad viršutinėje juostoje rodoma nauja versija.
9. Jei keitėsi `Extension/`: kiekviename kompiuteryje perkrauti plėtinį.

---

## 9. Dažnos problemos

| Simptomas | Priežastis | Sprendimas |
|---|---|---|
| Išleista versija be pakeitimų | Workflow paleistas antrą kartą be naujų commit'ų (pvz. v1.2.2 = v1.2.1) | Prieš paleidžiant patikrinti `git log vX.Y.Z..main`; nepaleisti du kartus |
| Žingsnis „Įrašyti versiją“ krenta | Kol vyko build, kažkas įkėlė į `main` (non-fast-forward) | Paleisti workflow iš naujo; tag ir Release nesukuriami, todėl nieko taisyti nereikia |
| Workflow paleistas ne iš `main` | `git push origin HEAD:main` bandytų įkelti kitos šakos būseną į `main` | Visada leisti iš `main` |
| `KAS_NAUJO.md` konfliktas sujungiant | Workflow išvalo failą, o šaka jį pildo | Palikti antraštę ir tik neišleistus punktus |
| Klientas nemato atnaujinimo | `auto_check_updates: false`, atidėta 4 val., kitas `github_repo`, Release ne „Latest“ arba be asset'o | Rankinis tikrinimas; patikrinti `config.json` ir Release |
| „Atsisiųstas failas nepilnas / kontrolinė suma nesutampa“ | Nutrūkęs atsisiuntimas, tarpinis serveris | Pakartoti; patikrinti tinklą |
| „Programos failas vis dar naudojamas“ | Antivirusinė ar kitas procesas laiko `.exe` > 30 s | Žurnale matyti; buvo atstatyta sena versija, pakartoti |
| „robocopy klaida N“ (N ≥ 8) | Nėra rašymo teisių (pvz. `Program Files`), pilnas diskas | Diegti į vartotojo rašomą aplanką; atlaisvinti vietos |
| Po atnaujinimo plėtinys senas | Chrome neperkrauna unpacked plėtinio | `chrome://extensions` → „Reload“, patikrinti versiją |
| Sistemos `TEMP` kelias su specialiais simboliais | – | Palaikoma (`_ps_quote`, UTF-8 BOM) |

---

## 10. Invariantai (keisti tik suderintai visur)

Pakeitus bet kurį iš šių dalykų, būtina atnaujinti visas susijusias vietas, kitaip **sustos įdiegtų klientų atnaujinimai**:

1. Asset'o pavadinimas `Podbase_Studio_vX.Y.Z.zip`: `package_release.py`, `release.yml` (ZIP patikra, `gh release create`), `RELEASE_ASSET_PATTERN`.
2. Programos aplanko ir `.exe` pavadinimas `Podbase_Konteineriai` / `Podbase_Konteineriai.exe`: PyInstaller `--name`, `PAYLOAD_DIR_NAME`, `PAYLOAD_EXE_NAME`, ZIP patikra workflow'e.
   Keičiant pavadinimą seni klientai atsisakys atnaujinti (5.5 p. 5 punktas). Reikalingas pereinamasis išleidimas.
3. `CURRENT_VERSION = "X.Y.Z"` eilutės formatas (regex `next_version.py`).
4. PyInstaller `--onedir` struktūra su `_internal/` (PyInstaller ≥ 6). Kitokia struktūra sugadintų 5.6 p. 3–5 punktus.
5. Vietinių failų sąrašas `/XF` PowerShell skripte ir `ensure_local_data_files()`.
6. `permissions: contents: write` ir push į `main` workflow'e.
7. `--add-data` sąrašas `release.yml` ir `build.bat` turi sutapti (pvz. `fonts;fonts`).
8. Atnaujintojas pats save keičia per išorinį PowerShell procesą. Pakeitimai `UPDATER_PS_TEMPLATE` įsigalioja tik **nuo kito** atnaujinimo, nes keitimą atlieka *senoji* versija. Klaida šiame skripte gali sugadinti visus atnaujinimus, todėl jį testuoti ypač atsargiai.

---

## 11. Saugumas ir ribojimai

- Vientisumas: dydis ir SHA-256 tikrinami pagal GitHub API, TLS tikrinamas visuose kanaluose.
- Autentiškumas: kodo parašo nėra. Pasitikima GitHub repozitorija ir paskyra, todėl prieiga prie `lkuprys/CC` = galimybė įdiegti kodą visuose kompiuteriuose. Apsaugoti paskyrą (2FA). `main` šakos apsauga rekomenduojama.
- Galimas patobulinimas: pasirašyti ZIP (pvz. Ed25519 raktas, viešasis raktas įkompiliuotas į programą) ir tikrinti parašą prieš diegiant.
- Klientas neturi „kanalų“ (beta / stable): visi gauna „Latest“. Pre-release žymėti per GitHub UI nebūtina, nes `/releases/latest` jų negrąžina.
- Grąžinti senesnę versiją galima tik išleidus naują, didesnę versiją su senu kodu (`git revert` → išleidimas).
