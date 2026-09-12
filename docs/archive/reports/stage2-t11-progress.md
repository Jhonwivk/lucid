# Stage 2 / T11 progress

> Historical checkpoint. Superseded by [current release status](../../status.md). This file is retained for audit context and is not a current plan.

T11 is complete as the formalization foundation. A confirmed baseline can be
bound once to scenario v1, with a typed formal definition, canonical hash,
claim-to-source evidence map, parent CAS, revision invalidation, and head
rollback. The Baseline workspace exposes this transition and the Results
workspace lets the user add and confirm the explicit typed training inputs
needed by the deterministic solver.

The generic baseline path remains deliberately conservative. It does not guess
sessions, capacities, rooms, instructors, or availability from prose. Missing
fields stay visible until the user supplies or confirms them.

See `docs/reports/stage2-complete-progress.md` for the complete Stage 2 path
and the remaining T20 acceptance gate.
