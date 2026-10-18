# colorgate_prn + HighGap

PNG/TIF → PRN generatorius Flora XTRA2512UV (ir GUNSJET 2513), atkuriantis ColorGate Productionserver išvestį.

* Užduotis integracijai: [INSTRUKCIJA_HighGap.md](INSTRUKCIJA_HighGap.md)
* Paketo aprašas: [colorgate_prn/README.md](colorgate_prn/README.md)

```
pip install -r requirements.txt
python tests/test_high_gap.py
python -m colorgate_prn generate --bundle colorgate_prn/bundle_flora --layout layout_flora.example.json --out lapas.prn --high-gap
```
