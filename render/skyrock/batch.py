#!/usr/bin/env python3
"""
Rendu skyrockfm -> LeMurSonore. Sortie : out/skyrock/.

  python3 batch.py            # tout
  python3 batch.py 00 05      # seulement ces prefixes (preview rapide)
"""
import json
import sys
from pathlib import Path

from logo_overlay import render

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LIB = ROOT / "library" / "skyrockfm"
OUT = ROOT / "out" / "skyrock"

SHOW = 4.5       # duree d'affichage du rectangle de texte, en debut de sortie


def cut_at(segs):
    """
    Ou couper l'intro : a la fin de la prise de parole du presentateur.
    Verifie sur frames — a +0.5s il a disparu et le carton du sujet demarre.
    """
    return round(segs[-1]["end"], 2) if segs else 0.0


def main():
    only = sys.argv[1:]
    cfg = json.loads((HERE / "config.json").read_text())
    speech_path = HERE / "recap_speech.json"
    speech = json.loads(speech_path.read_text()) if speech_path.exists() else {}
    durs = {v["file"]: v["dur"] for v in json.loads((HERE / "logos.json").read_text())}
    OUT.mkdir(parents=True, exist_ok=True)

    done = 0
    for f, c in cfg.items():
        if f.startswith("_"):
            continue
        if only and not any(f.startswith(p) for p in only):
            continue
        src = LIB / f
        if not src.exists():
            print(f"! {f} : absent de library/skyrockfm, sauté")
            continue

        text = c.get("text")
        trim = win = None
        if text:
            trim = cut_at(speech.get(f, []))
            reste = durs.get(f, 30.0) - trim
            win = (0.0, round(min(SHOW, max(reste - 0.5, 1.5)), 2))

        render(src, OUT / f, c["family"], text=text, text_window=win,
               trim_start=trim or None)
        tag = (f"coupe à {trim}s, texte 0-{win[1]}s" if text else "logo seul")
        print(f"✓ {f}  [{c['family']}, {tag}]")
        done += 1
    print(f"\n✓ {done} vidéos dans out/skyrock/")


if __name__ == "__main__":
    main()
