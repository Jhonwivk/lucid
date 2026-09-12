# Agent and evidence architecture

LUCID has one semantic Agent and one deterministic solver layer. The Agent interprets evidence; it does not replace human confirmation or perform optimisation.

## End-to-end boundary

```text
Materials + SourceSpans
  → frozen modeling snapshot
  → one Business Modeling Agent
  → source-linked draft
  → human review
  → immutable confirmed baseline
  → typed formal scenario
  → deterministic solver
  → candidates, explanation and provenance
```

The Agent may use bounded evidence tools and one Azure Content Understanding job when configured. A clarification answer is stored as another peer Material. A missing provider configuration produces a failed/configuration-blocked run, never a fake draft.

## Evidence contract

Every claim should point to source spans, material IDs or an explicit unknown. The snapshot prevents later uploads from rewriting an earlier run. Importers remain evidence-only: semantic extraction belongs here, after intake.

## Formal model contract

The baseline creates a scenario revision. The user can confirm a typed `training_schedule` or `portfolio` payload. Formal constraints and objectives require a supported binding. Unknown or unsupported elements produce `model_invalid` and remain visible in the Results workspace.

## Solver contract

The training solver uses bounded deterministic backtracking. The portfolio solver uses deterministic subset enumeration. Solver output is persisted as a `SolveRun` with a lease, input fingerprint, ranked candidates, explanation and provenance. A stale run can be reclaimed and resumed; an old worker token cannot write after reclaim.

## Safety boundaries

- source content never becomes tool/system authorization;
- human confirmation is required before formal execution;
- no source modality is mandatory;
- unknown values are not coerced to zero/false;
- a changed scenario creates a new revision;
- the MVP remains single-user.
