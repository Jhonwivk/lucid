# Stage 2 / T11 progress

Date: 2026-09-12.
Branch: `cursor/stage1-recoverable-frozen-review-loop`.

T11 has started with the first backend slice. It does not execute a solver.

## Implemented

- A confirmed `modeling_baseline` can be explicitly bound to a new scenario and revision 1 through `POST /api/projects/{project_id}/scenarios/from-baseline/{baseline_id}`. A baseline can only be bound once.
- `FormalModelIn` now supports a versioned typed definition containing variables, parameters, constraints, and objectives. The definition is persisted, hashed canonically, and returned with structural validation status.
- Scenario revision creation accepts `expected_parent_revision_id`; stale parents return a conflict instead of silently branching from a newer head.
- `POST /api/scenario-revisions/{revision_id}/invalidate` records a reason and timestamp, invalidates the attached formal model, rolls the project head back to the parent, and emits a change event.
- Schema migration 6 adds formal-definition and invalidation metadata without rewriting existing rows.

## Explicit boundary

The formal definition is a typed, auditable contract. It is not yet compiled into OR-Tools and it is not a schedule. T12 remains unimplemented. Missing semantic fields must remain visible as validation issues.

## Verification

`python scripts/verify_t11_formalization.py` proves baseline binding, definition round-trip/hash, v1 immutability, stale-parent rejection, invalidation, head rollback, and change events. Stage 1 recovery and review verifiers also pass.

## Next T11 slice

Add the scenario editing UI and dependency-aware invalidation display. Then enrich the training-schedule formal definition with explicit time slots, rooms, instructor availability, and session data before beginning T12.
