# Stage 2 T14 portfolio selection

> Historical checkpoint. Superseded by [current release status](../../status.md). This file is retained for audit context and is not a current plan.

T14 now has a bounded executable portfolio-selection slice. A formal model with
`family=portfolio` contains a finite item list, a budget, item values, required
items, and pairwise conflicts. `POST /api/projects/{project_id}/solve-portfolio`
enumerates the finite set deterministically, ranks feasible selections by
maximum total value (then cost and stable item keys), and persists the actual
solver run and every returned candidate.

The solver returns explicit `optimal`, `infeasible`, or `model_invalid` states.
An infeasible run includes the budget, required keys, and item set used to
explain the blocked search; it does not fabricate a selection. Candidate
records include selected keys, cost, value, remaining budget, formal-model
hash, and source-claim provenance.

The T14 proof script is `scripts/verify_t14_portfolio_solver.py`. It covers a
ranked feasible selection and a required-item-over-budget infeasible model.
