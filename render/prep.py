#!/usr/bin/env python3
"""
Prépare le batch : pour chaque reel de library/index.json, détecte le bord
haut du bloc vidéo et extrait une frame de lecture (pour transcrire le texte).
Écrit render/prep.json = [{file, video_top, w, h}] et scratch-frames/read-NN.png
"""
import json
import subprocess
from pathlib import Path
from detect import detect_video_top

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "library"
FRAMES = ROOT / "scratch-frames"


def main():
    FRAMES.mkdir(exist_ok=True)
    idx = json.loads((LIB / "index.json").read_text())
    prep = []
    for i, r in enumerate(idx):
        video = LIB / r["file"]
        top, w, h = detect_video_top(str(video))
        # frame de lecture : 1s après le début (texte statique toute la durée)
        out = FRAMES / f"read-{i:02d}.png"
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", "1.0", "-i", str(video), "-frames:v", "1", str(out),
        ], check=True)
        prep.append({"file": r["file"], "video_top": top, "w": w, "h": h})
        print(f"{i:02d} {r['file']:24s} top={top} ({w}x{h})")
    (ROOT / "render" / "prep.json").write_text(json.dumps(prep, indent=2))
    print(f"\n✓ render/prep.json ({len(prep)} reels)")


if __name__ == "__main__":
    main()
