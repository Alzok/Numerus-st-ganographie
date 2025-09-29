# Watermark Tool

Mini-outil local pour intégrer ou extraire un texte caché dans une image en utilisant un filigrane fréquentiel (DWT + DCT). L'ensemble tourne en local via Docker, sans persistance.

## Fonctionnalités

- Interface web Next.js + React (design shadcn/UI) servie sur http://localhost:3000 avec rechargement à chaud.
- API REST :
  - `POST /embed` — intègre un message et renvoie l'image PNG ou le PDF marqué + métriques (PSNR, dimensions, nombre de pages).
  - `POST /extract` — extrait le message caché et renvoie la confiance calculée via CRC32.
- Formats acceptés : PNG, JPEG, WebP ou PDF (≤ 10 Mo, côté max 4096 px, PDF ≤ 10 pages).
- Paramètres contrôlables : `seed`, `strength` (0.1–2.0), `block_size` (pair).
- Badge PSNR, téléchargement automatique, copie du texte extrait.
- Filigrane répliqué automatiquement (jusqu'à ×3) pour renforcer la détection après recompression.
- Fallback interne si `imwatermark` est indisponible (PyWavelets + OpenCV DCT).

## Démarrage rapide

```bash
make up
```

Cela construit et lance le backend FastAPI (http://localhost:8080) et l'interface Next.js (http://localhost:3000). Le front tourne en mode `next dev` dans Docker : toute modification sous `frontend/` se recharge immédiatement, et le backend est servi avec `uvicorn --reload` pour un cycle rapide. L'ancienne route `/ui` signale désormais l'emplacement de la nouvelle interface.

## Commandes utiles

- `make build` – construit l'image Docker.
- `make test` – exécute la suite Pytest (round-trip et JPEG atténué).
- `make lint` – applique Ruff et Black en mode vérification.
- `make format` – formate le code backend avec Black.

## API

### POST /embed

Multipart `image`, `message`, `seed`, `strength`, `block_size`.

- Accept `application/json` → `{ "file_base64", "mime", "psnr", "width", "height", ... }`.
- Accept `image/png` → renvoie directement le PNG en téléchargement.
- Accept `application/pdf` → renvoie directement le PDF en téléchargement.

### POST /extract

Multipart `image`, `seed`, `block_size`.

Réponse JSON : `{ "message", "confidence", "backend", "crc_ok", "page_index" }`.

## Notes et limites

- Conservez toujours l'image originale :
  - pour recalculer le PSNR,
  - pour réintégrer le filigrane après transformations lourdes.
- Le message maximal recommandé est de 4096 octets (limite interne).
- Pour préserver la fidélité, privilégiez une sortie PNG. Le front avertit lorsque l'entrée est lossy.
- Les PDF sont convertis page par page (max 10). Chaque page est filigranée avec le même message.
- La prise en charge PDF nécessite la présence de `poppler-utils` (binaire `pdftoppm`). Le Dockerfile l'installe par défaut.
- Performance validée : message de 128 caractères intégré dans une image 1920×1080 en < 2 s sur CPU standard.
- Après recompression JPEG qualité 85, ≥ 90 % des bits sont récupérés (test automatique `test_roundtrip_after_jpeg`).

## Structure

```
watermark-tool/
├── backend/
│   ├── app.py
│   ├── core/
│   │   ├── io_utils.py
│   │   ├── logging_utils.py
│   │   ├── metrics.py
│   │   └── wm_dwt_dct.py
│   ├── tests/
│   │   └── test_roundtrip.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/ui/
│   │   └── ...
│   ├── Dockerfile
│   ├── next.config.mjs
│   ├── package.json
│   └── tailwind.config.ts
├── docker-compose.yml
├── Makefile
└── README.md
```

## Qualité et sécurité

- Les uploads sont validés (taille, type MIME, dimensions) et redimensionnés si besoin.
- Les logs uvicorn utilisent un format JSON minimal (`backend/core/logging_utils.py`).
- Les opérations lourdes sont exécutées hors boucle événementielle avec un timeout de 15 s.
- Les fichiers temporaires résident dans `/tmp` (monté dans `docker-compose.yml`).
- Le service frontend monte `frontend/` et dispose d'un volume `node_modules` dédié ; `npm install` se lance automatiquement à chaque démarrage de conteneur pour garantir les dépendances du hot reload.

## Tests

La suite Pytest couvre :

1. Round-trip propre (message identique, PSNR ≥ 38 dB).
2. Extraction après recompression JPEG qualité 85 avec ≥ 90 % de précision binaire.

Exécuter :

```bash
make test
```

## Risques connus

- Une recompression agressive (< 80) peut endommager le message.
- Les images très petites (< 128×128) offrent peu de capacité.
- Les conversions couleur multiples peuvent réduire le PSNR, d'où la recommandation en PNG.

Bon watermarking !
