# -*- coding: utf-8 -*-
import os
import sys
import shutil
import zipfile
from updater import CURRENT_VERSION

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def make_release_zip():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(base_dir, "dist")
    app_build_dir = os.path.join(dist_dir, "Podbase_Konteineriai")
    
    if not os.path.exists(app_build_dir):
        print(f"[Packaging Error]: Nerastas sukompiliuotas aplankas {app_build_dir}")
        return

    out_zip_name = f"Podbase_Studio_v{CURRENT_VERSION}.zip"
    out_zip_path = os.path.join(dist_dir, out_zip_name)
    
    print(f"Pakuojamas GitHub Release atnaujinimo failas: {out_zip_name} ...")
    
    with zipfile.ZipFile(out_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Add Podbase_Konteineriai folder and all contents
        for root, dirs, files in os.walk(app_build_dir):
            for file in files:
                full_p = os.path.join(root, file)
                rel_p = os.path.relpath(full_p, dist_dir)
                zf.write(full_p, rel_p)
                
        # 2. Add Extension folder as Chrome_Extension
        ext_dir = os.path.join(base_dir, "Extension")
        if os.path.exists(ext_dir):
            for root, dirs, files in os.walk(ext_dir):
                for file in files:
                    full_p = os.path.join(root, file)
                    rel_p = os.path.relpath(full_p, ext_dir)
                    zf.write(full_p, os.path.join("Chrome_Extension", rel_p))
                    
        # 3. Add Paleisti_Programa.bat
        bat_file = os.path.join(base_dir, "Paleisti_Programa.bat")
        if os.path.exists(bat_file):
            zf.write(bat_file, "Paleisti_Programa.bat")
            
        # 4. Add NAUDOJIMO_INSTRUKCIJA.md
        doc_file = os.path.join(base_dir, "NAUDOJIMO_INSTRUKCIJA.md")
        if os.path.exists(doc_file):
            zf.write(doc_file, "NAUDOJIMO_INSTRUKCIJA.md")

    print(f"[OK] Sekmingai sukurtas ZIP paketas kelimui i GitHub Releases: {out_zip_path}")

if __name__ == "__main__":
    make_release_zip()
