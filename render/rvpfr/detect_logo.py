#!/usr/bin/env python3
"""
Localise le watermark rvpfr (losange "Rvp Fr" en script) incruste en BAS AU
CENTRE de chaque reel.

Difficulte : ce watermark n'est pas une couleur de marque isolable (comme le
vert rap.minute) mais un alpha-blend quasi transparent — sa couleur est celle
du decor, en un peu plus clair. Un seuil de luminosite ne marche pas.

Discriminant qui marche : le watermark est IMMOBILE alors que le decor bouge.
Ses CONTOURS sont donc presents au meme endroit sur toutes les frames. On
calcule le gradient de chaque frame (|dx| + |dy|) et on prend un PERCENTILE BAS
temporel (pas le min strict : sur une frame surexposee ou noire le watermark
disparait, un min ecraserait tout). Ce qui survit = ce qui a un contour a
chaque instant, donc l'incrustation.

Le decor peut lui aussi etre fixe (sous-titre incruste, meuble, mur) : on ne
garde donc que la plus grosse COMPOSANTE CONNEXE compacte (le watermark est un
bloc carre ; un sous-titre est une longue bande, un mur une grande tache).

Sortie : render/rvpfr/logos.json
  [{file, w, h, dur, box: [x0,y0,x1,y1] | null, radius, score, frames}]

`radius` = rayon, depuis le centre de la box, du plus lointain pixel du
watermark. C'est lui qui dimensionne le badge rond au rendu : le watermark est
un losange, la diagonale de sa box est donc bien plus grande que ce qu'il faut
reellement couvrir.
"""
import json
import subprocess
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LIB = ROOT / "library" / "rvpfr"
OUT = HERE / "logos.json"

# fenetre de recherche (coords relatives), mesuree sur les planches-contacts.
# Large en Y : la hauteur du watermark varie beaucoup d'un reel a l'autre
# (y 1035 a 1252 sur 1280), et sur les reels qui sont des captures d'ecran d'un
# post Instagram il remonte jusqu'a ~y 860 (il est incruste sur la video
# interieure, pas sur le cadre).
ZX0, ZX1 = 0.28, 0.72
ZY0, ZY1 = 0.62, 0.99

STEP = 0.4          # pas d'echantillonnage (s)
MAX_FRAMES = 140    # plafond memoire/temps sur les reels longs
PCT = 25            # percentile temporel du gradient (bas mais pas le min)
THRESH = 6.0        # gradient stable minimum pour qu'un pixel compte
NOISE_K = 3.0       # ... releve a NOISE_K x la mediane de la carte quand le
                    # fond est bruite en permanence (herbe, foule, grain) :
                    # sinon tout le cadre passe le seuil et se colle en une
                    # seule composante geante.
MIN_PIXELS = 250    # en dessous : bruit, pas un watermark
DENS_R = 2          # rayon du voisinage de densite (5x5)
DENS_MIN = 10       # voisins allumes minimum : elimine le bruit epars (herbe,
                    # grain de compression) sans manger les traits du logo
DILATE = 2          # rayon de dilatation avant l'etiquetage (relie les traits)
PAD = 5             # marge ajoutee autour de la bbox trouvee
# garde-fous de forme : le watermark est compact et carre
MAX_REL_W, MAX_REL_H = 0.26, 0.14
MIN_SIDE = 34               # un amas plus petit que ca n'est pas le losange
ASPECT = (0.45, 2.2)
# ... et il est CENTRE horizontalement : c'est le discriminant qui elimine le
# decor fixe (une chaussette blanche immobile, un meuble) parti sur le cote.
CENTER_TOL = 0.06           # ecart max du centre de la box au centre de l'image


def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v",
         "-show_entries", "stream=width,height:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    return s["width"], s["height"], float(d["format"]["duration"])


def crops(path, x0, y0, cw, ch, step):
    """Frames de la seule zone de recherche, en gris (pipe rawvideo).

    ATTENTION : les dimensions du crop DOIVENT etre paires. ffmpeg realigne
    silencieusement une largeur impaire, la taille reelle ne correspond alors
    plus a celle qu'on attend et le reshape decale l'image d'une frame a
    l'autre — ce qui detruit exactement le signal qu'on cherche (la stabilite).
    C'est garanti par search_zone().
    """
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-vf", f"crop={cw}:{ch}:{x0}:{y0},fps=1/{step}",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True)
    n = cw * ch
    for i in range(len(p.stdout) // n):
        yield np.frombuffer(p.stdout[i * n:(i + 1) * n], np.uint8).reshape(ch, cw)


def gradient(g):
    """|dx| + |dy| en differences centrees."""
    g = g.astype(np.float32)
    out = np.zeros_like(g)
    out[:, 1:-1] += np.abs(g[:, 2:] - g[:, :-2])
    out[1:-1, :] += np.abs(g[2:, :] - g[:-2, :])
    return out


def dilate(mask, r):
    """Dilatation carree de rayon r, en numpy pur (pas de scipy ici)."""
    out = mask.copy()
    for _ in range(r):
        acc = out.copy()
        acc[1:, :] |= out[:-1, :]
        acc[:-1, :] |= out[1:, :]
        acc[:, 1:] |= out[:, :-1]
        acc[:, :-1] |= out[:, 1:]
        out = acc
    return out


def density(mask, r):
    """Nombre de pixels allumes dans le voisinage (2r+1)^2 de chaque pixel."""
    h, w = mask.shape
    m = mask.astype(np.int16)
    acc = np.zeros((h, w), np.int16)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            acc[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)] += \
                m[max(0, -dy):h - max(0, dy), max(0, -dx):w - max(0, dx)]
    return acc


