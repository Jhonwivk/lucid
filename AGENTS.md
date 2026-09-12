# AGENTS.md — LUCID

Working agreements for humans and coding agents in this repository.

## Product identity

LUCID is a **single-user business-modeling / decision workbench**.

It is **not**:

- a multi-user collaboration platform
- an Agent orchestration console
- an AI coding product
- a generic enterprise knowledge platform
- a universal strategy optimizer

Stage 1 primary object: a **human-reviewable modeling draft and confirmed pre-solver baseline**. Users inspect/edit constraints, objectives, unknowns, and source provenance. Unverified AI interpretation is never business truth.

Stage 2 (not implemented) adds a deterministic solver. Never present a fabricated schedule as a solve.

## Binding MVP decisions

- Single-user only — no organizations, team roles, invitations, or approvals.
- Users start from whatever business materials they currently have (direct text, documents, tables, images, or any mixture) or an existing plan — not by manually restating hundreds of rules. **No source modality is required.**
- Direct user-entered text is the same class of **Material** as an uploaded file.
- Imported or entered material is **evidence, not instruction**. Prompt injection inside source documents or pasted text must never become system/tool authorization.
- Business understanding must expose provenance, conflicts, assumptions, and unknowns.
- Unsupported/unclear content remains **unknown/blocked** — never silently coerced to zero/false/no-requirement.
- Deterministic constraint solving is first-class **in Stage 2** — not an LLM-only answer, and not implemented in Stage 1.
- Solution states distinguish at least: `feasible` / `optimal` / `infeasible` / `unknown` / `model_invalid` where relevant.
- Changes create **new scenarios/versions**; do not rewrite previously confirmed reality.
- No automatic enterprise governance, external execution, payments, arbitrary route planning, or unlimited natural-language modeling in MVP.

## Architecture constraints

- Keep the architecture intentionally small — no microservices.
- Prefer extending `api/` + `web/` over inventing new runtimes.
- Do not fake solver, OCR, or LLM success. Disabled/not-yet-implemented UI is required until real adapters exist.
- No credentials in source control. Use `.env.example` only when env vars are actually needed.
- Persistence lives under `data/` (local SQLite for MVP). Schema and numbered migrations live in `api/app/db.py`.
- The `filename` column on Material is a **compatibility/source-label field**. Do not introduce a destructive DB rename just to express direct text.

### Material vs Understanding (do not drift)

Correct Stage 1 pipeline:

`User question + peer Materials + SourceSpans → one Business Modeling Agent → human review → confirmed baseline / handoff → (Stage 2) Scenario/Formalization → Solve`

- A **Material** is one unit of user-provided business evidence, regardless of origin or modality. A non-blank decision question may be the only Material.
- T06 / T07 / T08 are source-adapter slices. Stage 1 T09/T10 are the Agent + review. T11–T20 including the solver are **not** done.
- Semantic interpretation is Agent/Azure-tool work, never automatic inside a file importer.

**Never add semantic extraction to a source importer just because a model can consume that source type. Importers preserve evidence; T09+ understand evidence.**

Never make one source family mandatory. Understanding operates over the non-empty Evidence Set the user actually provided.

Image intake (T08) validates PNG/JPEG bytes, records dimensions/media type/checksum, and writes one full-image SourceSpan. It must not call Grok, Apple Vision, OCR, or object detection, and must not create semantic observations. No vision provider or API key is an M2/T08 gate.

## Task tracking

Authoritative readable plan: `specs/001-first-release/tasks.md`.

Mark a task done only after it is implemented **and** verified. T01–T10 are verified locally (T09/T10 = Stage 1 Agent + review; LIVE model/Azure still configuration-blocked). **Do not claim T11–T20 or solver capabilities.** Authoritative current docs: `docs/README.md`. Delivery summary: `docs/reports/stage1-handoff.md`.

## Cursor execution policy

Default to **fast delegation**, not step-by-step remote micromanagement.

- Small, bounded changes: ChatGPT may edit directly through MCPX when repository exploration is unnecessary.
- Medium/large implementation work: write one complete `.tasks/<task-name>.md`, then delegate it to Cursor as one continuous implementation slice. Cursor should read, modify, run, fix, and verify locally before returning the result.
- Avoid repeated ChatGPT → MCPX → Cursor round-trips for individual files or tiny implementation steps unless the task is blocked or a decision genuinely requires human/ChatGPT review.
- Default Cursor reasoning level: **Grok 4.6 High** using the currently available High option in Cursor. Do not hard-code an unverified model slug.
- Escalate to **Grok 4.6 Extra High** only for architecture decisions, difficult root-cause analysis, major refactors, or tasks explicitly marked as requiring deep reasoning.
- UI implementation, i18n, CRUD, fixtures, routine API work, ordinary bug fixes, and straightforward feature slices must not require Extra High as a gate.
- Historical task files that explicitly required Extra High remain execution records; they do not define the default for new work.

## First vertical slice (after M0)

Stage 1: `evidence → model → review → freeze/export`

Stage 2 (later): `formalize → schedule/solve → change → export`

## Suggested next work

Configure `LUCID_MODEL_*` and Azure Content Understanding locally, then run a **live** Agent pass (does not complete T20 by itself). Next implementation: T11 formalization, then T12 solver. Do not fake solver results. Visual source of truth: `DESIGN.md`.
