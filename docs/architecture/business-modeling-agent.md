# Business Modeling Agent — Stage 1 architecture

LUCID Stage 1 is the evidence and review layer: one Business Modeling Agent drafts source-grounded claims; a human reviews them; a confirmed baseline is exported. Stage 2 consumes that baseline with deterministic formal solvers. There is no multi-agent swarm or second content-understanding engine.

## Pipeline

```
User question + peer Materials
        │
        ▼
Frozen run snapshot (ids, versions, fingerprints)
        │
        ▼
ONE LangChain create_agent + LangGraph checkpointer
        │
        ├── inspect_evidence / read_source  (bounded, snapshot-only)
        ├── understand_material             (ONE Azure Content Understanding job)
        ├── ask_clarification               (interrupt; answer becomes peer text)
        └── submit_modeling_draft           (validated, forced unreviewed)
        │
        ▼
Human review (accept / edit / reject / not_applicable)
        │
        ▼
Immutable baseline + JSON/Markdown handoff
        │
        ▼
Stage 2: typed formal model, deterministic training/portfolio solver, what-if impact, comparison, history/export, and solver recovery. T20 live acceptance remains separate.
```

## One Agent

- Runtime: LangChain `create_agent` with LangGraph SQLite checkpointer keyed to the data directory.
- Public API never constructs `AdaptiveScriptModel`. Tests inject that double explicitly.
- Missing `LUCID_MODEL_NAME` / `LUCID_MODEL_BASE_URL` / `LUCID_MODEL_API_KEY` persists a **failed** run with `error_code=model_not_configured`. It is not a sample success.
- A non-blank decision question is durable direct-text evidence. Files are optional peers.

## One Azure service

- Installed SDK: `azure-ai-contentunderstanding`.
- Observed local signature used in code: `begin_analyze_binary` on the client; poller `operation_id` is the public job id.
- Continuation tokens stay private. They are not operation IDs, Agent-tool payloads, or browser fields.
- Timeout is not an empty successful result.
- Official Microsoft/LangChain HTTP docs were selected in the product brief. This wrap-up verified **installed** interfaces instead of guessing:

  - LangChain `create_agent(model, tools, *, system_prompt, checkpointer, name, response_format=...)`
  - LangGraph `SqliteSaver(conn)`
  - Azure `ContentUnderstandingClient.begin_analyze_binary(analyzer_id, binary_input, *, content_type=...)` (GA client, API version default `2025-11-01`)

## Snapshot, coverage, review

- Tool reads bind to the frozen run snapshot, not live Materials. Unrelated later uploads do not rewrite an old run. One clarification answer may append once as equal-status text.
- `read_source` returns actual offsets, `total`, `next_offset`, and truncation. Reading one excerpt is not whole-source analysis. `partially_processed` stays incomplete for draft/baseline readiness.
- New AI claims are forced `unreviewed`. `not_applicable` is stored only where the schema allows it.
- Effective export uses human review: accepted edits change semantics; rejected / not_applicable items are excluded; not every unknown blocks freeze.

## Persistence

Schema version **5** (`app_meta.schema_version`). Version 5 adds a partial unique index so one project can have at most one `queued` / `running` / `waiting_for_user` modeling run. Modeling tables live beside existing T03 project / understanding / scenario / SolveRun rows. Migration copies existing databases; it does not wipe user rows. Checkpointer connections are rebuilt per data directory.

## UI contract

Workspaces: Materials, Modeling, Baseline, Results. Compatibility routes: `/understanding` → Modeling, `/scenarios` → Baseline. `/api/readiness` returns non-secret presence flags only.
