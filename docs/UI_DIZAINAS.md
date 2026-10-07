# Podbase Container Studio – sąsajos dizainas

Vizualinė kalba: **Podbase WORK** – rami, plokščia, šiltai neutrali gamybos priemonė.
Daug baltos erdvės, ploni rėmeliai, jokių šešėlių, gradientų, švytėjimo ar animacijų (išskyrus įkėlimo indikatorius).
Kiekvienoje srityje – vienas aiškus pagrindinis veiksmas. Sąsajos tekstas – lietuviškai.

Šaltinis kode: `ui_kit.py` (žetonai, stilius, elementai), `app_gui.py` (ekranai).
Ekrano nuotraukos: `docs/dizainas/`.

---

## 1. Spalvos

### 1.1 Šviesi tema

| Žetonas | Reikšmė | Paskirtis |
|---|---|---|
| `page` | `#F8F8F7` | Puslapio fonas |
| `card` | `#FFFFFF` | Kortelės, skydeliai, laukai, viršutinė juosta |
| `fill` | `#F0F0EE` | Švelnus užpildas, užvedimas pele, segmentų takelis |
| `pressed` | `#E7E7E5` | Paspaustas mygtukas |
| `text` | `#171717` | Pagrindinis tekstas |
| `secondary` | `#5F5F5F` | Antrinis tekstas, piktogramos |
| `muted` | `#8A8A8A` | Etiketės, užuominos, vietos rezervavimo tekstas |
| `disabled` | `#B5B5B5` | Neaktyvus tekstas |
| `border` | `#E7E7E5` | Numatytasis rėmelis |
| `divider` | `#EEEEEC` | Skirtukai tarp eilučių / sričių |
| `strong` | `#D8D8D5` | Ryškesnis rėmelis (užvedus, tušti lizdai) |
| `primary` | `#111111` | Pagrindinis mygtukas |
| `primary_hover` | `#2A2A2A` | Pagrindinis mygtukas užvedus |
| `on_primary` | `#FFFFFF` | Tekstas ant pagrindinio mygtuko |
| `focus` | `#111111` | Fokusuoto lauko rėmelis |

### 1.2 Tamsi tema

| Žetonas | Reikšmė |
|---|---|
| `page` | `#121212` |
| `card` | `#1E1E1E` |
| `fill` / `strong` / `primary_hover` | `#2E2E2D` |
| `border` / `divider` / `pressed` | `#2C2C2B` |
| `text` / `on_primary` | `#F5F5F5` |
| `secondary` / `muted` / `focus` | `#A3A3A0` |
| `disabled` | `#5F5F5F` |
| `primary` | `#2D2D2D` |

### 1.3 Būsenos

| Būsena | Spalva | Šviesus fonas | Naudojimas |
|---|---|---|---|
| Sėkmė | `#198754` | `#EAF7EF` | „Paruošta“, „Pasiekiamas“, „Plėtinio ryšys veikia“ |
| Įspėjimas | `#B7791F` | `#FFF7E6` | Keli tinkami failai, „Vykdoma“ |
| Klaida / trynimas | `#D64545` | `#FDEEEE` | Nerastas failas, trynimo veiksmai |
| Informacija | `#3478F6` | `#EEF4FF` | „Tiesiogiai į HotFolderį“, informaciniai pranešimai |

- **Pranešimo rėmelis** – fonas sumaišytas su būsenos spalva 22 % („šiek tiek tamsesnis atspalvis“).
- **Tamsioje temoje** būsenų fonas = kortelė + 16 % būsenos spalvos, rėmelis = kortelė + 35 %. Atspalvis nesikeičia.
- Naudojami tik šilti neutralūs pilki. Jokių melsvai pilkų ir papildomų prekės ženklo spalvų.

---

## 2. Šriftai

- Šeima: **Inter** (įtraukta į programą, `fonts/`, OFL licencija), atsarginė – Segoe UI.
- Svoriai: 400 / 500 / 600 / 700.