def components(mask):
    """Etiquetage 8-connexe en deux passes + union-find (pas de scipy ici).

    Ne visite que les pixels allumes, donc reste rapide meme sur une grande
    fenetre de recherche. Retourne un tableau d'etiquettes (0 = fond).
    """
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    parent = [0]

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    ys, xs = np.nonzero(mask)
    for y, x in zip(ys.tolist(), xs.tolist()):
        nb = []
        if y > 0:
            for dx in (-1, 0, 1):
                nx = x + dx
                if 0 <= nx < w and lab[y - 1, nx]:
                    nb.append(int(lab[y - 1, nx]))
        if x > 0 and lab[y, x - 1]:
            nb.append(int(lab[y, x - 1]))
        if nb:
            m = min(nb)
            lab[y, x] = m
            for n in nb:
                union(m, n)
        else:
            parent.append(len(parent))
            lab[y, x] = len(parent) - 1

    root = np.array([find(i) for i in range(len(parent))], np.int32)
    return root[lab]


def search_zone(w, h):
    """Fenetre de recherche, coordonnees et dimensions forcees en PAIR."""
    x0 = int(w * ZX0) & ~1
    y0 = int(h * ZY0) & ~1
    cw = (int(w * ZX1) - x0) & ~1
    ch = (int(h * ZY1) - y0) & ~1
    return x0, y0, cw, ch


def logo_mask(path, w, h):
    """Masque des pixels du watermark, en coordonnees image.

    Retourne (mask HxW booleen, box, radius) ou (None, None, None).
    Expose separement pour que verify.py puisse controler la couverture sur les
    VRAIS pixels du logo et pas sur sa boite englobante : le losange laisse ses
    quatre coins vides, les compter ferait echouer un recouvrement pourtant
    parfait.
    """
    box, radius, _, _, sel, x0, y0 = _detect(path, w, h)
    if box is None:
        return None, None, None
    full = np.zeros((h, w), bool)
    full[y0:y0 + sel.shape[0], x0:x0 + sel.shape[1]] = sel
    return full, box, radius


def logo_box(path, w, h):
    box, radius, score, nframes, _, _, _ = _detect(path, w, h)
    return box, radius, score, nframes


def _detect(path, w, h):
    x0, y0, cw, ch = search_zone(w, h)

    stack = []
    for g in crops(path, x0, y0, cw, ch, STEP):
        stack.append(gradient(g))
        if len(stack) >= MAX_FRAMES:
            break
    if len(stack) < 4:
        return None, None, 0.0, len(stack), None, x0, y0

    score = np.percentile(np.stack(stack), PCT, axis=0)
    thr = max(THRESH, NOISE_K * float(np.median(score)))
    mask = score >= thr
    mask &= density(mask, DENS_R) >= DENS_MIN   # nettoyage du bruit epars
    if mask.sum() < MIN_PIXELS:
        return None, None, float(score.max()), len(stack), None, x0, y0

    lab = components(dilate(mask, DILATE))
    best = None
    for lid in np.unique(lab):
        if lid == 0:
            continue
        sel = (lab == lid) & mask          # bbox sur les vrais pixels, pas la dilatation
        n = int(sel.sum())
        if n < MIN_PIXELS:
            continue
        ys, xs = np.nonzero(sel)
        bw, bh = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
        if bw > w * MAX_REL_W or bh > h * MAX_REL_H:
            continue                        # bande de sous-titres, grande tache de decor
        if bw < MIN_SIDE or bh < MIN_SIDE:
            continue
        if not (ASPECT[0] <= bw / bh <= ASPECT[1]):
            continue
        cx = x0 + (int(xs.min()) + int(xs.max())) / 2
        if abs(cx - w / 2) > w * CENTER_TOL:
            continue                        # pas centre -> ce n'est pas le watermark
        if best is None or n > best[0]:
            best = (n, xs.min(), ys.min(), xs.max(), ys.max(), sel)

    if best is None:
        return None, None, float(score.max()), len(stack), None, x0, y0
    n, bx0, by0, bx1, by1, sel = best
    box = [max(0, int(bx0) + x0 - PAD), max(0, int(by0) + y0 - PAD),
           min(w, int(bx1) + x0 + PAD), min(h, int(by1) + y0 + PAD)]

    # rayon couvrant : distance du pixel de watermark le plus eloigne du centre
    ccx, ccy = (int(bx0) + int(bx1)) / 2, (int(by0) + int(by1)) / 2
    ys, xs = np.nonzero(sel)
    radius = float(np.sqrt((xs - ccx) ** 2 + (ys - ccy) ** 2).max())
    return box, round(radius, 1), float(score[mask].mean()), len(stack), sel, x0, y0


def main():
    out = []
    for f in sorted(LIB.glob("*.mp4")):
        w, h, dur = probe(f)
        box, radius, sc, nf = logo_box(f, w, h)
        out.append({"file": f.name, "w": w, "h": h, "dur": round(dur, 2),
                    "box": box, "radius": radius, "score": round(sc, 1), "frames": nf})
        if box:
            print(f"{f.name[:22]:<24} box={str(box):<30} "
                  f"{box[2]-box[0]:>3}x{box[3]-box[1]:<3}  r={radius:<5.1f} "
                  f"score={sc:.1f}  {nf}f")
        else:
            print(f"{f.name[:22]:<24} -- rien detecte (score max {sc:.1f}, {nf}f)")
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\n-> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
