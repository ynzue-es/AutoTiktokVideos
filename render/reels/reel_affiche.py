#!/usr/bin/env python3
"""Reel 9:16 « décomposition d'affiche » à partir du générateur de posters.

Le principe, et pourquoi il n'y a aucune IA vidéo là-dedans
-----------------------------------------------------------
`ScriptsShopify/posters.py` compose l'affiche par empilement : fond flouté,
pochette, tracklist, bloc artiste/titre/palette, signature, date, label. La
vidéo ne fait que rejouer cet empilement dans le temps. Il suffit donc de
récupérer les COUCHES, et tout le reste est de la composition PIL.

Les couches ne sont pas extraites en modifiant `poster()` — ce fichier est du
code de production catalogue, on n'y touche pas pour une vidéo. On les obtient
par DIFFÉRENCE : le fond flouté et la pochette se recomposent à l'identique
avec les fonctions publiques du module (`blurred_bg`, `load_cover`), et tout ce
qui les sépare de l'affiche finie est de l'encre. Ce masque d'encre est ensuite
découpé en blocs par PROJECTION — on cherche les grandes bandes vides entre les
groupes de texte, plutôt que de coder en dur des coordonnées qui changeraient
avec le nombre de titres.

Conséquence : le script marche sur n'importe quelle fiche du catalogue, y
compris une tracklist à 3 colonnes ou un nom d'artiste sur 2 lignes.

Découpage du montage (15 s, 30 fps, 1080x1920)
----------------------------------------------
    0,0 - 1,7   HOOK       pochette plein cadre, zoom lent, accroche texte
    1,7 - 2,4   POSE       la pochette recule à sa place sur le papier
    2,4 - 7,9   BUILD      les blocs de texte tombent un par un
    7,9 - 8,3   FONDU      vers la mise en scène
    8,3 - 10,4  CADRE      l'affiche encadrée au mur, travelling lent
   10,4 - 13,6  MUR        3 colonnes d'affiches en parallaxe
   13,6 - 15,0  CTA        marque + adresse

Usage
-----
    ScriptsShopify/.venv/bin/python render/reels/reel_affiche.py
    ... --album 1262014 --sortie ~/Desktop/reel.mp4

Le rendu est muet par défaut (piste AAC silencieuse, pour que le fichier ait
un flux audio). `--audio piste.mp3` pose une bande-son, avec fondus d'entrée
et de sortie calés sur la durée du montage.
"""

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

# --- accès au générateur d'affiches ----------------------------------------
# On importe le module du dépôt boutique tel quel : une seule source de vérité
# pour la mise en page. `images/` est ajouté au chemin pour `mockup_biais`, qui
# vit à côté et attend d'être importable par son nom.
BOUTIQUE = Path(__file__).resolve().parents[3] / "ScriptsShopify"
sys.path.insert(0, str(BOUTIQUE))
sys.path.insert(0, str(BOUTIQUE / "images"))
# Le dépôt boutique référence ses mockups en relatif : on s'y place. Le
# répertoire d'appel est retenu d'abord, sinon les chemins passés en ligne de
# commande (--audio, --sortie) changeraient de sens sous les pieds de
# l'utilisateur.
CWD0 = Path.cwd()
os.chdir(BOUTIQUE)

import posters                            # noqa: E402
import mockup_biais as mb                 # noqa: E402
from PIL import Image, ImageChops, ImageDraw, ImageFilter  # noqa: E402

CACHE = Path(__file__).resolve().parent / "cache"
CACHE.mkdir(exist_ok=True)

W, H, FPS = 1080, 1920, 30               # format Reels / Stories
AFF_W = 868                              # largeur de l'affiche à l'écran (3:4)
AFF_H = round(AFF_W * 4 / 3)
AFF_X, AFF_Y = (W - AFF_W) // 2, 300     # posée haut-centre : place au texte en bas
# Marge du papier et côté de la pochette, à l'échelle de l'écran. `poster()`
# réserve 5,5 % de la largeur en marge : la pochette animée doit atterrir
# EXACTEMENT là, sinon elle déborde sur le papier une fois posée.
MARGE_S = round(AFF_W * 0.055)
POCH_S = AFF_W - 2 * MARGE_S
# Pochette d'accroche : montrée entière et REDUITE (1200 px de source pour 960
# à l'écran), jamais agrandie. Posée haut pour laisser l'accroche texte sous
# elle, au-dessus des surcouches de Reels.
HOOK_W, HOOK_Y = 1012, 290

