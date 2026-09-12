# Stage 1 acceptance

Date: 2026-09-12. A worker exit code is **not** product acceptance.

## Verdict

| Layer | Result |
| --- | --- |
| Implementation of Stage 1 Agent + review + baseline + bilingual UI | Done locally |
| Eight original review findings + export/preview/UI wrap-up | Closed at contract level (B) and browser (D) |
| First-stage regression (T03, T05–T08, material abstraction, schema migration) | Pass |
| Six template source files via public intake | Pass (`scripts/verify_stage1_template_intake.py`). `expected.json` not sent |
| Web typecheck / production build | Pass (`npm run build` exit 0). `oxlint` warnings only |
| LIVE Agent + Azure (C) | **Blocked** — model and Azure config absent |
| Browser interactive walkthrough (D) | **Pass** — composer, question-only start, modeling blocker, materials, results, EN toggle, `/understanding` redirect. Screenshots under `docs/reports/screenshots/` |

Stage 1 is a locally verified **pre-solver** workbench. Live model/Azure execution is gated on configuration and is **not** claimed.

## Evidence levels

- **A — existing functionality.** Focused verifiers on temp DBs. User `data/lucid.db` was not reset.
- **B — Agent contract / doubles.** `scripts/verify_stage1_review_findings.py`. Doubles stay out of public product execution.
- **C — LIVE model/Azure.** Not run. `/api/readiness` reported `live_agent_possible=false`, `live_azure_possible=false` (presence flags only; no secret values).
- **D — browser.** Cursor browser against `http://127.0.0.1:5173/`. See `docs/reports/screenshots/README.md`.

## Commands (this wrap-up)

Working directory: `/Users/hairen/project/lucid`. Python: `api/.venv/bin/python`.

| Command | Exit |
| --- | --- |
| `python scripts/verify_stage1_review_findings.py` | **0** |
| `python scripts/verify_stage1_template_intake.py` | **0** |
| `python scripts/verify_stage1_migration.py` | **0** |
| `python scripts/verify_t03_persistence.py` | **0** |
| `python scripts/verify_material_abstraction.py` | **0** |
| `python scripts/verify_t05_templates.py` | **0** |
| `python scripts/verify_t06_import.py` | **0** |
| `python scripts/verify_t07_tables.py` | **0** |
| `python scripts/verify_t07_t08_import.py` | **0** |
| `python scripts/verify_t08_images.py` | **0** |
| `python scripts/verify_t08_vision.py` | **0** |
| `cd web && npm run build` | **0** |
| `cd web && npm run lint` | **0** (warnings: i18n export, SourceViewer deps — later included `material`) |
| `GET /api/health` | 200 |
| `GET /api/readiness` | 200, live flags false, no key values |

## Six cases — how far each layer went

Fixtures are **fictional business cases stored in genuine files**. The public holidays sample is real public holiday names/dates used inside a labeled fictional plant-shutdown question. `expected.json` is independent verification data and was never given to the Agent.

| Case | A intake | B doubles | C live | D browser |
| --- | --- | --- | --- | --- |
| Training Schedule | policy.md + demand.csv + leadership-memo.pdf | Shared contract suite, not this case’s live run | Blocked | Template card visible |
| Vehicle Validation Bench | xlsx + pdf + png | same | Blocked | Template card visible |
| Factory Maintenance Window | csv + md + png | same | Blocked | Template card visible |
| Supplier Capacity Allocation | xlsx + csv + pdf | same | Blocked | Template card visible |
| Product Portfolio Selection | json + md | same | Blocked | Template card visible |
| Retail Campaign Slotting | csv + json + txt | same | Blocked | Template card visible |
| Text-only question | Composer persisted 1 Material | Public API `model_not_configured` | Blocked | Full walkthrough |
| Public holidays sample | `plant-shutdown.md` + `federal-holidays-2026.json` | Intake only | Blocked | Not separately clicked |

Do **not** read this table as 6/6 live Agent runs.

## LIVE rerun (once configured)

Do **not** put secrets in chat. Create `lucid/.env` from `.env.example`:

- `LUCID_MODEL_NAME`
- `LUCID_MODEL_BASE_URL`
- `LUCID_MODEL_API_KEY`
- `AZURE_CONTENT_UNDERSTANDING_ENDPOINT`
- `AZURE_CONTENT_UNDERSTANDING_KEY` (or `AZURE_CONTENT_UNDERSTANDING_API_KEY`)
- `AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID`

Then:

```bash
cd /Users/hairen/project/lucid
./scripts/dev.sh
```

Open `http://127.0.0.1:5173/analyses`, start an analysis (files optional), run the modeling Agent, review claims, freeze baseline. Confirm `/api/readiness` flags without printing keys. Contract tests remain doubles.

## Out of scope (explicit)

T11–T20, deterministic solver, publish/deploy, multi-agent, extra content-understanding providers, OCR, fabricated schedules.
