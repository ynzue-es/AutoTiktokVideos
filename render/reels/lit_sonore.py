#!/usr/bin/env python3
"""Lit sonore original pour le reel, synthétisé de zéro.

Pourquoi le fabriquer plutôt que d'en prendre un
------------------------------------------------
La vidéo part en publicité payante : un master du commerce s'y fait bloquer
par Meta Rights Manager, et une piste de bibliothèque demande une licence et
un compte. Ici tout est calculé à partir d'ondes, donc rien à créditer, rien à
renouveler, et surtout : le TEMPO est connu du script vidéo, donc les blocs de
l'affiche tombent exactement sur les temps.

Ce n'est pas une composition, c'est une texture : une nappe d'accords, une
pulsation grave, un souffle. Elle tient sa place sous une voix off et ne
cherche pas à exister sans l'image.

Structure (100 BPM, 0,6 s par temps — la grille du montage)
    0,0 - 2,4   nappe seule, elle monte pendant l'accroche
    2,4 - 7,8   pulsation sur chaque temps : un coup par bloc qui tombe
    7,8 - 8,4   impact, la mise en scène arrive
    8,4 - 13,2  la texture s'ouvre, le mur d'affiches défile
   13,2 - 15,0  tout retombe sous le logo

    .venv/bin/python render/reels/lit_sonore.py --sortie lit.wav
"""

import argparse
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

SR = 44100
BPM = 100.0
TEMPS = 60.0 / BPM                       # 0,6 s — la maille de tout le montage

# La ligne d'accords, en fréquences de fondamentale. Am - F - C - G : la marche
# la plus banale du rock, et c'est très bien ainsi — elle doit passer inaperçue.
ACCORDS = [
    (110.00, 130.81, 164.81),            # Am
    (87.31, 130.81, 174.61),             # F
    (130.81, 164.81, 196.00),            # C
    (98.00, 123.47, 196.00),             # G
]


def _env(n, attaque, chute, tenue=0.0):
    """Enveloppe attaque / tenue / chute exponentielle, en échantillons."""
    a = max(1, int(attaque * SR))
    t = int(tenue * SR)
    c = max(1, int(chute * SR))
    e = np.zeros(n)
    e[:min(a, n)] = np.linspace(0, 1, a)[:min(a, n)]
    if a < n:
        e[a:min(a + t, n)] = 1.0
    d = a + t
    if d < n:
        reste = min(c, n - d)
        e[d:d + reste] = np.exp(-np.linspace(0, 5, c))[:reste]
    return e


def _passe_bas(x, coupure):
    """Filtre à un pôle. Suffisant : on ne cherche qu'à retirer l'aigreur des
    dents de scie, pas à sculpter un timbre."""
    a = np.exp(-2 * np.pi * coupure / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def _scie(freq, n, detune=0.006):
    """Deux dents de scie désaccordées : le battement fait toute l'épaisseur."""
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k, f in enumerate((freq * (1 - detune), freq * (1 + detune))):
        ph = (t * f) % 1.0
        out += (2 * ph - 1) * (0.5 if k else 0.5)
    return out / 2


def nappe(duree):
    """Le tapis d'accords, une mesure de 4 temps par accord."""
    n = int(duree * SR)
    out = np.zeros(n)
    mesure = 4 * TEMPS
    for i in range(int(np.ceil(duree / mesure))):
        d0 = int(i * mesure * SR)
        long = min(int(mesure * SR * 1.35), n - d0)   # les accords se chevauchent
        if long <= 0:
            break
        acc = ACCORDS[i % len(ACCORDS)]
        v = np.zeros(long)
        for j, f in enumerate(acc):
            v += _scie(f * (2 if j else 1), long) * (0.55 if j == 0 else 0.32)
        v *= _env(long, 0.35, mesure * 0.9, mesure * 0.25)
        out[d0:d0 + long] += v
    out = _passe_bas(out, 900)
    # respiration lente : sans elle la nappe est un bourdon, avec elle on la
    # prend pour un instrument tenu
    t = np.arange(n) / SR
    return out * (0.85 + 0.15 * np.sin(2 * np.pi * 0.18 * t))


def frappe(out, t0, gain=1.0):
    """Grosse caisse : un balayage de hauteur, comme une peau tendue."""
    d0 = int(t0 * SR)
    n = min(int(0.30 * SR), len(out) - d0)
    if n <= 0:
        return
    t = np.arange(n) / SR
    f = 48 + 95 * np.exp(-t * 32)        # 143 Hz -> 48 Hz en 30 ms
    out[d0:d0 + n] += np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.002, 0.26) * gain


def souffle(out, t0, gain=1.0, duree=0.05):
    """Bruit filtré : le grain qui empêche le tout de sonner synthétique."""
    d0 = int(t0 * SR)
    n = min(int(duree * SR), len(out) - d0)
    if n <= 0:
        return
    b = np.random.default_rng(int(t0 * 1000)).normal(0, 1, n)
    b = b - _passe_bas(b, 4000)          # passe-haut = signal moins ses graves
    out[d0:d0 + n] += b * _env(n, 0.001, duree) * 0.22 * gain


def impact(out, t0, gain=1.0):
    """L'accent des transitions : une frappe, plus une longue traîne de bruit."""
    frappe(out, t0, gain * 1.25)
    souffle(out, t0, gain * 2.2, duree=1.1)


