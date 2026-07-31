# Fallback paroles (optionnel)

LRCLIB couvre la grande majorité des morceaux et ne demande **aucune
installation**. Ce dossier n'est utile que pour les cas où LRCLIB ne trouve
rien : `syncedlyrics` interroge en plus Musixmatch et Netease.

Le pipeline détecte tout seul si ce venv existe. S'il est absent, il le
signale et continue — la vidéo est simplement rendue sans paroles.

## Installation

```bash
cd py
uv venv
uv pip install -r requirements.txt
```

Environ 5 Mo de dépendances (`requests`, `beautifulsoup4`, `rapidfuzz`).
Aucune clé d'API, aucun modèle à télécharger.

## Vérifier

```bash
.venv/bin/python fetch_fallback.py --title "Get Lucky" --artist "Daft Punk"
```

Écrit du LRC sur la sortie standard, ou sort en code 1 si rien n'est trouvé.
