# LUCID

Single-user **business-modeling workbench** (Stage 1: reviewed baseline + pre-solver handoff).

LUCID turns a decision question and whatever materials you already have into a source-grounded modeling draft for human review, then a confirmed baseline. It does **not** present unverified AI interpretation as business truth, and it does **not** run a solver in Stage 1.

Current docs: [docs/README.md](docs/README.md). Visual direction: [DESIGN.md](DESIGN.md) (Notion DESIGN.md fetched 2026-09-12 and adapted; not a marketing clone). Delivery summary: [docs/reports/stage1-handoff.md](docs/reports/stage1-handoff.md).

## Scope (MVP)

In scope:

- finite resource allocation / scheduling (primary vertical slice)
- finite portfolio / combination selection
- replanning / condition comparison across those families

Out of scope for MVP:

- multi-user collaboration, orgs, roles, invitations, approvals
- Agent orchestration console / AI coding product
- enterprise knowledge platform or universal strategy optimizer
- automatic enterprise governance, external execution, payments

## Stack

| Layer | Choice |
| --- | --- |
| Web UI | Vite + React + TypeScript |
| API | FastAPI (Python) |
| Persistence | SQLite (`data/lucid.db`) |
| Solver path (later) | Python OR-Tools / similar via the API |

See [docs/adr/ADR-0001-stack-and-runtime.md](docs/adr/ADR-0001-stack-and-runtime.md).

## Quick start

Prerequisites: Node.js 20+, Python 3.11+ (3.12 recommended), `uv` or `pip`.

```bash
# API
cd api
source .venv/bin/activate   # created during bootstrap; or: uv venv && uv pip install -r requirements.txt
uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8000 --reload

# Web (separate terminal)
cd web
npm install
npm run dev
```

Or from the repo root:

```bash
./scripts/dev.sh
```

- Landing / product shell: **http://127.0.0.1:5173/** (redirects to My Analyses)
- My Analyses: **http://127.0.0.1:5173/analyses**
- Workbench: **http://127.0.0.1:5173/analyses/:projectId/materials** (also `/modeling`, `/baseline`, `/results`; `/understanding` and `/scenarios` redirect)
- API health: **http://127.0.0.1:8000/api/health**
- Readiness (non-secret presence only): **http://127.0.0.1:8000/api/readiness**
- Persistence: SQLite file `data/lucid.db` (schema 4 after Stage 1). Optional demo seed: `POST http://127.0.0.1:8000/api/dev/seed-demo`.
- Composer: `POST /api/analyses/start` with `{ "title", "question", "text"? }`. A non-blank question is enough.
- Modeling: `POST /api/projects/{id}/modeling-runs`. Missing live model config fails honestly (`model_not_configured`); it does not emit a fake draft.
- Templates (T05): `GET /api/templates` lists six bilingual fixtures. `POST /api/templates/{id}/instantiate`. UI language is `en` / `zh-CN`.
- Import: peer Materials including `.json` / `.docx` / `.pptx` as raw files for Azure. Direct text: `POST /api/projects/{id}/materials/text`. Files: `POST /api/projects/{id}/materials/import`. Limit 12 MiB. No PDF OCR.

## Repository map

```
lucid/
  api/                 FastAPI service + SQLite bootstrap
  web/                 Vite React workbench UI
  data/                Local SQLite database (gitignored contents)
  docs/                 Current Stage 1 docs (see docs/README.md)
  DESIGN.md            Stage 1 visual direction (Notion DESIGN.md fetched 2026-09-12, adapted)
  specs/001-first-release/  Spec, plan, acceptance, tasks
  scripts/             Local demo helpers
  AGENTS.md            Agent working agreements
```

## Product docs

- [Docs index](docs/README.md)
- [Product baseline](docs/source/PRODUCT_BASELINE.md)
- [Business Modeling Agent](docs/architecture/business-modeling-agent.md)
- [Stage 1 handoff](docs/reports/stage1-handoff.md)
- [Stage 1 review](docs/reports/stage1-review.md)
- [Stage 1 acceptance](docs/reports/stage1-acceptance.md)
- [DESIGN.md](DESIGN.md)
- [Stack ADR](docs/adr/ADR-0001-stack-and-runtime.md)
- [Persistence ADR](docs/adr/ADR-0002-persistence-contract.md)
- [T05 i18n + templates](docs/design/T05-i18n-templates.md)
- [First-release spec](specs/001-first-release/spec.md)
- [Task plan](specs/001-first-release/tasks.md)

## Persistence (T03)

Local SQLite contract for AnalysisProject, material metadata, source spans, versioned understanding/baselines, rules, scenarios, formal-model metadata, SolveRun records, result-candidate metadata, and change history.

