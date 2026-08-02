#!/usr/bin/env python3
"""
Rend les 29 reels : header LeMurSonore + texte FR (translations.json) +
sous-titres FR (subs_fr.json, sur les clips parlés), calés via prep.json.
Sortie dans out/fr/.
"""
import json
from pathlib import Path
from tweet_overlay import render
from subtitles import build_cues

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "library"
OUT = ROOT / "out" / "fr"

# reels où une bande promo Sonotrade est incrustée en bas -> masquée + footer
# LeMurSonore. Valeur = (y_from, y_to) de la bande à recouvrir.
FOOTERS = {
    "22-DZNMXREgthY.mp4": (882, 1052),
}


def main():
    trans = json.loads((ROOT / "render" / "translations.json").read_text())
    prep = {p["file"]: p for p in json.loads((ROOT / "render" / "prep.json").read_text())}
    subs_path = ROOT / "render" / "subs_fr.json"
    subs = json.loads(subs_path.read_text()) if subs_path.exists() else {}
    OUT.mkdir(parents=True, exist_ok=True)

    for t in trans:
        f = t["file"]
        p = prep[f]
        cues = build_cues(subs[f]) if f in subs else None
        render(str(LIB / f), str(OUT / f), p["video_top"], t["fr"],
               cues=cues, video_bottom=p.get("video_bottom"),
               footer=FOOTERS.get(f))
        tag = f"+{len(cues)} subs" if cues else "sans subs"
        tag += " +footer" if f in FOOTERS else ""
        print(f"✓ {f}  (top={p['video_top']}, {tag})")
    print(f"\n✓ {len(trans)} vidéos dans out/fr/")


if __name__ == "__main__":
    main()
