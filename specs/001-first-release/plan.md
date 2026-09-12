# Plan — First release (001)

Status: historical phase map for the **full** first release (M0–M6 / T01–T20). Current Stage 1 delivery is T01–T10 locally (LIVE model/Azure still blocked). T11–T20 remain later work. Authoritative status: `tasks.md`. Delivery summary: `docs/reports/stage1-handoff.md`.

## Phases

### M0 — Bootstrap (T01–T02)

- Runnable local stack (Vite/React + FastAPI + SQLite)
- Product baseline docs + ADR + task tracking
- Landing + four-workspace shell

### M1 — Persistence + GUI skeleton (T03–T04)

- Persistence contract for project / understanding / scenario / result
- “My Analyses” list and deeper four-workspace GUI

### M2 — Materials intake (T05–T08)

Source-adapter / provenance slices. These are engineering tasks, **not** sequential user workflow stages. All source modalities are optional peers in one Evidence Set.

- Auditable fictional mixed-material fixtures (T05)
- T06: text/document material adapters — direct text + TXT/Markdown/text-PDF + provenance
- T07: table material adapter — CSV/XLSX + units/cell provenance
- T08: image material adapter — PNG/JPEG + image metadata/full-image provenance; no semantic understanding

No vision provider or API key is an M2/T08 gate.

### M3 — Understanding + formalization (T09–T11)

- T09: budgeted cross-material understanding over the current Evidence Set; model capability selected from actual evidence types
- Source-linked review/correction/confirmation
- Scenario editing + formal rule model + versioning

**Stage 1 mapping:** T09/T10 landed as one Business Modeling Agent + claim review + freeze/export (LIVE model/Azure still configuration-blocked). T11 formalization remains Stage 2 / later first-release work.

### M4 — Solve + compare (T12–T15)

- Deterministic training-scheduling solver
- Conflict explanation / conditional repair
- Portfolio combination selection
- Multi-solution comparison GUI

### M5 — Change, export, resilience (T16–T19)

- Change preview + feedback
- Result history + export
- Interrupted-task recovery + stale-run protection
- Data-handling / delete / boundary protections

### M6 — Acceptance (T20)

- Two complete end-to-end acceptance runs with real evidence

## Engineering principles

- Small architecture; extend `api/` + `web/`
- No fake solver/OCR/LLM success
- Mark tasks done only when verified
- Prefer durable contracts over throwaway mocks
- **Never add semantic extraction to a source importer just because a model can consume that source type. Importers preserve evidence; T09+ understand evidence.**
- Never make one source family mandatory. Understanding operates over the non-empty Evidence Set the user actually provided.

## Dependencies

- T03 before meaningful T04 data wiring
- T05 fixtures before serious import acceptance
- T06–T08 adapters complete before T09 (T09 consumes the unified Evidence Set; it does not re-implement intake)
- T11 formal model before T12 solver
- T12/T14 before T15 comparison depth
- T17–T19 before T20 acceptance evidence
