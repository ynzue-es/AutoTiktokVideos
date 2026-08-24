#!/usr/bin/env python3
"""Montage complet : plan UGC généré + décomposition de l'affiche + marque.

Le plan d'ouverture vient d'ElevenLabs (Veo 3.1 Fast) : une personne debout à
côté d'un cadre VIDE, caméra fixe. L'affiche du catalogue y est incrustée ici,
et le son d'origine est jeté — le modèle lui a fait dire que le cadre était
vide, ce qui était exact et inutilisable.

Ce que le montage enchaîne
--------------------------
     0,0 -  2,4   UGC, plan large, sous-titre
     2,4 -  4,2   punch-in sur le cadre
     4,2 -  6,6   retour au large, puis fondu
     6,6 - 13,8   l'affiche se reconstruit pièce par pièce
    13,8 - 16,2   la même, encadrée de trois quarts
    16,2 - 19,2   le mur d'affiches en parallaxe
    19,2 - 21,0   la marque

Pourquoi l'incrustation est calculée UNE fois
---------------------------------------------
La caméra est fixe et la personne ne passe jamais devant le cadre : la zone du
cadre est donc rigoureusement identique sur les 192 images. On y pose l'affiche
une seule fois, avec l'ombre du feuillage reprise du mur, et on recolle ce
morceau sur chaque image. C'est exact, et c'est instantané.

    ScriptsShopify/.venv/bin/python render/reels/mix.py --ugc <plan.mp4>
"""

import argparse
import subprocess
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

import numpy as np                        # noqa: E402
import reel_affiche as R                  # noqa: E402
from PIL import Image, ImageFilter    # noqa: E402
import mockup_biais as mb                 # noqa: E402
from suivi_cadre import coins_droites, _bbox_sombre  # noqa: E402

W, H, FPS = R.W, R.H, R.FPS

# Les bornes se lisent dans la TRANSCRIPTION du plan, jamais à l'oreille : la
# réplique va de 0,86 à 6,98 s, donc on garde le plan entier et le son s'arrête
# à 7,4 s, dans le silence qui suit. Sur un plan précédent la comédienne avait
# enchaîné une seconde phrase inventée à 4,1 s, et c'est la transcription qui a
# montré où couper pour la faire disparaître. Transcrire AVANT de monter.
UGC_FIN = 7.8
FONDU = 0.6                               # fondu croisé vers la suite
PUNCH = (3.0, 5.0)                        # bornes du plan serré
VOIX_FIN = 7.4                            # le son du plan s'arrête là

# Débord de l'affiche sous la feuillure, en pixels de sortie. Un relevé calé
# pile sur le bord intérieur laisse une bande de papier blanc visible du côté
# où la moulure se voit en épaisseur — c'est le défaut constaté sur le premier
# montage du plan 02. Dans un vrai encadrement le papier passe SOUS la
# feuillure : on dilate donc le quadrilatère de quelques pixels, ce qui
# supprime la bande sans manger la moulure.
DEBORD = 11

# La séquence qui suit. Toujours sur la grille de 0,6 s (100 BPM), pour que
# les blocs de l'affiche tombent sur les frappes du lit sonore.
# La construction de l'affiche est retirée : le plan filmé porte déjà l'idée,
# et l'enchaîner sur une démonstration de mise en page diluait la fin. On passe
# directement du mur à la mise en scène de trois quarts. Les trois premières
# durées restent déclarées à zéro parce que `_image` attend leurs bornes.
SEQ_MIX = [("hook", 0.0), ("pose", 0.0), ("build", 0.0), ("fondu", 0.6),
           ("cadre", 1.8), ("mur", 3.0), ("cta", 1.8)]
PAS_BLOCS = 0.3

# Un seul sous-titre, sur la phrase réellement prononcée. Au-delà, plus
# personne ne parle : incruster du texte sur la partie muette ferait lire un
# discours qui n'existe pas.
# Sous-titres calés sur les mots réellement prononcés (relevés par
# faster-whisper), coupés en deux au silence qui sépare les deux propositions.
SOUS_TITRES = [(0.70, 4.40, "J'AI ACCROCHÉ MON ALBUM PRÉFÉRÉ ICI"),
               (4.95, 7.45, "ÇA CHANGE TOUTE LA PIÈCE")]


