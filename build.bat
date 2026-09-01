@echo off
chcp 65001 >nul
echo Diegiamos reikalingos bibliotekos...
pip install -r requirements.txt

echo Kompiliuojama programa...
py -m PyInstaller --noconfirm --onedir --windowed --name "Podbase_Konteineriai" --icon="podbase_icon.ico" --add-data "models.json;." --add-data "jigs.json;." --add-data "config.json;." --add-data "podbase_logo.png;." --add-data "podbase_icon.png;." app_gui.py

echo Kompiliacija baigta! Rezultatas aplanke dist/Podbase_Konteineriai
pause
