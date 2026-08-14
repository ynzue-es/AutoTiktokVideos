# LeMurSonore — Pipelines reels FR

Scrape les reels de comptes Instagram, **retire leur marque**, **rebrande** en
LeMurSonore et **programme** la publication sur TikTok — en gardant l'audio
original.

**Quatre chaînes indépendantes**, une par compte source, chacune avec sa propre
librairie, ses rendus et son journal anti-doublon :

| | Source | Marque à retirer | Traitement | Section |
|---|---|---|---|---|
| **A** | `sonotradehq` | en-tête « faux tweet » | rebrand + traduction FR + sous-titres | §1-7 |
| **B** | `rap.minute` | hook vert `#00D392` | bande opaque + hook réécrit en violet | ci-dessous |
| **C** | `skyrockfm` | bandeau haut-droit | badge + coupe de l'intro présentateur | ci-dessous |
| **D** | `rvpfr` | filigrane bas-centre | badge rond statique | ci-dessous |

Les étapes §1 à §7 décrivent la chaîne A en détail ; les pipelines B, C et D
réutilisent le même socle (scrape, overlay PIL, publication) et sont documentés
dans leurs sections propres. **Exploitation courante** (comptes, replanification,
contrôles) : voir la section 🎛️ plus bas.

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
# --- compte par defaut (pipeline A) ---
ZERNIO_API_KEY=sk_xxxxxxxx          # publication (etape 7)
ZERNIO_TIKTOK_ACCOUNT=xxxxxxxx      # accountId TikTok (GET /api/v1/accounts)
ZERNIO_IG_ACCOUNT=xxxxxxxx          # accountId Instagram (compte Business requis)
# --- un jeu par compte supplementaire, suffixe repris par --key ---
ZERNIO_API_KEY_BOUTIQUE=sk_xxxxxxxx
ZERNIO_TIKTOK_ACCOUNT_BOUTIQUE=xxxxxxxx
```

⚠️ **Pas de commentaire en fin de ligne.** `post.ts` lit tout ce qui suit le `=`
jusqu'au saut de ligne : un `# …` collé derriere une cle finirait dans sa valeur
et casserait l'authentification. Les commentaires vont **au-dessus**.

Zernio est **gratuit jusqu'a 2 comptes sociaux**, puis facture par palier
(6 $/compte de 3 a 10, 3 $ de 11 a 100, 1 $ au-dela).

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
| **studio** (artiste au micro) | s1 : 00-04, 08, 11, 14-19 · s2 : 12 reels | badge logo seul |
| **LE RÉCAP** (présentateur incrusté) | s1 : 05-07, 09, 10, 13 · s2 : 15 reels | badge + **coupe de l'intro** + rectangle de texte |
| **karaoke** | s1 : 12 | badge logo seul |

Sur les LE RÉCAP, un présentateur ouvre la vidéo, incrusté en bas du cadre avec
ses sous-titres brûlés, un tampon de date et un logo Snapchat ; puis il
disparaît et la vidéo passe sur les images avec un carton de sujet. On **coupe
toute son intro** — ce qui élimine du même coup le tampon et le logo Snapchat —
et on affiche son propos reformulé dans un rectangle de texte, pendant 4,5 s.

### Stocks

Une **vague de scraping = un stock**, isolé de bout en bout. On n'écrase jamais
un stock existant : `scrape-reels.ts` purge les mp4 absents du nouvel index, et
les noms de fichiers (`NN-shortcode.mp4`) servent de clé au journal
anti-doublon — re-scraper en place décalerait les `NN` et reposterait du déjà
publié.

| Stock | Librairie | Rendus | Config / légendes | Journal |
|---|---|---|---|---|
| 1 | `library/skyrockfm-stock1/` (20) | `out/skyrock/` | `config.json` / `captions_fr.json` | `posted.json` |
| 2 | `library/skyrockfm-stock2/` (31) | `out/skyrock2/` | `config2.json` / `captions_fr2.json` | `posted2.json` |

`render/skyrock/stock.py` résout ces chemins ; tous les scripts acceptent
`--stock N` (défaut 1).

