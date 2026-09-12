# Stage 1 review

Date: 2026-09-12. Review of the interrupted Stage 1 implementation, plus the wrap-up in this session. No parallel rewrite.

Evidence: **B** (contract tests with labeled doubles in `scripts/verify_stage1_review_findings.py`) and **D** (browser walkthrough). Not a live model/Azure run.

## Eight original findings (closed at contract level)

| # | Finding | Fix | Status |
| --- | --- | --- | --- |
| 1 | Public `start_run(live=False)` built `AdaptiveScriptModel` | Public runner never constructs the scripted model. Missing config → `failed` / `model_not_configured`. Doubles only via `model=` | Fixed |
| 2 | Empty-material projects rejected before the question was stored | `POST /api/analyses/start` + `ensure_question_material` | Fixed |
| 3 | `read_source` treated requested end offsets as analyzed | Honest bounded ranges; page/sheet/cell select real content | Fixed |
| 4 | Tools read live Materials instead of a frozen snapshot | `snapshot_json`; clarification may append once | Fixed |
| 5 | Understanding written first; model-supplied `review_status` accepted | Validate then atomic write; AI claims forced `unreviewed` | Fixed |
| 6 | Export copied unreviewed arrays; rejected rules could freeze | Effective/excluded/pending partitions; freeze concurrency-safe | Fixed |
| 7 | Resume could overlap workers; global checkpointer | Atomic `waiting_for_user` claim; checkpointer per data dir | Fixed |
| 8 | `continuation_token[:80]` as operation id | Persist poller `operation_id`; tokens private | Fixed |

## Additional findings in this wrap-up

| # | Location | Impact | Fix | Verification |
| --- | --- | --- | --- | --- |
| 9 | `api/app/modeling/export.py` `render_markdown` | Markdown omitted parameters/entities/variables; refs were raw UUIDs | Export those sections; label sources by filename from coverage/snapshot | `verify_stage1_review_findings.py` asserts “Active parameters” and the edited parameter text |
| 10 | `modeling_routes.py` material preview | Offsets/page/sheet/cell were not used to select content | Preview query params; PDF `#page=` | Typecheck + UI source viewer |
| 11 | Modeling UI | Repeated config banners; source buttons showed UUID slices | One status strip; filename locators; source↔claim | Browser screenshots 02–05 |
| 12 | `DESIGN.md` | Claimed Notion reference was not fetched | Fetched 2026-09-12; adapted workbench tokens (not marketing purple/navy) | This file + `DESIGN.md` |
| 13 | `.gitignore` | `data/materials/`, backups, probe dumps, screenshot chrome profiles could leak | Ignored | File present |

## What this review is not

- Not LIVE acceptance (missing `LUCID_MODEL_*` and Azure CU config).
- Not a solver review (solver is Stage 2 / T12+).
- Not a claim that six fictional templates are real company operations.
