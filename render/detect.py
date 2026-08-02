#!/usr/bin/env python3
"""
Détecte le bord HAUT du bloc vidéo principal dans un reel "faux tweet".

Principe : le cadre vidéo est fixe toute la durée mais son contenu bouge,
alors que les bandes noires (au-dessus/en dessous) restent noires. On prend
le MAX temporel sur plusieurs frames -> les lignes "vidéo" s'allument. On
distingue la vidéo (lignes larges) du texte du tweet (lignes fines) par la
fraction de colonnes allumées sur chaque ligne.
"""
import subprocess
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageChops


def probe(video):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video,
    ]).decode().split()
    return int(out[0]), int(out[1]), float(out[2])


def frame_at(video, t, dest):
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", dest,
    ], check=True)


def detect_video_box(video, samples=12):
    W, H, dur = probe(video)
    acc = None
    with tempfile.TemporaryDirectory() as td:
        for i in range(samples):
            t = dur * (0.05 + 0.9 * i / max(1, samples - 1))
            p = f"{td}/f{i}.png"
            frame_at(video, t, p)
            img = Image.open(p).convert("RGB")
            acc = img if acc is None else ImageChops.lighter(acc, img)

    gray = acc.convert("L")
    th = gray.point(lambda p: 255 if p > 30 else 0)
    # resize BOX -> chaque ligne = moyenne = fraction de colonnes allumées *255
    col = th.resize((1, H), Image.BOX)
    frac = [col.getpixel((0, y)) / 255.0 for y in range(H)]

    # plus grand bloc contigu de lignes "larges"
    best = None
    run = None
    for y in range(H):
        if frac[y] > 0.5:
            if run is None:
                run = y
        else:
            if run is not None:
                if best is None or (y - run) > (best[1] - best[0]):
                    best = (run, y)
                run = None
    if run is not None and (best is None or (H - run) > (best[1] - best[0])):
        best = (run, H)

    if best is None or (best[1] - best[0]) < H * 0.12:
        return None, None, W, H
    return best[0], best[1], W, H


def detect_video_top(video, samples=12):
    top, bottom, W, H = detect_video_box(video, samples)
    return top, W, H


if __name__ == "__main__":
    top, bottom, W, H = detect_video_box(sys.argv[1])
    print(f"{Path(sys.argv[1]).name}\ttop={top}\tbottom={bottom}\t({W}x{H})")
