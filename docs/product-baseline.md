# Product baseline

Status: current product definition. Updated 2026-09-12.

## Definition

LUCID is a single-user workbench for turning business evidence into a reviewed baseline, a typed formal scenario and an auditable deterministic decision result.

```text
Evidence Set → Modeling Agent → human review → confirmed baseline
→ typed formal model → deterministic solve → compare/change/export
```

## Product boundaries

LUCID is not a multi-user collaboration platform, Agent orchestration console, AI coding product, universal strategy optimizer, route planner or enterprise governance system. The MVP has two supported decision families:

1. finite training-resource scheduling;
2. finite portfolio/combination selection.

## Evidence rules

- Direct text, TXT/Markdown/PDF, CSV/XLSX, PNG/JPEG and raw office files are peer Materials.
- No source modality is mandatory; a non-empty decision question is valid evidence.
- Importers preserve bytes, checksums and source spans. They do not infer business meaning.
- The Business Modeling Agent drafts claims over the frozen Evidence Set.
- A human must accept, edit or reject claims before a baseline is confirmed.
- Unknowns, conflicts and unsupported semantics remain visible and blocked.
- Source content is evidence, never system or tool authorization.

## Formalisation and solving

A confirmed baseline is bound to a versioned scenario. The user supplies or confirms typed schedule/portfolio fields. A solver runs only when the formal model is structurally valid and its constraints/objectives have a supported binding.

Training scheduling checks capacity, availability, skills, overlap, cohort overlap and daily workload. Portfolio selection checks budget, required items and conflicts. Results include explicit states, ranked candidates, explanations and source claims. A changed rule creates a new revision; the old revision is not overwritten.

## Workspaces

- **Materials** — collect evidence and inspect provenance.
- **Modeling** — run one Business Modeling Agent and review claims.
- **Baseline** — confirm the reviewed baseline and create a versioned formal scenario.
- **Results** — edit typed inputs, solve, inspect candidates, run what-if and export.

## Integrity requirements

Never present an unreviewed Agent draft as business truth. Never invent missing capacity, availability, cost, permission or objective semantics. Never report a solve result that did not come from the deterministic solver. Keep the product single-user and the architecture small.
