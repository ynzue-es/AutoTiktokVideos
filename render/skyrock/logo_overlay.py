#!/usr/bin/env python3
"""
Rebrand skyrockfm -> LeMurSonore.

Deux operations :
  1. LOGO : le bandeau de marque incruste en haut a droite (SKYROCK / PLANETE
     RAP / PR+ / LE RECAP / KARAOKE) est recouvert par un badge LeMurSonore.
  2. TEXTE (reels "LE RECAP" seulement) : le presentateur commente en voix off
     par-dessus les images. On reformule son propos et on l'affiche dans un
     rectangle de texte, pendant sa prise de parole uniquement.

L'ffmpeg local n'a ni libass ni drawtext : rendu PIL + overlay=0:0.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tweet_overlay import circle_logo, emoji_glyph, is_emoji  # noqa: E402

ASSETS_LOGO = str(Path(__file__).resolve().parent.parent.parent / "assets" / "logo.png")
COND_HEAVY = ("/System/Library/Fonts/Avenir Next Condensed.ttc", 8)

WHITE = (255, 255, 255, 255)
BADGE = (8, 8, 10, 255)        # fond du badge logo
BAND = (10, 0, 18, 255)        # fond du rectangle de texte
ACCENT = (139, 0, 255, 255)    # violet LeMurSonore (meme que le pipeline B)

# Boites de couverture du bandeau de marque, en coords 720x1280.
# detect_logo.py degrossit, mais il bave sur les fonds clairs (murs, spots) :
# ces valeurs sont MESUREES a la grille sur des frames reelles (cf. README).
FAMILY_BOX = {
    "studio": [503, 170, 676, 262],   # SKYROCK / PLANETE RAP / PR+
    "recap": [500, 64, 680, 182],     # badge LE RECAP (soleil compris)
    "karaoke": [522, 74, 676, 216],   # badge KARAOKE BOX
}


def font(px):
    return ImageFont.truetype(COND_HEAVY[0], px, index=COND_HEAVY[1])


def probe_size(video):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(video),
    ]).decode().strip()
    w, h = out.split(",")
    return int(w), int(h)


def round_rect(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def logo_badge(img, box, scale):
    """Recouvre la zone du logo d'origine et y pose le badge LeMurSonore."""
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    r = int(min(x1 - x0, y1 - y0) * 0.22)
    round_rect(d, (x0, y0, x1, y1), r, BADGE)
    d.rounded_rectangle((x0, y0, x1, y1), radius=r, outline=ACCENT,
                        width=max(2, int(2 * scale)))

    bw, bh = x1 - x0, y1 - y0
    pad = int(bh * 0.16)
    dia = bh - 2 * pad

    if bw >= bh * 2.4:
        # assez large : logo rond + mot-marque sur deux lignes
        disk = circle_logo(ASSETS_LOGO, dia)
        img.alpha_composite(disk, (x0 + pad, y0 + pad))
        tx = x0 + pad + dia + int(bh * 0.12)
        avail = x1 - tx - pad
        fs = max(9, int(bh * 0.30))
        f = font(fs)
        while fs > 8 and d.textlength("SONORE", font=f) > avail:
            fs -= 1
            f = font(fs)
        ty = y0 + (bh - int(fs * 2.15)) // 2
        d.text((tx, ty), "LE MUR", font=f, fill=WHITE)
        d.text((tx, ty + int(fs * 1.08)), "SONORE", font=f, fill=ACCENT)
    else:
        # trop etroit pour le texte : logo rond centre seul
        dia = min(bw, bh) - 2 * pad
        disk = circle_logo(ASSETS_LOGO, dia)
        img.alpha_composite(disk, (x0 + (bw - dia) // 2, y0 + (bh - dia) // 2))


def _tokens(text):
    toks, word = [], ""
    for ch in text:
        if is_emoji(ch):
            if word:
                toks.append(word)
                word = ""
            toks.append({"ch": ch})
        elif ch == " ":
            if word:
                toks.append(word)
                word = ""
            toks.append(" ")
        else:
            word += ch
    if word:
        toks.append(word)
    return toks


def text_png(W, H, text, scale):
    """Rectangle de texte (tiers superieur) portant le propos reformule."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    px = int(34 * scale)
    f = font(px)
    line_h = int(40 * scale)
    emoji_px = int(px * 0.92)
    margin = int(40 * scale)
    max_w = W - 2 * margin - int(28 * scale)

    lines, cur, cur_w = [], [], 0
    for tok in _tokens(text.upper()):
        w = int(emoji_px * 1.12) if isinstance(tok, dict) else d.textlength(tok, font=f)
        if tok == " ":
            if cur:
                cur.append(tok)
                cur_w += w
            continue
        if cur_w + w > max_w and cur:
            while cur and cur[-1] == " ":
                cur_w -= d.textlength(" ", font=f)
                cur.pop()
            lines.append(cur)
            cur, cur_w = [tok], w
        else:
            cur.append(tok)
            cur_w += w
    if cur:
        lines.append(cur)

    block_h = len(lines) * line_h
    pad = int(22 * scale)
    y0 = int(H * 0.30)
    y1 = y0 + block_h + 2 * pad
    round_rect(d, (margin, y0, W - margin, y1), int(16 * scale), BAND)
    d.rectangle((margin, y1 - max(3, int(4 * scale)), W - margin, y1), fill=ACCENT)

    y = y0 + pad
    for ln in lines:
        x = margin + int(24 * scale)
        for tok in ln:
            if isinstance(tok, dict):
                g = emoji_glyph(tok["ch"], emoji_px)
                if g:
                    img.alpha_composite(g, (int(x), int(y + (line_h - g.height) / 2)))
                x += int(emoji_px * 1.12)
            else:
                d.text((x, y), tok, font=f, fill=WHITE)
                x += d.textlength(tok, font=f)
        y += line_h
    return img


def render(video, out, family, text=None, text_window=None, trim_start=None):
    """
    family      : cle de FAMILY_BOX -> zone du logo a recouvrir
    text        : propos reformule (reels LE RECAP), sinon None
    text_window : (start, end) d'affichage du rectangle, sur la timeline de SORTIE
    trim_start  : coupe le debut (intro du presentateur). '-ss' place AVANT '-i'
                  ne s'applique qu'a l'entree suivante (la video) et remet les
                  timestamps a zero -> text_window se compte donc a partir de 0.
    """
    W, H = probe_size(video)
    scale = W / 720.0
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    box = [int(v * scale) for v in FAMILY_BOX[family]]
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    logo_badge(overlay, box, scale)

    tmp = []
    def save(im):
        fh = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        im.save(fh.name)
        tmp.append(fh.name)
        return fh.name

    seek = ["-ss", str(trim_start)] if trim_start else []
    inputs = [*seek, "-i", str(video), "-i", save(overlay)]
    fc = "[0:v][1:v]overlay=0:0[b0]"
    final = "[b0]"
    if text and text_window:
        inputs += ["-i", save(text_png(W, H, text, scale))]
        fc += (f";[b0][2:v]overlay=0:0:"
               f"enable='between(t,{text_window[0]},{text_window[1]})'[b1]")
        final = "[b1]"

    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
        "-filter_complex", fc, "-map", final, "-map", "0:a?",
        "-c:a", "aac", "-b:a", "128k", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
    ], check=True)
    for f in tmp:
        Path(f).unlink(missing_ok=True)
    return out
