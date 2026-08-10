#!/usr/bin/env python3
"""
Controle qualite des sorties out/rvpfr/ : plus rien du watermark rvpfr ne doit
subsister. Quatre tests par fichier.

1. COUVERTURE (test decisif, geometrique). On rejoue sur la SOURCE la detection
   de detect_logo.py pour recuperer le masque des pixels du watermark, on le
   dilate de SAFE px (pour attraper les traits trop pales pour avoir passe le
   seuil), et on verifie que tout ce masque tombe dans le disque OPAQUE du
   badge. Aucun pixel du logo ne doit en depasser.

   On teste le masque et non la bbox : le watermark est un losange, les quatre
   coins de sa boite sont du decor. Et on ne compare PAS source et sortie pixel
   a pixel : le badge est noir et blanc, sur un fond sombre ses pixels noirs
   sont identiques a ceux de la source par pure coincidence de couleur — ca
   ressemble a un residu alors que la couverture est parfaite.

2. OPACITE. Dans la sortie, le disque du badge doit etre entierement noir et
   blanc (le rond blanc + le M). Si du decor transparaissait, il amenerait de
   la couleur. Confirme que le badge est bien opaque et bien pose.

3. RESIDU. On rejoue la detection sur la SORTIE autour du badge, disque et
   ombre portee neutralises : un amas compact survivant signalerait une pointe
   du losange qui depasse. Limite connue : l'ombre portee doit etre neutralisee
   avec elle, donc ce test est aveugle sur les ~15 px qui bordent le badge —
   c'est le test 1 qui couvre cette zone-la.

4. INTEGRITE. Meme nombre de frames et meme duree de flux video que la source,
   piste audio toujours presente. (La duree du CONTENEUR bouge de ~0.1 s : le
   remux reecrit l'edit list du mp4. Sans effet sur l'image ni le son, donc on
   compare le flux video.)

Sortie non nulle si un fichier echoue.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

import detect_logo as D
from logo_overlay import SHADOW_BLUR, badge_diameter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LIB = ROOT / "library" / "rvpfr"
OUT = ROOT / "out" / "rvpfr"

SAFE = 3             # dilatation de securite du masque du watermark
SAMPLES = 6          # frames echantillonnees pour le test d'opacite
CHROMA_TOL = 26      # ecart max entre canaux pour dire "pixel achromatique"
CHROMA_MIN = 0.985   # fraction du disque qui doit etre achromatique
RES_HALO = 70        # rayon d'inspection au-dela du badge (test 3)
RES_MIN_PX = 150     # taille minimale d'un amas pour etre signale (test 3)
DUR_TOL = 0.05       # tolerance sur la duree du flux video, en secondes


def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,duration,nb_frames",
         "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    return {
        "w": v["width"], "h": v["height"],
        "vdur": float(v.get("duration") or d["format"]["duration"]),
        "frames": int(v.get("nb_frames") or 0),
        "audio": any(s["codec_type"] == "audio" for s in d["streams"]),
    }


def frame_at(path, t, w, h):
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    buf = p.stdout[:w * h * 3]
    if len(buf) < w * h * 3:
        return None
    return np.frombuffer(buf, np.uint8).reshape(h, w, 3)


def badge_geom(box, radius, w):
    dia = badge_diameter(box, w / 720.0, radius)
    return dia, (box[0] + box[2]) // 2, (box[1] + box[3]) // 2


def check_cover(mask, box, radius, w):
    """Pixels du watermark hors du disque opaque du badge, et debord max."""
    dia, cx, cy = badge_geom(box, radius, w)
    ys, xs = np.nonzero(mask)
    d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    out = d > dia / 2
    return int(out.sum()), (float(d.max() - dia / 2) if out.any() else 0.0)


def check_opacity(dst, box, radius, w, h, dur):
    """Fraction minimale de pixels achromatiques dans le disque du badge."""
    dia, cx, cy = badge_geom(box, radius, w)
    r = dia / 2 - 3
    yy, xx = np.ogrid[:h, :w]
    disk = (xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2
    ys, xs = np.nonzero(disk)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sub = disk[y0:y1, x0:x1]

    worst = 1.0
    for k in range(SAMPLES):
        f = frame_at(dst, dur * (k + 0.5) / SAMPLES, w, h)
        if f is None:
            continue
        c = f[y0:y1, x0:x1].astype(np.int16)
        chroma = c.max(axis=2) - c.min(axis=2)
        worst = min(worst, float(((chroma <= CHROMA_TOL) & sub).sum() / sub.sum()))
    return worst


def check_residual(dst, box, radius, w, h):
    """Amas de watermark encore detectable autour du badge (hors badge+ombre)."""
    dia, cx, cy = badge_geom(box, radius, w)
    x0, y0, cw, ch = D.search_zone(w, h)
    stack = []
    for g in D.crops(dst, x0, y0, cw, ch, D.STEP):
        stack.append(D.gradient(g))
        if len(stack) >= D.MAX_FRAMES:
            break
    if len(stack) < 4:
        return 0
    score = np.percentile(np.stack(stack), D.PCT, axis=0)

    # on neutralise le badge ET son ombre portee (stables par construction),
    # et on n'inspecte qu'une couronne autour : un debord serait la, pas a
    # l'autre bout du cadre (ou vit le texte incruste de la video source).
    lx, ly = cx - x0, cy - y0
    yy, xx = np.ogrid[:ch, :cw]
    d2 = (xx - lx) ** 2 + (yy - ly) ** 2
    r_in = dia / 2 + 3 * max(2, int(dia * SHADOW_BLUR)) + 4
    score = np.where((d2 <= r_in ** 2) | (d2 > (r_in + RES_HALO) ** 2), 0.0, score)

    thr = max(D.THRESH, D.NOISE_K * float(np.median(score[score > 0]) if (score > 0).any() else 0))
    m = score >= thr
    m &= D.density(m, D.DENS_R) >= D.DENS_MIN
    if m.sum() < RES_MIN_PX:
        return 0

    lab = D.components(D.dilate(m, D.DILATE))
    for lid in np.unique(lab):
        if lid == 0:
            continue
        sel = (lab == lid) & m
        n = int(sel.sum())
        if n < RES_MIN_PX:
            continue
        ys, xs = np.nonzero(sel)
        bw, bh = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
        if bw > w * D.MAX_REL_W or bh > h * D.MAX_REL_H:
            continue
        return n
    return 0


def main():
    geo = {v["file"]: v for v in json.loads((HERE / "logos.json").read_text())}
    files = sorted(OUT.glob("*.mp4"))
    if not files:
        print("aucune vidéo dans out/rvpfr/ — lance d'abord batch.py")
        return 1

    bad = 0
    for f in files:
        v = geo.get(f.name)
        if not v or not v["box"]:
            print(f"? {f.name}  absent de logos.json, non vérifiable")
            continue
        info, sinfo = probe(f), probe(LIB / f.name)
        w, h = info["w"], info["h"]

        errs = []
        mask, box, radius = D.logo_mask(LIB / f.name, w, h)
        chroma = None
        if mask is None:
            errs.append("watermark introuvable sur la source (rejeu de détection)")
        else:
            mask = D.dilate(mask, SAFE)
            n_out, dpx = check_cover(mask, box, radius, w)
            if n_out:
                errs.append(f"{n_out}px du watermark hors du badge (+{dpx:.0f}px)")
            chroma = check_opacity(f, box, radius, w, h, info["vdur"])
            if chroma < CHROMA_MIN:
                errs.append(f"badge non opaque ({chroma:.1%} achromatique)")
            res = check_residual(f, box, radius, w, h)
            if res:
                errs.append(f"résidu stable en bordure de badge ({res}px)")

        if info["frames"] and info["frames"] != sinfo["frames"]:
            errs.append(f"{info['frames']} frames ≠ source {sinfo['frames']}")
        if abs(info["vdur"] - sinfo["vdur"]) > DUR_TOL:
            errs.append(f"flux vidéo {info['vdur']:.2f}s ≠ source {sinfo['vdur']:.2f}s")
        if sinfo["audio"] and not info["audio"]:
            errs.append("piste audio perdue")

        if errs:
            bad += 1
            print(f"✗ {f.name}  " + " | ".join(errs))
        else:
            print(f"✓ {f.name}  {info['vdur']:.2f}s / {info['frames']}f, audio ok, "
                  f"badge opaque {chroma:.1%}, watermark entièrement recouvert")

    print(f"\n{'✗ ' + str(bad) + ' fichier(s) à revoir' if bad else '✓ tout est propre'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
