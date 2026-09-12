# ADR-0002 — SQLite persistence contract

- Status: Accepted
- Current schema: 9
- Date: 2026-09-11

## Decision

Keep SQLite in-process in the existing FastAPI service. Numbered migrations live in `api/app/db.py`; no ORM migration product or extra datastore is required for the single-user MVP.

The schema stores projects, Materials, SourceSpans, Agent revisions, baselines, scenarios, formal models, SolveRuns, candidates, leases, provenance and change events.

## Invariants

- Unknown business values stay SQL `NULL`.
- Confirmed snapshots are immutable; edits create revisions.
- Material content can be soft-deleted while provenance remains auditable.
- Solver state and workflow state are separate.
- Executed solver runs contain real candidates and an input fingerprint.
- Worker claims use owner/token leases, heartbeat, stale reclaim and project boundaries.
- No fake solver execution is accepted.

## Current solver states

`pending`, `running`, `feasible`, `optimal`, `infeasible`, `unknown`, `model_invalid`, `failed`, `cancelled`.

## Consequences

The API can reopen historical revisions, compare versions, export a self-contained solve package and resume an interrupted deterministic run without rewriting confirmed reality. SQLite remains appropriate for the local single-user MVP; a later multi-user product would need a separate storage decision.
