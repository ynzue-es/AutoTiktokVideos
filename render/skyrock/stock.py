#!/usr/bin/env python3
"""
Resolution des chemins d'un "stock" skyrockfm.

Un stock = une vague de scraping. On en ouvre un nouveau au lieu de re-scraper
par-dessus l'ancien : scrape-reels.ts purge les mp4 absents du nouvel index, et
les noms de fichiers (NN-shortcode.mp4) servent de cle au journal posted.json —
re-scraper en place decalerait les NN et casserait l'anti-doublon.

    library/skyrockfm-stock1/  ->  out/skyrock/   (vague 1, 20 reels)
    library/skyrockfm-stock2/  ->  out/skyrock2/  (vague 2, 31 reels)

Chaque script accepte --stock N (defaut 1).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def parse(argv=None):
    """Retourne (stock_id, argv_restant) — --stock N retire des arguments."""
    argv = list(sys.argv[1:] if argv is None else argv)
    sid = "1"
    if "--stock" in argv:
        i = argv.index("--stock")
        sid = argv[i + 1]
        del argv[i:i + 2]
    return sid, argv


class Stock:
    def __init__(self, sid="1"):
        self.id = str(sid)
        sfx = "" if self.id == "1" else self.id   # stock 1 = noms historiques
        self.lib = ROOT / "library" / f"skyrockfm-stock{self.id}"
        self.out = ROOT / "out" / f"skyrock{sfx}"
        self.logos = HERE / f"logos{sfx}.json"
        self.config = HERE / f"config{sfx}.json"
        self.speech = HERE / f"recap_speech{sfx}.json"
        self.captions = HERE / f"captions_fr{sfx}.json"

    def __repr__(self):
        return f"<stock {self.id}: {self.lib.name} -> {self.out.name}>"


def current(argv=None):
    """Stock designe par --stock, et arguments restants."""
    sid, rest = parse(argv)
    return Stock(sid), rest
