# LUCID

LUCID is a single-user workbench that turns business evidence into a reviewed formal model, runs bounded deterministic decision solvers, and shows the evidence behind each result.

The current release implements Stage 2 T11–T19 locally. T20 remains the only open acceptance gate because it requires two live Agent-backed runs with real user materials.

## What the product does

```text
materials → Agent draft → human review → confirmed baseline
→ typed scenario/model → deterministic solve
→ candidates + explanation + provenance → what-if → compare → export
```

The product supports two bounded model families:

- training schedules: sessions, time slots, rooms, instructors, capacity, availability, skills, overlap, workload and explicit objectives;
- portfolio selection: budget, required items, conflicts and maximize-value ranking.

Unknown or unsupported semantics stay blocked as `model_invalid`. The system never invents a rule, schedule or number.

## Run locally

Requirements: Python 3.11+, Node.js 20+, and `uv` or `pip`.

```bash
./scripts/dev.sh
```

Or start the API and web app separately:

```bash
cd api
uv venv
uv pip install -r requirements.txt
uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8000 --reload

cd web
npm install
npm run dev
```

Open <http://127.0.0.1:5173/>. The API health check is <http://127.0.0.1:8000/api/health> and the non-secret provider status is <http://127.0.0.1:8000/api/readiness>.

## Provider configuration

The deterministic Stage 2 solvers do not need a model API. The Stage 1 Business Modeling Agent needs:

```text
LUCID_MODEL_NAME
LUCID_MODEL_BASE_URL
LUCID_MODEL_API_KEY
```

Complex-file understanding can additionally use Azure Content Understanding:

```text
AZURE_CONTENT_UNDERSTANDING_ENDPOINT
AZURE_CONTENT_UNDERSTANDING_KEY
```

Without these settings, the app reports a configuration blocker and does not manufacture an Agent draft. Copy `.env.example` to `.env`; never commit secrets.

## Main API path

| Step | Endpoint |
| --- | --- |
| Create project | `POST /api/projects` |
| Add text or file evidence | `POST /api/projects/{id}/materials/text` or `/materials/import` |
| Start Agent modeling | `POST /api/projects/{id}/modeling-runs` |
| Create scenario from confirmed baseline | `POST /api/projects/{id}/scenarios/from-baseline/{baseline_id}` |
| Create what-if revision | `POST /api/scenarios/{scenario_id}/what-if` |
| Preview impact | `POST /api/scenarios/{scenario_id}/impact-preview` |
| Solve training schedule | `POST /api/projects/{id}/solve-training-schedule` |
| Solve portfolio | `POST /api/projects/{id}/solve-portfolio` |
| Compare revisions | `GET /api/scenarios/{scenario_id}/compare` |
| Resume a stale solver run | `POST /api/projects/{id}/solve-runs/{run_id}/resume` |
| Export JSON/Markdown | `GET /api/projects/{id}/solve-runs/{run_id}/export.json` or `.md` |
| Delete material content | `DELETE /api/projects/{id}/materials/{material_id}` |

The web workbench exposes the same path through Materials, Modeling, Baseline and Results.

## Verification

Focused checks use isolated temporary databases and real FastAPI/SQLite paths:

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

The repository also contains Stage 1 intake and review verifiers. The current task status is in [specs/001-first-release/tasks.md](specs/001-first-release/tasks.md).

## Scope and boundaries

LUCID is intentionally single-user. It is not a collaboration platform, Agent console, universal optimizer, route planner, payment system or enterprise governance product. Importers preserve evidence; the Agent interprets it; the formal model and deterministic solver decide only within the supported typed families.

## Documentation

Start with [the documentation index](docs/README.md). The five current documents are:

- [Product baseline](docs/source/PRODUCT_BASELINE.md)
- [Agent and evidence architecture](docs/architecture/business-modeling-agent.md)
- [Current release status](docs/status.md)
- [First-release specification](specs/001-first-release/spec.md)
- [Task and acceptance status](specs/001-first-release/tasks.md)

Architecture decisions and historical reports remain available under `docs/adr/`, `docs/design/` and `docs/archive/`, but they are not additional current plans.
