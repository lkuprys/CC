# Užduotis: pridėti funkciją „HighGap“

Šis aplankas skirtas įkelti į GitHub ir perduoti agentui (ar programuotojui), kuris integruos jį į
programą, kuri dabar gamina PRN failus Flora XTRA2512UV spausdintuvui.

## Kas čia yra

| kelias | kas tai |
|---|---|
| `colorgate_prn/` | Python paketas: PNG/TIF → PRN (+ BMP), atkuria ColorGate Productionserver išvestį |
| `colorgate_prn/bundle_flora/` | Flora nustatymai: profiliai + `setup.json` (išmatuotas spalvų modelis) |
| `colorgate_prn/bundle_gunsjet/`, `data/` | senas GUNSJET 2513 (Speed Screen), HighGap ten netaikomas |
| `colorgate_prn/README.md` | išsamus aprašas (formatai, tikslumas, kalibracija) |
| `tests/test_high_gap.py` | HighGap priėmimo testas |
| `layout_flora.example.json` | lapo išdėstymo pavyzdys (ColorGate konteineris „POD F2“) |
| `requirements.txt` | priklausomybės |

## Kas yra HighGap

Spausdinant ant safiano sleeve'ų, jie nuo UV šilumos išsipučia, todėl atstumas nuo galvučių iki paviršiaus
vietomis būna 3–4 mm. Iš tokio aukščio maži (6 pL) lašai nukrypsta ir virsta „rūku“.

HighGap režimas (išbandytas spausdinant, „variantas A“):
* vietoj mažų lašų naudojami vidutiniai: tas pats rašalo kiekis, perpus mažiau lašų, jie skrenda tiesiau;
* labai šviesūs tonai (< 0,05 lašo lygio) lieka mažais lašais. Tai profilio šviesiai pilkas melsvas fonas
  ant baltos (~1 % K, 1,7 % Lc, 1,3 % Lm), kuris **privalo išlikti** (pirmoje versijoje jis buvo nuimtas, ir tai klaida);
* rezultatas: maždaug +1,5–2 mm naudojamo tarpo, tik lengvas šešėlis į šoną. Spalvos ir fonas kaip ColorGate.

Parametrai yra `colorgate_prn/generator.py` → `HIGH_GAP = {"allowed_levels": (0, 2, 3), "small_below": 0.05, "floor": 0.0}`.
**Jų nekeisti** be naujo bandomojo spaudinio. Ypač nenustatyti `floor > 0`, nes tai nuima foną.

## Ką reikia padaryti programoje

1. Įtraukti paketą `colorgate_prn` (šio aplanko turinį) į programos repozitoriją, kartu su `bundle_flora/`.
2. Įdiegti priklausomybes: `pip install -r requirements.txt` (būtinas `numba`, be jo klaidų difuzija neveikia).
3. Pridėti **įjungiamą nustatymą „HighGap“** (varnelė / jungiklis UI ir/arba laukas konfigūracijoje bei
   užduoties parametruose). Numatytoji reikšmė: **išjungta** (išvestis tada tokia kaip ColorGate).
4. Generuojant PRN perduoti reikšmę į paketą:

   ```python
   from colorgate_prn import ColorGateSetup, generate_prn, load_layout

   setup = ColorGateSetup.load_bundle("colorgate_prn/bundle_flora")   # įkelti vieną kartą
   jobs, page_w, page_h = load_layout("layout.json", setup)           # arba Job(...) / container_layout(...)
   generate_prn(jobs, "lapas.prn", setup, page_width=page_w, page_height=page_h,
                high_gap=settings.high_gap)                            # <- HighGap jungiklis
   ```

   Komandinė eilutė (jei programa kviečia CLI):

   ```
   python -m colorgate_prn generate --bundle colorgate_prn/bundle_flora --layout layout.json --out lapas.prn [--high-gap]
   ```

5. HighGap galima įjungti visam lapui arba atskirai užduočiai, jei programa leidžia (vienas lapas = vienas
   `generate_prn` kvietimas, tad režimas taikomas visam lapui).
6. Pageidautina: PRN failo pavadinime ar žurnale pažymėti, kad naudotas HighGap (pvz., `_HG` priesaga),
   kad operatorius matytų, kuris failas kuriuo režimu sugeneruotas.
7. Jungiklis prasmingas tik bundle'ams su klaidų difuzija (Flora). Su `bundle_gunsjet` `generate_prn(..., high_gap=True)`
   meta `ValueError`: UI turėtų jungiklį slėpti arba išjungti.

## Priėmimo kriterijai

* `python tests/test_high_gap.py` (arba `python -m pytest tests`) praeina.
* HighGap išjungtas: PRN identiškas tam, kurį paketas generavo iki integracijos (tas pats kodas, tie patys parametrai).
* HighGap įjungtas: PRN antraštė, dydis ir darbų pozicijos tokios pačios kaip be HighGap, tik kitokie lašai.
  Patikrinti galima `python -m colorgate_prn compare a.prn b.prn`: vidutinis lygis („mean lvl“) visuose
  kanaluose turi sutapti ±2 %.
* Šviesus fonas ant baltos išlieka (žr. testą).

## Svarbu

* `bundle_flora/` turi ColorGate/ECI ICC profilius ir išmatuotą spalvų modelį. Repozitoriją laikykite **privačią**.
* Didelių failų (`*.prn`, `*.bmp`, bandomųjų PNG) į Git nekelti (`.gitignore` tai jau daro).
* Generavimas: ~50 s dviem 200×261 mm darbams lape 720×1800 dpi. Pirmas paleidimas po įdiegimo ~1–2 s ilgesnis (numba kompiliacija).