```bash
# nouveau stock : scraper large, puis dédupliquer par shortCode contre l'ancien
npx tsx src/scrape-reels.ts skyrockfm 50 --lib library/skyrockfm-stock2

cd render/skyrock
python3 detect_logo.py --stock 2       # degrossit la zone du bandeau -> logos2.json
# -> ecrire config2.json (family par reel + reels ecartes)
python3 transcribe_recap.py --stock 2  # Whisper FR sur les LE RECAP -> recap_speech2.json
# -> completer config2.json (texte reformulé) et captions_fr2.json
python3 batch.py --stock 2             # rendu -> out/skyrock2/
```

**Point de coupe.** Le présentateur parle d'une traite depuis `t=0`, puis se
tait et la vidéo enchaîne sur les images. `cut_at()` garde donc la **première
salve continue** de Whisper (seuil de silence 0,8 s) — surtout pas `segs[-1]`,
car l'audio du contenu (interview, live) est lui aussi transcrit et emporterait
presque toute la vidéo. Reste un cas où même ça déborde, quand le contenu
enchaîne sans silence : la clé `cut` de `config.json` force alors la valeur.
Sur le stock 2, un reel sur 15 était dans ce cas (`45`, 9,2 s détectés contre
5,2 s réels) — **chaque coupe est vérifiée sur une planche avant/après avant de
rendre.**

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
incrustations. Sur le stock 2 c'est le cas des **12 reels studio sur 12** : le
micro est floqué SKYROCK et la bonnette bouge, donc aucun overlay statique ne
peut la couvrir. Assumé, comme sur le stock 1.

**Reels écartés du stock 2** (4 sur 31) : bandeau hors charte (Difool Radio
Libre), aucun bandeau à rebrander (dessins animés), décor physique SKYROCK plein
cadre. Les raisons sont dans `_comment` de `config2.json`.

**Publication** : `--project skyrock --key NEXUS` pour le stock 1,
`--project skyrock2 --key NEXUS` pour le stock 2 (même compte, journaux
séparés).

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

## 🎛️ Exploitation courante (comptes, replanification, contrôles)

### Qui poste quoi

