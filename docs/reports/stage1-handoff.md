# Stage 1 handoff

Date: 2026-09-12. Workspace: `/Users/hairen/project/lucid`.
Branch: `cursor/stage1-recoverable-frozen-review-loop`.
Working base: HEAD `a73052d`. A worker exit code is not product acceptance.

This is the authoritative Stage 1 delivery summary. Historical notes under `/Users/hairen/project/.tasks/` are execution records, not a second spec.

Pipeline (unchanged; still one Business Modeling Agent, no solver):

`Materials → Material Normalization / Azure auxiliary tool → one Business Modeling Agent → human review → frozen baseline/export`

## What this wrap-up completed

Three leftover review items on the recoverable frozen-review loop. No second modeling Agent. No T11–T20 / solver.

1. **Clarification resume handover.** A waiting worker drops its `_threads` identity as soon as the run enters `waiting_for_user`, and again in `finally`. Human `resume_run` replaces a leftover waiting thread instead of treating it as the resume worker. The GraphInterrupt return path no longer writes `waiting_for_user` after a resume claim has moved the run to `running`; this prevents the old worker from overwriting the new worker's claim. After spawn, resume confirms the new thread took over the claim; if it did not start, `rollback_resume` restores the same pending clarification.

2. **BaselineWorkspace draft isolation and repeat freeze.** `selectBaselineDraft` only returns a draft for the latest modeling run. If that run has no draft, the page shows in-progress / no-draft copy and Freeze stays disabled. When an existing baseline is present, a draft from the latest run still exposes the Freeze action; historical project drafts are not offered as the freeze target.

3. **Public Azure locator map.** `understand_material` and `read_source` now return a bounded `provider_locators` list (`locator_id`, `kind`, `page`, `sheet`, `cell_ref`, `region`, `offset`, `length`, `coordinate_system`, `original_coordinates`). Nested `contents[*].spans` are mapped. Locators without a reliable original mapping are `original_coordinates='unknown'`. Provenance checks compare provider locator identity and offsets against the persisted map. Operation URLs, continuation tokens, and other secrets stay out of tool payloads.

Not done: solver, T11–T20, a second modeling Agent, GitHub CI (not executed this wrap-up), live Agent pass, live Azure job.

## Main files changed (this wrap-up)

Backend: `api/app/modeling/runner.py`, `tools.py`, `azure_cu.py`.

UI: `web/src/lib/sourceView.ts`, `web/src/pages/workspaces/BaselineWorkspace.tsx`, `web/src/pages/WorkbenchPage.tsx`.

Verifiers: `scripts/verify_stage1_recovery_snapshot.py`.

Docs: this file.

## Commands and results (this wrap-up)

| Command | Exit | Notes |
| --- | --- | --- |
| `api/.venv/bin/python -m compileall -q api/app` | 0 | |
| `api/.venv/bin/python scripts/verify_stage1_recovery_snapshot.py` | 0 | Labeled doubles, isolated temp dir. Covers leftover-waiting-thread resume, Baseline R1/R2 draft selection, Agent-constructed page-linked Azure refs. **Not** a live model/Azure run. |
| `api/.venv/bin/python scripts/verify_stage1_review_findings.py` | 0 | Labeled doubles, isolated temp dir. Env keys blanked so local `.env` cannot refill a live provider into this verifier. |
| `cd web && npm run build` | 0 | `tsc -b && vite build` |
| `cd web && npm run lint` | 0 | oxlint: existing i18n export warning; SourceViewer `setState` in preview effect warning. No errors. |
| `git diff --check` | 0 | No whitespace errors |

GitHub CI: **not run**. Do not treat the commands above as CI.

## Live providers (this wrap-up)

Read from local `lucid/.env` via `app.runtime_config.snapshot()` (presence flags only; no secret values):

| Provider | Presence | This wrap-up |
| --- | --- | --- |
| Live model (`LUCID_MODEL_*`) | keys present (`live_agent_possible=true`) | **NOT EXECUTED.** No live `graph.invoke` / Agent pass was run here. Labeled-double verifiers are evidence level B. |
| Azure Content Understanding | **BLOCKED** (`live_azure_possible=false`) | Missing endpoint/key. No live Azure job. |

Do not describe the isolated labeled-double tests as real provider verification.

## Verification split

| Layer | Result |
| --- | --- |
| Real model (C) | **NOT EXECUTED.** Keys are present locally; that is configuration, not an accepted live Agent pass. |
| Test doubles (B) | **Pass.** Recovery + findings verifiers on isolated temp dirs. |
| Azure live jobs | **BLOCKED.** |
| GitHub CI | **Not run.** |
| Solver / T11–T20 | **Not implemented.** |

## New regressions (from recovery verifier)

All of the following passed inside `verify_stage1_recovery_snapshot.py`:

- After `waiting_for_user`, a leftover alive thread is left in `_threads`; `resume_run` replaces it, the clarification is answered, and the run reaches `partial` / `completed` instead of staying `running`.
- Baseline selection: R1 has a draft, R2 is the latest run with no draft → selected draft is null (no R1 claims).
- `understand_material` and `read_source` on a succeeded Azure artifact return public locators; nested `contents[*].spans` preserve page/offset/length; an `EvidenceRef` built from a matching locator passes `validate_ref`, while mismatched locator coordinates fail.

## Remaining / blocked

1. Azure live jobs remain **BLOCKED** until Azure endpoint/key/analyzer are set. A live Agent pass is still a separate human exercise after `./scripts/dev.sh`; this wrap-up did not execute one.
2. Solver, T11–T20, publish/deploy: out of scope.
3. `graph.invoke` cannot be hard-cancelled; timeout relies on refusing late writes and recording a timeout event.
4. Duplicate-analysis remains disabled (no transactional copy API).

## Next-stage boundary

Stage 2 starts at formalization (T11) and a deterministic solver (T12). Do not mark T12–T20 complete because Stage 1 was finished. Do not present an Agent draft as a solved schedule.