BLANC = (245, 245, 245)
GRIS = (176, 176, 176)

LOGO = BOUTIQUE.parent / "Logos" / "LogoLMS.png"

# Voix off et sous-titres, dans un seul tableau : `lit_sonore.py` lit la
# colonne « dit » pour la synthèse, le montage lit la colonne « écrit ». Les
# deux ne peuvent pas se désynchroniser puisqu'il n'y a qu'une source.
#   (début, fin d'affichage, ce qui est dit, ce qui est écrit)
PHRASES = [
    (0.35, 2.30, "Vous aimez vraiment ce groupe ?",
     "VOUS AIMEZ VRAIMENT CE GROUPE ?"),
    (2.55, 4.90, "Bienvenue chez Le Mur Sonore.",
     "BIENVENUE CHEZ LE MUR SONORE"),
]


# ---------------------------------------------------------------------------
# Données
# ---------------------------------------------------------------------------
def charger(album_id):
    """(cover, meta) pour un album Deezer, avec cache disque.

    Deezer est appelé une fois par album et par machine : au-delà d'une
    poignée de rendus, ce sont les mêmes 6 albums qui reviennent et le cache
    fait passer une itération de montage de 40 s à 2 s.
    """
    fj, fp = CACHE / f"{album_id}.json", CACHE / f"{album_id}-1200.jpg"
    if fj.exists() and fp.exists():
        meta = json.loads(fj.read_text())
    else:
        meta = posters.album_details(album_id)
        # `cover_xl` pointe le 1000x1000. Le CDN sert jusqu'à 1200 et pas un
        # pixel de plus : au-delà il renvoie 1200 quelle que soit la taille
        # demandée. On prend ce maximum, parce que la vidéo agrandit la
        # pochette bien plus que ne le fait l'affiche.
        cov = posters.load_cover(meta["cover_xl"].replace("1000x1000", "1200x1200"))
        cov.save(fp, quality=95)
        fj.write_text(json.dumps(meta, ensure_ascii=False))
    return Image.open(fp).convert("RGB"), meta


# ---------------------------------------------------------------------------
# Extraction des couches
# ---------------------------------------------------------------------------
def _vides(proj, mini):
    """Intervalles [a, b) où la projection est nulle, d'au moins `mini` px.

    `proj` est une somme de pixels d'encre le long d'un axe. Ses zéros sont les
    gouttières : entre deux colonnes de tracklist, entre la palette et le
    genre, entre la tracklist et le label. C'est ce qui remplace des
    coordonnées codées en dur — elles dépendraient du nombre de titres.
    """
    out, debut = [], None
    for i, v in enumerate(proj):
        if v == 0 and debut is None:
            debut = i
        elif v != 0 and debut is not None:
            if i - debut >= mini:
                out.append((debut, i))
            debut = None
    if debut is not None and len(proj) - debut >= mini:
        out.append((debut, len(proj)))
    return out