| Rolė | Dydis | Svoris | Spalva | Pavyzdys |
|---|---|---|---|---|
| Puslapio pavadinimas (`title`) | 22 px | 600 | `text` | „Generavimo istorija“ |
| Kortelės pavadinimas (`subtitle`) | 17 px | 600 | `text` | „Brokų aplankas“ |
| Programos vardas (`appname`) | 15 px | 600 | `text` | „Podbase Container Studio“ |
| Tekstas (`body`) | 14 px | 400 | `text` | |
| Paryškintas tekstas (`strong`) | 14 px | 600 | `text` | „Stalas 1 iš 1“ |
| Antrinis (`secondary`) | 13 px | 400 | `secondary` | Aprašymai, „F2 · 3 × 6“ |
| Lauko etiketė (`label`) | 13 px | 600 | `text` | „Konteinerio pavadinimas“ |
| Užuomina (`caption`) | 12 px | 400 | `muted` | Paaiškinimai po laukais, versija |
| Skyriaus etiketė (`section`) | 11 px | 600 | `muted` | „MODELIAI“ – DIDŽIOSIOMIS, raidžių tarpas 1 px |
| Lentelės antraštė | 11 px | 600 | `muted` | „DATA“, „UŽSAKYMAS“ – DIDŽIOSIOMIS |

- Didžiosiomis raidėmis rašomos **tik** mažos skyriaus etiketės ir lentelių antraštės. Visa kita – sakinio raidėmis („Sukurti konteinerį“, ne „SUKURTI KONTEINERĮ“).
- **Kintantys skaičiai** (skaitikliai „9 / 18“, versija, „Stalas 1 iš 2“, lizdų numeriai) – lygaus pločio skaitmenys (`tnum`).
  Pavadinimams su brūkšneliu (PID-1001, BID-6363) `tnum` netaikomas, nes Inter tada praplatina brūkšnelį.

---

## 3. Forma ir tarpai

| Elementas | Kampų spindulys |
|---|---|
| Mygtukai, laukai, sąrašų elementai, lizdai | 12 px |
| Kortelės, skydeliai | 16 px |
| Dialogai | 24 px |
| Ženkliukai, žetonai, jungiklis | pilnai suapvalinti |

Kitų spindulių nėra.

- Rėmeliai 1 px (`border`) vietoj šešėlių.
- Tarpai – 4 / 8 px tinklelis. Puslapio paraštės 24 px (šonuose), 20 px (viršuje / apačioje). Tarpas tarp kortelių 16 px.
- Kortelių vidinės paraštės 16–20 px.

| Mygtuko aukštis | Kur |
|---|---|
| 32 px | Įrankių juostos (stalo valdymas), žetonai, mažas „Ištrinti įrašą“ |
| 40 px | Numatytasis, laukai |
| 44–48 px | Pagrindinis srities veiksmas („Siųsti į HotFolderį“, „Įkelti į redaktorių“) |
| 36 × 36 px | Piktogramų mygtukai viršutinėje juostoje |

---

## 4. Elementai

### 4.1 Mygtukai

| Tipas | Fonas | Tekstas | Rėmelis | Pastaba |
|---|---|---|---|---|
| Pagrindinis (`primary`) | `#111111` → `#2A2A2A` užvedus | baltas | `#111111` | **Tik vienas srityje** |
| Antrinis (numatytasis) | `card` → `fill` užvedus → `pressed` paspaudus | `text` | `border` | Piktogramos `secondary`, nedažomos |
| Sėkmė (`success`) | `#198754` | baltas | – | Užbaigimo veiksmams |
| Trynimas (`danger`) | `card` → `#FDEEEE` užvedus | `#D64545` | `border` | **Visada su patvirtinimu** |
| Trynimas dialoge (`danger-solid`) | `#D64545` | baltas | – | Patvirtinimo dialogo mygtukas |
| Be fono (`ghost`) | permatomas → `fill` užvedus | `text` | – | |
| Piktogramos mygtukas | permatomas → `fill` užvedus | – | – | 36 × 36 px, 12 px kampai |

