#!/usr/bin/env python3
"""Suit le cadre vide d'un plan filmé, image par image.

Pourquoi pas un simple relevé fixe
-----------------------------------
Le prompt demandait une caméra bloquée, et Veo a quand même laissé respirer le
cadrage de quelques pixels. À 24 images par seconde, un décalage de 3 px suffit
à faire vibrer l'affiche incrustée : elle se met à « nager » dans son cadre.
On relève donc le cadre sur CHAQUE image, puis on lisse la trajectoire.

La détection
------------
La moulure est noire, le mur clair, et la personne se tient à l'écart : dans
une zone d'intérêt qui l'exclut, les seuls pixels vraiment sombres sont ceux du
cadre. `coins_droites` en tire les quatre coins intérieurs par ajustement de
droites — le lissage temporel et le rejet des relevés aberrants sont, eux, du
ressort de l'appelant (`mix.quad_du_plan`).

La zone d'intérêt est VERROUILLÉE sur le relevé de la première image, élargie
d'une marge fixe. Elle ne suit pas la détection : une zone qui suit sa propre
sortie s'élargit à la moindre erreur, attrape la personne, et ne revient
jamais — c'est exactement ce qui s'est produit au premier essai.
"""

import numpy as np


def _bbox_sombre(gris, roi, seuil):
    """Enveloppe des pixels sombres dans `roi` = (x1, y1, x2, y2)."""
    x1, y1, x2, y2 = roi
    z = gris[y1:y2, x1:x2] < seuil
    if not z.any():
        return None
    ys, xs = np.where(z)
    return (x1 + int(xs.min()), y1 + int(ys.min()),
            x1 + int(xs.max()) + 1, y1 + int(ys.max()) + 1)


def coins_droites(gris, roi, seuil=95):
    """Les 4 coins intérieurs, par ajustement d'une droite sur chaque bord.

    Pourquoi pas la version rectangulaire
    -------------------------------------
    Le cadre du plan généré n'est pas parfaitement de face : sa moulure gauche
    se voit en épaisseur, et le bord intérieur haut remonte de treize pixels
    vers la droite. Un rectangle calé sur les extrêmes déborde alors sur la
    moulure d'un côté et laisse du blanc de l'autre — c'est exactement le
    défaut constaté au premier montage.

    On relève donc le bord intérieur ligne par ligne et colonne par colonne, on
    ajuste une droite sur chacun des quatre bords, et on les croise. C'est la
    méthode des relevés de `mockup_biais.QUADS`, faite ici automatiquement.
    """
    ext = _bbox_sombre(gris, roi, seuil)
    if ext is None:
        return None
    X1, Y1, X2, Y2 = ext
    L, Hh = X2 - X1, Y2 - Y1

    def bord(fixes, axe, sens, epaisseur=(3, 45)):
        """Fin de la moulure, sur chaque ligne (ou colonne).

        On cherche le premier segment sombre depuis le bord, puis on en prend
        l'autre extrémité : c'est là que commence le papier. On ne suppose PAS
        que la moulure démarre pile au bord de l'enveloppe — un cadre même
        légèrement incliné décale son montant d'une ligne à l'autre, et exiger
        du sombre dès le premier pixel écartait alors toutes les lignes.

        Un segment plus fin ou plus épais que la moulure attendue est rejeté :
        c'est du bruit, ou l'ombre portée du cadre sur le mur.
        """
        pts = []
        n = X2 - X1 if axe == "x" else Y2 - Y1
        for f in fixes:
            ligne = gris[f, X1:X2] if axe == "x" else gris[Y1:Y2, f]
            idx = range(n) if sens > 0 else range(n - 1, -1, -1)
            debut = None
            for i in idx:
                if ligne[i] < seuil:
                    debut = i
                    break
            if debut is None:
                continue
            i = debut
            while 0 <= i < n and ligne[i] < seuil:
                i += sens
            ep = abs(i - debut)
            if not (epaisseur[0] <= ep <= epaisseur[1]):
                continue
            pos = (X1 + i) if axe == "x" else (Y1 + i)
            pts.append((f, pos))
        return pts

    def droite(pts):
        """Régression robuste : un ajustement, puis on rejette au-delà de deux
        écarts-types et on recommence. Un reflet sur la moulure suffit à faire
        pencher une droite ajustée sur tous les points."""
        if len(pts) < 8:
            return None
        a = np.array(pts, float)
        for _ in range(2):
            p = np.polyfit(a[:, 0], a[:, 1], 1)
            res = np.abs(a[:, 1] - np.polyval(p, a[:, 0]))
            s = res.std() or 1.0
            garde = res < 2 * s
            if garde.sum() < 8:
                break
            a = a[garde]
        return np.polyfit(a[:, 0], a[:, 1], 1)

    lignes = range(Y1 + int(Hh * 0.18), Y1 + int(Hh * 0.82))
    colonnes = range(X1 + int(L * 0.18), X1 + int(L * 0.82))
    # x = f(y) pour les bords verticaux, y = f(x) pour les horizontaux
    g = droite(bord(lignes, "x", +1))
    d = droite(bord(lignes, "x", -1))
    h = droite(bord(colonnes, "y", +1))
    b = droite(bord(colonnes, "y", -1))
    if any(v is None for v in (g, d, h, b)):
        return None

    def croiser(vert, horiz):
        """x = a·y + b croisée avec y = c·x + d."""
        a, bb = vert
        c, dd = horiz
        x = (a * dd + bb) / (1 - a * c)
        return (x, c * x + dd)

    return (croiser(g, h), croiser(d, h), croiser(d, b), croiser(g, b))
