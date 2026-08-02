#!/usr/bin/env python3
"""
Génère un fichier ASS de sous-titres FR (style TikTok : blanc gras, contour
noir), calé en bas du bloc vidéo. Les segments longs sont découpés en cues
plus courtes, le temps réparti proportionnellement.
"""


def _wrap(text, max_chars):
    """Coupe le texte en <= 2 lignes d'environ max_chars."""
    words = text.split()
    if not words:
        return text
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = w if not cur else cur + " " + w
    lines.append(cur)
    return "\\N".join(lines[:2]) if len(lines) <= 2 else \
        "\\N".join([" ".join(lines[:-1]), lines[-1]])


def build_cues(segments, max_chars=38, max_dur=3.6):
    """segments: [{start,end,fr}] -> cues [{start,end,text}] découpées."""
    cues = []
    for s in segments:
        fr = s["fr"].strip()
        if not fr:
            continue
        dur = max(0.4, s["end"] - s["start"])
        # combien de cues ? selon longueur et durée
        n = max(1, int(len(fr) / (max_chars * 2)) + 1, int(dur / max_dur) + 1)
        if n == 1:
            cues.append({"start": s["start"], "end": s["end"], "text": fr})
            continue
        words = fr.split()
        # répartit les mots en n paquets ~équilibrés par nombre de caractères
        target = len(fr) / n
        chunks, cur, acc = [], "", 0
        for w in words:
            cur = w if not cur else cur + " " + w
            acc += len(w) + 1
            if acc >= target and len(chunks) < n - 1:
                chunks.append(cur)
                cur, acc = "", 0
        if cur:
            chunks.append(cur)
        # répartit le temps proportionnellement à la longueur des chunks
        total = sum(len(c) for c in chunks) or 1
        t = s["start"]
        for c in chunks:
            d = dur * len(c) / total
            cues.append({"start": round(t, 2), "end": round(t + d, 2), "text": c})
            t += d
    return cues


def _ts(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def write_ass(cues, path, W, H, video_bottom):
    scale = H / 1280.0
    fs = int(34 * scale)
    outline = max(2, int(2.6 * scale))
    shadow = max(1, int(1.2 * scale))
    margin_v = int(H - video_bottom + 26 * scale)  # bas des subs ~ bas de la vidéo
    max_chars = int(38 * (W / 720.0))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Arial,{fs},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, MarginL, MarginR, Effect, Text
"""
    lines = [header]
    for c in cues:
        txt = _wrap(c["text"], max_chars)
        lines.append(
            f"Dialogue: 0,{_ts(c['start'])},{_ts(c['end'])},Sub,,0,0,0,,{txt}\n"
        )
    with open(path, "w") as f:
        f.write("".join(lines))
    return path