- Tarp piktogramos ir teksto ~8 px. Piktograma 16 × 16 px.
- Neaktyvus mygtukas: tekstas `disabled`. Pagrindinis neaktyvus: fonas `strong`.

### 4.2 Laukai

- Tekstinis laukas, išskleidžiamas sąrašas, skaičiaus laukas: fonas `card`, rėmelis `border`, 12 px kampai, aukštis 40 px, paraštės 0 × 12 px.
- Užvedus rėmelis `strong`. Fokusas – rėmelis `#111111`.
- Vietos rezervavimo tekstas `muted`.
- **Etiketė visada virš lauko** (13 px, 600), tarpas 6 px. Užuomina po lauku – `caption`.
- Paieškos laukas: paieškos piktograma kairėje (`muted`), išvalymo mygtukas dešinėje.
- Išskleidžiamo sąrašo rodyklė – `secondary` spalvos chevronas. Atidarytas sąrašas – kortelė su 12 px kampais, pasirinktas elementas `fill`.

### 4.3 Jungiklis

Vietoj kvadratinės varnelės (jos kampai neatitiktų leistinų spindulių).
Takelis 36 × 20 px, pilnai suapvalintas: įjungtas `text`, išjungtas `strong`. Rutuliukas `card`. Tekstas dešinėje, tarpas 10 px.

### 4.4 Segmentų valdiklis (sub-režimai)

- Takelis `fill`, 12 px kampai, 4 px vidinės paraštės, aukštis 40 px.
- Segmentas 32 px, tekstas 13 px / 500, spalva `secondary`.
- Pasirinktas segmentas: fonas `card`, rėmelis `border`, tekstas `text`.
- Naudojamas: Nustatymų skiltys, tema „Šviesi / Tamsi“.

### 4.5 Pasirenkami žetonai (keli vienu metu)

- 32 px aukščio, pilnai suapvalinti (16 px), rėmelis `border`, tekstas 13 px / 500 `secondary`.
- Pažymėtas: fonas `fill`, rėmelis `text`, tekstas `text`, 600.
- Naudojami: modelio „Ieškomi failų tipai“ (TIF · PNG · JPG · WEBP).

### 4.6 Pagrindiniai skirtukai (pabraukimas)

- Tekstas 13 px / 500, be piktogramų, tarpas tarp skirtukų 24 px, aukštis 44 px.
- Aktyvus: `text` + 2 px `text` pabraukimas. Neaktyvus: `secondary`.
- Niekada nenaudojami dideli užpildyti mygtukai kaip skirtukai.

### 4.7 Būsenos ženkliukas

- 24 px aukščio, pilnai suapvalintas, paraštės 0 × 10 px, 12 px / 500.
- Fonas – būsenos šviesus fonas, tekstas ir taškas „●“ – būsenos spalva.
- Neutralus variantas: fonas `fill`, tekstas `secondary` (pvz. „Laikinas aplankas · 10 min.“).

### 4.8 Pranešimai

- Šviesiai tonuota kortelė (būsenos fonas), 1 px tamsesnio atspalvio rėmelis, 12 px kampai, paraštės 12–14 px.
- Piktograma 16 px būsenos spalva, pavadinimas 14 px / 600 `text`, tekstas 13 px `secondary`.
- **Iššokantys pranešimai** – lango dešiniajame viršutiniame kampe (po skirtukais), plotis iki 420 px, vienas po kito su 8 px tarpu.
  Įspėjimai apie kelis failus – apačioje dešinėje.
- Trukmė: įprasti 2,5–4,5 s, „Rasti keli tinkami failai“ – 10 s.
  Klaidos, kurias būtina pamatyti („Ne visi failai išsiųsti“, „Plėtinio ryšys neveikia“), lieka, kol uždaroma ✕.
