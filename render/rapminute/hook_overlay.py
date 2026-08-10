#!/usr/bin/env python3
"""
Moteur d'overlay "hook" rap.minute rebrande en violet fluo.

Principe : rap.minute pose un hook (texte blanc bold condense majuscule, avec
les mots-cles en vert #00D392 et une barre verticale verte a gauche) pendant
les ~5-8 premieres secondes. On COUVRE cette zone d'une bande opaque et on
reecrit NOTRE texte dans la meme grammaire, en violet fluo.

Balisage du texte : les mots entre *asterisques* passent en violet.
    "la reaction de *BOOBA* quand *SCH* repond"

L'ffmpeg local n'a ni libass ni drawtext : tout le rendu texte se fait en PIL,
puis un simple overlay=0:0 fenetre par enable='between(t,...)'.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tweet_overlay import emoji_glyph, is_emoji  # noqa: E402  (moteur emoji commun)

COND_HEAVY = ("/System/Library/Fonts/Avenir Next Condensed.ttc", 8)
COND_BOLD = ("/System/Library/Fonts/Avenir Next Condensed.ttc", 0)

WHITE = (255, 255, 255, 255)
PURPLE = (139, 0, 255, 255)       # #8B00FF - violet electrique
BAND = (10, 0, 18, 255)           # noir tres legerement violace
RULE = PURPLE[:3] + (110,)        # filet neon en bas de bande

# geometrie calee sur rap.minute, exprimee a 720px de large (scale = W/720)
MARGIN = 66       # x du bloc (mesure sur leurs reels : 66 a 720px, 100 a 1080px)
BAR_W = 7         # barre verticale d'accent
BAR_GAP = 22      # espace barre -> texte
FONT_PX = 33
LINE_H = 38
PAD_Y = 16        # marge verticale de la bande de couverture


def font(spec, px):
    return ImageFont.truetype(spec[0], px, index=spec[1])


def parse_markup(text):
    """'a *b* c' -> [(mot, is_purple), ...] en conservant les espaces."""
    out, buf, purple = [], "", False
    for ch in text:
        if ch == "*":
            if buf:
                out.append((buf, purple))
                buf = ""
            purple = not purple
        else:
            buf += ch
    if buf:
        out.append((buf, purple))
    return out


def to_tokens(text):
    """Aplati le balisage en tokens : (str|emoji, purple), espaces compris."""
    toks = []
    for chunk, purple in parse_markup(text):
        word = ""
        for ch in chunk:
            if is_emoji(ch):
                if word:
                    toks.append((word, purple))
                    word = ""
                if ch in "️‍" and toks and isinstance(toks[-1][0], dict):
                    toks[-1][0]["ch"] += ch
                else:
                    toks.append(({"ch": ch}, purple))
            elif ch == " ":
                if word:
                    toks.append((word, purple))
                    word = ""
                toks.append((" ", purple))
            else:
                word += ch
        if word:
            toks.append((word, purple))
    return toks


def tok_w(draw, tok, f, emoji_px):
    return int(emoji_px * 1.12) if isinstance(tok, dict) else draw.textlength(tok, font=f)


def wrap(draw, toks, f, max_w, emoji_px):
    """Retourne des lignes = listes de (tok, purple), coupees a max_w."""
    lines, cur, cur_w = [], [], 0
    for tok, purple in toks:
        w = tok_w(draw, tok, f, emoji_px)
        if tok == " ":
            if cur:
                cur.append((tok, purple))
                cur_w += w
            continue
        if cur_w + w > max_w and cur:
            while cur and cur[-1][0] == " ":   # pas d'espace en fin de ligne
                cur_w -= tok_w(draw, cur.pop()[0], f, emoji_px)
            lines.append(cur)
            cur, cur_w = [(tok, purple)], w
        else:
            cur.append((tok, purple))
            cur_w += w
    if cur:
        lines.append(cur)
    return lines


def line_width(draw, line, f, emoji_px):
    return sum(tok_w(draw, t, f, emoji_px) for t, _ in line)


def hook_png(W, H, band, text, scale, purple=PURPLE, band_rgba=BAND):
    """PNG plein cadre : bande de couverture + notre hook réécrit."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    px = int(FONT_PX * scale)
    f = font(COND_HEAVY, px)
    line_h = int(LINE_H * scale)
    emoji_px = int(px * 0.92)
    margin = int(MARGIN * scale)
    text_x = margin + int((BAR_W + BAR_GAP) * scale)
    max_w = W - text_x - int(24 * scale)

    lines = wrap(draw, to_tokens(text.upper()), f, max_w, emoji_px)
    block_h = len(lines) * line_h

    # la bande couvre LEUR zone et NOTRE bloc (le notre peut etre plus haut)
    cy = (band[0] + band[1]) / 2
    my0 = cy - block_h / 2
    pad = int(PAD_Y * scale)
    y0 = int(min(band[0], my0) - pad)
    y1 = int(max(band[1], my0 + block_h) + pad)
    y0, y1 = max(0, y0), min(H, y1)

    draw.rectangle((0, y0, W, y1), fill=band_rgba)
    draw.rectangle((0, y1 - max(2, int(3 * scale)), W, y1), fill=RULE)

    ty = int((y0 + y1 - block_h) / 2)
    draw.rectangle((margin, ty + int(4 * scale),
                    margin + int(BAR_W * scale), ty + block_h - int(4 * scale)),
                   fill=purple)

    y = ty
    for line in lines:
        x = text_x
        for tok, is_p in line:
            if isinstance(tok, dict):
                g = emoji_glyph(tok["ch"], emoji_px)
                if g:
                    img.alpha_composite(g, (int(x), int(y + (line_h - g.height) / 2)))
                x += int(emoji_px * 1.12)
            else:
                draw.text((x, y), tok, font=f, fill=purple if is_p else WHITE)
                x += draw.textlength(tok, font=f)
        y += line_h
    return img


def probe_size(video):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(video),
    ]).decode().strip()
    w, h = out.split(",")
    return int(w), int(h)


def render(video, out, hooks, trim_end=None, purple=PURPLE):
    """
    hooks : [{start, end, band:[y0,y1], text}] — un overlay fenetre par hook.
    trim_end : coupe la video a cette seconde (sert a virer l'outro rap.minute).
    """
    W, H = probe_size(video)
    scale = W / 720.0
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    tmp = []
    inputs = ["-i", str(video)]
    fc = ""
    cur = "[0:v]"
    for i, hk in enumerate(hooks):
        im = hook_png(W, H, hk["band"], hk["text"], scale, purple)
        fh = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        im.save(fh.name)
        tmp.append(fh.name)
        inputs += ["-i", fh.name]
        dst = f"[v{i}]"
        fc += (f"{cur}[{i + 1}:v]overlay=0:0:"
               f"enable='between(t,{hk['start']},{hk['end']})'{dst};")
        cur = dst
    fc = fc.rstrip(";") or "[0:v]null[v0]"
    final = cur if hooks else "[0:v]"

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs]
    if hooks:
        cmd += ["-filter_complex", fc, "-map", final]
    else:
        cmd += ["-map", "0:v"]
    cmd += ["-map", "0:a?"]
    if trim_end:
        cmd += ["-t", str(trim_end)]
    cmd += ["-c:a", "aac", "-b:a", "128k", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)

    for f in tmp:
        Path(f).unlink(missing_ok=True)
    return out
