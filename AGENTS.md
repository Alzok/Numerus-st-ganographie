# Repository Guidelines

## Project Structure & Module Organization
The repository is split between `backend/` (FastAPI service) and `frontend/` (Next.js UI). Core watermark primitives live in `backend/core/` (I/O helpers, metadata + overlay pipeline, metrics) and routes are registered in `backend/app.py`. The `frontend/app/` directory holds the main page shell and `frontend/components/` hosts reusable UI pieces. Docker orchestration is defined in `docker-compose.yml`, with developer shortcuts in the root `Makefile`.

## Build, Test, and Development Commands
`make up` rebuilds images and launches the stack (FastAPI on 8080, Next.js on 3000) with live reload. `make test` simply prints that no automated tests are available. `make lint` triggers Ruff and Black in check mode, while `make format` applies Black fixes. For frontend-only iterations you can run `docker compose run --rm frontend npm run dev` to start a fresh dev server without touching the backend service.

## Coding Style & Naming Conventions
Python code is formatted with Black (88-character lines, 4-space indents) and linted by Ruff; keep functions type-annotated and use snake_case for modules, variables, and function names. New watermark utilities should land under `backend/core/`, and additional FastAPI endpoints go through `backend/app.py`. TypeScript follows the Next.js ESLint defaults—match the existing two-space indentation, prefer PascalCase for React components, camelCase for hooks/utilities, and colocate UI primitives under `frontend/components/ui/`. Annotate client-side entry points with `"use client"` as in `frontend/app/page.tsx`.

## Testing Guidelines
Il n'existe pas de suite de tests automatisés ; documentez les vérifications manuelles pertinentes dans les PRs lorsque vous modifiez des flux sensibles.

## Commit & Pull Request Guidelines
Write commit messages in the imperative mood and focus each commit on a single concern. Rebase and resolve conflicts locally to keep history linear. Pull requests should include a concise summary, affected endpoints or UI areas, testing evidence (`make test`, manual checks), and relevant screenshots/GIFs for UI adjustments. Link issues when available and flag configuration changes that require rebuilding Docker images.

## Security & Configuration Tips
Keep secrets out of version control; Docker Compose already wires local development credentials. Backend PDF support depends on `poppler-utils`, so adjust `backend/Dockerfile` when new system packages are required and clear `/tmp` artifacts after experiments.
