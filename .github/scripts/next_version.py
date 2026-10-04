# -*- coding: utf-8 -*-
"""
Nustato naujos versijos numerį ir įrašo jį į updater.py (CURRENT_VERSION).

- Jei CURRENT_VERSION kode jau didesnė už paskutinį išleistą tag'ą (dar neišleista),
  naudojama ji.
- Kitaip padidinama paskutinė išleista versija (patch / minor / major).

Naudojimas: python next_version.py patch
Išveda: version=X.Y.Z (GitHub Actions išvesties formatu)
"""
import re
import subprocess
import sys
from pathlib import Path

UPDATER = Path(__file__).resolve().parents[2] / "updater.py"
VERSION_RE = re.compile(r'^CURRENT_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)


def parse(v):
    nums = [int(x) for x in re.findall(r"\d+", v)[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def latest_tag():
    out = subprocess.run(["git", "tag", "-l", "v*"], capture_output=True, text=True).stdout.split()
    tags = [parse(t) for t in out if re.match(r"^v\d+(\.\d+){0,2}$", t)]
    return max(tags) if tags else (0, 0, 0)


def main():
    bump = sys.argv[1] if len(sys.argv) > 1 else "patch"
    text = UPDATER.read_text(encoding="utf-8")
    m = VERSION_RE.search(text)
    if not m:
        sys.exit("updater.py faile nerasta CURRENT_VERSION")

    in_code = parse(m.group(1))
    released = latest_tag()

    if in_code > released:
        new = in_code
    else:
        major, minor, patch = released
        if bump == "major":
            new = (major + 1, 0, 0)
        elif bump == "minor":
            new = (major, minor + 1, 0)
        else:
            new = (major, minor, patch + 1)

    new_str = ".".join(map(str, new))
    UPDATER.write_text(VERSION_RE.sub(f'CURRENT_VERSION = "{new_str}"', text, count=1), encoding="utf-8")
    print(f"version={new_str}")


if __name__ == "__main__":
    main()
