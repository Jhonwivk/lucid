# ADR-0002 — SQLite persistence contract

- Status: Accepted
- Date: 2026-09-11
- Deciders: LUCID T03 persistence contract

## Context

M0 bootstrapped FastAPI + a SQLite file at `data/lucid.db` with only `app_meta`. T03 must persist AnalysisProject, material metadata, provenance spans, versioned understanding/baselines, rules, scenarios, formal-model metadata, SolveRun records, result-candidate metadata, and change history — without introducing a platform, ORM migration product, or microservice.

Product rules that the schema must encode:

- Unknown business values stay unknown (NULL), never coerced to `0` / `false`.
- Confirmed historical snapshots are not rewritten; edits create new revisions.
- Solver / review / version / workflow statuses are different concepts.
- No fake solver execution.

## Decision

Keep SQLite in-process in the existing API. Add an explicit integer `schema_version` in `app_meta` and apply numbered SQL migrations in `api/app/db.py` (currently version 1). No Alembic, no extra datastore.

### Immutability

- **Insert-only snapshots:** `understanding_revision`, `scenario_revision`, `rule`, `formal_model`, `material`, `source_span`, `solve_run`, `result_candidate`, `change_event`.
- **Mutable live pointers:** `analysis_project.latest_*` plus title / summary / `workflow_maturity`. These describe the current workbench head, not a rewritten history row.
- Creating understanding/scenario V2 inserts a new row with `parent_revision_id` pointing at V1. V1 remains GET-able with original body fields.

### Distinct state axes

| Axis | Column / type | Values |
| --- | --- | --- |
| Product / workflow maturity | `analysis_project.workflow_maturity` | `open`, `materials`, `understanding`, `scenarios`, `results`, `archived` |
| Rule / evidence review | `rule.review_status`, `rule.evidence_status` | review: `unreviewed` / `accepted` / `rejected` / `needs_clarification`; evidence: `present` / `missing` / `unknown` / `conflicted` |
| Scenario / model / understanding version | `version_state` | `draft`, `confirmed`, `superseded`, `invalidated` |
| Solver run | `solve_run.run_state` | `pending`, `running`, `feasible`, `optimal`, `infeasible`, `unknown`, `model_invalid`, `failed`, `cancelled` |

T03 never sets `solve_run.claimed_execution` to true and always stores `execution = not_executed`. Run-state labels may be recorded as metadata so later solver work (T12) has a place to land; they are not solve results.

### Unknowns

`cost`, `capacity`, `permission`, `objective_value`, `variable_count`, `constraint_count`, locator offsets, and similar business/model quantities are nullable. Application code must persist Python `None` as SQL NULL. Conditional rules default a missing external premise to `premise_status = unknown`, not `known_false`.

### Demo data

`POST /api/dev/seed-demo` may create one `is_demo = 1` project, clearly titled as demo data. It does not encode a training-scheduling solution.

## Alternatives considered

1. **SQLAlchemy + Alembic** — useful later; too much machinery for a local MVP with one file database.
2. **JSON document per project** — weak for lineage queries and foreign-key provenance.
3. **Updating revision rows in place** — rejected; violates “do not rewrite confirmed reality.”

## Consequences

- T04 can list/open analyses from `/api/projects` without inventing a second model.
- T11/T12 should attach real formalization and solver execution onto these tables (likely relaxing the `claimed_execution = 0` check when a real solver writes a run).
- Import parsing (T06+) fills material bytes/spans; T03 only stores metadata shapes.