- Unknown costs / permissions / capacities stay SQL `NULL` (never coerced to `0` / `false`).
- Edits create new revisions; historical snapshot rows are not rewritten.
- SolveRun stores state labels only. The solver is still **not** implemented (`claimed_execution` is always false).
- Proof helper: `python scripts/verify_t03_persistence.py` (uses a temp DB).

Useful endpoints:

| Method | Path |
| --- | --- |
| POST/GET | `/api/projects` |
| GET/PATCH | `/api/projects/{id}` |
| POST/GET | `/api/projects/{id}/materials` |
| POST | `/api/projects/{id}/materials/import` |
| POST | `/api/projects/{id}/materials/text` |
| GET | `/api/projects/{id}/source-spans` |
| POST | `/api/projects/{id}/understandings` |
| GET | `/api/understandings/{id}` |
| POST/GET | `/api/projects/{id}/scenarios` |
| POST | `/api/scenarios/{id}/revisions` |
| POST/GET | `/api/projects/{id}/solve-runs` |
| POST | `/api/dev/seed-demo` |
| GET | `/api/templates` |
| POST | `/api/templates/{id}/instantiate` |

See [docs/adr/ADR-0002-persistence-contract.md](docs/adr/ADR-0002-persistence-contract.md).

## Templates (T05)

Six auditable fictional mixed-material fixtures live under `fixtures/templates/`. Instantiation seeds T03 persistence from the authored `template.json` manifest and copies honest file metadata (byte size, SHA-256) from the real fixture bytes.

This built-in template loader is **not** the general import pipeline. General intake is T06–T08 (`POST /api/projects/{id}/materials/import` and `POST /api/projects/{id}/materials/text`). Templates still do not extract business semantics with an LLM. Independent counts and honesty checks live in each `expected.json`. Proof helper: `python scripts/verify_t05_templates.py` (uses a temp DB).

| Template | Sources |
| --- | --- |
| Training Schedule / 培训排程 | Markdown + CSV + PDF |
| Vehicle Validation Bench / 整车验证台架排程 | XLSX + PDF + PNG |
| Factory Maintenance Window / 工厂检修窗口排程 | CSV + Markdown + PNG |
| Supplier Capacity Allocation / 供应商产能分配 | XLSX + CSV + PDF |
| Product Portfolio Selection / 产品组合选择 | JSON + Markdown |
| Retail Campaign Slotting / 零售活动档期组合 | CSV + JSON + TXT |

## Materials (T06–T08)

Materials workspace records a non-empty **Evidence Set**. PDF, TXT/Markdown, CSV/XLSX, images, JSON/DOCX/PPTX (raw), and **direct user-entered text** are optional peers. No source type is mandatory. T09/T10 (Stage 1 Agent + review) consume this Evidence Set. Importers still do not extract business meaning.

- Direct text: `POST /api/projects/{project_id}/materials/text` with JSON `{ "text": "...", "label": "optional source label" }`. Stored as `kind=document`, `media_type=text/plain`, UTF-8 bytes/checksum, `source_origin=direct_text`. The `filename` column is a compatibility/source-label field.
- Files: `POST /api/projects/{project_id}/materials/import` (multipart field name `file`)
- Limit: **12 MiB** per item; tables also have a 5000-row / 25000-cell safety budget
- Persistence: copied bytes under `data/materials/{project_id}/` with a UUID-prefixed stored name
- Provenance: SourceSpan rows (`text_range` for text; 1-based `page` for PDF; `sheet` + A1 `cell_ref` for tables; one full-image `region` for images)
- CSV/XLSX: blank cells stay blank/unknown; formulas are stored as formula text and are not recalculated; unit hints are copied only from explicit header/value forms
- Images: PNG/JPEG bytes, Pillow-validated dimensions/format/mode/checksum, and exactly one honest full-image region (`x=0,y=0,width=1,height=1`, `region_state=full_image`). Semantic understanding is **not** performed during intake. No Grok/xAI/macOS Vision/OCR call.
- Not in T06–T08: LLM business understanding, RAG, solver execution, legacy `.xls`
- Encrypted PDFs and malformed files are rejected (4xx), not decrypted
- Proof helpers: `python scripts/verify_t06_import.py`, `python scripts/verify_t07_tables.py`, `python scripts/verify_t08_images.py`, `python scripts/verify_material_abstraction.py`

## Status

M0–M2 (T01–T08) remain verified.

**Stage 1 (T09/T10 mapping):** one Business Modeling Agent, one Azure Content Understanding tool, human review, confirmed baseline export, bilingual workbench. No solver. LIVE Agent/Azure runs require local `LUCID_MODEL_*` and Azure CU settings.

T11–T20 are **not** implemented. Do not treat SolveRun metadata or an Agent draft as an executed schedule.