def _plus_grand_vide(masque, boite, axe, marge=0.18):
    """Milieu de la plus large bande vide de `boite`, selon `axe` (0=x, 1=y).

    `marge` écarte les bords : la bande vide la plus large d'une zone de texte
    est presque toujours celle qui la précède ou la suit, pas celle qui la
    coupe en deux. On ne cherche donc qu'au centre. Rend None si la zone est
    d'un seul tenant (tracklist sur une colonne, par exemple).
    """
    z = masque.crop(boite)
    px = z.load()
    n = z.width if axe == 0 else z.height
    m = z.height if axe == 0 else z.width
    proj = [0] * n
    for i in range(n):
        s = 0
        for j in range(0, m, 2):          # 1 ligne sur 2 : le texte est épais
            s += px[i, j] if axe == 0 else px[j, i]
        proj[i] = s
    lo, hi = int(n * marge), int(n * (1 - marge))
    cands = [(b - a, a, b) for a, b in _vides(proj, 14) if lo < (a + b) // 2 < hi]
    if not cands:
        return None
    _, a, b = max(cands)
    return (boite[axe] + (a + b) // 2)


def couches(cover, meta):
    """L'affiche décomposée : (fond, pochette, [blocs d'encre]).

    Chaque élément rendu est une RGBA de la taille de l'affiche, prête à être
    composée dans l'ordre. Les blocs sortent dans l'ordre de lecture voulu à
    l'écran : tracklist (colonne par colonne), bloc artiste, bas de page.
    """
    aff = posters.poster(cover, meta)
    Wp, Hp = aff.size
    M = int(Wp * 0.055)
    cw = Wp - 2 * M

    fond = posters.blurred_bg(cover, Wp, Hp)
    pochette = cover.resize((cw, cw), Image.LANCZOS)
    base = fond.copy()
    base.paste(pochette, (M, M))

    # Tout ce qui reste entre `base` et l'affiche finie est de l'encre. Le
    # seuil à 10 absorbe le bruit de rééchantillonnage du fond flouté sans
    # manger l'anticrénelage des lettres, qui monte bien plus haut.
    encre = ImageChops.difference(aff, base).convert("L").point(
        lambda v: 255 if v > 10 else 0)

    haut = M + cw + int(Wp * 0.04)            # première ligne sous la pochette
    milieu_x = int(Wp * 0.52)                 # frontière tracklist / bloc droite

    # Gauche : la tracklist, et sous elle le label. Une bande vide les sépare.
    y_label = _plus_grand_vide(encre, (M, haut, milieu_x, Hp), 1, 0.22) or Hp
    # Gauche haut : une ou plusieurs colonnes de titres.
    x_col = _plus_grand_vide(encre, (M, haut, milieu_x, y_label), 0, 0.22)
    # Droite : artiste + titre + palette en haut, genre + signature + dates en
    # bas. Là encore, une vraie respiration entre les deux.
    y_pied = _plus_grand_vide(encre, (milieu_x, haut, Wp, Hp), 1, 0.22) or Hp

    boites = []
    if x_col:
        boites.append((M, haut, x_col, y_label))
        boites.append((x_col, haut, milieu_x, y_label))
    else:
        boites.append((M, haut, milieu_x, y_label))
    boites.append((milieu_x, haut, Wp, y_pied))
    boites.append((milieu_x, y_pied, Wp, Hp))
    boites.append((M, y_label, milieu_x, Hp))

    blocs = []
    for b in boites:
        m = Image.new("L", aff.size, 0)
        m.paste(encre.crop(b), (b[0], b[1]))
        if not m.getbbox():                   # bloc vide (album sans label…)
            continue
        # Un léger flou du masque rattrape le seuillage dur : sans lui, les
        # lettres composées sur le fond flouté portent un liseré crénelé.
        lay = aff.copy().convert("RGBA")
        lay.putalpha(m.filter(ImageFilter.GaussianBlur(0.6)))
        blocs.append(lay)
    return base, blocs


# ---------------------------------------------------------------------------
# Outils d'animation
# ---------------------------------------------------------------------------
def ease(p):
    """Sortie douce : rapide au départ, se pose sans rebond."""
    p = max(0.0, min(1.0, p))
    return 1 - (1 - p) ** 3


def rampe(t, t0, duree):
    return ease((t - t0) / duree) if duree else (1.0 if t >= t0 else 0.0)


def remplir(img, bw, bh):
    """Recadre au centre pour couvrir la boîte, sans déformer (cf. bot.fit_cover)."""
    r = max(bw / img.width, bh / img.height)
    n = img.resize((max(1, round(img.width * r)), max(1, round(img.height * r))),
                   Image.LANCZOS)
    l, t = (n.width - bw) // 2, (n.height - bh) // 2
    return n.crop((l, t, l + bw, t + bh))


def zoom_sur(src, bw, bh, k, cx=0.5, cy=0.5):
    """Recadrage au ratio cible, resserré de `k`, rendu en bw x bh.

    La fenêtre est TOUJOURS prise à la proportion de la sortie avant d'être
    réduite : une pochette carrée cadrée en 9:16 doit être rognée, jamais
    étirée. C'est ce qui permet d'utiliser la même fonction pour la pochette
    (1:1), le mockup (3:4) et l'affiche (3:4) sans les déformer.
    """
    r = bw / bh
    if src.width / src.height > r:
        h0, w0 = src.height, src.height * r
    else:
        w0, h0 = src.width, src.width / r
    cw, ch = w0 / k, h0 / k
    x = (src.width - cw) * cx
    y = (src.height - ch) * cy
    return src.crop((round(x), round(y), round(x + cw), round(y + ch))
                    ).resize((bw, bh), Image.LANCZOS)


def ombre(w, h, rayon=26, opacite=150):
    """Ombre portée douce sous l'affiche : elle la décolle du fond flouté."""
    o = Image.new("RGBA", (w + rayon * 4, h + rayon * 4), (0, 0, 0, 0))
    ImageDraw.Draw(o).rectangle((rayon * 2, rayon * 2 + 8, rayon * 2 + w,
                                 rayon * 2 + h + 8), fill=(0, 0, 0, opacite))
    return o.filter(ImageFilter.GaussianBlur(rayon))


def texte(img, s, taille, y, poids="heavy", couleur=BLANC, alpha=1.0,
          espace=0, ombre=True):
    """Une ligne centrée horizontalement, avec ombre de lisibilité.

    L'ombre n'est pas cosmétique : le texte passe sur des pochettes claires
    comme sur des fonds sombres, et Reels affiche par-dessus ses propres
    surcouches. Sans elle, une accroche disparaît sur un album clair. On la
    coupe (`ombre=False`) pour un texte SOMBRE sur fond clair, où elle ne
    ferait qu'épaissir les lettres d'un halo noir.
    """
    if alpha <= 0.01:
        return
    f = posters.af(poids, taille)
    d = ImageDraw.Draw(img)
    if espace:                                # interlettrage manuel (PIL n'en a pas)
        larg = sum(d.textlength(c, font=f) + espace for c in s) - espace
    else:
        larg = d.textlength(s, font=f)
    x = (img.width - larg) / 2
    a = int(255 * alpha)
    calque = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dc = ImageDraw.Draw(calque)
    passes = ((0, 3, (0, 0, 0), int(a * 0.55)), (0, 0, couleur, a))
    for dx, dy, col, al in (passes if ombre else passes[1:]):
        cx = x
        if espace:
            for c in s:
                dc.text((cx + dx, y + dy), c, font=f, fill=col + (al,))
                cx += dc.textlength(c, font=f) + espace
        else:
            dc.text((x + dx, y + dy), s, font=f, fill=col + (al,))
    img.alpha_composite(calque)


def sous_titre(img, s, alpha, y=1508, taille=40):
    """Sous-titre incrusté, sur une pastille sombre.

    Il n'est pas optionnel : la moitié des lectures se fait sans le son, et la
    pastille garantit la lisibilité aussi bien sur la pochette claire que sur
    le fond flouté. Position calée au-dessus des surcouches de Reels.
    """
    if alpha <= 0.01:
        return
    f = posters.af("heavy", taille)
    d = ImageDraw.Draw(img)
    esp = 3
    larg = sum(d.textlength(c, font=f) + esp for c in s) - esp
    pad_x, pad_y = 34, 20
    x0 = (img.width - larg) / 2 - pad_x
    calque = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dc = ImageDraw.Draw(calque)
    dc.rounded_rectangle((x0, y - pad_y, x0 + larg + 2 * pad_x,
                          y + taille + pad_y), radius=14,
                         fill=(10, 10, 12, int(205 * alpha)))
    cx = (img.width - larg) / 2
    for c in s:
        dc.text((cx, y - taille * 0.14), c, font=f,
                fill=BLANC + (int(255 * alpha),))
        cx += dc.textlength(c, font=f) + esp
    img.alpha_composite(calque)


def pastille_logo(chemin, largeur):
    """Le logo sur une plaque blanche arrondie.

    Le fichier est un lettrage NOIR sur transparent : posé tel quel sur le
    fond sombre du plan final, il disparaît. On ne le recolore pas — un logo
    se montre dans ses couleurs — on lui donne le fond pour lequel il est fait.
    """
    lg = Image.open(chemin).convert("RGBA")
    h = round(largeur * lg.height / lg.width)
    lg = lg.resize((largeur, h), Image.LANCZOS)
    mx, my = round(largeur * 0.085), round(h * 0.42)
    plaque = Image.new("RGBA", (largeur + 2 * mx, h + 2 * my), (0, 0, 0, 0))
    ImageDraw.Draw(plaque).rounded_rectangle(
        (0, 0, plaque.width - 1, plaque.height - 1),
        radius=round(plaque.height * 0.22), fill=(250, 250, 250, 255))
    plaque.alpha_composite(lg, (mx, my))
    return plaque


def voile(img, force):
    """Assombrit toute l'image (transitions, lisibilité d'un bloc de texte)."""
    if force <= 0:
        return img
    v = Image.new("RGBA", img.size, (0, 0, 0, int(255 * min(1.0, force))))
    img.alpha_composite(v)
    return img


# ---------------------------------------------------------------------------
# Montage
# ---------------------------------------------------------------------------
# Toutes les durées sont des multiples de 0,6 s, soit un temps à 100 BPM :
# c'est la grille de `lit_sonore.py`. Chaque transition tombe donc sur un
# temps fort, et les blocs de l'affiche sur la pulsation. Modifier une durée
# ici sans rester sur la grille désynchronise le son de l'image.
SEQ = [("hook", 1.8), ("pose", 0.6), ("build", 5.4), ("fondu", 0.6),
       ("cadre", 1.8), ("mur", 3.0), ("cta", 1.8)]

# Écart entre deux blocs de l'affiche, en secondes. 0,6 s = un temps à 100 BPM,
# 0,3 s = un demi-temps. Le montage `mix.py` prend le demi-temps : l'affiche y
# arrive après un plan filmé, elle doit se construire d'un trait plutôt que
# poser chaque bloc.
PAS_BLOCS = 0.6


def bornes():
    t, out = 0.0, {}
    for nom, d in SEQ:
        out[nom] = (t, t + d)
        t += d
    return out, t


def preparer(album, grille):
    """Tous les plans du montage, calculés une fois.

    Extrait de `rendre` pour que `mix.py` puisse composer les mêmes plans dans
    un autre ordre sans dupliquer un octet de préparation. Rend un dictionnaire
    plutôt qu'un tuple : le montage n'a pas à connaître l'ordre des éléments,
    et en ajouter un plus tard ne casse pas les appels existants.
    """
    cover, meta = charger(album)
    base, blocs = couches(cover, meta)
    aff_pleine = base.copy().convert("RGBA")
    for b in blocs:
        aff_pleine.alpha_composite(b)

    # Le fond du cadre 9:16 est tiré 12 % trop grand : la marge sert au
    # micro-travelling, qui donne la profondeur sans rien demander de plus.
    FOND = posters.blurred_bg(cover, round(W * 1.12), round(H * 1.12), 0.70
                              ).convert("RGBA")
    BASE_S = base.resize((AFF_W, AFF_H), Image.LANCZOS).convert("RGBA")
    BLOCS_S = [b.resize((AFF_W, AFF_H), Image.LANCZOS) for b in blocs]
    OMBRE = ombre(AFF_W, AFF_H)
    AFF_S = aff_pleine.resize((AFF_W, AFF_H), Image.LANCZOS)

    # Mise en scène : l'affiche encadrée, vue de trois quarts. L'homographie
    # coûte plusieurs secondes, on la calcule une seule fois et le mouvement
    # de caméra se fait ensuite par recadrage.
    CADRE = mb.inserer(aff_pleine.convert("RGB"), "mockup_side.png").convert("RGB")
    PASTILLE = pastille_logo(LOGO, 620) if LOGO.exists() else None
    if PASTILLE is None:
        print(f"  (logo absent : {LOGO} — plan final sans marque)")

    # Mur d'affiches : 3 bandes verticales pré-composées, que l'on fait
    # défiler à trois vitesses. C'est là que la parallaxe se voit vraiment,
    # et c'est aussi ce qui montre la profondeur du catalogue.
    COL_W, COL_GAP = 322, 27
    vignettes = []
    for aid in grille:
        c, m = charger(aid)
        vignettes.append(posters.poster(c, m).resize(
            (COL_W, round(COL_W * 4 / 3)), Image.LANCZOS).convert("RGB"))
    vignettes.append(AFF_S.convert("RGB").resize(
        (COL_W, round(COL_W * 4 / 3)), Image.LANCZOS))
    BANDES = []
    for i in range(3):
        ordre = [vignettes[(i * 3 + k) % len(vignettes)] for k in range(5)]
        vh = ordre[0].height + COL_GAP
        bande = Image.new("RGB", (COL_W, vh * len(ordre)), (10, 10, 12))
        for k, v in enumerate(ordre):
            bande.paste(v, (0, k * vh))
        BANDES.append(bande)

    return {"cover": cover, "meta": meta, "affiche": aff_pleine,
            "FOND": FOND, "BASE_S": BASE_S, "BLOCS_S": BLOCS_S, "OMBRE": OMBRE,
            "AFF_S": AFF_S, "CADRE": CADRE, "PASTILLE": PASTILLE,
            "BANDES": BANDES, "COL_W": COL_W, "COL_GAP": COL_GAP}


def image(t, B, A):
    """L'image de l'instant `t`, à partir des plans préparés par `preparer`."""
    return _image(t, B, A["FOND"], A["cover"], A["meta"], A["BASE_S"],
                  A["BLOCS_S"], A["OMBRE"], A["AFF_S"], A["CADRE"],
                  A["BANDES"], A["COL_W"], A["COL_GAP"], A["PASTILLE"])


def rendre(album, grille, sortie, secondes=None, audio=None):
    B, TOTAL = bornes()
    if secondes:
        TOTAL = secondes
    A = preparer(album, grille)
    meta = A["meta"]

    nb = int(TOTAL * FPS)
    # Sans bande-son fournie, on écrit quand même une piste silencieuse : un
    # mp4 sans flux audio se fait refuser par plusieurs outils de publication,
    # et Reels le traite comme une vidéo muette plutôt que comme une erreur.
    if audio:
        src_a = ["-i", str(audio)]
        # 0,25 s de montée, 0,6 s de descente : le montage se termine sur le
        # CTA, une coupe franche de la musique s'y entend.
        filtre_a = ["-af", f"afade=t=in:st=0:d=0.25,"
                           f"afade=t=out:st={TOTAL - 0.6:.2f}:d=0.6"]
    else:
        src_a = ["-f", "lavfi", "-i",
                 "anullsrc=channel_layout=stereo:sample_rate=44100"]
        filtre_a = []
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", *src_a,
         "-c:v", "libx264", "-preset", "slow", "-crf", "19",
         "-profile:v", "high", "-pix_fmt", "yuv420p",
         *filtre_a, "-c:a", "aac", "-b:a", "192k", "-shortest",
         "-movflags", "+faststart", str(sortie)],
        stdin=subprocess.PIPE)

    for n in range(nb):
        t = n / FPS
        img = image(t, B, A)
        ff.stdin.write(img.convert("RGB").tobytes())
        if n % 30 == 0:
            print(f"  {t:5.1f}s / {TOTAL:.1f}s", flush=True)
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit("ffmpeg a échoué")
    return meta


