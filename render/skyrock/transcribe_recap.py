#!/usr/bin/env python3
"""
Transcrit en FRANCAIS les reels "LE RECAP" (le presentateur commente par-dessus
les images). Sert de matiere premiere pour reformuler son propos dans le
rectangle de texte du rendu.

Sortie : render/skyrock/recap_speech.json  = {file: [{start, end, fr}]}
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "render"))
from transcribe import transcribe  # noqa: E402

LIB = ROOT / "library" / "skyrockfm"
OUT = HERE / "recap_speech.json"

# reels au format "LE RECAP" reperes sur les planches-contacts
RECAP = ["05", "06", "07", "09", "10", "13"]


def main():
    out = {}
    for pref in RECAP:
        f = next(LIB.glob(f"{pref}-*.mp4"))
        segs, info = transcribe(str(f), language="fr")
        out[f.name] = [{"start": s["start"], "end": s["end"], "fr": s["en"]}
                       for s in segs]
        print(f"{f.name}: {len(segs)} segments (p={info.language_probability:.2f})",
              flush=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n-> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
