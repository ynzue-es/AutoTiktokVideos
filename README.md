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

Secrets dans `.env` à la racine (gitignoré) :

```
APIFY_TOKEN=apify_api_xxxxxxxxxxxxxxxxx
ZERNIO_API_KEY=sk_xxxxxxxx          # publication (étape 7)
ZERNIO_TIKTOK_ACCOUNT=xxxxxxxx      # accountId TikTok (GET /api/v1/accounts)
ZERNIO_IG_ACCOUNT=xxxxxxxx          # accountId Instagram (compte Business requis)
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

## 7. Publier / programmer sur TikTok + Instagram  →  Zernio

Publication via **Zernio** (API REST, gratuit pour 2 comptes) : Zernio héberge la
vidéo et gère l'auth des plateformes — **pas de Make, pas de stockage externe, pas
d'app Meta/TikTok à faire valider**. Flux par vidéo : `presign → PUT upload →
POST /posts` (TikTok + IG).

Clés dans `.env` : `ZERNIO_API_KEY`, `ZERNIO_TIKTOK_ACCOUNT`, `ZERNIO_IG_ACCOUNT`
(récupérer les accountId via `GET https://zernio.com/api/v1/accounts`).

```bash
npx tsx src/post.ts                         # DRY-RUN (défaut) : montre le planning, ne poste rien
npx tsx src/post.ts --go --schedule         # PROGRAMME 1/jour à 19h (Paris) dès demain
npx tsx src/post.ts --go --now --only 02    # publie 1 vidéo tout de suite (test)
npx tsx src/post.ts --go --schedule --start 2026-09-01   # démarre la vague à une date précise
```

- **Sécurité** : sans `--go`, rien n'est posté (dry-run). Toujours vérifier l'aperçu d'abord.
- **Ordre** : trié par vues d'origine (meilleures d'abord), via `library/index.json`.
- **Cadence** : constante `SLOTS` en haut de `src/post.ts` (`["19:00"]` = 1/jour ;
  mettre `["12:30","18:00","21:00"]` pour 3/jour). Créneaux = heure de Paris.
- **Journal anti-doublon** : `render/posted.json` liste les vidéos déjà planifiées ;
  elles sont automatiquement sautées aux vagues suivantes (`--force` pour outrepasser).
- **Légende** = titre FR + hashtags (constante `HASHTAGS` dans `src/post.ts`).
- **IG >90s** : les vidéos de plus de 90s partent sur TikTok seulement (limite Reels).