def quad_du_plan(chemin, echelle):
    """Relève le cadre vide, et le rend à l'échelle du montage.

    Rend UN QUADRILATÈRE PAR IMAGE. Un relevé fixe ne suffit pas : malgré la
    consigne de caméra bloquée, le cadre du plan 02 dérive de onze pixels vers
    la gauche pendant les six premières secondes. Une position figée — même
    prise là où l'affiche paraît la mieux calée — laisse alors une bande de
    papier blanc à l'autre bout du plan. C'est le défaut constaté le
    24/08/2026, et il ne se corrige qu'en suivant.

    Les coins viennent de `coins_droites`, qui ajuste une droite sur chaque
    bord intérieur. La version qui prenait simplement l'enveloppe des pixels
    sombres donnait un cadre 24 px trop large : l'affiche montait alors sur la
    moulure à droite et en bas.
    """
    lu = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(chemin),
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        check=True, capture_output=True).stdout
    tailles = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(chemin)],
        check=True, capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(tailles[0]), int(tailles[1])
    n = len(lu) // (w * h)
    g = np.frombuffer(lu, np.uint8).reshape(n, h, w)

    # Première image : la personne n'est pas encore entrée, le cadre est seul.
    ref = _bbox_sombre(g[0], (int(w * 0.38), 0, w, int(h * 0.68)), 95)
    if ref is None:
        raise SystemExit("aucun cadre sombre trouvé sur la première image")
    m = 45
    roi = (max(0, ref[0] - m), max(0, ref[1] - m),
           min(w, ref[2] + m), min(h, ref[3] + m))
    releves = [q for q in (coins_droites(g[i], roi) for i in range(n))
               if q is not None]
    if len(releves) < 10:
        raise SystemExit(f"cadre trop rarement détecté ({len(releves)}/{n})")
    # Trajectoire complète, une entrée par image. Les relevés manquants ou
    # aberrants sont remplacés par la médiane globale AVANT lissage : un coin
    # qui saute de 80 px (la comédienne passe près du cadre et sa chevelure
    # entre dans la zone) tirerait la moyenne glissante sur un demi-second.
    tous = [coins_droites(g[i], roi) for i in range(n)]
    med = np.median(np.array(releves, float), axis=0)
    seuil = 25.0
    propres = []
    rejets = 0
    for q in tous:
        a = np.array(q, float) if q is not None else None
        if a is None or np.abs(a - med).max() > seuil:
            a = med
            rejets += 1
        propres.append(a)

    # Lissage temporel : la dérive réelle est lente (une dizaine de pixels sur
    # tout le plan), le bruit de détection est rapide. Une moyenne glissante
    # garde la première et supprime le second.
    a = np.array(propres)
    fen, d = 11, 5
    lisses = np.empty_like(a)
    for i in range(n):
        lisses[i] = a[max(0, i - d):min(n, i + d + 1)].mean(axis=0)

    quads = [tuple(map(tuple, np.array(mb._decaler(f * echelle, DEBORD), float)))
             for f in lisses]
    derive = np.abs(lisses[0] - lisses[-1]).max()
    print(f"cadre relevé sur {len(releves)}/{n} images "
          f"({rejets} remplacés), dérive {derive:.1f} px, "
          f"débord {DEBORD} px")
    return quads, n


