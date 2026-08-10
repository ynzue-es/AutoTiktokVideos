#!/usr/bin/env python3
"""
Rendu final rvpfr : watermark rvpfr -> badge LeMurSonore. Sortie : out/rvpfr/.

Lit logos.json (produit par detect_logo.py) et recouvre la zone detectee.
Un reel sans box detectee n'est pas rendu (mieux vaut rien qu'un badge pose
au hasard) ; il est signale en fin de run.

  python3 batch.py              # tout
  python3 batch.py 00 13        # seulement ces prefixes (preview rapide)
"""
import json
import sys
from pathlib import Path

from logo_overlay import badge_diameter, render

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LIB = ROOT / "library" / "rvpfr"
OUT = ROOT / "out" / "rvpfr"


def main():
    only = sys.argv[1:]
    geo = json.loads((HERE / "logos.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)

    done, skipped = 0, []
    for v in geo:
        f = v["file"]
        if only and not any(f.startswith(p) for p in only):
            continue
        if not v["box"]:
            skipped.append(f)
            print(f"! {f} : aucun watermark localise, saute")
            continue
        dia = badge_diameter(v["box"], v["w"] / 720.0, v.get("radius"))
        render(LIB / f, OUT / f, v["box"], v.get("radius"))
        print(f"✓ {f}  badge ⌀{dia}px centre sur "
              f"({(v['box'][0]+v['box'][2])//2},{(v['box'][1]+v['box'][3])//2})")
        done += 1

    print(f"\n✓ {done} vidéos dans out/rvpfr/")
    if skipped:
        print(f"! {len(skipped)} non rendues : {', '.join(skipped)}")


if __name__ == "__main__":
    main()
