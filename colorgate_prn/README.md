# colorgate_prn — ColorGate PRN generavimas be ColorGate

Atkuria ColorGate Productionserver 10 išvestį spausdintuvui **GUNSJET 2513**
(720×1200 dpi, kanalai C M Y K Lc Lm W, 2 bitai/pikselis).

Palyginimas su tikru ColorGate PRN (`2681 test 2vnt_1_1_1.prn`):

| kanalas | identiški pikseliai |
|---|---|
| C | 99.97 % |
| M | 99.94 % |
| Y | 99.83 % |
| K | 99.94 % |
| Lc | 99.54 % |
| Lm | 99.69 % |
| W | 99.998 % |

Likę skirtumai daugiausia kyla iš rastro matricos, kuri dabar yra **įvertinta** iš pavyzdžio.
Kaip ją padaryti tikslią, žr. skyrių „Kalibracija“.

## Diegimas

```
pip install numpy tifffile imagecodecs pillow scipy
```

## Greitas startas

```
python -m colorgate_prn generate --bundle colorgate_prn/bundle_gunsjet --layout layout_example.json --out lapas.prn
```

Arba iš Python:

```python
from colorgate_prn import ColorGateSetup, Job, generate_prn

setup = ColorGateSetup.load_bundle("colorgate_prn/bundle_gunsjet")
jobs = [Job("106887.tif", x=0, y=0),               # pozicija įrenginio pikseliais
        Job.mm("106888.tif", x_mm=352.15, y_mm=0)]   # arba milimetrais
generate_prn(jobs, "lapas.prn", setup)               # sukuria ir lapas.bmp
```

## Pozicijos ir ofsetai (keičiami)

* **Darbų koordinatės:** `Job(tif, x, y)` pikseliais arba `Job.mm(...)`, `layout.json` failas
  (`"units": "px"` arba `"mm"`), arba `side_by_side(tifs, setup, gap_px)`.
  ColorGate pavyzdyje: 1-as darbas x=0, 2-as x=9982 (tarpas 1195 px = 42,2 mm), y=0.
* **Lapo dydis:** `page_width` / `page_height`; jei nenurodyta, lapas apima visus darbus.
* **Rastro kanalų ofsetai:** `data/SpeedScreen_256x448px.json`, laukas `"offsets"`:
  kanalas → `[ox, oy]`. Kanalas skaito slenkstį `thr[(y+oy) % 448, (x+ox) % 256]`,
  kur x, y skaičiuojami nuo darbo kairiojo viršutinio kampo.

## ColorGate grandinė (atkurta ir patikrinta)

1. TIF CMYK → **USWebCoatedSWOP.icc → Kingt 720x1200 M+ 300.icm**, santykinis kolorimetrinis + BPC
   (ColorGate intent 7), LittleCMS.
2. Užduoties kreivė Yellow kanalui (`settings.xml` → `ExtraColorTransfer`, kubinė Bézier kreivė).
3. **Lin2**: 4 kanalų 1D kreivės (.ccx `Linearization Id=2`, ICC DeviceLink, rašalo ribos).
4. **Rašalo skaidymas**: C → C + Lc, M → M + Lm (.ccx `ColorTransfer`).
5. **Lin1**: 6 kanalų 1D kreivės (maks. rašalas: C 34,9 %, M 65,1 %, Y 80 %, K 70,2 %, Lc 94,1 %, Lm 91 %).
6. **Lašų dydžiai** (.ccx `DropletCurves`): tonas 0–0,33 → mažas lašas 0→100 %,
   0,33–0,66 → mažas→vidutinis, 0,66–1 → vidutinis→didelis.
7. **W**: spot kanalas „W“ → DeviceWhite (`w.cct`), kiekis = 1 − W/255 (Photoshop spot konvencija),
   be ICC konversijos.
8. **Mastelis**: dydis = ceil(px × 720/300) ir ceil(px × 1200/300); Mitchell-Netravali kubinė
   interpoliacija (B=C=1/3), centruota. Pirma keičiamas CMYK mastelis, po to spalvos.
9. **Speed Screen 256×448**: viena 8 bitų slenksčių matrica visiems kanalams, kiekvienas kanalas
   turi savo ofsetą, matrica pririšta prie darbo kampo.
   `lygis = floor(t) + (round(frac(t)·255) > slenkstis)`.
10. **PRN**: 48 B antraštė + eilutės pakaitomis po kanalą, 4 px/baitas (žr. `prn_format.py`).

## Bundle (be ColorGate)

`bundle_gunsjet/` turi ICC profilius ir `setup.json` (kreivės). Jei ColorGate nustatymai pasikeičia
(kitas profilis, .ccx ar Y kreivė), bundle sukurkite iš naujo:

```
python -m colorgate_prn bundle --job-settings "C:\ProgramData\ColorGATE Software\Productionserver10\JobDir\GUNSJET 2513\<darbas>.CJB\settings.xml" --out colorgate_prn/bundle_gunsjet
```

## Kalibracija (tikslus rastras)

1. `python -m colorgate_prn chart --out chart.tif`. Sukuriami `chart.tif` ir `chart.json`.
2. `chart.tif` per ColorGate su tais pačiais nustatymais, išvestis į failą (spausdinti nereikia).
3. `python -m colorgate_prn calibrate --prn chart.prn --chart chart.json`.
   Įrašomas tikslus `data/SpeedScreen_256x448px.*`. Įvertinta versija lieka `..._estimated`.

## Palyginimas

```
python -m colorgate_prn compare colorgate.prn mano.prn
```

## Ko neatkurta

* **BMP:** ColorGate BMP beveik tuščias. Čia daroma paprasta spalvota miniatiūra (500 px pločio).
* **Antraštė:** laukų 0x1C, 0x20 ir 0x2C prasmė nežinoma, juose visada 0.
* **Spalvos:** ±1/255 skirtumai, nes LittleCMS skaičiuoja 8 bitais, o ColorGate turi savo CMM.
