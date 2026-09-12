# Stage 2 T12: executable training-schedule solver

T12 now has one real, deterministic vertical slice. A `training_schedule`
formal definition contains sessions, finite time slots, rooms, and instructors.
The compiler validates these typed entities and the solver exhaustively searches
the finite assignment space in stable key order.

The solver enforces only explicitly declared, supported bindings: room capacity
and availability, instructor availability and skills, room/instructor overlap,
cohort overlap, and daily instructor load. It scores feasible solutions using
declared minimizing objectives (preferred-day and evening-session penalties),
with priority and weight applied, and returns ranked deterministic candidates.
Unknown constraint expressions, unsupported objective directions, and missing
availability declarations are `model_invalid`; they are never silently treated
as unrestricted. If no session can be assigned, the run is `infeasible` with
per-session blocker counts. A finite search budget returns `unknown` when it is
exhausted before proving a result.

`POST /api/projects/{project_id}/solve-training-schedule` persists an executed
`solve_run` and a result candidate containing assignments, objective breakdown,
blockers, input fingerprint, definition hash, and source-claim evidence refs.
The existing metadata-only solve-run endpoint remains available for historical
fixtures and does not claim execution.

This is intentionally a bounded training-scheduling compiler. Objectives or
constraint semantics outside the supported typed slice remain visible as
unsupported/model-invalid; they are not silently translated into solver logic.
