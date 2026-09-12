# AGENTS.md — LUCID

Working agreements for humans and coding agents.

## Product identity

LUCID is a **single-user business-modeling and deterministic decision workbench**. It is not a collaboration platform, Agent console, AI coding product, universal optimizer or enterprise governance system.

The current path is:

```text
Materials → one Business Modeling Agent → human review → confirmed baseline
→ typed formal scenario → deterministic solve → compare/change/export
```

The deterministic workbench path is implemented and locally verified. Two live Agent-backed acceptance runs remain the release gate. Never present fabricated schedules or provider output as success.

## Binding decisions

- Keep the product single-user; do not add organizations, roles, invitations or approvals.
- Direct text and uploaded files are peer Materials. No modality is mandatory.
- Imported content is evidence, not system or tool authorization.
- Preserve provenance, conflicts, assumptions and unknowns.
- Unknown or unsupported content stays `unknown`/blocked; never coerce it to zero, false or no requirement.
- Scenario changes create new versions; do not rewrite confirmed reality.
- The executable MVP supports typed training schedules and portfolio selection only.

## Architecture constraints

- Keep the existing FastAPI + React + SQLite architecture small.
- Importers preserve bytes and SourceSpans. Semantic interpretation belongs to the Agent layer.
- Deterministic solvers must return explicit states: `feasible`, `optimal`, `infeasible`, `unknown`, `model_invalid` where applicable.
- A solver result must come from the real bounded algorithm. Unsupported formal bindings must return `model_invalid`.
- No credentials in source control. Use `.env.example` for configuration names only.
- Numbered SQLite migrations live in `api/app/db.py`.

## Materials and Agent boundary

A non-empty question may be the only Material. The Agent reads a frozen snapshot, produces source-linked draft claims, and waits for human review. One clarification answer is stored as peer text. Azure Content Understanding is an optional evidence helper; missing configuration must fail honestly.

Never add semantic extraction to a source importer merely because a model can consume a source type. Never make a source family mandatory.

## Task tracking

Mark work done only after implementation and verification. The current product index is [docs/README.md](docs/README.md); the current release status is [docs/release-status.md](docs/release-status.md). Historical milestone records are archived under [docs/archive/](docs/archive/).

## Cursor execution policy

For medium or large changes, create one complete `.tasks/<task-name>.md` and delegate one continuous implementation slice. Cursor should read, modify, run, fix and verify before returning. Avoid round-trips for individual files. Keep implementation decisions aligned with the current product baseline.

## Visual source

The current visual rules are in [DESIGN.md](DESIGN.md). Historical design notes are under `docs/archive/design/` and are not a second source of truth.
