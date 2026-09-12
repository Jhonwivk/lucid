# Stage 1 handoff

Date: 2026-09-12. Workspace: `/Users/hairen/project/lucid`.  
Observed assistant: Cursor Grok 4.6. A worker exit code is not product acceptance.

This is the authoritative Stage 1 delivery summary. Historical notes under `/Users/hairen/project/.tasks/` are execution records, not a second spec.

## What this slice completed

- One Business Modeling Agent (LangChain `create_agent` + LangGraph SQLite checkpointer + Pydantic draft + one Azure Content Understanding tool) on the existing FastAPI/SQLite/React app.
- Equal Materials: a non-blank decision question is enough; files are optional peers.
- Human review (accept / edit / reject / not_applicable), immutable freeze, JSON + Markdown pre-solver export.
- Public product path never runs `AdaptiveScriptModel`. Missing `LUCID_MODEL_*` fails honestly.
- Workbench UI adapted from the fetched Notion DESIGN.md (workbench language only).
- First-stage regression, contract tests, six-template public intake, and a browser walkthrough.

Not done: live model/Azure runs, solver, T11–T20.

## Main files changed (this wrap-up)

Backend: `api/app/modeling/export.py`, `persistence.py`, `modeling_routes.py`, `.gitignore`, `scripts/verify_stage1_review_findings.py`, `scripts/verify_stage1_template_intake.py`.

UI: `web/src/index.css`, `App.css`, `i18n.tsx`, `lib/format.ts`, `api/client.ts`, `AnalysesPage.tsx`, `WorkbenchPage.tsx`, `SourceViewer.tsx`, `ModelingWorkspace.tsx`, `MaterialsWorkspace.tsx`, `BaselineWorkspace.tsx`, `ResultsWorkspace.tsx`.

Docs: `DESIGN.md`, `docs/README.md`, `docs/source/PRODUCT_BASELINE.md`, `docs/architecture/business-modeling-agent.md`, `docs/reports/stage1-*.md`, `docs/reports/screenshots/*.png`, `README.md`, `AGENTS.md`, `specs/001-first-release/{spec,plan,tasks,acceptance}.md`.

Earlier Stage 1 Agent modules (`api/app/modeling/*`, schema 4) were retained and finished, not rebuilt.

## Review findings and fixes

See `docs/reports/stage1-review.md`. Eight original correctness gaps stay closed. This wrap-up also fixed Markdown export completeness/source labels, preview locators, and workbench chrome.

## Commands and results

| Command | Exit | Notes |
| --- | --- | --- |
| `api/.venv/bin/python scripts/verify_stage1_review_findings.py` | 0 | Doubles, isolated temp dir |
| `api/.venv/bin/python scripts/verify_stage1_template_intake.py` | 0 | Six fixture source sets + text-only + public sample |
| `api/.venv/bin/python scripts/verify_stage1_migration.py` | 0 | schema 2/3 → 4, projects=9 materials=14, no wipe |
| `api/.venv/bin/python scripts/verify_t03_persistence.py` | 0 | |
| `api/.venv/bin/python scripts/verify_material_abstraction.py` | 0 | |
| `api/.venv/bin/python scripts/verify_t05_templates.py` | 0 | Six templates instantiate |
| `api/.venv/bin/python scripts/verify_t06_import.py` | 0 | |
| `api/.venv/bin/python scripts/verify_t07_tables.py` | 0 | |
| `api/.venv/bin/python scripts/verify_t07_t08_import.py` | 0 | |
| `api/.venv/bin/python scripts/verify_t08_images.py` | 0 | |
| `api/.venv/bin/python scripts/verify_t08_vision.py` | 0 | no vision runtime |
| `cd web && npm run build` | 0 | |
| `cd web && npm run lint` | 0 | oxlint warnings only |
| `GET http://127.0.0.1:8000/api/health` | 200 | already-running uvicorn |
| `GET http://127.0.0.1:8000/api/readiness` | 200 | live flags false; no secrets |
| Installed SDK check | — | `create_agent(..., checkpointer=)`; `SqliteSaver(conn)`; `ContentUnderstandingClient.begin_analyze_binary` |

User data: `data/lucid.db` schema 4, not reset. Browser created project `5b862ede-2ae1-4476-9cd1-0cc2a1311ac7` (question-only). Pre-Stage-1 backups under `data/backups/` were not wiped.

## Six cases

See the table in `docs/reports/stage1-acceptance.md`. Intake of real fixture bytes: **yes**. Live Agent per case: **blocked**. Do not treat template instantiation as a live Agent run. Fixtures are fictional; files are genuine formats.

## Verification split

| Layer | Result |
| --- | --- |
| Real model (C) | **Blocked.** Missing `LUCID_MODEL_NAME`, `LUCID_MODEL_BASE_URL`, `LUCID_MODEL_API_KEY`. Cursor chat is not backend model access. |
| Test doubles (B) | **Pass.** Public API rejects `live` and does not emit a sample draft. |
| Browser (D) | **Pass.** Screenshots in `docs/reports/screenshots/`. |
| Azure live jobs | **Blocked.** Missing endpoint/key/analyzer. |

## Local start

```bash
cd /Users/hairen/project/lucid
./scripts/dev.sh
```

- Web: http://127.0.0.1:5173/analyses
- API: http://127.0.0.1:8000/api/health
- Readiness: http://127.0.0.1:8000/api/readiness
- Example walkthrough project: http://127.0.0.1:5173/analyses/5b862ede-2ae1-4476-9cd1-0cc2a1311ac7/modeling

## Remaining / blocked

1. LIVE Agent and Azure cannot run until `lucid/.env` is filled (names in `.env.example`). Then rerun `./scripts/dev.sh` and exercise Modeling → review → freeze.
2. Solver, T11–T20, publish/deploy: out of scope.
3. Duplicate-analysis remains disabled (no transactional copy API).
4. Official Azure REST docs were not required after installed-SDK signature check. Notion DESIGN.md **was** fetched this session.

## Next-stage boundary

Stage 2 starts at formalization (T11) and a deterministic solver (T12). Do not mark T12–T20 complete because Stage 1 was finished. Do not present an Agent draft as a solved schedule.
