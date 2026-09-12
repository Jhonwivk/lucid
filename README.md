# LUCID

LUCID is a single-user business-modeling and deterministic decision workbench. It turns business evidence into a reviewed baseline, a typed scenario, and auditable solver results with explanations and provenance.

The product path is:

```text
Materials → Business Modeling Agent → human review → confirmed baseline
→ typed formal scenario → deterministic solve → compare / what-if / export
```

## What you can do

- collect text and uploaded evidence while preserving checksums, source spans and deletion state;
- review source-linked claims from one Business Modeling Agent and confirm a baseline;
- model and solve finite training schedules or portfolio selections with bounded deterministic algorithms;
- inspect ranked candidates, explanations, source provenance, revision comparisons and exports;
- create what-if revisions without changing the confirmed baseline.

Unknown or unsupported semantics remain visible and blocked as `model_invalid`. The application never invents a rule, schedule or number.

## Run locally

Requirements: Python 3.11+, Node.js 20+, and `uv` or `pip`.

```bash
./scripts/dev.sh
```

To start the services separately:

```bash
cd api
uv venv
uv pip install -r requirements.txt
uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8000 --reload

cd web
npm install
npm run dev
```

Open <http://127.0.0.1:5173/>. The API health check is <http://127.0.0.1:8000/api/health> and non-secret provider readiness is <http://127.0.0.1:8000/api/readiness>.

## Provider configuration

Deterministic solvers run without a model API. Agent-backed modeling requires:

```text
LUCID_MODEL_NAME
LUCID_MODEL_BASE_URL
LUCID_MODEL_API_KEY
```

Complex-file understanding can additionally use:

```text
AZURE_CONTENT_UNDERSTANDING_ENDPOINT
AZURE_CONTENT_UNDERSTANDING_KEY
```

Copy `.env.example` to `.env`; never commit secrets. When provider settings are absent, the app reports a configuration blocker and does not fabricate a draft.

## Verify

Focused checks use temporary SQLite databases and real FastAPI paths:

```bash
python scripts/verify_t11_formalization.py
python scripts/verify_t11_material_lineage.py
python scripts/verify_t12_training_solver.py
python scripts/verify_t13_t14_t16.py
python scripts/verify_t14_portfolio_solver.py
python scripts/verify_t17_t19_solver_history.py
python scripts/verify_t19_material_delete.py
cd web && npm run build && npm run lint
```

See [docs/development.md](docs/development.md) for setup, environment variables and the complete local verification path. The current release gate and known limits are in [docs/release-status.md](docs/release-status.md).

## Documentation

- [Documentation index](docs/README.md)
- [Product baseline](docs/product-baseline.md)
- [Architecture and data flow](docs/architecture.md)
- [Development and verification](docs/development.md)
- [Release status and known limits](docs/release-status.md)

LUCID deliberately stays single-user. It is not a collaboration platform, Agent console, universal optimizer, route planner or enterprise governance product.
