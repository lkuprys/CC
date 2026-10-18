# colorgate_prn — ColorGate PRN generavimas be ColorGate

Atkuria ColorGate Productionserver išvestį dviem spausdintuvams:

| bundle | spausdintuvas | įvestis | raiška | kanalai | rastras |
|---|---|---|---|---|---|
| `bundle_gunsjet` | GUNSJET 2513 (PS10) | CMYK TIF + W spot | 720×1200 | C M Y K Lc Lm W | Speed Screen 256×448 |
| `bundle_flora` | Flora XTRA2512UV, hotfolder „POD F2“ (PS23) | RGB PNG | 720×1800 | C M Y K Lc Lm | Error Diffusion („Smooth“) |

Pastaba: ColorGate 23 eilė vadinasi „GUNSJET 2513“, bet jos PRN spausdina Flora valdiklis
(`CG OUTPUT\POD F2`). Senasis GUNSJET bundle priklauso Productionserver 10 kompiuteriui.

## Diegimas

```
pip install --user numpy tifffile imagecodecs pillow scipy numba
```

`numba` reikalingas klaidų difuzijai (Flora).

## Flora: greitas startas

```
python -m colorgate_prn generate --bundle colorgate_prn/bundle_flora --layout layout_flora.json --out lapas.prn
```

`layout_flora.json` (ColorGate konteinerio išdėstymas, mm):

```json
{
  "container": {"gap_mm": 221.2, "top_mm": 26.5, "page_width_mm": 850.2},
  "jobs": [ {"image": "01_testastestas.png"}, {"image": "02_PID-107854.png"} ]
}
```

Arba iš Python:

```python
from colorgate_prn import ColorGateSetup, Job, generate_prn, container_layout
s = ColorGateSetup.load_bundle("colorgate_prn/bundle_flora")
jobs = container_layout(["a.png", "b.png"], s, gap_mm=221.2, top_mm=26.5)   # arba Job("a.png", x=0, y=1878)
generate_prn(jobs, "lapas.prn", s, page_width=24100)                        # sukuria ir lapas.bmp
```

### Ką daro ColorGate (Flora), nustatyta iš PRN ir JobDir

* **PRN antraštė:** tokia pati kaip GUNSJET (48 B, `YR`), 6 kanalai C M Y K Lc Lm, 2 bitai, 3 lašų dydžiai.
  Eilutės ilgis baitais lygiuojamas į 4 (6025 → 6028).
* **Darbo dydis:** hotfolder'is kiekvieną darbą ištempia iki **200 × 261 mm** (proporcijos nelaikomos):
  5669 × 18496 px. Dydis nepriklauso nuo PNG dpi.
* **Pasukimas:** 180° (`TURN2`).
* **Konteineris:** darbai iš kairės į dešinę, x = Σ(round(200 mm) + round(221,2 mm)) = 0, 11939 px;
  y = round(26,5 mm) = 1878; lapo plotis 850,2 mm = 24100 px; aukštis = 1878 + 18496.
  Viską galima keisti per `layout.json` (`container` arba `jobs` su `x`/`y` px ar mm).
* **Mastelis:** pirma keičiamas RGB mastelis (Mitchell kubinis, centruotas), paskui spalvos.
  Branduolio ar eiliškumo pakeitimas tonų beveik nekeičia (< 0,001).
* **Spalvos:** sRGB → „Soft leather 260410 285H+ 10_100K.icc“ → kreivės → 2026.ccx (Lin2, C/M skaidymas į
  šviesius rašalus, Lin1, lašų dydžiai 1/3 ir 2/3). ColorGate'o RGB→CMYK žingsnio LittleCMS neatkuria:
  balta (255,255,255) ColorGate gauna apie 3,5 % C/M/K (rašalas ant baltos: K 1,1 %, Lc 1,7 %, Lm 1,3 %).
  Todėl RGB→įrenginio CMYK **išmatuotas kalibracijos lentele** (13³ tinklelis + pilkų skalė).
  Modelis (`setup.json` → `rgb_lut`): LittleCMS perceptual (sRGB → išvesties profilis) duoda formą tarp
  tinklelio taškų (K pradžia, GCR), o išmatuota pataisa (`residual`, tetraedrinė interpoliacija) ją
  pritraukia prie ColorGate tinklelio taškuose. Tamsiems beveik pilkiems tonams taikoma papildoma
  pataisa iš 256 pilkų langelių (`grey_corr`). Viskas daroma įrenginio CMYK erdvėje, prieš netiesinį
  C→C+Lc / M→M+Lm skaidymą. Perceptual pagrindas veikė geriau nei relative, saturation ar vien lentelė.
