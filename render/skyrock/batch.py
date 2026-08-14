#!/usr/bin/env python3
"""
Rendu skyrockfm -> LeMurSonore. Un stock en entree, out/skyrock*/ en sortie.

  python3 batch.py                       # tout le stock 1
  python3 batch.py --stock 2             # tout le stock 2
  python3 batch.py --stock 2 00 05       # seulement ces prefixes (preview)
"""
import json
from pathlib import Path

from logo_overlay import render
from stock import current

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
STOCK, ARGS = current()
LIB = STOCK.lib
OUT = STOCK.out

SHOW = 4.5       # duree d'affichage du rectangle de texte, en debut de sortie


GAP = 0.8        # silence qui separe le presentateur de l'audio du contenu


def cut_at(segs):
    """
    Ou couper l'intro : a la fin de la prise de parole du presentateur.

    Il parle d'une traite depuis t=0, puis se tait et la video enchaine sur les
    images. On garde donc la PREMIERE salve continue, pas le dernier segment :
    l'audio du contenu (interview, live) est lui aussi transcrit et prendre
    segs[-1] emporterait presque toute la video.

    Reste un cas ou meme ca deborde — le contenu enchaine sans silence. La cle
    'cut' de config.json force alors la valeur (verifiee a l'image).
    """
    if not segs:
        return 0.0
    end = segs[0]["end"]
    for a, b in zip(segs, segs[1:]):
        if b["start"] - a["end"] > GAP:
            break
        end = b["end"]
    return round(end, 2)


def main():
    only = ARGS
    cfg = json.loads(STOCK.config.read_text())
    speech = json.loads(STOCK.speech.read_text()) if STOCK.speech.exists() else {}
    durs = {v["file"]: v["dur"] for v in json.loads(STOCK.logos.read_text())}
    OUT.mkdir(parents=True, exist_ok=True)

    done = 0
    for f, c in cfg.items():
        if f.startswith("_"):
            continue
        if only and not any(f.startswith(p) for p in only):
            continue
        src = LIB / f
        if not src.exists():
            print(f"! {f} : absent de {LIB.name}, sauté")
            continue

        text = c.get("text")
        trim = win = None
        if text:
            trim = c.get("cut") or cut_at(speech.get(f, []))
            reste = durs.get(f, 30.0) - trim
            win = (0.0, round(min(SHOW, max(reste - 0.5, 1.5)), 2))

        render(src, OUT / f, c["family"], text=text, text_window=win,
               trim_start=trim or None)
        tag = (f"coupe à {trim}s, texte 0-{win[1]}s" if text else "logo seul")
        print(f"✓ {f}  [{c['family']}, {tag}]")
        done += 1
    print(f"\n✓ {done} vidéos dans {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
