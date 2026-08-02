#!/usr/bin/env python3
"""Ajoute video_bottom à prep.json (détection de la box complète)."""
import json
from pathlib import Path
from detect import detect_video_box

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "library"
PREP = ROOT / "render" / "prep.json"


def main():
    prep = json.loads(PREP.read_text())
    for p in prep:
        top, bottom, w, h = detect_video_box(str(LIB / p["file"]))
        p["video_top"] = top if top is not None else p.get("video_top")
        p["video_bottom"] = bottom
        print(f"{p['file']}: top={top} bottom={bottom}", flush=True)
    PREP.write_text(json.dumps(prep, indent=2))
    print(f"\n✓ prep.json augmenté ({len(prep)} reels)")


if __name__ == "__main__":
    main()
