# Release status

Updated: 2026-09-12.

## Shipped

The current checkout includes the complete deterministic workbench path:

- evidence intake with checksums, source spans, provenance and soft deletion;
- one Business Modeling Agent boundary with human claim review and confirmed baselines;
- versioned scenarios, typed training-schedule and portfolio formal models, and revision compare/what-if;
- bounded deterministic scheduling and portfolio enumeration with ranked candidates, explanations and explicit solver states;
- JSON and Markdown exports, solve history, lease recovery and project-boundary protection;
- Materials, Modeling, Baseline and Results workspaces in the React client.

## Live acceptance gate

The only remaining release gate is two live Agent-backed runs using real user evidence through the complete path:

```text
material intake → Agent extraction → human confirmation
→ typed formalization → deterministic solve → what-if → export
```

Provider credentials and Azure configuration are optional for local deterministic verification. When they are absent, the application reports a configuration blocker and does not claim a successful Agent run.

## Known limits

The MVP supports only finite training scheduling and finite portfolio selection. Generic or incomplete formal models remain unavailable to the solver and return `model_invalid`; unknown values are never coerced to zero or false. LUCID remains a single-user workbench without organizations, roles, invitations or approvals.
