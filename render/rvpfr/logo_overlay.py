#!/usr/bin/env python3
"""
Moteur d'overlay rvpfr : on couvre leur watermark (losange "Rvp Fr" en bas au
centre) par un badge rond LeMurSonore.

Le watermark d'origine est un alpha-blend translucide : on ne peut pas
l'effacer, seulement le RECOUVRIR. Le badge est donc 100% opaque et son
diametre part du `radius` mesure par detect_logo.py (distance du pixel de
watermark le plus eloigne du centre), plus une marge — pas de la diagonale de
la bbox, qui surdimensionnerait le badge puisque le losange laisse ses coins
vides.

Pour que ca n'ait pas l'air rafistole : ombre portee douce sous le badge et
fin liseret, comme un avatar pose sur l'image — la meme grammaire que le rond
LeMurSonore du pipeline A (on reutilise d'ailleurs son circle_logo).

L'ffmpeg local n'a ni libass ni drawtext : le badge est rendu en PIL puis
composite par un simple overlay=0:0, actif toute la duree.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tweet_overlay import DEFAULT_LOGO, circle_logo  # noqa: E402

# geometrie du badge, exprimee a 720px de large (scale = W / 720)
MARGIN = 13          # marge de recouvrement ajoutee autour de la bbox detectee
MIN_DIA = 92         # diametre plancher : sous ca le logo M devient illisible
MAX_DIA = 150        # garde-fou : une bbox aberrante ne doit pas manger l'image
SHADOW_BLUR = 0.07   # rayon du flou de l'ombre, en fraction du diametre
SHADOW_DY = 0.035    # decalage vertical de l'ombre, en fraction du diametre
SHADOW_A = 95        # opacite de l'ombre
RING = (0, 0, 0, 30)  # liseret : detache le badge d'un fond blanc
SS = 4               # supersampling du rond (PIL ne lisse pas les ellipses)


def badge_diameter(box, scale, radius=None):
    """Diametre du badge : rayon couvrant du watermark + marge.

    `radius` vient de logos.json (distance du pixel de watermark le plus
    eloigne du centre). Sans lui on retombe sur la demi-diagonale de la bbox,
    plus large que necessaire — le watermark est un losange, ses coins sont
    vides.
    """
    if radius is None:
        bw, bh = box[2] - box[0], box[3] - box[1]
        radius = (bw ** 2 + bh ** 2) ** 0.5 / 2
    dia = 2 * (radius + MARGIN * scale)
    return int(max(MIN_DIA * scale, min(MAX_DIA * scale, dia)))


def badge_png(W, H, box, scale, radius=None, logo=DEFAULT_LOGO):
    """PNG plein cadre : ombre douce + rond blanc + M LeMurSonore."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dia = badge_diameter(box, scale, radius)
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    x, y = cx - dia // 2, cy - dia // 2

    # ombre portee : disque noir flou, legerement plus grand et decale vers le bas
    blur = max(2, int(dia * SHADOW_BLUR))
    grow = blur
    sh = Image.new("RGBA", (dia + 6 * grow, dia + 6 * grow), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse(
        (3 * grow - grow // 2, 3 * grow - grow // 2,
         3 * grow + dia + grow // 2, 3 * grow + dia + grow // 2),
        fill=(0, 0, 0, SHADOW_A))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    img.alpha_composite(sh, (x - 3 * grow, y - 3 * grow + int(dia * SHADOW_DY)))

    # rond + liseret dessines en grand puis reduits : bord net, pas crenele
    big = circle_logo(logo, dia * SS)
    ring = Image.new("RGBA", big.size, (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((0, 0, dia * SS - 1, dia * SS - 1), outline=RING,
                                 width=max(SS, int(dia * SS * 0.012)))
    big.alpha_composite(ring)           # compositing, pas un remplacement de pixels
    img.alpha_composite(big.resize((dia, dia), Image.LANCZOS), (x, y))
    return img


def probe_size(video):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(video),
    ]).decode().strip()
    w, h = out.split(",")
    return int(w), int(h)


def render(video, out, box, radius=None, logo=DEFAULT_LOGO):
    """Recouvre la zone `box` du watermark rvpfr par le badge LeMurSonore.

    Le badge reste affiche toute la duree : sur certains reels le watermark
    d'origine disparait par moments (montage de plusieurs clips), mais notre
    marque, elle, doit rester constante.
    """
    W, H = probe_size(video)
    scale = W / 720.0
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    im = badge_png(W, H, box, scale, radius, logo)
    fh = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    im.save(fh.name)
    try:
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(video), "-i", fh.name,
            "-filter_complex", "[0:v][1:v]overlay=0:0[v]",
            "-map", "[v]", "-map", "0:a?",
            "-c:a", "copy",                      # audio d'origine intact
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
        ], check=True)
    finally:
        Path(fh.name).unlink(missing_ok=True)
    return out