def construire(duree, jalons, avec_voix=True):
    n = int(duree * SR)
    mix = nappe(duree) * 0.34

    # Pulsation : elle démarre avec la construction de l'affiche et s'arrête
    # avec elle. Un temps = un bloc qui tombe.
    t = jalons["build"]
    while t < jalons["fondu"]:
        fort = round((t - jalons["build"]) / TEMPS) % 2 == 0
        frappe(mix, t, 0.75 if fort else 0.5)
        souffle(mix, t + TEMPS / 2, 0.8)
        t += TEMPS

    # Le mur d'affiches : deux fois plus dense, c'est le pic du montage.
    t = jalons["cadre"]
    while t < jalons["cta"]:
        frappe(mix, t, 0.62)
        souffle(mix, t + TEMPS / 2, 1.0)
        souffle(mix, t + TEMPS / 4, 0.45)
        t += TEMPS

    for t0 in (jalons["fondu"], jalons["mur"], jalons["cta"]):
        impact(mix, t0)

    if avec_voix:
        from reel_affiche import PHRASES
        mix = poser_voix(mix, [(t0, dit) for t0, _, dit, _ in PHRASES])

    # Fondu général : entrée douce, sortie sur le logo.
    env = np.ones(n)
    env[:int(0.6 * SR)] = np.linspace(0, 1, int(0.6 * SR))
    q = int(1.0 * SR)
    env[-q:] = np.linspace(1, 0, q)
    mix *= env

    crete = np.max(np.abs(mix)) or 1.0
    mix = np.tanh(mix / crete * 1.4) * 0.82      # limiteur doux
    return mix


# --- voix off ---------------------------------------------------------------
# La synthèse est celle de macOS (`say`) : elle est installée, gratuite, et ne
# sort de la machine à aucun moment. Le ton un peu plat d'un GPS est exactement
# ce qui est demandé — une voix qui annonce, pas une voix qui joue.
VOIX = "Thomas"
DEBIT = 178                              # mots/minute ; au-delà ça mange les liaisons

# Les phrases viennent du montage (`reel_affiche.PHRASES`) : une seule source
# pour ce qui est dit et ce qui est écrit à l'écran, sinon les deux dérivent.


def dire(texte, voix=VOIX, debit=DEBIT):
    """Une phrase synthétisée, rendue en mono 44,1 kHz normalisé."""
    with tempfile.TemporaryDirectory() as d:
        aiff = Path(d) / "v.aiff"
        subprocess.run(["say", "-v", voix, "-r", str(debit), "-o", str(aiff),
                        texte], check=True)
        pcm = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(aiff), "-ar", str(SR),
             "-ac", "1", "-f", "s16le", "-"],
            check=True, capture_output=True).stdout
    v = np.frombuffer(pcm, "<i2").astype(np.float64) / 32768
    crete = np.max(np.abs(v)) or 1.0
    return v / crete


def poser_voix(mix, phrases):
    """Ajoute les phrases et baisse le lit sonore dessous (ducking).

    Sans ducking, la nappe et la voix occupent la même bande et la phrase
    devient une bouillie sur un haut-parleur de téléphone. On descend le lit à
    40 % pendant qu'elle parle, avec 0,18 s de pente de part et d'autre — assez
    lent pour ne pas s'entendre, assez rapide pour dégager la première syllabe.
    """
    duck = np.ones(len(mix))
    pistes = []
    for t0, txt in phrases:
        v = dire(txt)
        d0 = int(t0 * SR)
        n = min(len(v), len(mix) - d0)
        if n <= 0:
            continue
        pistes.append((d0, v[:n]))
        pente = int(0.18 * SR)
        a = max(0, d0 - pente)
        b = min(len(mix), d0 + n + int(0.30 * SR))
        creux = np.ones(len(mix))
        creux[a:b] = 0.40
        creux[a:a + pente] = np.linspace(1, 0.40, min(pente, b - a))
        fin = min(len(mix), b + pente)
        creux[b:fin] = np.linspace(0.40, 1, fin - b)
        duck = np.minimum(duck, creux)
    mix *= duck
    for d0, v in pistes:
        mix[d0:d0 + len(v)] += v * 0.82
    return mix


def ecrire(mix, chemin):
    pcm = (np.clip(mix, -1, 1) * 32767).astype("<i2")
    stereo = np.repeat(pcm[:, None], 2, axis=1).ravel()
    with wave.open(str(chemin), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sortie",
                    default=str(Path(__file__).resolve().parent / "lit-sonore.wav"))
    ap.add_argument("--duree", type=float, default=15.0)
    ap.add_argument("--sans-voix", action="store_true",
                    help="lit sonore seul, sans la voix off")
    a = ap.parse_args()
    # Le chemin est résolu AVANT l'import : `reel_affiche` fait un chdir vers
    # le dépôt boutique (ses mockups sont référencés en relatif), donc tout
    # chemin relatif changerait de sens une ligne plus bas.
    sortie = Path(a.sortie).expanduser().resolve()
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from reel_affiche import bornes
    B, _ = bornes()
    jalons = {k: v[0] for k, v in B.items()}
    ecrire(construire(a.duree, jalons, not a.sans_voix), sortie)
    print("OK ->", sortie)