def _image(t, B, FOND, cover, meta, BASE_S, BLOCS_S, OMBRE, AFF_S, CADRE,
           BANDES, COL_W, COL_GAP, PASTILLE=None):
    """Compose l'image de l'instant `t`."""
    img = Image.new("RGBA", (W, H), (8, 8, 10, 255))

    # ---- 1 & 2. HOOK, POSE, BUILD : un seul plan, sans coupe -------------
    # La pochette n'est JAMAIS recadrée ni agrandie : Deezer plafonne à
    # 1200 px et un gros plan la pixellisait. Elle est montrée entière, à
    # 960 px de large — c'est-à-dire réduite, donc nette — puis elle rétrécit
    # jusqu'à sa place sur le papier. Le mouvement est le hook, pas le zoom.
    # Un montage peut supprimer la construction en mettant hook/pose/build à
    # zéro (`mix.py` le fait pour enchaîner directement sur la mise en scène).
    # Sans cette garde, les trois phases vides se replieraient sur l'instant 0
    # et repeindraient un fond par-dessus le plan précédent.
    if B["build"][1] > B["hook"][0] and t < B["fondu"][1]:
        pose = rampe(t, B["pose"][0], B["pose"][1] - B["pose"][0])
        # Travelling continu du fond, du premier au dernier frame du build :
        # il n'y a plus de raccord à masquer entre l'accroche et la démo.
        av = t / max(0.1, B["fondu"][1])
        dx = (FOND.width - W) * (0.30 + 0.34 * av)
        dy = (FOND.height - H) * (0.68 - 0.34 * av)
        img.alpha_composite(FOND.crop((round(dx), round(dy),
                                       round(dx) + W, round(dy) + H)))

        # Entrée : la pochette descend de 70 px en fondu. Une image fixe au
        # frame 1 est ce qui se fait dépasser ; 0,5 s de mouvement suffit.
        entree = rampe(t, 0.0, 0.5)
        k = ease(pose)
        # dérive lente pendant l'accroche (960 -> 930), puis rétrécissement
        depart = HOOK_W - 30 * min(1.0, t / max(0.1, B["hook"][1]))
        pw = ph = round(depart + (POCH_S - depart) * k)
        px = round((W - pw) / 2 * (1 - k) + (AFF_X + MARGE_S) * k)
        py = round((HOOK_Y + (1 - entree) * 70) * (1 - k)
                   + (AFF_Y + MARGE_S) * k)

        for d0, d1, _dit, ecrit in PHRASES:
            sous_titre(img, ecrit,
                       rampe(t, d0, 0.22) * (1 - rampe(t, d1 - 0.22, 0.22)))

        plaque = Image.new("RGBA", (AFF_W, AFF_H), (0, 0, 0, 0))
        if pose > 0.55:                       # le papier apparaît sous la pochette
            a = (pose - 0.55) / 0.45
            b = BASE_S.copy()
            b.putalpha(int(255 * a))
            plaque.alpha_composite(b)

        # Un bloc par TEMPS (0,6 s à 100 BPM) : chacun se pose exactement sur
        # une frappe du lit sonore. L'animation dure un peu moins qu'un temps
        # pour que le bloc soit arrivé quand le coup tombe.
        deb = B["build"][0]
        for i, bl in enumerate(BLOCS_S):
            a = rampe(t, deb + i * PAS_BLOCS, min(0.5, PAS_BLOCS * 1.4))
            if a <= 0.01:
                continue
            lay = bl if a >= 0.999 else bl.copy()
            if a < 0.999:
                lay.putalpha(lay.getchannel("A").point(lambda v: int(v * a)))
            plaque.alpha_composite(lay, (0, round(28 * (1 - a))))

        if pose > 0.05:                       # l'ombre suit le papier
            img.alpha_composite(OMBRE, (AFF_X - OMBRE.width // 2 + AFF_W // 2,
                                        AFF_Y - OMBRE.height // 2 + AFF_H // 2))
        img.alpha_composite(plaque, (AFF_X, AFF_Y))
        poch = remplir(cover.convert("RGBA"), pw, ph)
        if entree < 0.999:
            poch.putalpha(poch.getchannel("A").point(
                lambda v: int(v * entree)))
        img.alpha_composite(poch, (px, py))

        # Le bas de l'écran appartient aux surcouches de Reels (légende,
        # boutons) : toute l'information utile reste au-dessus de 80 % de la
        # hauteur. L'accroche du build passe donc AU-DESSUS de l'affiche.
        fin = rampe(t, B["build"][1] - 1.7, 0.5)
        texte(img, "TRACKLIST COMPLÈTE · IMPRESSION MUSÉE", 30, 186, "demi",
              GRIS, fin, 5)

    # ---- 3. CADRE : la mise en scène produit ----------------------------
    if B["fondu"][0] <= t < B["mur"][0]:
        p = (t - B["fondu"][0]) / (B["cadre"][1] - B["fondu"][0])
        vue = zoom_sur(CADRE.convert("RGBA"), W, H, 1.32 - 0.16 * p, 0.5, 0.46)
        vue.putalpha(int(255 * min(1.0, (t - B["fondu"][0]) / 0.4)))
        img.alpha_composite(vue)
        a = rampe(t, B["cadre"][0], 0.4) * (1 - rampe(t, B["cadre"][1] - 0.3, 0.3))
        voile(img, 0.22 * a)
        texte(img, "ENCADRÉE, PRÊTE À ACCROCHER", 44, 1306, "heavy", BLANC, a, 3)
        texte(img, "30×40 · 40×50 · 50×70", 32, 1398, "demi", GRIS, a, 6)

    # ---- 4. MUR : trois colonnes en parallaxe ---------------------------
    if B["mur"][0] <= t < B["cta"][0]:
        p = (t - B["mur"][0]) / (B["mur"][1] - B["mur"][0])
        img.paste((10, 10, 12), (0, 0, W, H))
        x = (W - (3 * COL_W + 2 * COL_GAP)) // 2
        for i, bande in enumerate(BANDES):
            # trois vitesses : c'est l'écart entre elles qui fait la profondeur
            v = (0.62, 1.0, 0.80)[i]
            dy = (bande.height - H) * (p * v * 0.55 + i * 0.06) % max(1, bande.height - H)
            img.alpha_composite(bande.crop((0, round(dy), COL_W, round(dy) + H)
                                           ).convert("RGBA"), (x, 0))
            x += COL_W + COL_GAP
        voile(img, 0.52)
        a = rampe(t, B["mur"][0] + 0.15, 0.45) * (1 - rampe(t, B["mur"][1] - 0.35, 0.35))
        texte(img, "PLUS DE 6 000 ARTISTES", 60, 838, "heavy", BLANC, a, 3)
        texte(img, "ton album est dedans", 42, 928, "demi", GRIS, a, 2)

    # ---- 5. CTA ---------------------------------------------------------
    if t >= B["cta"][0]:
        p = rampe(t, B["cta"][0], 0.35)
        fin = Image.new("RGBA", (W, H), (12, 12, 14, 255))
        fin.alpha_composite(zoom_sur(FOND, W, H, 1.10, 0.5, 0.35))
        voile(fin, 0.42)
        fin.putalpha(int(255 * p))
        img.alpha_composite(fin)
        texte(img, "AFFICHES ENCADRÉES", 32, 762, "demi", GRIS, p, 9)
        if PASTILLE is not None:
            lg = PASTILLE if p >= 0.999 else PASTILLE.copy()
            if p < 0.999:
                lg.putalpha(lg.getchannel("A").point(lambda v: int(v * p)))
            img.alpha_composite(lg, ((W - lg.width) // 2, 846))
        texte(img, "lemursonore.fr", 40, 1006, "demi", (16, 16, 18), p, 3,
              ombre=False)
    return img


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--album", type=int, default=1262014,
                    help="album Deezer principal (défaut : Nirvana · Nevermind)")
    ap.add_argument("--grille", default="6575789,7573078,12114240,12047952,6237061,119282",
                    help="albums du mur d'affiches, séparés par des virgules")
    ap.add_argument("--sortie", default=str(Path.home() / "Desktop" / "reel-nirvana.mp4"))
    ap.add_argument("--secondes", type=float, default=None,
                    help="tronque le rendu (mise au point)")
    ap.add_argument("--audio", default=None,
                    help="bande-son à poser sous le montage (fichier local)")
    a = ap.parse_args()

    def _abs(v):
        """Résout un chemin de la ligne de commande depuis le dossier d'appel."""
        q = Path(v).expanduser()
        return q if q.is_absolute() else (CWD0 / q).resolve()

    audio = _abs(a.audio) if a.audio else None
    if audio and not audio.exists():
        raise SystemExit(f"bande-son introuvable : {audio}")
    meta = rendre(a.album, [int(x) for x in a.grille.split(",")],
                  _abs(a.sortie), a.secondes, audio)
    print(f"OK -> {a.sortie}  |  {meta['artist']} · {meta['title']}")