* **Rastras:** daugialygė Floyd–Steinberg klaidų difuzija (7/16, 3/16, 5/16, 1/16), slenkstis 0,5,
  klaida prasideda nuo 0 darbo kampe, serpentine. Pirmoji taškų eilutė baltame plote sutampa su ColorGate
  tiksliai (Lc 16-a, Lm 21-a, K 25-a eilutė, taškai kas 5 px), bet toliau taškų vietos skiriasi.

### Tikslumas (testas: `Container - 01_testastestas_1_1_1.prn`)

| kanalas | vid. lygis ColorGate | vid. lygis mūsų | identiški px | bloko (32 px) tono klaida p99 |
|---|---|---|---|---|
| C | 0.0020 | 0.0020 | 99.6 % | 0.002 |
| M | 0.0194 | 0.0199 | 96.6 % | 0.005 |
| Y | 0.0433 | 0.0434 | 93.2 % | 0.004 |
| K | 0.1003 | 0.1001 | 90.1 % | 0.007 |
| Lc | 0.0605 | 0.0604 | 90.9 % | 0.003 |
| Lm | 0.0586 | 0.0579 | 91.4 % | 0.007 |

(Su pagrindine ir tamsių tonų lentele. Vien su pagrindine K p99 buvo 0,044, o giliuose šešėliuose K iki 0,34
lygio per mažai.) Tonai (rašalo kiekis plote) sutampa, atskiri taškai — ne: klaidų difuzija chaotiška,
vos kitokia tono reikšmė duoda kitas taškų vietas.

### Aukšto tarpo režimas (`--high-gap`)

