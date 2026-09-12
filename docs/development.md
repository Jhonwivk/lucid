# Development

## Prerequisites

Install Python 3.11 or newer, Node.js 20 or newer, and `uv` (or a compatible `pip`). The API uses FastAPI with SQLite; the web client is a Vite React application.

## Setup and run

The convenience script starts both services:

```bash
./scripts/dev.sh
```

For separate processes, install API dependencies in `api`, run Uvicorn on port 8000, then install web dependencies in `web` and run the Vite development server on port 5173. The root README contains the exact commands.

Copy `.env.example` to `.env` for local settings. Deterministic solving needs no provider credentials. Agent-backed modeling uses `LUCID_MODEL_NAME`, `LUCID_MODEL_BASE_URL` and `LUCID_MODEL_API_KEY`; optional Azure Content Understanding uses `AZURE_CONTENT_UNDERSTANDING_ENDPOINT` and `AZURE_CONTENT_UNDERSTANDING_KEY`. Never commit `.env` or credentials.

## Verification

Run focused API checks from the repository root:

```bash
python scripts/verify_t11_formalization.py
python scripts/verify_t11_material_lineage.py
python scripts/verify_t12_training_solver.py
python scripts/verify_t13_t14_t16.py
python scripts/verify_t14_portfolio_solver.py
python scripts/verify_t17_t19_solver_history.py
python scripts/verify_t19_material_delete.py
```

Build and lint the web client:

```bash
cd web
npm run build
npm run lint
```

The focused checks exercise materials, source lineage, baseline and scenario revisions, both deterministic solver families, export, recovery, deletion and project boundaries. A provider-free environment can verify the deterministic path; the release status records the remaining live Agent-backed acceptance gate.

## Contribution boundaries

Keep the FastAPI + React + SQLite architecture small. Importers preserve bytes and source spans; semantic interpretation belongs to the Business Modeling Agent. Solvers must return explicit states (`feasible`, `optimal`, `infeasible`, `unknown`, `model_invalid`) and must never invent unsupported results. Preserve project boundaries, provenance and scenario revisions.
