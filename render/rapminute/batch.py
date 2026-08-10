#!/usr/bin/env python3
"""
Rendu final rap.minute -> DA violet fluo. Sortie : out/rapminute/.

Croise hooks.json (geometrie detectee : zone + timing) et hooks_fr.json
(notre texte). Un reel absent de hooks_fr.json n'est pas rendu.

  python3 batch.py              # tout
  python3 batch.py 00 13        # seulement ces prefixes (preview rapide)
"""
import json
import sys
from pathlib import Path

from hook_overlay import render

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LIB = ROOT / "library" / "rapminute"
OUT = ROOT / "out" / "rapminute"

# marge de securite autour de leur fenetre : leur texte apparait/disparait en
# fondu, l'echantillonnage a 0.25s peut rogner les bords.
PAD_T = 0.35


def main():
    only = sys.argv[1:]
    geo = {v["file"]: v for v in json.loads((HERE / "hooks.json").read_text())}
    texts = json.loads((HERE / "hooks_fr.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)

    done = 0
    for f, text in texts.items():
        if f.startswith("_") or f not in geo:
            continue
        if only and not any(f.startswith(p) for p in only):
            continue
        v = geo[f]
        if not v["hooks"]:
            print(f"! {f} : aucune zone detectee, saute")
            continue
        hk = dict(v["hooks"][0])
        hk["start"] = max(0, hk["start"] - PAD_T)
        hk["end"] = min(v["dur"], hk["end"] + PAD_T)
        hk["text"] = text
        render(LIB / f, OUT / f, [hk])
        print(f"✓ {f}  ({hk['start']:.1f}-{hk['end']:.1f}s, "
              f"bande y {hk['band'][0]}-{hk['band'][1]})")
        done += 1
    print(f"\n✓ {done} vidéos dans out/rapminute/")


if __name__ == "__main__":
    main()
