#!/usr/bin/env python3
"""
Detecte les pilules vertes rap.minute (#00D392) dans chaque reel.

Sortie : render/rapminute/green.json
  [{file, w, h, fps, segments: [{start, end, box: [x0,y0,x1,y1], lines: n}]}]

Methode : on echantillonne 1 frame toutes les STEP secondes via ffmpeg (pipe
rawvideo, pas d'ecriture disque), on masque les pixels proches du vert de marque,
puis on regroupe les frames consecutives qui portent du vert en segments.
La box d'un segment = union des boxes de ses frames (la pilule peut grossir
quand le texte s'ecrit mot par mot).
"""
import json
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
LIB = ROOT / "library" / "rapminute"
OUT = Path(__file__).resolve().parent / "green.json"

GREEN = np.array([0, 211, 146], dtype=np.int16)
TOL = 26          # distance max par canal pour considerer un pixel "vert marque"
MIN_PIXELS = 900  # en dessous : bruit (vetement vert, neon...), pas une pilule
STEP = 0.25       # pas d'echantillonnage en secondes


def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v",
         "-show_entries", "stream=width,height:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    return s["width"], s["height"], float(d["format"]["duration"])


def frames(path, w, h, step):
    """Yield (t, ndarray HxWx3) en echantillonnant a 1/step fps."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-vf", f"fps=1/{step}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True)
    n = w * h * 3
    buf = p.stdout
    for i in range(len(buf) // n):
        yield i * step, np.frombuffer(buf[i * n:(i + 1) * n], np.uint8).reshape(h, w, 3)


def green_box(img):
    """Bounding box des pixels vert-marque, ou None."""
    d = np.abs(img.astype(np.int16) - GREEN).max(axis=2)
    mask = d <= TOL
    if mask.sum() < MIN_PIXELS:
        return None
    ys, xs = np.nonzero(mask)
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def main():
    files = sorted(LIB.glob("*.mp4"))
    out = []
    for f in files:
        w, h, dur = probe(f)
        hits = []
        for t, img in frames(f, w, h, STEP):
            b = green_box(img)
            if b:
                hits.append((t, b))

        # regroupe les frames vertes consecutives (<= 2 pas de trou) en segments
        segs = []
        for t, b in hits:
            if segs and t - segs[-1]["end"] <= STEP * 2.5:
                s = segs[-1]
                s["end"] = t
                s["box"] = [min(s["box"][0], b[0]), min(s["box"][1], b[1]),
                            max(s["box"][2], b[2]), max(s["box"][3], b[3])]
            else:
                segs.append({"start": t, "end": t, "box": b})

        for s in segs:
            s["end"] = round(min(s["end"] + STEP, dur), 2)
            s["start"] = round(s["start"], 2)

        out.append({"file": f.name, "w": w, "h": h, "dur": round(dur, 2),
                    "segments": segs})
        tot = sum(s["end"] - s["start"] for s in segs)
        print(f"{f.name}  {w}x{h}  {len(segs)} segment(s)  {tot:.1f}s de vert")

    OUT.write_text(json.dumps(out, indent=2))
    print(f"\n-> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
