# LeMurSonore — Pipeline reels FR

Scrape les reels d'un compte Instagram "faux tweet", **rebrande** en LeMurSonore,
**traduit** le texte du tweet en FR et **sous-titre** en français la parole
anglaise — tout en gardant l'audio original.

Format source visé : carte "faux tweet" (en-tête compte + texte + vidéo carrée
en dessous, sur fond noir). Testé sur `@sonotradehq`.

---

## 0. Prérequis (une fois)

Outils système (déjà installés sur cette machine) :

- **node + tsx** (`npm install` à la racine installe tsx/typescript)
- **python3** + libs : `pip install pillow faster-whisper`
- **ffmpeg** + **ffprobe** (build local : PAS de libass/drawtext → les overlays
  sont rendus en PIL, ne pas compter sur le filtre `subtitles`)
- **yt-dlp** (fallback audio)

Secret : token Apify dans `.env` à la racine (gitignoré) :

```
APIFY_TOKEN=apify_api_xxxxxxxxxxxxxxxxx
```

Le logo doit être dans `assets/logo.png` (M noir sur fond blanc/transparent).

---

## 1. Scraper les reels  →  `library/`

```bash
npx tsx src/scrape-reels.ts <compte> <N>
# ex : npx tsx src/scrape-reels.ts sonotradehq 30
```

- Actor Apify `apify/instagram-reel-scraper` (pay-per-result, ~5 $/mois offerts).
- Télécharge les mp4 dans `library/` + `library/index.json` (vues, caption, date…).
- **Auto-fallback audio** : certains `videoUrl` Apify sont vidéo-seule (surtout les
  1080×1920). Le script détecte l'absence d'audio et re-télécharge via yt-dlp.
- Purge les orphelins d'un run précédent.

**Rate limits Instagram** : viser < 200 résultats/run, pas plus d'1 scrape/profil
/heure, étaler dans le temps. Quelques centaines de reels/jour max.

---

## 2. Préparer  →  `render/prep.json`

```bash
cd render
python3 prep.py            # détecte le bloc vidéo + extrait 1 frame/reel (lecture)
python3 augment_prep.py    # ajoute video_bottom (haut ET bas du bloc)
```

`prep.json` = `[{file, video_top, video_bottom, w, h}]`.

**Détection** (`detect.py`) : le cadre vidéo est fixe mais son contenu bouge, alors
que les bandes noires restent noires → on prend le **max temporel** sur ~12 frames
et on distingue la vidéo (lignes larges) du texte (lignes fines). Robuste aux
scènes sombres.

Les frames `scratch-frames/read-NN.png` servent à **lire les textes à l'œil**.

---

## 3. Traduire le texte du tweet  →  `render/translations.json`

⚠️ **Le texte affiché ≠ la caption Apify.** Il faut lire chaque
`scratch-frames/read-NN.png` et écrire la traduction FR (punchy, naturelle, on
garde les noms propres). Format :

```json
{ "i": 0, "file": "00-....mp4", "en": "texte anglais lu", "fr": "traduction FR" }
```

Retirer ici les reels non pertinents (ex : une pub de l'app source).

---

## 4. Transcrire l'audio  →  `render/transcripts.json`

```bash
cd render
python3 transcribe_all.py     # faster-whisper (modèle "small"), CPU, ~10-15 min
```

Sort `{file: [{start, end, en}]}`. Segments = 0 sur les clips musique/sans parole.

---

## 5. Sous-titres FR  →  `render/subs_fr.json`

Éditer la table `FR` dans `render/build_subs.py` : pour chaque reel **clairement
parlé**, coller la liste FR **dans le même ordre** que les segments de
`transcripts.json` (1 pour 1, même nombre). Puis :

```bash
cd render
python3 build_subs.py
```

**Ne PAS sous-titrer** : musique pure, hallucinations Whisper
("Thank you for watching"), rap trop mal transcrit, pubs. Ces reels gardent juste
header + titre (le visuel porte).

---

## 6. Rendu final  →  `out/fr/`

```bash
cd render
python3 batch.py
```

Pour chaque reel : header LeMurSonore (logo rond + nom + badge + @lemursonore.fr,
ancien en-tête écrasé) + titre FR + sous-titres FR timés (si présents) + footer
rebrand (si listé dans `FOOTERS`). Audio original conservé.

Régénérer après n'importe quelle modif de texte/traduction : `python3 batch.py`.

---

## Cas particuliers / décisions par défaut

- **Reels sans parole** (concert, musique, danse) → pas de sous-titres.
- **Reels = pub de l'app source** (écrans produit) → **retirés** de `translations.json`.
- **Bande promo incrustée en bas** (footer "… Link in bio" + carte) → masquée et
  remplacée par le footer LeMurSonore. À déclarer dans `FOOTERS` de `batch.py` :
  `{"22-....mp4": (y_from, y_to)}` (mesurer la bande sur une frame).
- **Sous-titres EN d'origine** (incrustés au milieu par la source) → laissés ; le
  FR est ajouté en bas.
- **Rap mal transcrit** : pour un rendu propre, récupérer les vraies paroles à la
  main plutôt que la sortie Whisper.

## Layout / style (dans `render/tweet_overlay.py`)

- Tout est calibré pour 720px de large (`scale = W/720`), marche en 1080×1920 aussi.
- Header : rond blanc + logo recadré, nom Arial Bold blanc + badge doré, handle gris.
- Texte : Arial, blanc, wrap auto, emojis couleur (Apple Color Emoji, strike 160px).
- Sous-titres : Arial Bold blanc + contour noir, en bas du bloc vidéo, cues
  découpées (`subtitles.py`).
- Logo résolu en chemin absolu (`DEFAULT_LOGO`) — marche quel que soit le cwd.

## Arborescence

```
assets/logo.png            logo M (fourni)
.env                       APIFY_TOKEN (gitignoré)
src/scrape-reels.ts        étape 1 (scrape + fallback yt-dlp)
library/                   mp4 bruts + index.json (gitignoré)
render/
  detect.py                détection bloc vidéo (haut/bas)
  prep.py / augment_prep.py prep.json + frames de lecture
  translations.json        titres FR (édité à la main)
  transcribe.py / transcribe_all.py  Whisper → transcripts.json
  build_subs.py            table FR sous-titres → subs_fr.json
  subtitles.py             découpe cues + PNG sous-titres
  tweet_overlay.py         moteur d'overlay (header, footer, subs)
  batch.py                 rendu final → out/fr/
montage/                   utilitaires ffmpeg (crop vertical) — réserve
out/fr/                    vidéos finales (gitignoré)
```