**Gérer/annuler un post planifié** (récupère l'id dans la sortie du script) :
```bash
KEY=$(grep '^ZERNIO_API_KEY=' .env | cut -d= -f2)
curl -X DELETE -H "Authorization: Bearer $KEY" https://zernio.com/api/v1/posts/<ID>
```

---

## 🔁 Refaire une vague plus tard (grossir + continuer à poster)

Quand ça marche et qu'on veut enchaîner avec du nouveau contenu — **simple et rapide** :

```bash
# 1. Re-scraper les derniers reels du compte source (nouveaux depuis la dernière fois)
npx tsx src/scrape-reels.ts sonotradehq 30

# 2. Prépa + transcription
cd render && python3 prep.py && python3 augment_prep.py && python3 transcribe_all.py && cd ..

# 3. Traduire À LA MAIN les NOUVELLES vidéos :
#    - lire scratch-frames/read-NN.png -> ajouter les entrées dans render/translations.json
#    - compléter la table FR dans render/build_subs.py pour les clips parlés
cd render && python3 build_subs.py && python3 batch.py && cd ..

# 4. Programmer UNIQUEMENT les nouvelles (le journal saute celles déjà postées),
#    en démarrant après la file en cours :
npx tsx src/post.ts --schedule --start 2026-08-31          # aperçu
npx tsx src/post.ts --go --schedule --start 2026-08-31     # go
```

Le journal `render/posted.json` garantit qu'on ne reposte jamais une vidéo déjà
programmée, même si le scrape ramène les mêmes fichiers. Seules les nouvelles
partent. Les 2 seules étapes manuelles restent **la traduction du titre** et **des
sous-titres** — le reste est automatique.

---

## 🟣 Pipeline B — rap.minute → DA violet fluo (`render/rapminute/`)

Deuxième chaîne, **indépendante** de la première. Pas de traduction, pas de
sous-titres : rap.minute poste des reels FR avec un **hook** (texte blanc bold
condensé majuscule, mots-clés en vert `#00D392`, barre verticale verte à gauche)
affiché pendant les ~5-8 premières secondes. On **couvre cette zone** d'une bande
opaque et on **réécrit notre texte** dans la même grammaire, en violet.

```bash
# 1. Scraper dans un dossier ISOLE (--lib obligatoire, voir avertissement plus bas)
npx tsx src/scrape-reels.ts rap.minute 20 --lib library/rapminute

# 2. Detection : couleur de marque -> zone + timing du hook
cd render/rapminute
python3 detect_green.py     # bbox des pixels verts     -> green.json
python3 detect_hook.py      # bloc de texte complet     -> hooks.json

# 3. Ecrire NOS hooks a la main dans hooks_fr.json (seule etape manuelle)

# 4. Rendu + controle qualite
python3 batch.py            # tout            -> out/rapminute/
python3 batch.py 00 13      # juste ces prefixes (preview rapide)
python3 verify.py           # 0 pixel vert residuel dans les sorties ?
```

⚠️ **`--lib` n'est pas optionnel en pratique.** `scrape-reels.ts` purge en fin de
run tous les `.mp4` absents du nouvel index et écrase `index.json`. Scraper un
2e compte dans `library/` **détruirait** la librairie sonotradehq. Un dossier par
compte source.

**Pourquoi deux détecteurs.** Le vert de marque est rare, donc facile à isoler —
mais sa bbox ne couvre que les *mots-clés*, pas les lignes entièrement blanches.
`detect_hook.py` repart de cette bbox et étend au bloc réel. Le piège : un seuil
« pixel blanc » attrape aussi le décor clair (gradins, murs, ciel). Le
discriminant qui marche est **la stabilité temporelle** — le texte est immobile,
le décor bouge : on prend l'**intersection** des masques sur la fin du segment
(fin seulement, car le texte s'écrit mot par mot).

**Balisage du texte** (`hooks_fr.json`) : les mots entre `*astérisques*` sortent
en violet, tout le reste en blanc. Le texte est passé en majuscules au rendu.

```json
"13-DbnbfhCguQA.mp4": "la réaction de *travis scott* quand le dj lance *son morceau* à ibiza 🤯"
```

**Style** (constantes en haut de `hook_overlay.py`) : violet `#8B00FF`, bande
`#0A0012` + filet néon bas, Avenir Next Condensed Heavy, géométrie calée sur la
leur (`MARGIN=66` à 720px de large, `LINE_H=38`). La bande s'agrandit toute
seule si notre texte prend plus de lignes que le leur. Audio d'origine conservé.

### Publier le pipeline B

`src/post.ts` est multi-projet et multi-compte :

```bash
# aperçu (dry-run) puis go — 1/jour à 12h30 sur la clé BOUTIQUE
npx tsx src/post.ts --project rapminute --key BOUTIQUE --schedule --slots 12:30
npx tsx src/post.ts --project rapminute --key BOUTIQUE --schedule --slots 12:30 --go
```

- `--project` : jeu de chemins (`fr` = pipeline A, `rapminute` = pipeline B).
  Chaque projet a **son propre journal anti-doublon**.
- `--key SUFFIXE` : lit `ZERNIO_API_KEY_SUFFIXE` & co. Sans `--key`, clé par défaut.
- `--slots` : créneaux/jour, ex `07:00` ou `12:30,18:00,21:00` (heure de Paris).
- Un workspace **sans compte Instagram** poste sur TikTok seulement (détecté tout seul).
- Les astérisques du balisage `*mot*` sont retirées de la légende publiée.

⚠️ L'API Zernio renvoie `scheduledFor` en **UTC**. En été, 12h30 Paris s'affiche
`10:30` — c'est normal, pas un décalage à corriger.

**Reels écartés du lot de 20** (absents de `hooks_fr.json`) :

| Reel | Raison |
|---|---|
| `01` | Sous-titré en pilules vertes de bout en bout — autre format |
| `19` | Vidéo repostée d'un autre compte (quiz « Smugglers Society ») |
| `04`, `07` | Aucun hook au début, uniquement l'outro promo rap.minute |

Pour récupérer `04`/`07` : leur écrire un hook, puis couper l'outro via
`trim_end` (déjà supporté par `hook_overlay.render`).

---

## 🎙️ Pipeline C — skyrockfm → LeMurSonore (`render/skyrock/`)

Troisième chaîne. skyrockfm incruste un **bandeau de marque en haut à droite**
(SKYROCK / PLANÈTE RAP / PR+ / LE RÉCAP / KARAOKE BOX) : on le recouvre d'un
badge LeMurSonore. Deux formats coexistent dans le compte :

| Format | Reels | Traitement |
|---|---|---|
| **studio** (artiste au micro) | 00-04, 08, 11, 14-19 | badge logo seul |
| **LE RÉCAP** (présentateur en voix off) | 05, 06, 07, 09, 10, 13 | badge + **coupe de l'intro** + rectangle de texte |
| **karaoke** | 12 | badge logo seul |

Sur les LE RÉCAP, un présentateur ouvre la vidéo face caméra. On **coupe toute
son intro** et on affiche à la place son propos reformulé dans un rectangle de
texte, pendant 4,5 s.

```bash
npx tsx src/scrape-reels.ts skyrockfm 20 --lib library/skyrockfm

cd render/skyrock
python3 detect_logo.py        # degrossit la zone du bandeau -> logos.json
python3 transcribe_recap.py   # Whisper FR sur les LE RECAP -> recap_speech.json
# -> editer config.json (family + texte reformulé) et captions_fr.json
python3 batch.py              # rendu -> out/skyrock/
```

**Point de coupe.** La fin de la prise de parole donnée par Whisper coïncide
avec la disparition du présentateur (vérifié image par image : à +0,5 s il n'est
déjà plus là et le carton du sujet démarre). `cut_at()` s'appuie donc dessus.
`-ss` est placé **avant** `-i`, donc il ne s'applique qu'à la vidéo et remet les
timestamps à zéro — la fenêtre du rectangle de texte se compte à partir de 0.

⚠️ **`detect_logo.py` ne suffit pas seul.** Les logos changent en cours de vidéo
(SKYROCK sur un plan, PR+ sur le suivant), et les décors de studio clairs et
fixes (murs, spots) passent le filtre « pixel clair et immobile ». Le détecteur
prend donc l'union des fenêtres glissantes puis la plus grosse composante
connexe — mais il bave encore sur 6 reels sur 20. Les boîtes réellement
utilisées (`FAMILY_BOX` dans `logo_overlay.py`) ont été **mesurées à la grille
sur des frames réelles**, pas prises du détecteur.

**Non traité** : les logos Skyrock qui font partie du décor filmé (mur du studio,
bonnette de micro) restent visibles — ce sont des objets physiques, pas des
incrustations.

**Publication** : `--project skyrock --key NEXUS` (voir la section ci-dessus).

---

## 💧 Pipeline D — rvpfr → LeMurSonore (`render/rvpfr/`)

Quatrième chaîne, la plus simple. rvpfr appose un **filigrane « Rvp Fr »** (script
en losange, translucide) **en bas au centre**. On le recouvre d'un badge rond
LeMurSonore, en overlay statique sur toute la durée.

```bash
npx tsx src/scrape-reels.ts rvpfr 20 --lib library/rvpfr

cd render/rvpfr
python3 detect_logo.py    # zone du filigrane -> logos.json
python3 batch.py          # rendu -> out/rvpfr/
python3 verify.py         # controle de recouvrement
```

La position du filigrane varie d'un reel à l'autre (y ≈ 1070-1250 en général,
mais 866 sur `17` et 1035 sur `19`), d'où une détection par reel plutôt qu'une
zone fixe — à l'inverse du pipeline C.

⚠️ **`verify.py` est trop sensible.** Il signale tout pixel stable en bordure du
badge, or beaucoup de ces reels embarquent leurs propres incrustations fixes
(logos de chaînes, bandeaux de texte). Sur la vague du 10 août il a levé `03` et
`17` : inspection à la grille sur les frames source **et** rendues → le losange
« Rvp Fr » était intégralement recouvert dans les deux cas, le « résidu » étant
le rond rouge et le texte « …eka offi » appartenant à la vidéo d'origine. Un
signalement de ce script demande une vérification visuelle, ce n'est pas un
verdict.

**Publication** : `--project rvpfr --key LEMURSONORE`.

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
src/scrape-reels.ts        étape 1 (scrape + fallback yt-dlp, option --lib)
src/post.ts                étape 7 (publie/programme via Zernio)
library/                   mp4 bruts sonotradehq + index.json (gitignoré)
library/rapminute/         mp4 bruts rap.minute + index.json (gitignoré)
render/rapminute/          pipeline B (DA violette) :
  detect_green.py            pixels verts de marque  -> green.json
  detect_hook.py             bloc de texte complet   -> hooks.json
  hooks_fr.json              NOS hooks (édité à la main, *mot* = violet)
  hook_overlay.py            moteur bande + texte violet
  batch.py                   rendu -> out/rapminute/
  verify.py                  contrôle : 0 vert résiduel
render/
  detect.py                détection bloc vidéo (haut/bas)
  prep.py / augment_prep.py prep.json + frames de lecture
  translations.json        titres FR (édité à la main)
  transcribe.py / transcribe_all.py  Whisper → transcripts.json
  build_subs.py            table FR sous-titres → subs_fr.json
  subtitles.py             découpe cues + PNG sous-titres
  tweet_overlay.py         moteur d'overlay (header, footer, subs)
  batch.py                 rendu final → out/fr/
  posted.json              journal anti-doublon des vidéos déjà programmées
montage/                   utilitaires ffmpeg (crop vertical) — réserve
out/fr/                    vidéos finales (gitignoré)
```
