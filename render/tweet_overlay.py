#!/usr/bin/env python3
"""
Moteur d'overlay "faux tweet" : rond logo + nom + badge + texte FR (avec
emojis couleur), posé au-dessus du bloc vidéo principal (dont le bord haut
est détecté séparément, cf detect.py).

Utilisable en CLI (un reel) ou importable : render(...).
"""
import argparse
import re
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

DEFAULT_LOGO = str(Path(__file__).resolve().parent.parent / "assets" / "logo.png")
ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"
ARIAL_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
ARIAL_BLACK = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
APPLE_EMOJI = "/System/Library/Fonts/Apple Color Emoji.ttc"

WHITE = (255, 255, 255, 255)
GREY = (110, 118, 125, 255)
GOLD = (255, 194, 39, 255)
BLACK = (0, 0, 0, 255)

# détecte un caractère emoji (plages usuelles) ; FE0F/ZWJ gérés comme liants
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002190-\U000021FF"
    "\U00002B00-\U00002BFF\U0001F1E6-\U0001F1FF\U0000FE00-\U0000FE0F\U0000200D]"
)


def is_emoji(ch):
    return bool(EMOJI_RE.match(ch))


@lru_cache(maxsize=256)
def emoji_glyph(ch, size):
    """Rend un emoji couleur (Apple Color Emoji) à ~size px."""
    try:
        f = ImageFont.truetype(APPLE_EMOJI, 160)  # strike valide Apple Color Emoji
        tmp = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((10, 10), ch, font=f, embedded_color=True)
        bbox = tmp.getbbox()
        if bbox:
            tmp = tmp.crop(bbox)
        tmp.thumbnail((size, size), Image.LANCZOS)
        return tmp
    except Exception:
        return None


def tokenize(text):
    """Découpe en tokens : mots, espaces, emojis (chaque emoji = 1 token)."""
    tokens = []
    buf = ""
    for ch in text:
        if is_emoji(ch):
            if buf:
                tokens.append(buf)
                buf = ""
            # colle les liants (FE0F/ZWJ) au token emoji précédent
            if ch in "️‍" and tokens and tokens[-1].get("emoji"):
                tokens[-1]["ch"] += ch
            else:
                tokens.append({"emoji": True, "ch": ch})
        else:
            buf += ch
    if buf:
        tokens.append(buf)
    return tokens


def token_width(draw, tok, font, emoji_px):
    if isinstance(tok, dict):
        return int(emoji_px * 1.15)
    return draw.textlength(tok, font=font)


def wrap_rich(draw, text, font, max_w, emoji_px):
    """Retourne une liste de lignes ; chaque ligne = liste de tokens."""
    lines = []
    for para in text.split("\n"):
        cur, cur_w = [], 0
        # on découpe le paragraphe en (mot | emoji) séparés par espaces
        words = re.split(r"(\s+)", para)
        for word in words:
            if word == "":
                continue
            toks = tokenize(word)
            w = sum(token_width(draw, t, font, emoji_px) for t in toks)
            space_w = draw.textlength(" ", font=font) if word.strip() == "" else 0
            if word.strip() == "":
                # espace : on l'ajoute si la ligne n'est pas vide
                if cur:
                    cur.append(" ")
                    cur_w += draw.textlength(" ", font=font)
                continue
            if cur_w + w <= max_w or not cur:
                cur.extend(toks)
                cur_w += w
            else:
                lines.append(cur)
                cur, cur_w = toks, w
        lines.append(cur)
    return lines


def draw_line(img, draw, x, y, tokens, font, fill, emoji_px, line_h):
    cx = x
    for tok in tokens:
        if isinstance(tok, dict):
            g = emoji_glyph(tok["ch"], emoji_px)
            if g:
                gy = y + (line_h - g.height) // 2 - int(line_h * 0.12)
                img.alpha_composite(g, (int(cx), int(gy)))
            cx += int(emoji_px * 1.15)
        else:
            draw.text((cx, y), tok, font=font, fill=fill)
            cx += draw.textlength(tok, font=font)


