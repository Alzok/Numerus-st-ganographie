# Watermark Tool

Mini-outil local pour cacher ou révéler un texte destiné aux IA de lecture de documents : le message est ajouté sous forme de calque quasi invisible (overlay léger pour les images, texte transparent pour les PDF). L'ensemble tourne en local via Docker, sans persistance.

## Fonctionnalités

- Interface web Next.js + React (design shadcn/UI) servie sur http://localhost:3000 avec rechargement à chaud.
- API REST :
- `POST /embed` — intègre un message et renvoie l'image PNG ou le PDF marqué + métriques (PSNR quand applicable, dimensions, etc.).
- `POST /extract` — lit le message caché (lecture directe des calques/metadata) et renvoie le texte décodé.
- Formats acceptés : PNG, JPEG, WebP ou PDF (≤ 10 Mo, côté max 4096 px, PDF ≤ 10 pages).
- Données injectées dans les metadata du PNG/PDF et doublées d'un calque texte totalement invisible (police minuscule, opacité très faible).
- Texte caché intégré sous forme de calque quasi invisible (overlay léger sur les images, calque texte transparent dans les PDF).
- Badge PSNR (pour les variantes PNG), téléchargement automatique, copie du texte extrait.
- Seed publique fixe (`123456`) afin que tout décodeur compatible puisse extraire le message sans information supplémentaire.

## Démarrage rapide

```bash
make up
```

Cela construit et lance le backend FastAPI (http://localhost:8080) et l'interface Next.js (http://localhost:3000). Le front tourne en mode `next dev` dans Docker : toute modification sous `frontend/` se recharge immédiatement, et le backend est servi avec `uvicorn --reload` pour un cycle rapide. L'ancienne route `/ui` signale désormais l'emplacement de la nouvelle interface.

## Commandes utiles

- `make build` – construit l'image Docker.
- `make test` – indique simplement qu'aucune suite automatisée n'est disponible.
- `make lint` – applique Ruff et Black en mode vérification.
- `make format` – formate le code backend avec Black.

## API

### POST /embed

Multipart `image`, `message`.

- Accept `application/json` →
  ```json
  {
    "file_base64": "...",        // ressource principale (PNG ou PDF selon l'entrée)
    "filename": "...",
    "mime": "image/png",
    "pdf_base64": "...",        // présent lorsque l'entrée est une image
    "pdf_filename": "...",
    "pdf_mime": "application/pdf",
    "psnr": 42.0,                // null pour les entrées PDF
    "width": 1024,
    "height": 768
  }
  ```
- Accept `image/png` → renvoie directement le PNG (cas d'entrée image).
- Accept `application/pdf` → renvoie directement le PDF (cas d'entrée image ou PDF).

### POST /extract

Multipart `image`.

Réponse JSON : `{ "message", "confidence", "page_index" }`.

## Notes et limites

- Conservez toujours l'image originale :
  - pour recalculer le PSNR,
  - pour réintégrer le filigrane après transformations lourdes.
- Aucune limite stricte sur la taille du message n'est imposée, mais rester sous quelques kilo-octets conserve un rendu totalement invisible.
- Pour préserver la fidélité, privilégiez une sortie PNG. Le front avertit lorsque l'entrée est lossy.
- Les PDF sont convertis page par page (max 10). Chaque page reçoit un calque texte transparent.
- La prise en charge PDF nécessite la présence de `poppler-utils` (binaire `pdftoppm`). Le Dockerfile l'installe par défaut.

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

## Risques connus

- Une recompression agressive (< 80) peut endommager le message.
- Les images très petites (< 128×128) offrent peu de capacité.
- Les conversions couleur multiples peuvent réduire le PSNR, d'où la recommandation en PNG.

Bon watermarking !