- Įterptas pranešimas (pvz. Paieškos aplankų skiltyje) – tos pačios išvaizdos kortelė puslapyje.

### 4.9 Dialogai

- Balta kortelė, 24 px kampai, 1 px rėmelis, be šešėlio. Paraštės 24 / 24 / 20 px.
- Už dialogo – priglušintas langas (`#171717`, 28 % nepermatomumo), be suliejimo.
- Pavadinimas 17–18 px / 600, tekstas 13 px `secondary`.
- Veiksmai apačioje dešinėje: antrinis kairėje, pagrindinis dešinėje.
- **Patvirtinimas prieš trynimą**: „Ištrinti įrašą?“ / „Išvalyti stalą?“ + paaiškinimas + „Atšaukti“ ir raudonas „Ištrinti“ / „Išvalyti“.

### 4.10 Lentelės ir sąrašai

- Be tinklelio, tik 1 px `divider` linija po kiekviena eilute. Eilutės aukštis 40 px, tekstas 14 px.
- Antraštė 36 px: 11 px / 600 `muted` DIDŽIOSIOMIS, apačioje `border` linija.
- Pasirinkta / užvesta eilutė: fonas `fill`. Eilučių numerių nėra.
- Vieno stulpelio sąrašuose (modeliai, rėmai) antraštė paslėpta – virš sąrašo yra skyriaus etiketė.

### 4.11 Eigos juosta

Plona 6 px juosta: takelis `fill`, užpildas `text`, pilnai suapvalinta, be teksto.

### 4.12 Tuščia būsena

Viena `secondary` eilutė (pvz. „Sugeneruoti konteineriai atsiras čia.“) ir, jei reikia, vienas antrinis mygtukas.

---

## 5. Stalo lizdai

Lizdai – 12 px kampų plytelės tinklelyje (8 px tarpai, 16 px kortelės paraštės). Minimalus aukštis 96 px (vienos eilutės rėmuose 180–320 px).

| Būsena | Fonas | Rėmelis | Numeris | Pavadinimas |
|---|---|---|---|---|
| Laisvas | `page` | 1 px brūkšninis `strong` (užvedus `muted`) | `muted`, be fono | „Laisvas“ 12 px `muted`, centre „+“ |
| Užimtas | `card` | 1 px `border` (užvedus `strong`) | ženkliukas `fill` / `secondary`, 11 px / 600 | 12 px / 600 `text` |
| Tuščias lizdas | `card` | 1 px brūkšninis `strong` | kaip užimto | „Tuščias lizdas“ `muted`; vietoj miniatiūros – šachmatinis raštas (`fill` / `card`, 8 px langeliai) |
| Nerasta | `#FDEEEE` | 1 px `#D64545` | „04 · Nerasta“ raudonai ant `card` | raudonai |
| Keli failai | `#FFF7E6` | 1 px `#B7791F` | „02 · Keli failai“ | gintaro spalva |
| Tempiama virš | `#EEF4FF` | 1 px `#3478F6` | – | – |

- Viršuje dešinėje – du 26 px piktogramų mygtukai („Dublikuoti“ +, „Išimti iš lizdo“ 🗑), rodomi tik užimtame lizde.
- Miniatiūra centre (75 px, vienos eilutės rėmuose 95 px). Be URL – `muted` nuotraukos piktograma.
- **Be mirksėjimo**: nerasti failai pažymimi statiškai.
- Užvedus pelę po generavimo: užuomina su paimtu failu (pavadinimas, aplankas, data).
- Numeracija: 01 – apatinis dešinysis lizdas, eilutė pildoma į kairę, tada kita eilutė aukščiau.

---

## 6. Ekranai

