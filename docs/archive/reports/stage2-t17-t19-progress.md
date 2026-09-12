# Stage 2 T17–T19 backend progress

> Historical checkpoint. Superseded by [current release status](../../status.md). This file is retained for audit context and is not a current plan.

The solver result boundary now preserves an auditable history instead of only
storing a status label.

## T17 — history and export

- `solve_run` stores a deterministic `input_fingerprint` for the exact
  scenario revision and formal model used.
- `result_candidate` stores the result payload, solver explanation, and
  provenance payload alongside the label and objective value.
- `GET /api/projects/{project_id}/solve-runs/{run_id}/export.json` returns a
  self-contained `lucid.solve-run.v1` document containing the project,
  scenario revision, formal model, candidates, baseline handoff, materials,
  source spans, and related change events.

## T18 — recovery and stale-run protection

- A worker claims a run with an owner and opaque lease token.
- Heartbeat and completion requests must provide the exact current token;
  omitting it or reusing an old token is rejected.
- Heartbeats keep the lease alive.
- A live lease cannot be claimed by another worker.
- A stale lease can be reclaimed, always receives a fresh token, increments
  `resume_count`, and clears the stale timestamp.
- A previous worker token cannot write a completion after reclamation.
- `claimed_execution` remains compatible with the existing SQLite constraint;
  active ownership is represented by the lease fields and exposed as a
  derived response value.

## T19 — project boundary

Solve-run reads, completion, explanation recording, and exports can be scoped
to a project. A run ID from another project returns not-found at the boundary,
and the export assembles provenance only from the owning project.

Verification:

```text
python scripts/verify_t17_t19_solver_history.py
```

The verifier uses an isolated temporary SQLite/data directory and proves
history round-trip, stale worker recovery, old-token rejection, self-contained
export, and cross-project export denial.
