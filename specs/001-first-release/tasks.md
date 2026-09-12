# Tasks — First release (001)

Authoritative readable MVP task plan. Update status only after implementation **and** verification.

Status legend: `done` | `not_started` | `in_progress` | `blocked`

| ID | Task | Status |
| --- | --- | --- |
| T01 | workspace + runnable baseline | done |
| T02 | product baseline + task tracking | done |
| T03 | persistence contract for project / understanding / scenario / result | done |
| T04 | “My Analyses” + four-workspace GUI | done |
| T05 | auditable fictional mixed-material fixtures + independent expectations | done |
| T06 | text/document material adapters — direct text + TXT/Markdown/text-PDF + provenance | done |
| T07 | table material adapter — CSV/XLSX + units/cell provenance | done |
| T08 | image material adapter — PNG/JPEG + image metadata/full-image provenance; no semantic understanding | done |
| T09 | budgeted cross-material understanding over the current Evidence Set; model capability selected from actual evidence types | done |
| T10 | source-linked review / correction / batch confirmation | done |
| T11 | scenario editing + formal rule model + invalidation/versioning | not_started |
| T12 | deterministic training-scheduling solver | not_started |
| T13 | leave/change conflict explanation + conditional repair | not_started |
| T14 | portfolio combination selection in the same workflow | not_started |
| T15 | explainable multi-solution comparison GUI | not_started |
| T16 | change preview + actual feedback | not_started |
| T17 | result history + independent file export | not_started |
| T18 | interrupted-task recovery + stale-run protection | not_started |
| T19 | data-handling/delete/boundary protections | not_started |
| T20 | two complete end-to-end acceptance runs with real evidence | not_started |

## Notes

- T01/T02 marked done only after M0 verification (install, build, launch, shell load).
- T03 marked done after SQLite migration + API proof scenarios (reopen, immutable V1/V2, unknown premise, null cost, SolveRun metadata without execution).
- T04 marked done after My Analyses + four workspaces were wired to T03 records, built, and verified against the live API.
- T05 marked done after six built-in templates instantiated through the real FastAPI/SQLite path, independent `expected.json` checks passed, and the web app built/linted. Built-in template seeding is **not** the general import pipeline (T06+).
- T06 marked done after direct-text Material persistence (`POST /api/projects/{id}/materials/text`) plus TXT / Markdown / text-PDF multipart import persisted real bytes + SourceSpan rows, collision-safe storage was proven, unsupported/oversize/malformed/encrypted rejects were 4xx, and focused verification passed. Direct text is a first-class Material (`kind=document`, `media_type=text/plain`, `source_origin=direct_text`). The `filename` column is a compatibility/source-label field, not a product requirement that every Material be a file.
- T07 marked done after `python3 scripts/verify_t07_tables.py` proved public CSV/XLSX import through real FastAPI + temp SQLite/data: bytes/checksum, sheet+A1 provenance, explicit unit hints, formula text without recalculation, blank/unknown not coerced, duplicate filenames independent, malformed/unsupported/oversize 4xx with no false partial records.
- T08 marked done after PNG/JPEG intake persisted real bytes, Pillow-validated dimensions/format/mode/checksum, and exactly one honest full-image SourceSpan (`region_state=full_image`, normalized top-left `x=0,y=0,width=1,height=1`) with `semantic_understanding=not_performed`. Image intake performs **zero** Grok/xAI/macOS Vision/OCR/object-detection calls. No vision provider or API key is an M2/T08 gate.
- T06/T07/T08 are engineering adapter slices, not sequential user workflow stages. After verified implementation they are `done` and **M2 is complete**.
- **Stage 1 mapping (2026-09-12):** T09 is implemented as the single Business Modeling Agent over a frozen Material snapshot (question-only evidence allowed). T10 is implemented as claim review (accept/edit/reject/not_applicable) plus freeze/export of an effective baseline. Local contract tests and UI landed. LIVE model/Azure execution is still configuration-blocked and is **not** T20.
- T11–T20 remain `not_started`. Do not mark solver, scenario formalization, or two live end-to-end runs complete from Stage 1.
- Agent interrupt/resume/cancel is part of T09 (Stage 1). T18 remains **solver-run** recovery and is not done.
- T09 consumes the unified Evidence Set. It must understand whatever the user actually supplied. Complex files use the one Azure Content Understanding tool when configured; otherwise coverage stays incomplete. T09 must not silently coerce missing information.
- Do not mark later tasks done from documentation alone.
- Recommended immediate work after LIVE config: real Agent + Azure run on a user analysis (T20 still separate). Then T11 formalization / T12 solver.

## Architecture guardrail

**Never add semantic extraction to a source importer just because a model can consume that source type. Importers preserve evidence; T09+ understand evidence.**

Never make one source family mandatory. Understanding operates over the non-empty Evidence Set the user actually provided.