### 6.1 Lango karkasas

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [logo] Podbase Container Studio      ● Plėtinio ryšys veikia  v1.2.4 📄 ⟳ ◐ │  viršutinė juosta 56 px, balta, 1 px apatinė linija
├──────────────────────────────────────────────────────────────────────────┤
│ Konteineriai   Istorija   Nustatymai                                        │  skirtukai 44 px, balta, 1 px apatinė linija
│ ‾‾‾‾‾‾‾‾‾‾‾‾                                                                │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   puslapis (#F8F8F7), paraštės 24 px                                     │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

- Lango antraštė – Windows sistemos. Minimalus dydis 1024 × 680, numatytas 1280 × 820.
- Viršutinė juosta: logotipas 22 px + pavadinimas kairėje. Dešinėje: plėtinio ryšio būsena (žalia / raudona „Plėtinio ryšys neveikia“), versija (`caption`), piktogramų mygtukai: žurnalas, atnaujinimų tikrinimas, temos perjungimas.

### 6.2 Konteineriai (Studija)

```
┌ kortelė ─────────────────────────────────────────────────────────────────┐
│ Konteinerio pavadinimas        Modelis                 Rėmas     Išvestis  │
│ [ pvz. BID-6363          ]     [ iPad 7/8         ▾ ]  F2 · 3×6  (● Tiesiogiai į HotFolderį) │
│ ──────────────────────────────────────────────────────────────────────── │
│ [←] Stalas 1 iš 1 [→] [+ Naujas stalas]  ▬▬▬▬──── 9 / 18                  │
│                       [+ Pridėti] [⬚ Tuščias lizdas] [⟳ Apversti tvarką] [🗑 Išvalyti stalą] │
└──────────────────────────────────────────────────────────────────────────┘
┌ kortelė: stalo tinklelis ────────────────────────────────────────────────┐
│ [lizdas][lizdas][lizdas][lizdas][lizdas][lizdas]                          │
│ [lizdas][lizdas][lizdas][lizdas][lizdas][lizdas]                          │
│ [  06  ][  05  ][  04  ][  03  ][  02  ][  01  ]                          │
└──────────────────────────────────────────────────────────────────────────┘
[📁 Atidaryti HotFolderį]                 eigos tekstas   [ Siųsti į HotFolderį ]  ← 48 px, juodas
```

- Išvesties ženkliukas: informacinis „Tiesiogiai į HotFolderį“ arba neutralus „Laikinas aplankas · 10 min.“.
- Pagrindinis mygtukas: „Siųsti į HotFolderį“ / „Sukurti konteinerį“. Vykdant – „Vykdoma…“, šalia antriniu tekstu rodoma eiga.
- „Išvalyti stalą“ – raudonas tekstas, su patvirtinimu.

### 6.3 Istorija

```
Generavimo istorija            [🔍 Ieškoti pagal užsakymą ar modelį] [⟳ Atnaujinti] [🗑 Išvalyti istoriją]
┌ kortelė: lentelė ────────────────────────────┐ ┌ kortelė: detalės ───────────────┐
│ DATA       UŽSAKYMAS  MODELIS   STALAI DIZAINAI│ │ BID-6360                         │
│ 2026-10-05 BID-6360   iPad 7/8  1 st.  5 vnt. │ │ Data      2026-10-05 14:20       │
│ ...                                          │ │ Modelis   iPad 7/8               │
│                                              │ │ Rėmas / Išvestis / Kiekis        │
│                                              │ │ ───────────────────────────────  │
│                                              │ │ BID-6360 (skyriaus etiketė)      │
│                                              │ │ 01  PID-1001                     │
│                                              │ │ [  Įkelti į redaktorių  ] juodas │
│                                              │ │ [⟳ Siųsti dar kartą][📁 Aplankas]│
│                                              │ │ [🗑 Ištrinti įrašą]               │
└──────────────────────────────────────────────┘ └──────────────────────────────────┘
```

- Lentelė : detalės = 3 : 2, tarpas 16 px. Detalių kortelė min. 360 px.
- Detalių meta – dviejų stulpelių sąrašas: raktas `muted`, reikšmė `text`.

### 6.4 Nustatymai

```
Nustatymai                                          (Šviesi | Tamsi)  [💾 Išsaugoti]
(Modeliai | Rėmai | Paieškos aplankai | Atnaujinimai)      ← segmentų valdiklis
┌ 300 px: sąrašas ──────┐ ┌ kortelė: forma ───────────────────────────────────┐
│ MODELIAI               │ │ iPad 7/8                                           │
│ [🔍 Ieškoti modelio]   │ │ Modelio pavadinimas                                │
│ iPad 7/8               │ │ [                                                ] │
│ iPad 10.9 2022         │ │ Rėmas                    Išvestis                  │
│ ...                    │ │ [ F2            ▾ ]      [ Tiesiogiai į …     ▾ ]  │
│                        │ │ Spaudos failų aplankas                             │
│                        │ │ [ \\192.168.1.143\…                 ] [📁 Naršyti…]│
│                        │ │ Paskirtis (HotFolderis arba aplankas)              │
│                        │ │ Kiti pavadinimai                                   │
│ [+ Naujas] [🗑 Ištrinti]│ │ Ieškomi failų tipai  (TIF) (PNG) (JPG) (WEBP)      │
└────────────────────────┘ └────────────────────────────────────────────────────┘
```

- **Modeliai**: sąrašas + forma (2 stulpelių tinklelis, 16 px tarpai). Laukai: pavadinimas, rėmas, išvestis, spaudos failų aplankas, paskirtis, kiti pavadinimai, ieškomi failų tipai.
- **Rėmai**: sąrašas + forma: pavadinimas, eilutės, stulpeliai, „Lizdų iš viso“ (neutralus ženkliukas „18 lizdų · 3 × 6“), pastaba.
- **Paieškos aplankai**: kortelė „Brokų aplankas“ (aprašymas, „Aplanko kelias“ + „Pasirinkti…“, būsenos ženkliukas „Pasiekiamas / Nerastas arba nepasiekiamas / Nenustatytas“) ir informacinis pranešimas apie visada ieškomus aplankus.
- **Atnaujinimai**: kortelė su logotipu, pavadinimu, „Įdiegta versija v…“, mygtukai „Atidaryti žurnalą“ (antrinis) ir „Tikrinti atnaujinimus“ (pagrindinis); kortelė „Automatiniai atnaujinimai“ su „GitHub repozitorija“ ir jungikliu.

### 6.5 Atnaujinimo dialogai

- **„Yra nauja programos versija“**: ženkliukai „Dabartinė v1.2.3“ (neutralus) → „Nauja v1.2.4“ (sėkmė), etiketė „Kas naujo“, pakeitimų laukas (fonas `page`, 160 px), paaiškinimas, mygtukai „Priminti vėliau“ / „Atnaujinti dabar“.
- **„Atsisiunčiamas atnaujinimas“**: plona eigos juosta, būsena (lygaus pločio skaitmenys), „Atšaukti“.

---

## 7. Tekstų taisyklės

- Sakinio raidės: „Sukurti konteinerį“, „Išvalyti istoriją“, „Naujas stalas“.
- Be emoji ir šauktukų pavadinimuose: „Konteineris sukurtas“, ne „🚀 KONTEINERIS SUKURTAS!“.
- Trumpai ir dalykiškai: „1 st., 8 failų. Aplankas bus išvalytas po 10 min.“
- Trynimo patvirtinimas visada paaiškina pasekmes: „Spaudos failai neliečiami.“ / „Šio veiksmo atšaukti negalima.“

## 8. Ko nedaryti

- Gradientų, šešėlių, švytėjimo, stiklo efektų, neono, pulsavimo ar šokinėjimo.
- Daugiau nei vieno juodo (pagrindinio) mygtuko vienoje srityje; spalvotų mygtukų eilės.
- DIDŽIŲJŲ RAIDŽIŲ mygtukų ir pavadinimų; itin storo šrifto.
- Naujų spalvų ar kampų spindulių, kurių nėra šiame dokumente.
- Trynimo be patvirtinimo.
