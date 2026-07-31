#!/usr/bin/env python3
"""
Secours pour la recuperation des paroles.

N'est appele que lorsque LRCLIB ne renvoie rien de synchronise. La lib
`syncedlyrics` interroge plusieurs fournisseurs (Musixmatch, LRCLIB, Netease),
tous gratuits et sans cle.

Ecrit le LRC brut sur la sortie standard, ou ne produit rien et sort en 1
si aucune parole synchronisee n'a ete trouvee. C'est le contrat attendu par
src/pipeline/3-lyrics.ts.
"""

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True)
    parser.add_argument("--artist", required=True)
    args = parser.parse_args()

    try:
        import syncedlyrics
    except ImportError:
        print(
            "syncedlyrics n'est pas installe — voir py/README.md",
            file=sys.stderr,
        )
        return 1

    query = f"{args.title} {args.artist}"

    try:
        # synced_only garantit qu'on ne recupere pas des paroles a plat,
        # inutilisables pour un affichage mot par mot.
        lrc = syncedlyrics.search(query, synced_only=True)
    except TypeError:
        # Les versions plus anciennes n'exposent pas synced_only.
        lrc = syncedlyrics.search(query)
    except Exception as exc:  # le reseau ou un fournisseur peut tomber
        print(f"syncedlyrics a echoue : {exc}", file=sys.stderr)
        return 1

    if not lrc or "[" not in lrc:
        print("aucune parole synchronisee trouvee", file=sys.stderr)
        return 1

    sys.stdout.write(lrc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
