# First-release specification

LUCID is a single-user evidence-to-decision workbench. The first release supports one scheduling workflow and one portfolio workflow with reviewable provenance and versioned scenarios.

## User path

```text
collect evidence → run one Agent → review claims → confirm baseline
→ enter/confirm typed model → solve → change/compare → export
```

## Required behaviours

- Materials can be direct text or uploaded files; no modality is mandatory.
- Importers preserve evidence and provenance but do not infer business semantics.
- Agent output is a draft until a human confirms it.
- Unknowns remain blocked rather than silently filled.
- Scenario edits create new revisions.
- Solver states distinguish `optimal`, `infeasible`, `unknown` and `model_invalid`.
- Results include candidates, explanation, provenance and export.
- The product remains single-user.

## Supported model families

**Training schedule:** sessions, slots, rooms, instructors, capacity, availability, skills, overlap and workload.

**Portfolio:** budget, required items, conflicts and maximize-value ranking.

Generic or unsupported models are inspectable but not executable.

## Release status

T11–T19 are implemented and locally verified. T20 is blocked until two live Agent-backed evidence runs complete the full path. See [current status](../../release-status.md), [tasks](tasks.md) and [acceptance](acceptance.md).