def probe_size(video):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", video,
    ]).decode().strip()
    w, h = out.split(",")
    return int(w), int(h)


def trim_logo(logo):
    """Recadre le logo sur son contenu (ignore les marges blanches/transparentes)."""
    if logo.mode == "RGBA" and logo.getchannel("A").getextrema()[0] < 255:
        bbox = logo.getchannel("A").getbbox()  # marge transparente
    else:
        gray = logo.convert("L")
        mask = gray.point(lambda p: 255 if p < 220 else 0)  # contenu = pixels sombres
        bbox = mask.getbbox()
    return logo.crop(bbox) if bbox else logo


def circle_logo(logo_path, diameter):
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
    disk = Image.new("RGBA", (diameter, diameter), WHITE)
    if logo_path and Path(logo_path).exists():
        logo = trim_logo(Image.open(logo_path).convert("RGBA"))
        pad = int(diameter * 0.24)  # le mark occupe ~52% du rond, bien centré
        box = diameter - 2 * pad
        logo.thumbnail((box, box), Image.LANCZOS)
        disk.alpha_composite(logo, ((diameter - logo.width) // 2,
                                    (diameter - logo.height) // 2))
    else:
        d = ImageDraw.Draw(disk)
        f = ImageFont.truetype(ARIAL_BLACK, int(diameter * 0.6))
        tb = d.textbbox((0, 0), "M", font=f)
        d.text(((diameter - (tb[2] - tb[0])) / 2 - tb[0],
                (diameter - (tb[3] - tb[1])) / 2 - tb[1]), "M", font=f, fill=BLACK)
    out = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    out.paste(disk, (0, 0), mask)
    return out


def verified_badge(size):
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(badge)
    d.ellipse((0, 0, size - 1, size - 1), fill=GOLD)
    d.line([(size * 0.28, size * 0.52), (size * 0.44, size * 0.68),
            (size * 0.74, size * 0.34)], fill=WHITE,
           width=max(2, size // 8), joint="curve")
    return badge


def build_overlay(W, H, video_top, name, handle, text, logo_path, scale):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = int(30 * scale)
    text_font = ImageFont.truetype(ARIAL, int(30 * scale))
    name_font = ImageFont.truetype(ARIAL_BOLD, int(30 * scale))
    handle_font = ImageFont.truetype(ARIAL, int(27 * scale))
    emoji_px = int(30 * scale)
    line_h = int(38 * scale)

    max_w = W - 2 * margin
    lines = wrap_rich(draw, text, text_font, max_w, emoji_px)

    header_h = int(64 * scale)
    gap = int(16 * scale)
    text_bottom = video_top - int(14 * scale)
    text_top = text_bottom - len(lines) * line_h
    header_top = text_top - gap - header_h

    # bande noire opaque : couvre l'ancien header + texte jusqu'au bloc vidéo
    draw.rectangle((0, 0, W, video_top), fill=BLACK)

    dia = header_h
    img.alpha_composite(circle_logo(logo_path, dia), (margin, header_top))
    tx = margin + dia + int(14 * scale)
    draw.text((tx, header_top + int(4 * scale)), name, font=name_font, fill=WHITE)
    name_w = draw.textlength(name, font=name_font)
    bsize = int(26 * scale)
    img.alpha_composite(verified_badge(bsize),
                        (int(tx + name_w + 8 * scale), header_top + int(6 * scale)))
    draw.text((tx, header_top + int(36 * scale)), handle, font=handle_font, fill=GREY)

    y = text_top
    for ln in lines:
        draw_line(img, draw, margin, y, ln, text_font, WHITE, emoji_px, line_h)
        y += line_h
    return img


def wrap_plain(draw, text, font, max_w, max_lines=2):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = w if not cur else cur + " " + w
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:  # fusionne le surplus dans la dernière ligne
        lines = lines[:max_lines - 1] + [" ".join(lines[max_lines - 1:])]
    return lines


def subtitle_png(text, W, H, video_bottom, scale):
    """PNG plein cadre transparent avec un sous-titre FR (blanc, contour noir)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fs = int(34 * H / 1280)
    font = ImageFont.truetype(ARIAL_BOLD, fs)
    lines = wrap_plain(d, text, font, int(W * 0.86))
    line_h = int(fs * 1.22)
    y = video_bottom - int(26 * scale) - line_h * len(lines)
    stroke = max(2, int(fs * 0.11))
    for ln in lines:
        w = d.textlength(ln, font=font)
        d.text(((W - w) / 2, y), ln, font=font, fill=WHITE,
               stroke_width=stroke, stroke_fill=BLACK)
        y += line_h
    return img


def draw_footer(img, W, y_from, y_to, logo_path, scale):
    """Couvre une bande basse et y pose un footer LeMurSonore (logo + brand)."""
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, y_from, W, y_to), fill=BLACK)
    cy = (y_from + y_to) // 2
    dia = int(42 * scale)
    name = "lemursonore.fr"
    link = "Lien en bio"
    name_font = ImageFont.truetype(ARIAL, int(27 * scale))
    link_font = ImageFont.truetype(ARIAL_BOLD, int(27 * scale))
    gap, gap2 = int(12 * scale), int(22 * scale)
    nw = draw.textlength(name, font=name_font)
    lw = draw.textlength(link, font=link_font)
    x = (W - (dia + gap + nw + gap2 + lw)) // 2
    img.alpha_composite(circle_logo(logo_path, dia), (int(x), cy - dia // 2))
    x += dia + gap
    ty = cy - int(15 * scale)
    draw.text((x, ty), name, font=name_font, fill=WHITE)
    x += nw + gap2
    draw.text((x, ty), link, font=link_font, fill=WHITE)


def render(video, out, video_top, text, name="LeMurSonore",
           handle="@lemursonore.fr", logo=DEFAULT_LOGO,
           cues=None, video_bottom=None, footer=None):
    W, H = probe_size(video)
    scale = W / 720.0
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    tmp = []
    def save(im):
        f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        im.save(f.name)
        tmp.append(f.name)
        return f.name

    overlay_img = build_overlay(W, H, video_top, name, handle, text, logo, scale)
    if footer:  # (y_from, y_to) : masque la promo Sonotrade + footer LeMurSonore
        draw_footer(overlay_img, W, footer[0], footer[1], logo, scale)
    header_png = save(overlay_img)
    inputs = ["-i", video, "-i", header_png]
    fc = "[0:v][1:v]overlay=0:0[b0]"

    # sous-titres FR : un PNG par cue, overlay-é sur sa fenêtre temporelle
    if cues and video_bottom:
        for i, c in enumerate(cues):
            inputs += ["-i", save(subtitle_png(c["text"], W, H, video_bottom, scale))]
            src, dst = f"[b{i}]", f"[b{i + 1}]"
            fc += (f";{src}[{i + 2}:v]overlay=0:0:"
                   f"enable='between(t,{c['start']},{c['end']})'{dst}")
        final = f"[b{len(cues)}]"
    else:
        final = "[b0]"

    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
        "-filter_complex", fc, "-map", final, "-map", "0:a?",
        "-c:a", "copy", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out,
    ], check=True)
    for f in tmp:
        Path(f).unlink(missing_ok=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--video-top", type=int, required=True)
    ap.add_argument("--name", default="LeMurSonore")
    ap.add_argument("--handle", default="@lemursonore.fr")
    ap.add_argument("--text", required=True)
    ap.add_argument("--logo", default=DEFAULT_LOGO)
    a = ap.parse_args()
    render(a.video, a.out, a.video_top, a.text, a.name, a.handle, a.logo)
    print(f"✓ {a.out}")


if __name__ == "__main__":
    main()
