# Acceptance — First release (001)

## Global acceptance rules

- Single-user only behavior throughout.
- Imported or entered content never elevates to system/tool authorization.
- Unknowns remain blocked until explicitly resolved.
- Scenario changes create new versions; confirmed baselines are not overwritten in place.
- Solver results expose explicit state labels (`feasible` / `optimal` / `infeasible` / `unknown` / `model_invalid` as applicable).
- No simulated success for unimplemented adapters.
- No required input modality. Direct text, files, and mixtures are all valid Evidence Sets.
- Source adapters must not perform semantic business understanding.

## Milestone gates

| Gate | Required evidence |
| --- | --- |
| M0 | App builds/starts; landing + workbench shell loads; docs/tasks present |
| M1 | Persistence contract + My Analyses / four workspaces backed by real records |
| M2 | Fixtures plus peer Materials (direct text / TXT-MD-PDF / CSV-XLSX / PNG-JPEG) persist with source spans / cell / full-image region provenance. No vision provider/API key gate |
| M3 | Understanding review/correction + formal scenario model versioning |
| M4 | Deterministic schedule + portfolio solve + comparison UI |
| M5 | Change preview, export, recovery, boundary protections |
| M6 | Two full E2E acceptance runs with artifacts |

## M0 acceptance (this bootstrap)

- [x] `/Users/hairen/project/lucid` exists as dedicated project
- [x] API health endpoint responds
- [x] Web landing loads at local Vite URL
- [x] Workbench routes for Materials / Modeling / Baseline / Results (`/understanding` and `/scenarios` redirect)
- [x] Product baseline + ADR + specs + AGENTS.md present
- [ ] T11–T20 capabilities (explicitly **not** claimed; T09/T10 are Stage 1 below)

## T06–T08 intake (M2)

- [x] Direct user-entered text is a first-class Material (`POST /api/projects/{id}/materials/text`)
- [x] TXT / Markdown / text-PDF multipart import into an existing project
- [x] Stored bytes + SHA-256 + SourceSpan provenance
- [x] CSV / XLSX cell provenance through real FastAPI + temp SQLite/data (T07)
- [x] PNG / JPEG bytes + image metadata + exactly one honest full-image region span; semantic understanding is not performed; no Grok/xAI/macOS Vision call is required or made (T08)
- [x] An analysis may contain only direct text, only files, or an arbitrary mixture; no modality is required
- M2 is **complete** after T06 + T07 + T08 all pass. No vision provider/API key is an M2 gate.

## T20 acceptance (future)

1. Scheduling vertical slice with real evidence artifacts
2. Portfolio combination workflow with real evidence artifacts

## Stage 1 (T09/T10 mapping, 2026-09-12)

- [x] One Business Modeling Agent over a frozen Material snapshot; question-only evidence allowed
- [x] Claim review + freeze/export of an effective pre-solver baseline
- [x] Local contract tests and browser walkthrough
- [ ] LIVE model + Azure Content Understanding (configuration-blocked; not T20)

T11–T20 remain not started. Solver results are not Stage 1 acceptance.
