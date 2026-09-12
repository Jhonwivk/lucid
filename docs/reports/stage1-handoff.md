# Stage 1 handoff

Date: 2026-09-12. Workspace: `/Users/hairen/project/lucid`.
Branch: `cursor/stage1-recoverable-frozen-review-loop`.
Observed assistant: Cursor Grok 4.6. A worker exit code is not product acceptance.

This is the authoritative Stage 1 delivery summary. Historical notes under `/Users/hairen/project/.tasks/` are execution records, not a second spec.

Pipeline (unchanged; still one Business Modeling Agent, no solver):

`Materials → Material Normalization / Azure auxiliary tool → one Business Modeling Agent → human review → frozen baseline/export`

## What this wrap-up completed

Review leftovers on the recoverable frozen-review loop, without a second modeling Agent and without T11–T20 / solver:

1. **One active modeling run per project.** Transactional `BEGIN IMMEDIATE` check plus SQLite partial unique index on `queued` / `running` / `waiting_for_user`. Concurrent `POST` / `create_run` / `start_run` yield one winner and HTTP 409. Two `_spawn` workers on the same run: one `ConflictError`.
2. **Stricter provenance.** Exact quote with offsets matches only the offset slice. Claimed page/sheet/cell/region must exist on the snapshot span. `azure_markdown` requires persisted analyzer + operation identity and checksum. Quote-in-span-but-wrong-offset rejects with `claim_key[index]`.
3. **SourceViewer snapshot vs live.** `runId` is passed only when the selected material is in `latestRun.snapshot.materials` with `snapshot_path` + checksum and no `copy_error`. Otherwise the live preview endpoint is used. Synthetic snapshot materials keep real `kind` / `media_type` / `byte_size` / `checksum` / `filename` / `role`. Preview checks run id, material id, and checksum.
4. **Latest run selection.** Backend `list_runs` and UI `selectLatestModelingRun` sort `updated_at DESC`, `created_at DESC`, `id DESC`. Pinned run is honored; `runs[0]` is not implicit truth.
5. **Baseline export UX.** Retry keeps the failed kind (JSON failure does not retry Markdown). External `currentBaselineId` changes reselect. Loading / error / retry state stay kind-specific.
6. **Timeout late activity.** Terminal CAS remains. After timeout, `increment_tool_count` / `update_coverage` / `append_event` / `save_draft` / success status writes are rejected. Timeout is recorded in the same transaction as the failed status. `graph.invoke` is still not forcibly cancelled; late tools cannot restore success.

Not done: solver, T11–T20, a second modeling Agent, GitHub CI (not executed this wrap-up).

## Main files changed (this wrap-up)

Backend: `api/app/db.py` (schema 5), `api/app/modeling/persistence.py`, `provenance.py`, `runner.py`, `tools.py`, `api/app/modeling_routes.py`.

UI: `web/src/lib/sourceView.ts`, `web/src/pages/workspaces/ModelingWorkspace.tsx`, `BaselineWorkspace.tsx`, `web/src/components/SourceViewer.tsx`, `web/src/api/types.ts`, `web/src/api/client.ts`.

Verifiers: `scripts/verify_stage1_recovery_snapshot.py`, `scripts/verify_stage1_review_findings.py`.

Docs: this file, `docs/architecture/business-modeling-agent.md` (schema 5), `README.md` (schema 5).

## Commands and results (this wrap-up)

| Command | Exit | Notes |
| --- | --- | --- |
| `api/.venv/bin/python -m compileall -q api/app` | 0 | |
| `api/.venv/bin/python scripts/verify_stage1_recovery_snapshot.py` | 0 | Labeled doubles, isolated temp dir. Covers concurrent active-run CAS, frozen bytes, tampered snapshot, forged quote / wrong-offset quote, missing snapshot → live fallback, PDF/image/table/text snapshot preview after live delete, timeout late-write guard. **Not** a live model/Azure run. |
| `api/.venv/bin/python scripts/verify_stage1_review_findings.py` | 0 | Labeled doubles, isolated temp dir. Env keys blanked so local `.env` cannot refill a live provider into this verifier. |
| `cd web && npm run build` | 0 | `tsc -b && vite build` |
| `cd web && npm run lint` | 0 | oxlint: existing i18n export warning; SourceViewer `setState` in preview effect warning. No errors. |
| `git diff --check` | 0 | No whitespace errors |

GitHub CI: **not run**. Do not treat the commands above as CI.

## Live providers (this wrap-up)

Read from local `lucid/.env` via `app.runtime_config.snapshot()` (presence flags only; no secret values):

| Provider | Presence | This wrap-up |
| --- | --- | --- |
| Live model (`LUCID_MODEL_*`) | keys present (`live_agent_possible=true`) | **Not executed.** No live `graph.invoke` / Agent pass was run here. Labeled-double verifiers are evidence level B. |
| Azure Content Understanding | **BLOCKED** (`live_azure_possible=false`) | Missing endpoint/key/analyzer. No live Azure job. |

Do not describe the isolated labeled-double tests as real provider verification.

## Verification split

| Layer | Result |
| --- | --- |
| Real model (C) | **Not re-run this wrap-up.** Keys are present locally; that is configuration, not an accepted live Agent pass. |
| Test doubles (B) | **Pass.** Recovery + findings verifiers on isolated temp dirs. |
| Azure live jobs | **BLOCKED.** |
| GitHub CI | **Not run.** |
| Solver / T11–T20 | **Not implemented.** |

## Concurrent run / snapshot / quote / UI fallback (from recovery verifier)

All of the following passed inside `verify_stage1_recovery_snapshot.py`:

- Dual `create_run` and dual `start_run`: one `ok`, one `ConflictError`; HTTP `POST` while queued is 409.
- Dual `_spawn` on one run: one worker, one conflict.
- Frozen snapshot bytes survive live replace/delete; tampered snapshot bytes are `stale_input` and block draft submit.
- Forged page/sheet/offset/quote, missing coverage, Azure self-proof without artifact, quote present in the same span but not in the given offset, `source_span_id` + claimed page when the span has no page, Azure `operation_id` mismatch: all rejected with `claim_key[index]` where applicable.
- After deleting live files: PDF, image, table, and text snapshot preview/content still render with the frozen kind/media_type/checksum; wrong checksum query is 409.
- Missing snapshot identity: snapshot preview 404; live preview 200 with a non-`modeling-runs` content URL.
- Timeout: late increment/coverage/event/draft/completed writes raise `StaleRunError`; status stays `failed` / `timeout`; no submitted-draft event.

## Remaining / blocked

1. Azure live jobs remain **BLOCKED** until Azure endpoint/key/analyzer are set. A live Agent pass is still a separate human exercise after `./scripts/dev.sh`; this wrap-up did not execute one.
2. Solver, T11–T20, publish/deploy: out of scope.
3. `graph.invoke` cannot be hard-cancelled; timeout relies on refusing late writes and recording a timeout event.
4. Duplicate-analysis remains disabled (no transactional copy API).

## Next-stage boundary

Stage 2 starts at formalization (T11) and a deterministic solver (T12). Do not mark T12–T20 complete because Stage 1 was finished. Do not present an Agent draft as a solved schedule.