def eclairage(chemin, quad):
    """La lumière du mur, prête à multiplier l'affiche.

    Le mur porte une diagonale de soleil et l'ombre d'un feuillage. Sans les
    reporter sur le papier, l'affiche a l'air d'un autocollant posé sur la
    photo. On divise l'image par son blanc de référence, on floute largement
    pour ne garder que les variations lentes — l'ombre dure que la moulure
    projette sur le papier éteindrait le bord de l'affiche — et on normalise
    sur l'intérieur du cadre.

    La carte est calculée UNE fois : la lumière ne bouge pas d'une image à
    l'autre, seul le cadre dérive, et de onze pixels.
    """
    from io import BytesIO
    png = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(chemin), "-vf",
         f"scale={W}:{H}:flags=lanczos", "-frames:v", "1",
         "-f", "image2pipe", "-vcodec", "png", "-"],
        check=True, capture_output=True).stdout
    im = Image.open(BytesIO(png)).convert("RGB")
    px = np.asarray(im, np.float32)
    m = mb._masque((W, H), mb._decaler(quad, -mb.MARGE))
    blanc = np.percentile(px[m > 0.99], mb.BLANC, axis=0)
    rel = np.clip(px / np.maximum(blanc, 1.0), 0.0, 1.0)
    large = np.hypot(*(np.array(quad[1]) - np.array(quad[0])))
    lisse = Image.fromarray((rel * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(float(max(8.0, large / 40))))
    ecl = np.asarray(lisse, np.float32) / 255.0
    dedans = m > 0.99
    if dedans.any():
        ecl = ecl / max(float(np.median(ecl[dedans])), 1e-3)
    return np.clip(ecl, 0.0, 1.12)


def poser(affiche, quad, ecl):
    """L'affiche projetée dans `quad`, et son masque — pour UNE image.

    L'affiche est d'abord ramenée par LANCZOS à la taille qu'elle occupera :
    `transform` n'échantillonne que 4×4 pixels autour du point lu, elle
    sauterait neuf pixels sur dix en réduisant 1800 px d'un coup.
    """
    coins = np.array(quad, float)
    large = (np.hypot(*(coins[1] - coins[0]))
             + np.hypot(*(coins[2] - coins[3]))) / 2
    haute = (np.hypot(*(coins[3] - coins[0]))
             + np.hypot(*(coins[2] - coins[1]))) / 2
    taille = (max(1, round(large)), max(1, round(haute)))
    art = affiche.resize(taille, Image.LANCZOS).transform(
        (W, H), Image.PERSPECTIVE, mb._homographie(quad, *taille),
        Image.BICUBIC)
    m = mb._masque((W, H), quad)[..., None].astype(np.float32)
    return np.asarray(art, np.float32) * ecl, m


def flux_ugc(chemin):
    """Les images du plan, rééchantillonnées au format du montage."""
    return subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(chemin),
         "-vf", f"fps={FPS},scale={W}:{H}:flags=lanczos",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        # stdin coupé : ffmpeg le lit par défaut. Lancé depuis une boucle
        # `while read` du shell, il avale les lignes du fichier que la boucle
        # est en train de parcourir, et un rendu sur deux part avec les
        # arguments du suivant.
        stdin=subprocess.DEVNULL)


def cadrer(img, k, cx=0.5, cy=0.5):
    """Recadrage resserré de `k`, au format de sortie."""
    if k <= 1.001:
        return img
    cw, ch = img.width / k, img.height / k
    x, y = (img.width - cw) * cx, (img.height - ch) * cy
    return img.crop((round(x), round(y), round(x + cw), round(y + ch))
                    ).resize((W, H), Image.LANCZOS)


