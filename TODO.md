# Rebuild Plan (from scratch)

## 1. Repository Skeleton
- [x] Recreate root layout (`backend/`, `frontend/`, `tmp/`, `README.md`, `Makefile`, `.gitignore`, `docker-compose.yml`).
- [x] Populate `.gitignore` with Python, Node, Docker, and editor artifacts.
- [x] Restore `README.md` (Watermark Tool description, structure, quick start, commands, API notes, etc.).

## 2. Backend (FastAPI service)
- [x] Recreate Python package structure (`backend/__init__.py`, `backend/app.py`, `backend/core/`, `backend/tests/`).
- [x] Under `backend/core/`, rebuild modules:
  - [x] `io_utils.py` (upload validation, PDF handling via pdf2image, encoding helpers).
  - [x] `logging_utils.py` (JSON log formatter).
  - [x] `metrics.py` (PSNR, bit accuracy, etc.).
  - [x] `wm_dwt_dct.py` (DWT+DCT watermark pipeline with fallback & optional imwatermark).
- [x] Recreate `backend/requirements.txt` (FastAPI, uvicorn, numpy, opencv-python, pywavelets, pdf2image, pillow, imwatermark optional, ruff, black, pytest, etc.).
- [x] Implement FastAPI app in `backend/app.py`:
  - [x] Logging config referencing `logging_utils`.
  - [x] Routes: `/healthz`, `/ui` (HTML redirect), `/embed` (watermark embedding), `/extract`, `/embed/capacity`.
  - [x] Shared validation helpers (strength, block size, seed).
- [x] Recreate tests in `backend/tests/` (roundtrip clean, after JPEG, PDF roundtrip, capacity checks).

## 3. Backend Containerization
- [x] Restore `backend/Dockerfile` (python:3.11-slim, deps for OpenCV & poppler-utils, non-root user, copy backend+frontend for imwatermark fallback, expose 8080).
- [x] Ensure requirements installed and permissions set (chown to app user).

## 4. Frontend (Next.js app)
- [x] Recreate Next.js project under `frontend/` with structure:
  - [x] `app/` (layout.tsx, page.tsx, globals.css).
  - [x] `components/ui/` (shadcn-style components: button, badge, card, input, label, select, spinner, textarea, tooltip, toast).
  - [x] `lib/utils.ts` (cn helper etc.).
  - [x] `public/` assets (logo if any).
  - [x] Config files: `package.json`, `package-lock.json`, `tsconfig.json`, `tailwind.config.ts`, `postcss.config.js`, `next.config.mjs`, `next-env.d.ts`.
- [x] Implement watermark UI per original behaviour:
  - [x] Upload (drag/drop) supporting PNG/JPEG/WebP/PDF, preview logic.
  - [x] Modes `embed`/`extract` with form controls (seed, strength, block size select, message textarea with capacity feedback).
  - [x] Toast + Tooltip providers, fetch logic to backend endpoints, download of results.
  - [x] Capacity pre-check (uses `/embed/capacity` to clamp message, display info, disable submit if insufficient).
  - [x] Extraction view with confidence badge, copy button.
- [x] Restore styling (Tailwind, shadcn classes, French text labels).
- [x] Recreate `frontend/Dockerfile` (node:20-alpine, install deps, run dev server).

## 5. Docker & Tooling
- [x] Recreate `docker-compose.yml` with services `backend` and `frontend`, volumes for hot reload, environment vars (NEXT_PUBLIC_API_BASE_URL, NODE_ENV, CHOKIDAR_USEPOLLING, PYTHONPATH, etc.).
- [x] Restore root `Makefile` targets (`up`, `build`, `test`, `lint`, `format`).
- [ ] Ensure `make test` runs `docker compose run --rm backend pytest -q`, lint uses ruff & black, format uses black.

## 6. Linting & Formatting
- [ ] Re-add tooling configs if any (e.g., ruff config, editorconfig). If not previously separate, embed rules in commands.
- [ ] Verify `make lint` and `make format` operate successfully after code restoration.

## 7. Documentation & Guides
- [ ] Update/restore `AGENTS.md` (Repository Guidelines) with accurate instructions about structure, commands, style, testing, PR etiquette.
- [ ] Confirm README quick-start (`make up`, API description) matches rebuilt stack.

## 8. Verification
- [ ] Run `make up` to ensure Docker stack boots (backend 8080, frontend 3000).
- [ ] Manually test:
  - [ ] Embed small PNG (short message) -> download result, verify PSNR.
  - [ ] Embed + extract with PDF multi-page.
  - [ ] Capacity feedback for tiny image (should warn/disallow).
  - [ ] Extract existing watermark (UI path).
- [ ] Run `make test`, `make lint`, `make format` locally and confirm success.

## 9. Version Control & Delivery
- [ ] Stage all restored files, review diffs.
- [ ] Commit with clear message (ex: "Restore project scaffold and capacity tooling").
- [ ] Prepare PR description summarizing rebuild steps and tests executed.

---
Chaque case devra être cochée au fur et à mesure durant la reconstruction.
