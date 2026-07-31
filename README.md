# AutoTiktokVideos

Pipeline local de génération de vidéos verticales 1080×1920 : des plans vidéo
muets, la bande-son studio d'un morceau, ses paroles allumées mot par mot en
néon, et un effet de pluie.

100 % local. Aucune API payante, aucune clé.

---

## Principe

Le son des vidéos sources est **entièrement supprimé**. La seule bande-son est
celle du morceau, prise dans sa **version studio** — ce qui est la clé de tout
le reste : les timings de LRCLIB sont calés sur cet enregistrement, donc
directement exploitables sans aucun forced alignment.

```
0s                    10s                   20s
├──── plan artiste ────┤──── ville nuit ────┤
│                   fondu noir              │
├───────── pluie (continue) ────────────────┤
├───────── musique studio (continue) ───────┤
├───────── paroles néon mot-à-mot ──────────┤
```

Le nombre de plans et leurs durées sont libres ; 10 + 10 n'est que l'exemple.

---

## Prérequis

| Outil | Rôle |
|---|---|
| Node ≥ 20 | orchestrateur et Remotion |
| `yt-dlp` | téléchargement (`brew install yt-dlp`) |
| `ffmpeg` / `ffprobe` | découpe et recadrage |
| Python 3.10+ | **optionnel**, uniquement pour le fallback paroles |

---

## Utilisation

```bash
npm install
npm run run -- configs/example.json
```

Le MP4 sort dans `out/<slug>.mp4`.

### Reprendre à une étape

Chaque étape détecte ses propres sorties et passe son tour. Pour itérer sur le
style sans retélécharger :

```bash
npm run run -- configs/example.json --from 4     # rendu seul
npm run run -- configs/example.json --only 3     # paroles seules
npm run run -- configs/example.json --force      # ignore le cache
```

### Prévisualiser dans le Studio

```bash
npm run dev
```

Change `slug` dans les props pour ouvrir n'importe quel run déjà préparé.

### Étapes isolées

```bash
npm run step:download -- configs/example.json
npm run step:cut      -- configs/example.json
npm run step:lyrics   -- configs/example.json
npm run step:render   -- configs/example.json
```

---

## Le fichier de config

```jsonc
{
  "slug": "artiste-morceau",

  // Doit pointer vers la version STUDIO : clip officiel ou chaîne "- Topic".
  // Avec un live, les timings LRCLIB ne correspondront pas.
  "music": { "url": "https://…", "start": "01:12.0", "end": "01:32.0" },

  // Autant de plans que voulu, dans l'ordre. Leur son est toujours supprimé.
  "clips": [
    { "label": "artiste",  "url": "https://…", "start": "02:10", "duration": 10 },
    { "label": "ville",    "url": "https://…", "start": "00:35", "duration": 10 }
  ],

  "transition": { "fadeToBlackSec": 0.6 },

  "track": {
    "title": "…",
    "artist": "…",
    "lang": "fr",
    "lrclibId": null      // à renseigner si LRCLIB se trompe de version
  },

  "lyrics": {
    "wordsPerPage": 3,
    "maxLineDurationSec": 6,
    "uppercase": true
  },

  "style": {
    "neonColor": "#00E5FF",
    "idleColor": "#FFFFFF",
    "idleOpacity": 0.35,
    "fontSize": 110,
    "bottomOffset": 420,
    "maxWidthPct": 0.72,  // largeur max : au-delà, l'interface TikTok recouvre
    "bottomScrim": 0.55,
    "fontFile": null      // ex. "theboldfont.ttf" déposé dans public/fonts/
  },

  "rain": {
    "enabled": true,
    "style": "onScreen",  // "onScreen" = gouttes sur l'objectif | "falling" = averse
    "intensity": 0.6,
    "angleDeg": 12,       // n'a d'effet qu'en mode "falling"
    "opacity": 0.5
  },

  "fps": 30
}
```

Les temps acceptent `92`, `"1:32"`, `"01:32.500"` ou `"00:01:32.500"`.

---

## Comment ça marche

### 1 · Téléchargement — `src/pipeline/1-download.ts`

`yt-dlp --download-sections` ne tire que la fenêtre utile plus 2 s de marge de
chaque côté. Sur un concert d'une heure cela fait quelques Mo au lieu de
plusieurs Go. La coupe est exacte à la frame (vérifié : 14.000000 s demandées,
14.000000 s obtenues).

Les plans visuels sont téléchargés en `-f bv*` — piste vidéo seule, leur son
n'est jamais rapatrié.

### 2 · Découpe — `src/pipeline/2-cut.ts`

Agrandissement jusqu'à couvrir le cadre puis rognage centré :
`scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920`.
Une source 16:9 perd donc beaucoup sur les côtés, c'est attendu en vertical.

