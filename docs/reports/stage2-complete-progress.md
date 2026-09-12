# Stage 2 implementation report

Date: 2026-09-12.
Branch: `cursor/stage1-recoverable-frozen-review-loop`.

Stage 2 now has a real local vertical implementation from material evidence to
formalization, deterministic solving, what-if impact, comparison, export, and
recovery. It remains a single-user workbench and does not silently invent
missing business facts.

## Implemented path

```text
direct text / TXT / Markdown / PDF / CSV / XLSX / PNG / JPEG
  → Material + SourceSpan + checksum
  → Business Modeling Agent review / confirmed baseline
  → scenario v1
  → typed training_schedule or portfolio formal model
  → structural validation and source_claims
  → deterministic solver
  → persisted SolveRun + candidates + explanation + provenance
  → what-if impact preview / new revision
  → scenario comparison / history / export
```

The existing source adapters remain evidence-only. A generic confirmed
baseline does not silently become a schedule: the user must supply or confirm
the typed sessions, time slots, rooms, and instructors before the schedule
solver becomes available.

## Solver slices

- Training schedules use deterministic finite backtracking over sessions, time
  slots, rooms, and instructors. Capacity, availability, skills, overlap,
  cohort overlap, and daily-load constraints are checked explicitly through
  declared formal bindings. Unknown constraints/objectives return
  `model_invalid`; they are never ignored. Preferred-day and evening penalties
  are scored deterministically, and a search budget returns `unknown` when it
  cannot finish.
- Portfolio selection uses deterministic enumeration with budget, required
  items, pairwise conflicts, and explicit maximize-value objective.
- Solver states include `optimal`, `infeasible`, and `model_invalid`. Unsupported
  semantics remain visible as model-invalid rather than being guessed.
- Candidate payloads include assignments or selected items, objective breakdown,
  explanation, formal definition hash, and claim-to-source evidence references.
- The Results workspace persists and displays the full ranked candidate set up
  to the requested bound; it does not collapse multi-solution output into one
  fabricated answer.

## Change and resilience

- CAS-protected scenario revisions prevent stale parent writes.
- What-if changes create a new revision and can target nested schedule or
  portfolio resources.
- Impact preview probes the real deterministic compiler without claiming a
  persisted solve result.
- Comparison shows formal-element, rule, and related SolveRun differences.
- Solve history exports self-contained JSON and Markdown packages.
- Solve workers use owner/token leases, heartbeat, stale reclaim, and old-token
  rejection.
- Cross-project reads and exports are rejected. Deleted material content is
  inaccessible while its provenance metadata remains available for audit.

## Verification

Focused verifiers pass:

```text
verify_t11_formalization.py
verify_t11_material_lineage.py
verify_t12_training_solver.py
verify_t13_t14_t16.py
verify_t14_portfolio_solver.py
verify_t17_t19_solver_history.py
verify_t19_material_delete.py
verify_stage1_review_findings.py
verify_stage1_recovery_snapshot.py
```

The web application builds and lints with only the repository's existing
non-blocking warnings.

## Remaining acceptance gate

T20 is intentionally blocked. The local implementation has not claimed two
live Agent-backed runs because this checkout has no live model/Azure
configuration. Two real evidence cases must still run through material intake,
Agent extraction, human confirmation, typed formalization, solving, change,
and export before the first-release acceptance is complete.