Kai galvutės nuo paviršiaus 3–4 mm (pvz., nuo UV šilumos išsipūtę safiano sleeve'ai):

```
python -m colorgate_prn generate --bundle colorgate_prn/bundle_flora --layout layout_flora.json --out lapas.prn --high-gap
```

* **Be mažų lašų** (`--drops 0,2,3`). Tas pats rašalo kiekis sudedamas perpus mažesniu kiekiu vidutinių lašų,
  kurie skrenda tiesiau ir mažiau virsta „rūku“. Klaidų difuzija išlaiko vidutinį lygį (rašalo tūrį).
  ColorGate šiems vaizdams beveik vien mažus lašus naudoja (testo PRN: 98 % visų lašų).
* **Šviesus fonas lieka kaip ColorGate** (`--small-below 0.05`). Profilis baltoms vietoms deda šviesiai
  pilką melsvą foną (~1,1 % K, 1,7 % Lc, 1,3 % Lm). Tokie šviesūs tonai toliau spausdinami mažais lašais.
* Bandymas ant safiano sleeve'ų 3–4 mm aukštyje: maždaug +1,5–2 mm naudojamo tarpo, tik lengvas šešėlis į šoną.
  Pirmoje versijoje fonas buvo nuimtas (`--floor 0.03`), todėl dingo. Dabar `--floor` pagal nutylėjimą 0,
  jo nenaudokite, jei fonas reikalingas.
* Prielaida: vidutinis lašas ≈ 2 maži (KM1024i 6/12/18 pL).

Variantai (vidutinis lygis visuose kaip ColorGate: M 0.0199, Y 0.0434, K 0.100, Lc 0.0604, Lm 0.0579):

| failas | komanda | fonas | likęs vaizdas |
|---|---|---|---|
| `mano_flora.prn` | (be parinkčių) | maži lašai | maži lašai (kaip ColorGate) |
| `mano_flora_highgap.prn` | `--high-gap` | maži lašai, identiškas ColorGate | vidutiniai lašai |
| `mano_flora_highgap_B.prn` | `--drops 0,2,3` | vidutiniai lašai (perpus rečiau) | vidutiniai lašai |

### Kalibracija (spalvos)

1. `python -m colorgate_prn rgb-chart --out flora_rgb_chart.png` (2339×3059 px, kaip tikri darbai).
2. **Originalų** PNG failą (nekeistą, nesumažintą) įmeskite į „POD F2“ hotfolder'į, išvestis į failą.
3. ```
   python -m colorgate_prn calibrate-rgb --bundle colorgate_prn/bundle_flora --prn "<ColorGate PRN>" ^
          --chart flora_rgb_chart.json --image "<JobDir\<darbas>.CJB\EPS-Data\*.png>"
   ```
   `--image`: būtent tas PNG, kurį gavo ColorGate (jei jis buvo sumažintas, langelių pozicijos perskaičiuojamos).

Dabartinė lentelė išmatuota iš `Container - image-1792312558838_1_1_1.prn` (lentelė buvo sumažinta iki 1529×2000).

**Tamsių tonų lentelė (rekomenduojama):** `rgb-chart --kind dark` (11³ spalvų 0–96, jau sukurta:
`flora_rgb_chart_dark.png`). Paleiskite per „POD F2“ ir pridėkite prie esamų matavimų su `--add`:

```
python -m colorgate_prn calibrate-rgb --add --bundle colorgate_prn/bundle_flora --prn "<PRN>" ^
       --chart flora_rgb_chart_dark.json --image "<JobDir\<darbas>.CJB\EPS-Data\*.png>"
```

Modelis tada naudoja 20 lygių tinklelį (abiejų lentelių lygių sąjunga).

Dabartiniame bundle yra abi: pagrindinė (`Container - image-1792312558838_1_1_1.prn`) ir tamsi
(`flora_rgb_chart_dark_1_1_1.prn`, suripinta ranka su POD F1 nustatymais, originalaus dydžio — matavimas
darbo dydį atpažįsta pats). Persidengiančios spalvos abiejose lentelėse sutampa ±0,0003.

### Bundle sukūrimas iš naujo (pasikeitus profiliui, .ccx ar hotfolder'iui)

```
python -m colorgate_prn bundle --job-settings "C:\ProgramData\ColorGATE Software\Productionserver23\JobDir\GUNSJET 2513\<darbas>.CJB\settings.xml" --out colorgate_prn/bundle_flora
```

Po to būtinai paleiskite kalibraciją iš naujo, nes `bundle` lentelės nesukuria.

## GUNSJET 2513 (senas, Productionserver 10)

```
python -m colorgate_prn generate --bundle colorgate_prn/bundle_gunsjet --layout layout_example.json --out lapas.prn
```

Grandinė: TIF CMYK → USWebCoatedSWOP → „Kingt 720x1200 M+ 300.icm“ (rel. kolorimetrinis + BPC) → Y kreivė →
Lin2 → C/M skaidymas → Lin1 → lašai; W spot → DeviceWhite; Speed Screen 256×448
(`data/SpeedScreen_256x448px.*`, kanalų ofsetai `"offsets"`). Tiksli matrica:
`chart` → ColorGate → `calibrate` (žr. `calibrate.py`). Identiški px: 99,5–99,99 %.

## Kitos komandos

```
python -m colorgate_prn compare colorgate.prn mano.prn
python -m colorgate_prn info failas.prn
```

## Ko neatkurta

* **Flora taškų vietos:** tikslus ColorGate klaidų difuzijos variantas (kraštai, tono kvantavimas) nežinomas.
* **BMP:** paprasta spalvota miniatiūra (500 px pločio, kaip ColorGate), turinys kitoks.
* **Antraštė:** laukų 0x1C, 0x20 ir 0x2C prasmė nežinoma, ten visada 0.