L'audio sort en WAV plutôt qu'en AAC : pas de délai d'amorçage, donc pas de
décalage de quelques millisecondes entre le son et les paroles.

### 3 · Paroles — `src/pipeline/3-lyrics.ts`

On ne transcrit **jamais**. Le texte affiché vient toujours de vraies paroles.

1. **LRCLIB** (`/api/get`, sinon `/api/search`). Attention : le classement de
   `/api/search` est purement textuel et remonte volontiers des remixes de dix
   minutes avant l'original — d'où le rescoring maison dans `lrclib.ts`, qui
   pénalise `remix`, `live`, `sped up`… Si l'heuristique se trompe quand même,
   les candidats alternatifs sont affichés dans les logs et `track.lrclibId`
   permet d'épingler le bon.
2. **Fallback** `syncedlyrics` si LRCLIB n'a rien (voir `py/README.md`).
3. **Ligne → mot** : LRCLIB ne donne qu'un timestamp par ligne. La durée de
   chaque ligne est répartie entre ses mots **au prorata des syllabes** — un
   mot de trois syllabes tient l'écran plus longtemps qu'un monosyllabe, ce qui
   colle nettement mieux au chant qu'une répartition au nombre de caractères.

Deux garde-fous :

- `maxLineDurationSec` empêche une ligne suivie d'un pont instrumental
  d'étirer ses mots sur trente secondes.
- La pagination est **équilibrée** : sept mots par paquets de trois donnent
  3+2+2 et non 3+3+1, pour ne jamais laisser un mot orphelin à l'écran.

Sortie : `public/runs/<slug>/lyrics/words.json`, qui contient à la fois les
pages prêtes à afficher et un tableau au format `Caption` de
`@remotion/captions`.

### 4 · Rendu — `src/remotion/`

Adapté de `remotion-dev/template-tiktok`. Sa transcription Whisper (`sub.mjs`,
`whisper-config.mjs`) a été retirée au profit des paroles connues, et son
`Page.tsx` — qui comparait déjà le temps courant aux bornes de chaque token —
sert de base au néon.

Empilement, du fond vers l'avant :

```
fond noir → plans vidéo → pluie → dégradé de lisibilité → paroles
```

La pluie passe **derrière** le texte : devant, ses traînées claires traversent
les lettres et brouillent le halo.

- **`NeonWord.tsx`** — cinq `text-shadow` de rayons croissants autour d'un cœur
  blanc : les petits rayons donnent le trait lumineux, les grands la diffusion
  dans l'air. Un `spring` à l'allumage imite l'amorçage d'un tube, et une
  oscillation lente évite le halo parfaitement figé.
- **`RainOverlay.tsx`** — deux rendus. `onScreen` (défaut) simule des gouttes
  **sur l'objectif** : impact, adhérence à la vitre, glissement des plus
  grosses avec traînée, et réfraction via `backdrop-filter` — c'est ce flou
  d'arrière-plan qui donne l'impression de voir l'image *à travers* la goutte.
  Aucune ombre interne sombre n'est appliquée : sur un plan nocturne elle
  transformerait la goutte en pastille grise, alors que de l'eau ne se voit
  qu'à son liseré lumineux et à ce qu'elle déforme. `falling` rend l'averse
  classique vue de loin.

  Dans les deux cas les gouttes sont tirées via `random()` de Remotion, jamais
  `Math.random()` : la position ne dépend que du numéro d'image, donc n'importe
  quelle image peut être calculée seule. C'est indispensable au rendu
  multi-processus, sinon la pluie scintille au lieu de tomber.
- **`Root.tsx`** — la composition n'est pilotée que par `slug` ;
  `calculateMetadata` relit les manifestes des étapes 2 et 3 pour en déduire
  plans, bande-son, paroles et durée. C'est ce qui permet d'ouvrir un run dans
  le Studio sans repasser par l'orchestrateur.

La durée finale s'aligne sur le plus court entre le visuel et la musique : ni
musique qui continue sur du noir, ni image qui tourne dans le silence.

---

## Police

Par défaut une police système grasse (`Impact`), pour un rendu identique hors
ligne. Pour autre chose, dépose un `.ttf` dans `public/fonts/` et renseigne
`style.fontFile` — il sera chargé via `FontFace` avant la première mesure de
texte.

---

## Arborescence

```
configs/            les fichiers de config
src/pipeline/       une étape = un fichier, + run.ts (orchestrateur)
src/remotion/       la composition
py/                 fallback paroles (optionnel)
public/runs/<slug>/ fichiers de travail, servis par Remotion
out/<slug>.mp4      le résultat
```

`public/runs/` grossit vite : chaque run garde ses téléchargements et ses
segments pour permettre de reprendre à une étape. Supprime le dossier d'un run
quand tu n'en as plus besoin.
