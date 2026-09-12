# Current release status

Updated: 2026-09-12

## Shipped locally

T11–T19 are implemented and verified on the current branch:

- scenario creation from a confirmed baseline, typed formal definitions and revision CAS;
- deterministic training-schedule backtracking and portfolio enumeration;
- explicit `optimal`, `infeasible`, `unknown` and `model_invalid` outcomes;
- ranked candidates, explanations and source/material provenance;
- what-if impact preview, revision comparison and actual feedback;
- JSON/Markdown solve history export;
- solver leases, stale-worker reclaim and deterministic resume;
- material soft deletion with retained provenance;
- project-boundary protection;
- Results workbench editors and candidate visualisation.

## Evidence for this status

The focused verifiers pass for T11, mixed-material lineage, T12, T13/T14/T16, T17–T19, Stage 1 review/recovery, templates and intake. The web application builds and lints with only existing non-blocking warnings.

## One remaining gate

T20 is blocked until two runs use live model/Azure configuration and real user evidence all the way through:

```text
material intake → live Agent extraction → human confirmation
→ typed formalisation → solve → what-if → export
```

Fixtures and direct database setup do not count as T20. This is an acceptance requirement, not a missing deterministic solver implementation.

## Product limits

The MVP has two executable model families: training schedules and portfolios. Generic or incomplete formal models remain visible but unavailable to a solver. Unsupported rules return `model_invalid`; they are not silently approximated.
