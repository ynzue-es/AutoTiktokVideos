#!/usr/bin/env python3
"""
Localise le bandeau de marque (SKYROCK / PLANETE RAP / PR+ / LE RECAP / KARAOKE)
incruste en haut a droite de chaque reel skyrockfm.

Deux difficultes :
  1. le logo CHANGE en cours de video (SKYROCK sur un plan, PR+ sur le suivant)
     -> on ne peut pas prendre l'intersection temporelle sur toute la duree ;
  2. le decor de studio est clair et fixe par moments (murs, spots, logo mural)
     -> un simple "pixel clair et immobile" ramene aussi du decor.

Methode : sur chaque fenetre glissante de STAB frames, on garde les pixels
clairs ET immobiles, on prend l'UNION sur la video (capte chaque variante), puis
on ne conserve que la PLUS GROSSE COMPOSANTE CONNEXE. Le logo est un bloc dense
et compact ; le decor residuel se disperse en petits amas et tombe.

Sortie : render/skyrock/logos.json  [{file, w, h, dur, box:[x0,y0,x1,y1]|null}]
"""
import json
import subprocess
from collections import deque
from pathlib import Path

import numpy as np

from stock import current  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
STOCK, _ = current()
LIB = STOCK.lib
OUT = STOCK.logos

STEP = 0.5
BRIGHT = 195
STABLE = 12
STAB = 5             # frames consecutives sur lesquelles le pixel doit tenir
MIN_PIXELS = 220
# fenetre de recherche, mesuree sur les planches de coins (coords relatives)
ZX0, ZX1 = 0.63, 1.0
ZY0, ZY1 = 0.04, 0.27
PAD = 6              # marge ajoutee autour de la bbox trouvee


def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v",
         "-show_entries", "stream=width,height:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    return s["width"], s["height"], float(d["format"]["duration"])


def frames(path, w, h):
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps=1/{STEP}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True)
    n = w * h * 3
    for i in range(len(p.stdout) // n):
        yield np.frombuffer(p.stdout[i * n:(i + 1) * n], np.uint8).reshape(h, w, 3)


def largest_component(mask):
    """BFS 8-connexe ; retourne le masque de la plus grosse composante."""
    seen = np.zeros_like(mask)
    best, best_n = None, 0
    H, W = mask.shape
    for sy in range(H):
        for sx in range(W):
            if not mask[sy, sx] or seen[sy, sx]:
                continue
            q, cells = deque([(sy, sx)]), []
            seen[sy, sx] = True
            while q:
                y, x = q.popleft()
                cells.append((y, x))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            q.append((ny, nx))
            if len(cells) > best_n:
                best, best_n = cells, len(cells)
    return best, best_n


def logo_box(path, w, h):
    x0, x1 = int(w * ZX0), int(w * ZX1)
    y0, y1 = int(h * ZY0), int(h * ZY1)
    crops = [f[y0:y1, x0:x1].astype(np.int16) for f in frames(path, w, h)]
    if len(crops) < STAB:
        return None

    acc = np.zeros(crops[0].shape[:2], bool)
    for i in range(len(crops) - STAB + 1):
        win = crops[i:i + STAB]
        ref = win[STAB // 2]
        bright = (ref >= BRIGHT).all(axis=2)
        still = np.ones_like(bright)
        for f in win:
            still &= (np.abs(f - ref).max(axis=2) <= STABLE)
        acc |= bright & still

    if acc.sum() < MIN_PIXELS:
        return None
    cells, n = largest_component(acc)
    if n < MIN_PIXELS:
        return None
    ys = [c[0] for c in cells]
    xs = [c[1] for c in cells]
    return [max(0, min(xs) + x0 - PAD), max(0, min(ys) + y0 - PAD),
            min(w, max(xs) + x0 + PAD), min(h, max(ys) + y0 + PAD)]


def main():
    out = []
    for f in sorted(LIB.glob("*.mp4")):
        w, h, dur = probe(f)
        box = logo_box(f, w, h)
        out.append({"file": f.name, "w": w, "h": h, "dur": round(dur, 2), "box": box})
        if box:
            s = 720.0 / w   # affiche en coords 720 pour comparer 720p et 1080p
            print(f"{f.name[:22]:<24} box={str(box):<28} "
                  f"{box[2]-box[0]:>3}x{box[3]-box[1]:<3}  "
                  f"@720: x{int(box[0]*s)}-{int(box[2]*s)} y{int(box[1]*s)}-{int(box[3]*s)}")
        else:
            print(f"{f.name[:22]:<24} -- rien detecte")
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\n-> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
