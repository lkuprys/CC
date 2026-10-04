# -*- coding: utf-8 -*-
import os
import sys
import subprocess
from updater import CURRENT_VERSION
from package_release import make_release_zip

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def run_cmd(cmd, check=True):
    """cmd gali būti eilutė arba argumentų sąrašas (sąrašas saugesnis tekstui su kabutėmis)."""
    print(f">> Running: {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    res = subprocess.run(cmd, shell=isinstance(cmd, str), text=True)
    if check and res.returncode != 0:
        print(f"[Error] Command failed with code {res.returncode}")
        sys.exit(res.returncode)
    return res.returncode

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)
    
    version = CURRENT_VERSION
    tag = f"v{version}"
    release_title = f"Podbase Container Studio {tag}"
    zip_name = f"Podbase_Studio_{tag}.zip"
    zip_path = os.path.join(base_dir, "dist", zip_name)
    
    notes = sys.argv[1] if len(sys.argv) > 1 else f"Podbase Container Studio {tag} atnaujinimas su automatiniu diegimo pataisymu ir patobulinimais."

    # 0. Apsauga: ta pati versija negali būti išleista antrą kartą.
    # Kitaip programos atnaujinimo nepamatytų (versija ta pati), o senas release būtų perrašytas.
    existing_remote = subprocess.run(
        ["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"],
        capture_output=True, text=True
    ).stdout.strip()
    existing_release = subprocess.run(
        ["gh", "release", "view", tag, "--repo", "lkuprys/CC"],
        capture_output=True, text=True
    ).returncode == 0
    if existing_remote or existing_release:
        print(f"[Klaida] Versija {tag} jau isleista GitHub'e.")
        print("Padidinkite CURRENT_VERSION faile updater.py (pvz. 1.1.1 -> 1.1.2) ir paleiskite is naujo.")
        sys.exit(1)

    print("==================================================================")
    print(f"  PRADEDAMAS AUTOMATINIS VERSIJOS {tag} ISLEIDIMAS")
    print("==================================================================")

    # 1. Kompiliuojame su PyInstaller
    print("\n[1/5] Kompiliuojama programa su PyInstaller...")
    run_cmd(
        'py -m PyInstaller --noconfirm --onedir --windowed --name "Podbase_Konteineriai" '
        '--icon="podbase_icon.ico" --add-data "models.json;." --add-data "jigs.json;." '
        '--add-data "config.json;." --add-data "podbase_logo.png;." --add-data "podbase_icon.png;." app_gui.py'
    )

    # 2. Pakuojame Release ZIP
    print("\n[2/5] Formuojamas Release ZIP paketas...")
    make_release_zip()

    if not os.path.exists(zip_path):
        print(f"[Error] Nerastas sugeneruotas zip failas: {zip_path}")
        sys.exit(1)

    # 3. Git commit & push
    print("\n[3/5] Keliame pakeitimus i Git repozitorija...")
    run_cmd("git add -A")
    # Commit if there are changes
    run_cmd(["git", "commit", "-m", f"release: {tag} - {notes}"], check=False)
    run_cmd("git push origin main")

    # 4. Git tag
    print(f"\n[4/5] Kuriame ir keliame Git zyma {tag}...")
    run_cmd(["git", "tag", tag])
    run_cmd(["git", "push", "origin", tag])

    # 5. GitHub Release sukurimas per gh CLI
    print(f"\n[5/5] Skelbiame GitHub Release ir prisegame {zip_name}...")
    
    run_cmd(["gh", "release", "create", tag, zip_path,
             "--title", release_title, "--notes", notes, "--latest", "--repo", "lkuprys/CC"])

    print("\n==================================================================")
    print(f"  [OK] VERSIJA {tag} SEKMINGAI PASKELBTA GITHUB RELEASES!")
    print(f"  Nuoroda: https://github.com/lkuprys/CC/releases/tag/{tag}")
    print("==================================================================")

if __name__ == "__main__":
    main()
