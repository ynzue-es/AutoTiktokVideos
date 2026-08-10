#!/usr/bin/env python3
"""
Controle qualite : plus aucun pixel vert rap.minute ne doit subsister dans
out/rapminute/. Rejoue la meme detection que detect_green.py sur les sorties.

Un residu = la bande de couverture est trop courte (fondu d'apparition mal
borne) ou trop etroite. Sortie non nulle si un residu est trouve.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = ROOT / "out" / "rapminute"

GREEN = np.array([0, 211, 146], dtype=np.int16)
TOL = 26
MIN_PIXELS = 900
STEP = 0.25


def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v",
         "-show_entries", "stream=width,height:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    return s["width"], s["height"], float(d["format"]["duration"])


def main():
    bad = 0
    for f in sorted(OUT.glob("*.mp4")):
        w, h, dur = probe(f)
        p = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(f), "-vf", f"fps=1/{STEP}",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, check=True)
        n = w * h * 3
        hits = []
        for i in range(len(p.stdout) // n):
            img = np.frombuffer(p.stdout[i * n:(i + 1) * n], np.uint8).reshape(h, w, 3)
            cnt = int((np.abs(img.astype(np.int16) - GREEN).max(axis=2) <= TOL).sum())
            if cnt >= MIN_PIXELS:
                hits.append((round(i * STEP, 2), cnt))
        if hits:
            bad += 1
            head = ", ".join(f"t={t}s ({c}px)" for t, c in hits[:4])
            print(f"✗ {f.name}  {len(hits)} frame(s) avec du vert : {head}")
        else:
            print(f"✓ {f.name}")
    print(f"\n{'✗ ' + str(bad) + ' fichier(s) a revoir' if bad else '✓ aucun résidu vert'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