def rendre(ugc, album, grille, sortie, audio=None):
    R.SEQ = SEQ_MIX                       # le montage impose sa propre séquence
    R.PAS_BLOCS = PAS_BLOCS
    B, DUREE_SUITE = R.bornes()
    TOTAL = UGC_FIN - FONDU + DUREE_SUITE

    # Les sous-titres du reel autonome accompagnaient sa voix off. Ici la seule
    # parole est celle du plan filmé, sur les quatre premières secondes : après
    # elle, l'image se suffit et tout texte incrusté serait un commentaire.
    R.PHRASES = []
    R.PAS_BLOCS = PAS_BLOCS

    A = R.preparer(album, grille)
    quads, _ = quad_du_plan(ugc, W / 720)
    ecl = eclairage(ugc, quads[0])
    affiche = A["affiche"].convert("RGB")

    # Centre du cadre, en fractions : c'est la cible du punch-in. Pris au
    # milieu du plan, là où le cadre a fini de dériver.
    milieu = quads[len(quads) // 2]
    xs = [q[0] for q in milieu]
    ys = [q[1] for q in milieu]
    cx, cy = (min(xs) + max(xs)) / 2 / W, (min(ys) + max(ys)) / 2 / H

    flux = flux_ugc(ugc)
    octets = W * H * 3
    nb = int(TOTAL * FPS)
    # Bande-son en deux temps : la voix du plan telle qu'elle a été générée,
    # puis le lit sonore qui prend le relais quand elle a fini sa phrase. Les
    # fondus se chevauchent d'un cheveu pour qu'il n'y ait pas de trou.
    #
    # `normalize=0` sur amix : sans lui, ffmpeg divise chaque entrée par leur
    # nombre et la voix ressort deux fois trop basse — alors qu'ici les deux
    # sources ne se superposent presque pas.
    entrees = ["-i", str(ugc)]
    if audio:
        entrees += ["-i", str(audio)]
        filtre = (
            f"[1:a]atrim=0:{VOIX_FIN},asetpts=PTS-STARTPTS,"
            f"afade=t=out:st={VOIX_FIN - 0.7:.2f}:d=0.7[voix];"
            f"[2:a]afade=t=in:st={VOIX_FIN - 0.9:.2f}:d=0.9,"
            f"afade=t=out:st={TOTAL - 0.8:.2f}:d=0.8[lit];"
            f"[voix][lit]amix=inputs=2:duration=longest:normalize=0[a]")
    else:
        filtre = (f"[1:a]atrim=0:{VOIX_FIN},asetpts=PTS-STARTPTS,"
                  f"afade=t=out:st={VOIX_FIN - 0.7:.2f}:d=0.7[a]")
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-"] + entrees
        + ["-filter_complex", filtre, "-map", "0:v", "-map", "[a]",
           "-c:v", "libx264", "-preset", "slow", "-crf", "19",
           "-profile:v", "high", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", str(sortie)],
        stdin=subprocess.PIPE)

    derniere = None
    for i in range(nb):
        t = i / FPS
        img = None

        if t < UGC_FIN:
            brut = flux.stdout.read(octets)
            if len(brut) == octets:
                a = np.frombuffer(brut, np.uint8).reshape(H, W, 3).astype(np.float32)
                # L'affiche est reprojetée à CHAQUE image : le cadre dérive, et
                # une incrustation calculée une fois laisserait une bande de
                # papier blanc partout où le cadre n'est plus à sa position
                # moyenne.
                art, m = poser(affiche, quads[min(i, len(quads) - 1)], ecl)
                a = a * (1.0 - m) + art * m
                derniere = Image.fromarray(
                    np.clip(a, 0, 255).astype(np.uint8), "RGB")
            if derniere is not None:
                # Punch-in : coupe franche sur le cadre, puis desserrage lent.
                # Un zoom continu depuis le plan large ferait « caméra qui
                # zoome » ; la coupe fait « deuxième plan », ce qui est le
                # rythme d'un vrai montage.
                if PUNCH[0] <= t < PUNCH[1]:
                    p = (t - PUNCH[0]) / (PUNCH[1] - PUNCH[0])
                    img = cadrer(derniere, 1.62 - 0.18 * p, cx, cy)
                else:
                    img = cadrer(derniere, 1.0)
                img = img.convert("RGBA")
                for d0, d1, txt in SOUS_TITRES:
                    R.sous_titre(img, txt,
                                 R.rampe(t, d0, 0.22)
                                 * (1 - R.rampe(t, d1 - 0.22, 0.22)),
                                 y=1470, taille=36)

        if t >= UGC_FIN - FONDU:
            suite = R.image(t - (UGC_FIN - FONDU), B, A)
            if img is None:
                img = suite
            else:
                # fondu croisé : la suite monte pendant que l'UGC reste
                p = (t - (UGC_FIN - FONDU)) / FONDU
                suite.putalpha(int(255 * min(1.0, p)))
                img.alpha_composite(suite)

        ff.stdin.write(img.convert("RGB").tobytes())
        if i % 30 == 0:
            print(f"  {t:5.1f}s / {TOTAL:.1f}s", flush=True)

    ff.stdin.close()
    # Le plan dure 8 s et le montage n'en lit que 6,6 : ffmpeg a encore des
    # images à écrire dans un tuyau que l'on referme. On l'arrête avant, sinon
    # il signale un « broken pipe » qui n'est pas une erreur mais qui la
    # ressemble assez pour faire perdre du temps à la prochaine lecture.
    flux.terminate()
    flux.stdout.close()
    flux.wait()
    if ff.wait() != 0:
        raise SystemExit("ffmpeg a échoué")
    print(f"OK -> {sortie}  |  {A['meta']['artist']} · {A['meta']['title']}")
    return TOTAL


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ugc", required=True, help="le plan généré (mp4)")
    ap.add_argument("--album", type=int, default=1262014)
    ap.add_argument("--grille",
                    default="6575789,7573078,12114240,12047952,6237061,119282")
    ap.add_argument("--audio", default=None)
    ap.add_argument("--sortie",
                    default=str(Path.home() / "Desktop" / "reel-ugc-nirvana.mp4"))
    a = ap.parse_args()
    cwd0 = R.CWD0

    def _abs(v):
        q = Path(v).expanduser()
        return q if q.is_absolute() else (cwd0 / q).resolve()

    rendre(_abs(a.ugc), a.album, [int(x) for x in a.grille.split(",")],
           _abs(a.sortie), _abs(a.audio) if a.audio else None)
