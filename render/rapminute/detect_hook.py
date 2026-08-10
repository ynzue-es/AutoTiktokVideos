#!/usr/bin/env python3
"""
Delimite le BLOC DE TEXTE complet du hook rap.minute (lignes blanches + mots
verts + barre verticale), pas seulement les pixels verts.

green.json ne donne que la bbox des mots verts : une ligne entierement blanche
depasse au-dessus/en dessous. Ici on repart de cette bbox, on elargit la fenetre
de recherche, et on garde les LIGNES (rangees de pixels) qui portent du texte.

Texte = pixel quasi-blanc (>= WHITE_MIN sur les 3 canaux) ou vert de marque.
Discriminant cle : le texte est IMMOBILE, le decor bouge. On prend donc
l'INTERSECTION temporelle des masques blancs (un mur blanc filme camera a
l'epaule ne survit pas au ET, le texte si). On echantillonne la fin du segment
seulement, une fois le texte entierement ecrit (il s'ecrit mot par mot).

Sortie : render/rapminute/hooks.json
  [{file, w, h, dur, hooks: [{start, end, band: [y0, y1], text_x0}]}]
"""
import json
import subprocess
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LIB = ROOT / "library" / "rapminute"
GREEN_JSON = HERE / "green.json"
OUT = HERE / "hooks.json"

GREEN = np.array([0, 211, 146], dtype=np.int16)
TOL = 26
WHITE_MIN = 232      # un pixel de texte blanc est quasi sature sur les 3 canaux
ROW_MIN = 14         # pixels de texte minimum pour qu'une rangee compte
GAP_ROWS = 26        # trou vertical max tolere a l'interieur d'un meme bloc
SEARCH_PAD = 0.14    # fenetre de recherche = bbox verte +/- 14% de la hauteur
STABLE_FROM = 0.45   # on n'echantillonne qu'a partir de 45% du segment


def frames_between(path, w, h, t0, t1, n=8):
    """n frames reparties entre t0 et t1, en une seule passe ffmpeg."""
    dur = max(t1 - t0, 0.1)
    fps = max(n / dur, 0.1)
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(t0), "-t", str(dur), "-i", str(path),
         "-vf", f"fps={fps}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True)
    npx = w * h * 3
    buf = p.stdout
    for i in range(len(buf) // npx):
        yield np.frombuffer(buf[i * npx:(i + 1) * npx], np.uint8).reshape(h, w, 3)


def text_mask(img):
    """Masque booleen : texte blanc OU vert de marque."""
    white = (img >= WHITE_MIN).all(axis=2)
    green = (np.abs(img.astype(np.int16) - GREEN).max(axis=2) <= TOL)
    return white | green


def band_for(path, w, h, seg):
    """Bande verticale [y0,y1] du bloc de texte + x de depart du texte."""
    y0g, y1g = seg["box"][1], seg["box"][3]
    pad = int(h * SEARCH_PAD)
    ys, ye = max(0, y0g - pad), min(h, y1g + pad)

    # fin du segment : le texte y est deja entierement ecrit
    t0 = seg["start"] + (seg["end"] - seg["start"]) * STABLE_FROM
    acc = None
    for img in frames_between(path, w, h, t0, seg["end"]):
        m = text_mask(img[ys:ye])
        acc = m if acc is None else (acc & m)   # ET temporel : garde l'immobile
    if acc is None:
        return None

    rows = acc.sum(axis=1)
    hot = np.nonzero(rows >= ROW_MIN)[0]
    if hot.size == 0:
        return None

    # groupe les rangees chaudes, garde le groupe qui recouvre la bbox verte
    groups, start, prev = [], hot[0], hot[0]
    for r in hot[1:]:
        if r - prev > GAP_ROWS:
            groups.append((start, prev))
            start = r
        prev = r
    groups.append((start, prev))

    gy0, gy1 = y0g - ys, y1g - ys
    best = max(groups, key=lambda g: min(g[1], gy1) - max(g[0], gy0))

    sub = acc[best[0]:best[1] + 1]
    cols = np.nonzero(sub.sum(axis=0) >= 2)[0]
    x0 = int(cols.min()) if cols.size else seg["box"][0]
    return [int(best[0] + ys), int(best[1] + ys)], x0


def main():
    green = json.loads(GREEN_JSON.read_text())
    out = []
    for v in green:
        path = LIB / v["file"]
        hooks = []
        for seg in v["segments"]:
            r = band_for(path, v["w"], v["h"], seg)
            if not r:
                continue
            band, x0 = r
            hooks.append({"start": seg["start"], "end": seg["end"],
                          "band": band, "text_x0": x0})
        out.append({"file": v["file"], "w": v["w"], "h": v["h"],
                    "dur": v["dur"], "hooks": hooks})
        for hk in hooks:
            b = hk["band"]
            print(f"{v['file'][:22]:<24} {hk['start']:>5.1f}-{hk['end']:<5.1f} "
                  f"band y {b[0]:>4}-{b[1]:<4} (h={b[1]-b[0]:>3})  x0={hk['text_x0']}")

    OUT.write_text(json.dumps(out, indent=2))
    print(f"\n-> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
