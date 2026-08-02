#!/usr/bin/env python3
"""
Transcrit les 29 reels traduits (ordre de translations.json) et écrit
render/transcripts.json = {file: [{start,end,en}]}. Long (Whisper CPU).
"""
import json
from pathlib import Path
from transcribe import transcribe

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "library"


def main():
    trans = json.loads((ROOT / "render" / "translations.json").read_text())
    out = {}
    for t in trans:
        f = t["file"]
        segs, info = transcribe(str(LIB / f))
        out[f] = segs
        print(f"{f}: {len(segs)} segments (p={info.language_probability:.2f})",
              flush=True)
    (ROOT / "render" / "transcripts.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n✓ transcripts.json ({len(out)} reels)")


if __name__ == "__main__":
    main()
