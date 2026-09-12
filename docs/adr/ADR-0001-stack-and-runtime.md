# ADR-0001 — Stack and runtime

- Status: Accepted
- Date: 2026-09-11
- Deciders: LUCID M0 bootstrap (T01)

## Context

LUCID needs a polished local web workbench that can later:

- persist projects / understanding / scenarios / results locally
- ingest documents and tables
- call Python-based optimization / constraint solvers
- start simply for demos

M0 must establish a **real** runnable baseline — not a throwaway static mock.

## Decision

Use a small two-process local stack:

| Concern | Choice | Why |
| --- | --- | --- |
| UI | **Vite + React + TypeScript** | Fast local DX, modern responsive GUI, durable component/CSS system for later workspaces |
| API | **FastAPI (Python)** | Natural home for document ingestion helpers and OR-Tools / PuLP / similar solvers |
| Persistence | **SQLite** file under `data/` | Zero-ops local persistence; sufficient for single-user MVP |
| Routing (UI) | React Router | Simple client routes for landing + four workspaces |
| Dev proxy | Vite → `127.0.0.1:8000` | One browser origin during development |

### Actual versions installed at M0 bootstrap

Recorded during verification (may drift as lockfiles update):

- Node.js: v26.8.1 / npm 11.11.0
- `react` / `react-dom`: 19.3.0
- `react-router-dom`: 7.18.3
- `vite`: 8.3.0
- `typescript`: 6.0.3
- `@vitejs/plugin-react`: 6.1.1
- `oxlint`: 1.82.0
- `fastapi`: 0.141.1
- `uvicorn`: 0.52.4
- Python venv: CPython 3.12.11 via `uv`

### Local URLs

- Web: `http://127.0.0.1:5173/`
- API: `http://127.0.0.1:8000/`
- Health: `http://127.0.0.1:8000/api/health`

### Launch commands

```bash
# API
cd api && source .venv/bin/activate
uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8000 --reload

# Web
cd web && npm run dev
```

## Alternatives considered

1. **Next.js full-stack** — fewer processes, but Python solver integration becomes a sidecar anyway; adds framework weight for a local workbench.
2. **SPA + Node API only** — weak fit for OR-Tools and scientific Python ingestion libraries.
3. **Desktop shell (Electron/Tauri)** — unnecessary packaging complexity for M0 demos.
4. **Static HTML mock** — rejected; would be replaced wholesale in T03/T04.

## Consequences

- Agents extend `api/` and `web/` instead of rescaffolding.
- SQLite schema/contracts land in T03 without changing the runtime shape.
- Solver work stays in Python and is exposed through API endpoints.
- CORS is limited to local Vite origins; production packaging can collapse to a single host later if needed.

## Non-decisions (intentionally deferred)

- AuthN/AuthZ (single-user local)
- Object storage / cloud DB
- Worker queues / microservices
- LLM / understanding-model provider selection (T09; not a Materials intake concern)
