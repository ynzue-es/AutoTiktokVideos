#!/usr/bin/env python3
"""
Construit render/subs_fr.json = {file: [{start,end,fr}]} en zippant les
timings de transcripts.json avec les traductions FR ci-dessous.
Seuls les reels avec de la parole claire sont sous-titrés (les autres :
musique / hallucination / promo -> pas de subs).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# FR dans le MÊME ORDRE que les segments de transcripts.json (1 pour 1)
FR = {
  "00-DZNazttCjS0.mp4": [
    "Tu veux entendre un de mes sons ? Ouais.",
    "Je lance la boîte à rythmes,",
    "et à peine deux-trois secondes plus tard,",
    "il enchaîne direct :",
    "« Hi! My name is »",
    "« My name is... »",
    "Je voulais juste être sûr que",
    "sur chaque prod qu'il me passait,",
    "j'avais déjà une punchline prête.",
    "« Salut gamin !",
    "T'aimes la violence ?",
    "Tu veux me voir planter des clous de 9 cm",
    "à travers mes paupières ? »",
    "Je vois que ça fait réagir Dre,",
    "il rigole, il me freine pas,",
    "il me laisse provoquer.",
  ],
  "01-DZNaq8djzGA.mp4": [
    "Le truc drôle avec le Record Plant, c'est qu'il y a un terrain de basket dedans.",
    "Tom savait déjà qu'il n'enregistrait pas ce soir-là.",
    "Il allait juste jouer au basket.",
    "Donc moi j'allais faire un beat là.",
    "J'allais pas gâcher du temps de studio.",
    "J'ai sorti un simple piano dans Citrus, le plug-in de base, c'est ça qui est drôle.",
    "Et ensuite j'ai ajouté ce Gross Beat.",
    "Tous les gars sur FL qui utilisent Gross Beat connaissent le truc du half-speed.",
    "Je l'ai ralenti de moitié, mais pas à fond.",
    "Donc je l'ai mis genre à moitié.",
    "Ça donne l'impression qu'il se passe plus de choses.",
    "Tu entends encore un peu les notes que je joue.",
    "Mais ça ajoute des notes aléatoires qui se répondent.",
    "Tout le reste sonnait grave et sombre.",
    "Un truc a fait tilt dans ma tête : je vais ajouter ce piano plus aigu.",
    "J'ai senti que cette partie resterait dans la tête des gens.",
  ],
  "05-DZNbJ-7DyEX.mp4": [
    "J'm'en fous, je rigole pas avec toi.",
    "Va te coucher.",
    "Elle m'a pas... elle m'a pas laissé avec un flingue.",
    "J'appelle Jaffa, je l'emmène là-bas.",
    "Comment ? Pour qu'ils viennent t'embarquer ?",
  ],
  "08-DZNa98aDoew.mp4": [
    "Attendez, quelqu'un me regarde, c'est chaud.",
    "Il est là-bas.",
    "Fais ce que t'as à faire, mec.",
    "Tu vois comment il me regarde ?",
    "Tu marches, et là quelqu'un se met à te fixer.",
    "Moi, genre, tu vois ce que je veux dire ?",
    "Comme s'il me cherchait, tu vois ?",
    "Là je peux continuer ou aller le confronter.",
    "Je crois que je vais continuer, tu vois ?",
    "Je sais pas ce qu'il a sur lui, tu vois ?",
    "Il est accompagné.",
    "On se capte plus tard, mec.",
    "Va nulle part tout seul.",
  ],
  "10-DZNZ_f2Dh5r.mp4": [
    "Très positif, vu que j'ai 46 ans et que je fais ça depuis...",
    "Putain !",
    "Désolé.",
    "Le temps, comme je disais, et moi, tu sais, j'ai 56 ans.",
    "Putain !",
    "Désolé.",
  ],
  "13-DZNYVFEEblG.mp4": [
    "J'ai un son où j'ai transformé du Michael Jackson en truc de gangster, genre, euh...",
    "En Californie ensoleillée, sous les palmiers, moi et mon gars, stylé, caisse en candy paint, tu me connais, je sirote dans une Benz, la fumée sort par la fenêtre, blah !",
    "J'vois un hater au coin d'la rue, il te fonce dessus, il est mort, genre ça va, ça va, non ça va pas, il s'est fait serrer par un général des rues.",
  ],
  "14-DZNYIVQkXw_.mp4": [
    "Je sais que tu m'aimes pas, bébé, prends ma main mais tu ne t'accrocheras jamais.",
    "Ne me l'explique pas.",
    "T'as commencé par le refrain cette fois ?",
    "Donc, tu vois ce que je veux dire ?",
    "Ouais, t'as commencé.",
    "Tu veux faire ça ?",
    "Mais du coup je commence là ?",
    "Ça devrait être...",
    "Ça devrait faire...",
  ],
  "15-DZNYqbuks46.mp4": [
    "Ça a quel goût ?",
    "Du sperme — pas que je sache quel goût ça a, mais si je devais deviner, je dirais du sperme.",
    "Perds pas ton temps à regarder cette émission.",
    "Le pire truc... je sais pas c'est quoi le plus maléfique que j'ai fait.",
    "Mais le truc le plus stylé que j'ai fait sans le dire à personne,",
    "c'est qu'une fois j'ai renversé une vieille dame.",
    "Enfin, ouais, ok.",
    "Évidemment.",
  ],
  "16-DZNbEeHjmOE.mp4": [
    "Ah ok. Celle-là c'était la facile. Allez, on en fait une autre : les chevaux. J'aime bien, ça c'est de l'équitation.",
    "De l'équitation qui caracole, au fait, regarde ce cheval. T'as vu, le cheval fait le Crip Walk !",
    "T'as vu ça ? Oh !",
    "Ça c'est gangsta, un vrai mope.",
    "Regarde cette meuf. Allez quoi, ce cheval est incroyable. Faut que je le mette dans le clip.",
    "Oh !",
    "Il me faut ce cheval — le Crip Walk est officiellement aux JO, mec. T'as vu ça ?",
  ],
  "17-DZNYBnplMPq.mp4": [
    "Allez, on va les chercher !",
  ],
  "18-DZNYxRLiXnY.mp4": [
    "« Red Hot Lover ». Oh, j'aime bien celle-là. Mets-la dans la salle de bain.",
    "Regarde, à un point près. Je peux pas faire ça avec ma copine, les gens genre...",
    "C'est quand même rentré ! C'est...",
    "Les Lakers ont encore marqué !",
  ],
  "24-DZNXk2YEY-j.mp4": [
    "On n'est pas contre les rappeurs, on n'est pas contre les rappeurs, mais on est contre ces voyous, ces voyous, ces voyous.",
  ],
  "25-DZNaTJcknxR.mp4": [
    "T'as déjà gagné, si des gens chantent tes sons mot pour mot, si t'es un héros dans ta ville.",
    "Écoute, s'il y a des gens avec des boulots normaux, qui sortent sous la pluie, sous la neige,",
    "qui dépensent leur argent durement gagné pour venir à tes concerts, t'as pas besoin de ça.",
    "Je te le promets, t'as déjà gagné.",
  ],
  "27-DZNZhanCmeD.mp4": [
    "Dis, Jim, tu crois que je peux voler comme un papillon ?",
    "Bam.",
    "Eh bien.",
    "Piquer comme une abeille ?",
    "Woo !",
    "T'as déjà la partie papillon, frère Michael,",
    "et tu parles tout doux pour compléter le cycle.",
    "Mais avant de piquer les gens à les rendre fous,",
    "faut te muscler et continuer à manger ton gruau.",
    "Mec, t'es givré, toi.",
  ],
  "28-DZNW18LEYL2.mp4": [
    "On cherche, tu sais, des morceaux, c'est que des pièces du puzzle, tu vois.",
    "C'est bien, ça.",
    "Parle-lui.",
    "Je veux juste trouver un couplet vraiment fort.",
    "Ça c'est un couplet de malade, et après on trouvera le concept. T'en es où ?",
  ],
}


def main():
    trans = json.loads((ROOT / "render" / "transcripts.json").read_text())
    subs = {}
    for f, fr_list in FR.items():
        segs = trans[f]
        if len(segs) != len(fr_list):
            raise SystemExit(f"{f}: {len(segs)} segments != {len(fr_list)} FR")
        subs[f] = [{"start": s["start"], "end": s["end"], "fr": fr}
                   for s, fr in zip(segs, fr_list)]
    (ROOT / "render" / "subs_fr.json").write_text(
        json.dumps(subs, ensure_ascii=False, indent=2))
    print(f"✓ subs_fr.json ({len(subs)} reels sous-titrés)")


if __name__ == "__main__":
    main()