Un compte Zernio par pipeline. **Aucun compte Instagram n'est rattaché aux trois
nouveaux workspaces** → ils publient sur TikTok uniquement (`post.ts` le détecte
seul). Les pseudos se ressemblent beaucoup : se fier au suffixe de clé, pas au
nom affiché (tous s'appellent « Le Mur Sonore »).

| Clé `.env` | TikTok | Pipeline | `--project` | Créneaux |
|---|---|---|---|---|
| `ZERNIO_API_KEY` | @lemursonore | A — sonotradehq | `fr` | 19h00 |
| `…_BOUTIQUE` | @lemursonoreee | B — rap.minute | `rapminute` | 12h30 |
| `…_NEXUS` | @lemursonoree | C — skyrockfm | `skyrock`, `skyrock2` | 12h00 + 18h30 |
| `…_LEMURSONORE` | @lemursonorefr | D — rvpfr | `rvpfr` | 21h00 |

Vérifier que deux clés ne pointent pas sur le même compte : comparer le
`platformUserId` (l'`openId` TikTok), **pas** `displayName`.

```bash
set -a; . ./.env; set +a
curl -s -H "Authorization: Bearer $ZERNIO_API_KEY_NEXUS" \
  https://zernio.com/api/v1/accounts | python3 -m json.tool | head -40
```

### Auditer la file

```bash
set -a; . ./.env; set +a
curl -s -H "Authorization: Bearer $ZERNIO_API_KEY_NEXUS" \
  "https://zernio.com/api/v1/posts?limit=200" > /tmp/z.json
python3 - <<'PY'
import json, datetime, collections
P = datetime.timezone(datetime.timedelta(hours=2))   # Paris ete
p = json.load(open("/tmp/z.json"))["posts"]
d = sorted(datetime.datetime.fromisoformat(x["scheduledFor"].replace("Z", "+00:00")).astimezone(P)
           for x in p if x["status"] == "scheduled")
print(collections.Counter(x["status"] for x in p))
print(f"{len(d)} programmes : {d[0]:%d/%m %H:%M} -> {d[-1]:%d/%m %H:%M}")
print("doublons de creneau :", len(d) - len(set(d)))
print("jours a != 2 posts :", {k: v for k, v in collections.Counter(f"{x:%d/%m}" for x in d).items() if v != 2})
PY
```

### Déplacer ou publier un post déjà créé

L'API accepte **`PUT /posts/:id`** (pas `PATCH`, qui répond 405). Le média reste
hébergé chez Zernio : on rejoue la date sans réuploader, et elle se propage au
niveau plateforme.

```bash
# decaler un post
curl -X PUT -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"scheduledFor":"2026-08-25T12:30:00","timezone":"Europe/Paris"}' \
  https://zernio.com/api/v1/posts/<ID>

# publier tout de suite un creneau rate
curl -X PUT -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"publishNow":true}' https://zernio.com/api/v1/posts/<ID>

# annuler
curl -X DELETE -H "Authorization: Bearer $KEY" https://zernio.com/api/v1/posts/<ID>
```

⚠️ Pour décaler **toute une série**, relire l'état **avant** chaque passe et
n'appliquer qu'une fois : un post déjà déplacé à la main sera redéplacé par la
passe globale et créera un doublon de jour (vu en vrai). Contrôler avec le script
d'audit ci-dessus juste après.

### Le premier post part demain, pas aujourd'hui

`post.ts` ancre la première date à **demain** (`baseDate()`). Pour démarrer le
jour même ou reprendre une file existante : `--start 2026-08-22`.

### Contrôler l'audio des sources

`scrape-reels.ts` teste la *présence* d'un flux audio, pas le *signal*. Un reel
peut arriver avec une piste vide (Instagram sert parfois un flux de 5 kb/s à
-91 dB quand la musique a été retirée) et passer le filtre. Avant de programmer :

```bash
for f in out/<projet>/*.mp4; do
  m=$(ffmpeg -hide_banner -i "$f" -af volumedetect -f null - 2>&1 | grep mean_volume)
  echo "$(basename $f) $m"
done          # < -60 dB = muet, a ecarter
```

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
.env                       APIFY_TOKEN + 4 cles Zernio (gitignore)
src/scrape-reels.ts        scrape + fallback yt-dlp (option --lib obligatoire)
src/post.ts                publie/programme via Zernio (--project / --key / --slots)

library/                   SOURCES, toutes gitignorees — un dossier par compte
  library/                   sonotradehq      (pipeline A)
  library/rapminute/         rap.minute       (pipeline B)
  library/skyrockfm-stock1/  skyrockfm vague 1 (pipeline C)
  library/skyrockfm-stock2/  skyrockfm vague 2 (pipeline C)
  library/rvpfr/             rvpfr            (pipeline D)

render/                    pipeline A (faux tweet -> FR) :
  detect.py                  detection bloc video (haut/bas)
  prep.py / augment_prep.py  prep.json + frames de lecture
  translations.json          titres FR (edite a la main)
  transcribe.py / transcribe_all.py   Whisper -> transcripts.json
  build_subs.py              table FR sous-titres -> subs_fr.json
  subtitles.py               decoupe cues + PNG sous-titres
  tweet_overlay.py           moteur d'overlay commun (header, footer, subs, emoji)
  batch.py                   rendu -> out/fr/
  posted.json                journal anti-doublon

render/rapminute/          pipeline B (DA violet fluo) :
  detect_green.py            pixels verts de marque  -> green.json
  detect_hook.py             bloc de texte complet   -> hooks.json
  hooks_fr.json              NOS hooks (a la main, *mot* = violet)
  hook_overlay.py            moteur bande + texte violet
  batch.py / verify.py       rendu -> out/rapminute/ ; controle 0 vert residuel

render/skyrock/            pipeline C (badge + coupe d'intro) :
  stock.py                   resolution des chemins par stock (--stock N)
  detect_logo.py             degrossit la zone du bandeau -> logos*.json
  transcribe_recap.py        Whisper FR sur les LE RECAP -> recap_speech*.json
  logo_overlay.py            badge LeMurSonore + rectangle de texte (FAMILY_BOX)
  batch.py                   rendu -> out/skyrock/ et out/skyrock2/
  config.json  / config2.json        family + texte reformule + cut (a la main)
  captions_fr.json / captions_fr2.json   legendes publiees (a la main)
  posted.json  / posted2.json        journaux anti-doublon (un par stock)

render/rvpfr/              pipeline D (filigrane bas-centre) :
  detect_logo.py             localise le filigrane -> logos.json
  logo_overlay.py            badge rond, overlay statique
  batch.py / verify.py       rendu -> out/rvpfr/
  captions_fr.json           legendes publiees (a la main)

montage/                   utilitaires ffmpeg (crop vertical) — reserve
out/                       RENDUS, tous gitignores :
  out/fr/  out/rapminute/  out/skyrock/  out/skyrock2/  out/rvpfr/
```
