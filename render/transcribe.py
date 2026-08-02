#!/usr/bin/env python3
"""
Transcrit l'audio (anglais) d'un reel en segments timés, via faster-whisper.
Usage : python3 transcribe.py <video.mp4>  -> imprime les segments.
"""
import sys
import json
from faster_whisper import WhisperModel

_MODEL = None


def model():
    global _MODEL
    if _MODEL is None:
        _MODEL = WhisperModel("small", device="cpu", compute_type="int8")
    return _MODEL


def transcribe(video, language="en"):
    segments, info = model().transcribe(
        video, language=language, vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
    )
    out = []
    for s in segments:
        txt = s.text.strip()
        if txt:
            out.append({"start": round(s.start, 2), "end": round(s.end, 2), "en": txt})
    return out, info


if __name__ == "__main__":
    segs, info = transcribe(sys.argv[1])
    print(f"# lang={info.language} p={info.language_probability:.2f} "
          f"segments={len(segs)}")
    print(json.dumps(segs, ensure_ascii=False, indent=2))
