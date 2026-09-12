# Spec — First release (001)

Status: this file is the **full first-release** product spec (T01–T20). It is not a claim that every item is already shipped.

**Stage 1 (2026-09-12):** T01–T10 locally — evidence → one Business Modeling Agent → human review → freeze/export of a pre-solver baseline. **Stage 2:** T11–T19 are implemented and locally verified; T20 remains blocked on two live Agent-backed acceptance runs. LIVE model/Azure remains configuration-blocked in this checkout.

T20 remains the final acceptance gate: two complete live evidence runs. Historical execution notes under `/Users/hairen/project/.tasks/` are not a second current plan.

## Goal

Deliver a single-user LUCID workbench that supports one complete scheduling vertical slice and one portfolio-selection workflow, with reviewable understanding, versioned scenarios, deterministic solving, comparison, and export.

## Users

- Single local user planning under finite business constraints (e.g., training schedules, portfolio combinations).

## In scope

- Record a non-empty Evidence Set of peer Materials: direct user-entered text, TXT/Markdown/text-PDF, CSV/XLSX, and PNG/JPEG
- Budgeted cross-material understanding loop over the current Evidence Set, with provenance
- Source-linked review / correction / batch confirmation
- Scenario editing + formal rule model + invalidation/versioning
- Deterministic training-scheduling solver
- Leave/change conflict explanation + conditional repair
- Portfolio combination selection in the same workflow
- Explainable multi-solution comparison
- Change preview + actual feedback
- Result history + independent file export
- Interrupted-task recovery + stale-run protection
- Data-handling / delete / boundary protections
- Two complete end-to-end acceptance runs with real evidence

## Out of scope

- Multi-user collaboration, organizations, roles, invitations, approvals
- Agent orchestration console / AI coding product
- Automatic enterprise governance, external execution, payments
- Arbitrary route planning or unlimited natural-language modeling
- Treating imported or entered prompt-injection text as system authorization
- Requiring any particular source modality
- Semantic understanding inside source adapters (including image OCR/object detection/Grok/macOS Vision during intake)

## Core quality bars

1. Materials are evidence, not instructions. Direct user-entered text is the same class of Material as uploaded files.
2. Unknowns stay unknown/blocked until resolved.
3. Confirmed reality is not silently rewritten — changes fork scenarios.
4. Solver outcomes use explicit states: feasible / optimal / infeasible / unknown / model_invalid.
5. AI assistance never replaces human confirmation of the business baseline.
6. Materials and Understanding are separate layers. Importers preserve evidence; T09+ understand evidence.

## Success definition

A user can complete:

`evidence → understand → correct → schedule → change → export`

from whatever materials they actually have (text only, files only, or mixed), and a second portfolio workflow using the same product architecture, with auditable fixtures and independent expectations.
