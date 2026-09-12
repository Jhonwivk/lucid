# Stage 2 implementation task

Build and verify a real single-user LUCID workflow from the existing Stage 1 confirmed baseline through scenario/formalization, deterministic training-scheduling solve, what-if changes, infeasibility explanation, candidate comparison, history/export, recovery/stale-run protection, and a visual workbench flow.

Constraints:

- Preserve the Material/Evidence Set → Business Modeling Agent → human review → confirmed baseline boundary.
- Use source-linked claims and preserve unknowns; never silently invent business rules or solver outcomes.
- Keep the architecture small: existing FastAPI, SQLite, and React workbench.
- A solver result must come from a real deterministic algorithm and must distinguish feasible, optimal, infeasible, unknown, and model_invalid where relevant.
- Keep this product single-user. Do not introduce collaboration accounts, approvals, or a multi-agent console.
- Complete a narrow training-scheduling vertical slice first, then extend it with what-if, explanations, comparison, export, recovery, and UI.
- Run focused verifiers plus existing Stage 1 verification before marking tasks complete.
