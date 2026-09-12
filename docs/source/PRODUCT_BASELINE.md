# Product baseline — LUCID

Status: binding for MVP / first release planning  
Last updated: 2026-09-12 (Stage 2 local implementation; T20 live acceptance pending)

## One-sentence definition

LUCID is a single-user workbench for turning business materials into a reviewed modeling baseline, then (Stage 2) solving scenarios with a deterministic solver.

## What LUCID is not

- Multi-user collaboration platform
- Agent orchestration console
- AI coding product
- Generic enterprise knowledge platform
- Universal strategy optimizer

## Problem families (initial)

1. **Finite resource allocation / scheduling** — primary vertical slice
2. **Finite portfolio / combination selection** — second full workflow
3. **Replanning / condition comparison** across supported families

## Binding abstraction

`User-provided evidence set → normalized Materials + SourceSpans → Business Modeling Agent draft → Human review → Confirmed baseline → Scenario/Formalization → deterministic Solve → change/compare/export`

- A **Material** is one unit of user-provided business evidence, regardless of origin or modality.
- An **Evidence Set** is the collection of Materials currently supplied to an analysis.
- A non-blank **decision question** may be the sole persisted direct-text evidence. Files are optional peers.
- PDF, TXT/Markdown, CSV/XLSX, images, JSON, raw DOCX/PPTX, and **direct user-entered text** are optional peers. No source type is mandatory.
- The only precondition for modeling is a non-empty evidence set (question-only counts).
- `document` / `table` / `image` are source-family / adapter / rendering details, not separate product workflows.
- Direct user-entered text is the same class of Material as an uploaded file.
- The Materials layer preserves raw source, provenance, and unknowns. It does not infer business meaning.
- T06 / T07 / T08 are source-adapter and provenance implementation slices, not sequential user workflow stages.
- Stage 1 (T09/T10 mapping) consumes the unified Evidence Set with **one** Business Modeling Agent and **one** Azure Content Understanding service. Human review remains mandatory. The solver is Stage 2.

**Never add semantic extraction to a source importer just because a model can consume that source type. Importers preserve evidence; the Agent understands evidence.**

Likewise, never make one source family mandatory. Understanding operates over the non-empty Evidence Set the user actually provided.

## Primary user workflow

`collect evidence set → run modeling agent → review/edit/reject claims → freeze baseline → export handoff → (Stage 2) formalize → solve → compare`

First real vertical slice after M0, **as far as Stage 1 goes**:

`evidence → model → review → freeze/export`

Solver, fabricated schedules, and T11–T20 formalization remain out of Stage 1.

## Key product object

A human-reviewable **modeling draft + confirmed baseline**, including:

- decision brief
- entities / parameters
- hard / soft / conditional constraints
- objectives
- assumptions / unknowns / conflicts
- source provenance

Users inspect and edit these. Unverified AI interpretation is never authoritative business truth. A confirmed baseline is the immutable input to a versioned formal model; only a validated typed model can execute a solver.

## Binding decisions

| Decision | Rule |
| --- | --- |
| Tenancy | Single-user only; no orgs, roles, invitations, approvals |
| Starting point | Whatever business materials the user currently has, or an existing plan. No required modality |
| Import semantics | Materials are **evidence**, not system instructions |
| Direct text | First-class Material; never a system prompt/instruction |
| Prompt injection | Content in sources must never become tool/system authorization |
| Understanding | Consumes the entire current Evidence Set; must expose provenance, conflicts, assumptions, unknowns |
| Ambiguity | Unknown/blocked — never silent coercion to zero/false/no-requirement |
| Solving | Deterministic constraint solving is first-class |
| Solution states | At least `feasible` / `optimal` / `infeasible` / `unknown` / `model_invalid` |
| Change model | New scenarios/versions; do not rewrite confirmed reality |
| Explicit non-goals | No automatic enterprise governance, external execution, payments, arbitrary route planning, or unlimited NL modeling in MVP |
| Vision/API keys | Not an M2 / Materials intake gate. Image intake stores bytes + metadata + full-image provenance only |

## Workspace metaphor

The durable product surfaces are:

1. **Materials** — the current Evidence Set with provenance (question, entered text, and/or uploaded files)
2. **Modeling** (compat: Understanding) — one Agent draft plus human review
3. **Baseline** (compat: Scenarios) — immutable confirmed input and versioned formalization
4. **Results** — deterministic candidates, explanations, what-if impact, and exported history

Stage 1 fills Materials, Modeling, and Baseline with real contracts. Stage 2 extends Baseline and Results with executable typed solver paths while keeping generic or incomplete models visibly unavailable.

## Safety / integrity notes

- Do not treat LLM output as confirmed constraints without human review.
- Do not mark unsupported content as “no requirement.”
- Do not silently overwrite a confirmed baseline when the user explores a change — fork a scenario.
- Do not simulate solver/OCR/LLM success in the UI.
- Do not perform semantic business understanding inside source adapters.
