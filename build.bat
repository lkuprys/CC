@echo off
chcp 65001 >nul
echo Diegiamos reikalingos bibliotekos...
pip install -r requirements.txt

echo Kompiliuojama programa...
py -m PyInstaller --noconfirm --onedir --windowed --name "Podbase_Konteineriai" --icon="podbase_icon.ico" --add-data "models.json;." --add-data "jigs.json;." --add-data "config.json;." --add-data "podbase_logo.png;." --add-data "podbase_icon.png;." --add-data "fonts;fonts" --add-data "colorgate_prn/data;colorgate_prn/data" --add-data "colorgate_prn/bundle_gunsjet;colorgate_prn/bundle_gunsjet" --add-data "colorgate_prn/bundle_flora;colorgate_prn/bundle_flora" --add-data "remo_paruosimas;remo_paruosimas" --collect-submodules imagecodecs app_gui.py

echo.
echo Pakuojamas ZIP paketas GitHub Releases...
py package_release.py

echo.
echo ======================================================================
echo Kompiliacija ir pakavimas baigtas!
echo Sukompiliuota programa: dist\Podbase_Konteineriai
echo Paruostas GitHub Release ZIP: dist\Podbase_Studio_v*.zip
echo ======================================================================
pause

