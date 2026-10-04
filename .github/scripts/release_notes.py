# -*- coding: utf-8 -*-
"""
Paruošia išleidimo aprašą (rodomas programos atnaujinimo lange).

Prioritetas:
1. Tekstas, įvestas paleidžiant workflow (aplinkos kintamasis NOTES).
2. KAS_NAUJO.md turinys.
3. Commit'ų pavadinimai nuo paskutinio išleidimo.

Aprašas įrašomas į dist/release_notes.md, o KAS_NAUJO.md išvalomas kitai versijai.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEXT_FILE = ROOT / "KAS_NAUJO.md"
OUT_FILE = ROOT / "dist" / "release_notes.md"
HEADER = "<!-- Pakeitimai, kurie bus parodyti kitame atnaujinime. Išleidus versiją šis failas išvalomas automatiškai. -->\n"


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8").stdout.strip()


def from_commits():
    tags = [t for t in git("tag", "-l", "v*", "--sort=-v:refname").split() if t]
    rng = f"{tags[0]}..HEAD" if tags else "HEAD"
    subjects = git("log", rng, "--no-merges", "--format=%s").splitlines()
    subjects = [s for s in subjects if s and not re.match(r"^(Versija v|release:)", s)]
    return "\n".join(f"- {s}" for s in subjects)


def main():
    # Windows konsolė pagal nutylėjimą ne UTF-8; be šito lietuviškos raidės sukeltų klaidą
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    notes = (os.environ.get("NOTES") or "").strip()

    if not notes and NEXT_FILE.exists():
        text = NEXT_FILE.read_text(encoding="utf-8")
        notes = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()

    if not notes:
        notes = from_commits()

    if not notes:
        notes = "Smulkūs patobulinimai."

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(notes + "\n", encoding="utf-8")
    NEXT_FILE.write_text(HEADER, encoding="utf-8")
    print(notes)


if __name__ == "__main__":
    main()
