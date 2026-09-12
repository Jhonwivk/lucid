# Stage 1 handoff

Date: 2026-09-12. Workspace: `/Users/hairen/project/lucid`.
Branch: `cursor/stage1-recoverable-frozen-review-loop`.
Working base: HEAD `416ae9a`. A worker exit code is not product acceptance.

This is the authoritative Stage 1 delivery summary. Historical notes under `/Users/hairen/project/.tasks/` are execution records, not a second spec.

Pipeline (unchanged; still one Business Modeling Agent, no solver):

`Materials → Material Normalization / Azure auxiliary tool → one Business Modeling Agent → human review → frozen baseline/export`

## What this wrap-up completed

Four remaining review leftovers on the recoverable frozen-review loop. No second modeling Agent. No T11–T20 / solver.

1. **Clarification wall-time.** `waiting_for_user` clears `wall_deadline_at` (including `update_run`, GraphInterrupt, and `rollback_resume`). Human wait does not consume the Agent wall budget. `claim_resume` installs a fresh execution deadline from `max_wall_seconds` on the same run / same LangGraph checkpoint / same clarification. A late human answer after the old deadline has expired does not immediately timeout.

2. **Terminal write race.** `save_draft` validates, then opens a `BEGIN IMMEDIATE` persist transaction that re-checks writable status and CAS-updates the run before inserting draft / claims / understanding / project-head. Cancel or timeout in that window rolls the whole write back. `update_coverage`, `append_event`, and `increment_tool_count` refuse writes after the run leaves `queued` / `running` / `waiting_for_user`. Terminal CAS is unchanged: no “write then repair status”.

3. **ModelingWorkspace draft isolation.** `selectDraftForRun` returns only a draft for the selected `latestRunId`. If that run has no draft, the UI shows in-progress / no-draft copy and empty claims. Review and freeze are disabled unless the visible draft belongs to the current run and is still `draft`. Coverage, snapshot, and events continue to come from the same selected run.

4. **Freeze + Azure provenance.** `freeze_baseline` re-reads every snapshot file before confirming the draft. Missing bytes, `copy_error`, or checksum mismatch fail freeze and leave `version_state=draft`. `azure_markdown` requires a persisted artifact with `status=succeeded`, non-negative offsets that stay inside derived markdown, and a persisted locator map whenever the ref also claims original page/sheet/cell/region. Quote-in-whole-markdown is not enough for that mixed-locator case.

Not done: solver, T11–T20, a second modeling Agent, GitHub CI (not executed this wrap-up), live Agent pass, live Azure job.

## Main files changed (this wrap-up)

Backend: `api/app/modeling/persistence.py`, `provenance.py`, `runner.py`, `snapshot.py`.

UI: `web/src/lib/sourceView.ts`, `web/src/pages/workspaces/ModelingWorkspace.tsx`, `web/src/i18n.tsx`.

Verifiers: `scripts/verify_stage1_recovery_snapshot.py`.

Docs: this file.

## Commands and results (this wrap-up)

| Command | Exit | Notes |
| --- | --- | --- |
| `api/.venv/bin/python -m compileall -q api/app` | 0 | |
| `api/.venv/bin/python scripts/verify_stage1_recovery_snapshot.py` | 0 | Labeled doubles, isolated temp dir. Covers late clarification after an expired wall deadline, save_draft cancel-between-validate-and-persist, R1/R2 draft selection, freeze after snapshot tamper, failed Azure artifact, Azure offset overflow, page=1 + Azure without/with a page=2 locator map. **Not** a live model/Azure run. |
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

- Run enters `waiting_for_user`, old `wall_deadline_at` is set in the past, user resumes: same run and thread continue; status is not `timeout`; the clarification answer is consumed and a draft is published.
- `save_draft` hook cancels after validation and before persist: `StaleRunError`, no draft row, project head unchanged, run stays `cancelled`.
- Pure `select_draft_for_run`: R1 has a draft, selecting R2 returns no draft and no R1 claims.
- Snapshot bytes tampered after `save_draft` and before `freeze_baseline`: freeze fails; draft remains `draft`.
- Failed Azure artifact that still has `derived_markdown`: rejected (`succeeded` required).
- Azure markdown `end_offset` past derived length: rejected.
- `page=1` plus `azure_markdown` without a locator map, and `page=1` with a persisted map that only has `page=2`: both rejected. Quote presence in the whole markdown is not accepted as proof.

## Remaining / blocked

1. Azure live jobs remain **BLOCKED** until Azure endpoint/key/analyzer are set. A live Agent pass is still a separate human exercise after `./scripts/dev.sh`; this wrap-up did not execute one.
2. Solver, T11–T20, publish/deploy: out of scope.
3. `graph.invoke` cannot be hard-cancelled; timeout relies on refusing late writes and recording a timeout event.
4. Duplicate-analysis remains disabled (no transactional copy API).

## Next-stage boundary

Stage 2 starts at formalization (T11) and a deterministic solver (T12). Do not mark T12–T20 complete because Stage 1 was finished. Do not present an Agent draft as a solved schedule.
