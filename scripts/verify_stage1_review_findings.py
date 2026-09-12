#!/usr/bin/env python3
"""Contract checks for the eight Stage 1 review findings.

Labeled doubles only. This is evidence level B, not a live model/Azure run.
Uses an isolated temporary data dir so the user's lucid.db is not touched.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "api"
sys.path.insert(0, str(API_ROOT))

TMP = Path(tempfile.mkdtemp(prefix="lucid-stage1-findings-"))
os.environ["LUCID_DATA_DIR"] = str(TMP)
os.environ["LUCID_DB_PATH"] = str(TMP / "lucid.db")
for key in (
    "LUCID_MODEL_NAME",
    "LUCID_MODEL_BASE_URL",
    "LUCID_MODEL_API_KEY",
    "AZURE_CONTENT_UNDERSTANDING_ENDPOINT",
    "AZURE_CONTENT_UNDERSTANDING_KEY",
    "AZURE_CONTENT_UNDERSTANDING_API_KEY",
    "AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID",
):
    os.environ.pop(key, None)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def _draft(**overrides):
    from app.modeling.draft import ModelingDraft

    body = {
        "completeness": "partial",
        "decision_brief": {"what_to_decide": "Choose a plant shutdown window."},
        "entities": [],
        "parameters": [
            {
                "claim_key": "p-1",
                "name": "overtime_cap",
                "raw_value": "8 hours",
                "normalized_value": 8.0,
                "unit": "hour",
                "evidence_refs": [],
            }
        ],
        "decision_variables": [],
        "constraints": [
            {
                "claim_key": "c-1",
                "strength": "hard",
                "original_statement": "Overtime must not exceed 8 hours.",
                "proposed_interpretation": "hard cap of 8 hours",
                "evidence_refs": [],
            }
        ],
        "objectives": [
            {
                "claim_key": "o-1",
                "original_statement": "Minimize overtime cost.",
                "evidence_refs": [],
            }
        ],
        "assumptions": [],
        "unknowns": [
            {
                "claim_key": "u-1",
                "claim_kind": "unknown",
                "original_statement": "Exception owner is unnamed.",
                "evidence_refs": [],
            }
        ],
        "conflicts": [],
        "readiness_issues": ["Partial by design"],
        "coverage": [],
    }
    body.update(overrides)
    return ModelingDraft.model_validate(body)


def main() -> None:
    from fastapi.testclient import TestClient

    from app.db import ensure_database
    from app.modeling import persistence, runner
    from app.modeling.checkpointer import reset_checkpointer
    from app.modeling.context import CURRENT_RUN, RunContext
    from app.modeling.fakes import AdaptiveScriptModel, ScriptedAzure
    from app.modeling.tools import inspect_evidence, read_source, set_azure_client, understand_material
    from app.main import app
    from app import ingest, store
    from app.schemas import ProjectCreate

    ensure_database()
    reset_checkpointer()
    client = TestClient(app)

    readiness = client.get("/api/readiness").json()
    expect(readiness["live_agent_possible"] is False, "live agent must be blocked without config")
    expect("api_key" not in json.dumps(readiness).lower() or readiness["model"]["api_key_present"] is False, "no secret values")
    expect(readiness["model"]["api_key_present"] is False, "api key presence is boolean only")

    # 1. Public API never runs the scripted double; missing config is failed.
    project = client.post("/api/projects", json={"title": "Public fake check", "summary": "q"}).json()
    forbidden = client.post(
        f"/api/projects/{project['id']}/modeling-runs",
        json={"question": "Can we shut the plant on New Year's Day?", "live": False},
    )
    expect(forbidden.status_code == 422, f"live flag must be rejected, got {forbidden.status_code} {forbidden.text}")
    started = client.post(
        f"/api/projects/{project['id']}/modeling-runs",
        json={"question": "Can we shut the plant on New Year's Day?"},
    )
    expect(started.status_code == 200, started.text)
    run = started.json()
    expect(run["status"] == "failed", f"missing model must fail, got {run['status']}")
    expect(run["error_code"] == "model_not_configured", run.get("error_code"))
    expect(run["live_execution"] is False, "must not claim live execution")
    expect(run.get("drafts") in (None, []), "must not silently produce a sample draft")
    materials = client.get(f"/api/projects/{project['id']}/materials").json()
    expect(len(materials) >= 1, "question-only evidence must be persisted")

    # 2. Question-only evidence is valid standalone source.
    q_project = store.create_project(ProjectCreate(title="Question only", decision_question="Hire 3 extra inspectors in June?"))
    expect(store.list_materials(q_project["id"]) == [], "empty before start")
    failed_or_started = runner.start_run(q_project["id"], "Hire 3 extra inspectors in June?")
    expect(len(store.list_materials(q_project["id"])) >= 1, "question became a material")
    expect(failed_or_started["question_material_id"], "question material is source-linked")

    # Contract path with injected double (explicitly not live).
    contract = store.create_project(ProjectCreate(title="Contract double"))
    ingest.ingest_direct_text(contract["id"], "Capacity must not exceed 12 seats. Overtime requires approval.", label="Policy")
    contract_run = runner.start_run(
        contract["id"],
        "How should we staff the June window?",
        model=AdaptiveScriptModel(),
    )
    expect(contract_run["live_execution"] is False, "injected double is not live")
    finished = runner.wait_for_run(contract_run["id"], timeout=60)
    expect(finished["status"] in {"partial", "completed", "waiting_for_user"}, finished)
    expect(finished["drafts"], "contract double should submit a draft")

    # 3. Honest bounded reads.
    long_text = "A" * 12000 + "TAIL"
    long_project = store.create_project(ProjectCreate(title="Bounded read"))
    imported = ingest.ingest_direct_text(long_project["id"], long_text, label="Long source")
    long_run = persistence.create_run(
        long_project["id"],
        question="What does the long source say?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
        question_material_id=imported["material"]["id"],
    )
    persistence.update_run(long_run["id"], status="running")
    token = CURRENT_RUN.set(
        RunContext(
            project_id=long_project["id"],
            run_id=long_run["id"],
            thread_id=long_run["thread_id"],
            live_execution=False,
        )
    )
    try:
        payload = json.loads(
            read_source.invoke(
                {
                    "material_id": imported["material"]["id"],
                    "start_offset": 0,
                    "end_offset": 50000,
                }
            )
        )
        expect(payload["locator"]["end_offset"] == len(payload["excerpt"]), "end_offset is actual excerpt end")
        expect(payload["locator"]["end_offset"] < 50000, "must not record the oversized requested end")
        expect(payload["truncated"] is True, "long read is truncated")
        expect(payload["total_chars"] == len(long_text), "total_chars is the full source")
        expect(payload["next_offset"] == payload["locator"]["end_offset"], "next_offset continues after the excerpt")
        after = persistence.get_run(long_run["id"])
        coverage = {item["material_id"]: item for item in after["coverage"]}
        expect(
            coverage[imported["material"]["id"]]["state"] == "partially_processed",
            "one excerpt is not whole-material analyzed",
        )

        table_project = store.create_project(ProjectCreate(title="Cell select"))
        from app.schemas import MaterialCreate, SourceSpanCreate

        table = store.persist_imported_material(
            table_project["id"],
            MaterialCreate(
                filename="grid.csv",
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                kind="table",
                byte_size=12,
                checksum="abc",
                metadata={"stored_path": "materials/missing.csv", "source_origin": "upload"},
            ),
            [
                SourceSpanCreate(
                    material_id="pending",
                    locator_kind="cell",
                    sheet="Shifts",
                    cell_ref="B2",
                    excerpt="12 seats",
                ),
                SourceSpanCreate(
                    material_id="pending",
                    locator_kind="cell",
                    sheet="Shifts",
                    cell_ref="C9",
                    excerpt="night crew",
                ),
            ],
        )
        table_run = persistence.create_run(
            table_project["id"],
            question="Which cell?",
            live_execution=False,
            model_configured=False,
            azure_configured=False,
        )
        persistence.update_run(table_run["id"], status="running")
        CURRENT_RUN.reset(token)
        token = CURRENT_RUN.set(
            RunContext(
                project_id=table_project["id"],
                run_id=table_run["id"],
                thread_id=table_run["thread_id"],
                live_execution=False,
            )
        )
        cell = json.loads(
            read_source.invoke(
                {
                    "material_id": table["material"]["id"],
                    "sheet": "Shifts",
                    "cell_ref": "C9",
                }
            )
        )
        expect("night crew" in cell["excerpt"], f"must select the requested cell, got {cell['excerpt']}")
        expect(cell["locator"].get("cell_ref") == "C9", cell["locator"])
        missing = json.loads(
            read_source.invoke(
                {
                    "material_id": table["material"]["id"],
                    "sheet": "Shifts",
                    "cell_ref": "Z99",
                }
            )
        )
        expect("error" in missing, "unknown cell is not silently echoed")
    finally:
        CURRENT_RUN.reset(token)

    # 4. Frozen snapshot: later uploads do not alter an old run.
    snap_project = store.create_project(ProjectCreate(title="Snapshot freeze"))
    first = ingest.ingest_direct_text(snap_project["id"], "Original policy: max 8 overtime hours.", label="V1")
    snap_run = persistence.create_run(
        snap_project["id"],
        question="What is the overtime rule?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
        question_material_id=first["material"]["id"],
    )
    persistence.update_run(snap_run["id"], status="running")
    ingest.ingest_direct_text(snap_project["id"], "Unrelated later upload that must not join the old run.", label="Later")
    token = CURRENT_RUN.set(
        RunContext(
            project_id=snap_project["id"],
            run_id=snap_run["id"],
            thread_id=snap_run["thread_id"],
            live_execution=False,
        )
    )
    try:
        inspected = json.loads(inspect_evidence.invoke({}))
        ids = {item["id"] for item in inspected["materials"]}
        expect(first["material"]["id"] in ids, "snapshot keeps original material")
        expect(len(ids) == len(snap_run["snapshot"]["materials"]), "unrelated upload is not in the old snapshot")
        later = [item for item in store.list_materials(snap_project["id"]) if item["id"] not in ids]
        expect(later, "later upload exists on the project")
        ghost = json.loads(read_source.invoke({"material_id": later[0]["id"]}))
        expect("error" in ghost, "old run cannot read a later unrelated material")
    finally:
        CURRENT_RUN.reset(token)

    # 5. Atomic unreviewed drafts: validate first, force unreviewed, no stray understanding.
    atomic = store.create_project(ProjectCreate(title="Atomic draft"))
    src = ingest.ingest_direct_text(atomic["id"], "Do not exceed 4 concurrent bays.", label="Bays")
    atomic_run = persistence.create_run(
        atomic["id"],
        question="How many bays?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
        question_material_id=src["material"]["id"],
    )
    bad = _draft(
        constraints=[
            {
                "claim_key": "c-1",
                "strength": "hard",
                "original_statement": "Invented constraint",
                "evidence_refs": [
                    {
                        "material_id": "not-in-snapshot",
                        "precision": "exact",
                        "coordinate_system": "original_text",
                        "quote": "made up",
                    }
                ],
                "review_status": "accepted",
            }
        ]
    )
    before = store.list_understandings(atomic["id"])
    try:
        persistence.save_draft(atomic_run["id"], bad)
        raise SystemExit("FAIL: invalid evidence_refs must not save")
    except ValueError as exc:
        expect("evidence_refs" in str(exc), str(exc))
    after = store.list_understandings(atomic["id"])
    expect(len(after) == len(before), "failed draft must not leave an understanding")
    dup = _draft(
        constraints=[
            {
                "claim_key": "c-1",
                "strength": "hard",
                "original_statement": "one",
                "evidence_refs": [],
            },
            {
                "claim_key": "c-1",
                "strength": "soft",
                "original_statement": "two",
                "evidence_refs": [],
            },
        ]
    )
    try:
        persistence.save_draft(atomic_run["id"], dup)
        raise SystemExit("FAIL: duplicate claim keys must not save")
    except ValueError as exc:
        expect("duplicate" in str(exc), str(exc))
    persistence.update_run(atomic_run["id"], status="cancelled")
    try:
        persistence.save_draft(atomic_run["id"], _draft())
        raise SystemExit("FAIL: cancelled run must not publish")
    except persistence.StaleRunError:
        pass
    live_run = persistence.create_run(
        atomic["id"],
        question="How many bays?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
        question_material_id=src["material"]["id"],
    )
    accepted_looking = _draft(
        constraints=[
            {
                "claim_key": "c-1",
                "strength": "hard",
                "original_statement": "Do not exceed 4 concurrent bays.",
                "review_status": "accepted",
                "evidence_refs": [
                    {
                        "material_id": src["material"]["id"],
                        "source_span_id": src["spans"][0]["id"],
                        "precision": "approximate",
                        "coordinate_system": "original_text",
                    }
                ],
            }
        ]
    )
    saved = persistence.save_draft(live_run["id"], accepted_looking)
    claim = next(item for item in saved["claims"] if item["claim_key"] == "c-1")
    expect(claim["review_status"] == "unreviewed", "model cannot accept its own rules")

    # 6. Effective reviewed export.
    persistence.review_claim(claim["id"], action="rejected")
    obj = next(item for item in saved["claims"] if item["claim_key"] == "o-1")
    persistence.review_claim(obj["id"], action="accepted", edited_text="Minimize overtime only when stated.")
    param = next(item for item in saved["claims"] if item["claim_key"] == "p-1")
    persistence.review_claim(param["id"], action="accepted", edited_text="overtime cap is unknown")
    history = persistence.list_claim_review_events(claim["id"])
    expect(history, "review is audited")
    frozen = persistence.freeze_baseline(atomic["id"], saved["id"])
    handoff = frozen["handoff"]
    active_keys = {item.get("claim_key") for item in handoff.get("constraints") or []}
    expect("c-1" not in active_keys, "rejected constraints are not active")
    excluded_keys = {item.get("claim_key") for item in (handoff.get("excluded") or {}).get("constraints") or []}
    expect("c-1" in excluded_keys, "rejected constraints stay in exclusions")
    obj_active = (handoff.get("objectives") or [None])[0]
    expect(obj_active and "Minimize overtime only when stated." in json.dumps(obj_active), obj_active)
    param_active = (handoff.get("parameters") or [None])[0]
    expect(param_active.get("normalized_value") in (None, ""), "edited parameter cannot keep contradicting 8.0")
    expect("source" in frozen["markdown"].lower() or "material" in frozen["markdown"], "markdown has source refs")
    expect("Active parameters" in frozen["markdown"], "markdown must export parameters")
    expect("overtime cap is unknown" in frozen["markdown"], "accepted parameter edit must appear in markdown")
    expect(src["material"]["id"] not in frozen["markdown"] or "source “" in frozen["markdown"], "markdown should prefer source labels over raw UUIDs")
    try:
        persistence.review_claim(claim["id"], action="accepted")
        raise SystemExit("FAIL: confirmed claims must be immutable")
    except store.ConflictError:
        pass

    # Unreviewed source-backed constraint blocks freeze.
    block_project = store.create_project(ProjectCreate(title="Block freeze"))
    block_src = ingest.ingest_direct_text(block_project["id"], "Must close on federal holidays.", label="Holidays")
    block_run = persistence.create_run(
        block_project["id"],
        question="When must we close?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
        question_material_id=block_src["material"]["id"],
    )
    block_draft = persistence.save_draft(
        block_run["id"],
        _draft(
            constraints=[
                {
                    "claim_key": "c-1",
                    "strength": "hard",
                    "original_statement": "Must close on federal holidays.",
                    "evidence_refs": [
                        {
                            "material_id": block_src["material"]["id"],
                            "source_span_id": block_src["spans"][0]["id"],
                            "precision": "approximate",
                            "coordinate_system": "original_text",
                        }
                    ],
                }
            ]
        ),
    )
    try:
        persistence.freeze_baseline(block_project["id"], block_draft["id"])
        raise SystemExit("FAIL: unreviewed source-backed constraint must block freeze")
    except store.ConflictError:
        pass
    # Unknowns do not by themselves block freeze after review of the constraint.
    c1 = next(item for item in block_draft["claims"] if item["claim_key"] == "c-1")
    persistence.review_claim(c1["id"], action="accepted")
    o1 = next(item for item in block_draft["claims"] if item["claim_key"] == "o-1")
    persistence.review_claim(o1["id"], action="accepted")
    p1 = next(item for item in block_draft["claims"] if item["claim_key"] == "p-1")
    persistence.review_claim(p1["id"], action="not_applicable")
    frozen2 = persistence.freeze_baseline(block_project["id"], block_draft["id"])
    expect(frozen2["handoff"]["unknowns"], "unknowns remain visible")
    expect(frozen2["solver"] == "not_executed", "handoff is pre-solver")

    # 7. Idempotent resume / overlapping workers.
    clarify_project = store.create_project(ProjectCreate(title="Resume"))
    ingest.ingest_direct_text(clarify_project["id"], "Approval owner is missing.", label="Gap")
    clarify_run = runner.start_run(
        clarify_project["id"],
        "Who approves overtime?",
        model=AdaptiveScriptModel(clarify_once=True),
    )
    waiting = runner.wait_for_run(clarify_run["id"], timeout=60)
    expect(waiting["status"] == "waiting_for_user", waiting)
    blank = client.post(f"/api/modeling-runs/{waiting['id']}/resume", json={"answer": "   "})
    expect(blank.status_code == 422, f"blank resume {blank.status_code}")
    first = client.post(
        f"/api/modeling-runs/{waiting['id']}/resume",
        json={"answer": "The plant manager is the overtime approver."},
    )
    expect(first.status_code == 200, first.text)
    second = client.post(
        f"/api/modeling-runs/{waiting['id']}/resume",
        json={"answer": "Someone else."},
    )
    expect(second.status_code == 409, f"duplicate resume {second.status_code} {second.text}")
    resumed = runner.wait_for_run(waiting["id"], timeout=60)
    expect(resumed["status"] in {"partial", "completed"}, resumed)
    answers = [item for item in store.list_materials(clarify_project["id"]) if "Clarification" in (item.get("filename") or "")]
    expect(len(answers) == 1, f"clarification evidence must be idempotent, got {len(answers)}")

    # 8. Private Azure operation state.
    from app.modeling.azure_cu import AzureContentUnderstanding, derive_representation

    azure_project = store.create_project(ProjectCreate(title="Azure privacy"))
    image_meta = ingest.ingest_direct_text(azure_project["id"], "placeholder", label="Bytes")
    azure_run = persistence.create_run(
        azure_project["id"],
        question="Read the image",
        live_execution=False,
        model_configured=False,
        azure_configured=True,
        question_material_id=image_meta["material"]["id"],
    )
    persistence.update_run(azure_run["id"], status="running")
    secret = "PRIVATE_CONTINUATION_TOKEN_OPAQUE_SECRET_VALUE_NOT_AN_ID"
    set_azure_client(
        ScriptedAzure(operation_id="op-azure-real-id", token=secret, markdown="Holiday names on page 1.")
    )
    token = CURRENT_RUN.set(
        RunContext(
            project_id=azure_project["id"],
            run_id=azure_run["id"],
            thread_id=azure_run["thread_id"],
            live_execution=False,
        )
    )
    try:
        understood = json.loads(understand_material.invoke({"material_id": image_meta["material"]["id"]}))
        expect(understood["operation_id"] == "op-azure-real-id", understood)
        blob = json.dumps(understood)
        expect(secret not in blob, "continuation token must not appear in tool output")
        expect(understood["operation_id"] != secret[:80], "token prefix is not an operation id")
        public_cached = persistence.get_cached_analysis(
            image_meta["material"]["id"],
            image_meta["material"]["checksum"],
            "prebuilt-document",
            include_secrets=False,
        )
        expect(public_cached is not None and "continuation_token" not in public_cached, public_cached)
        private_cached = persistence.get_cached_analysis(
            image_meta["material"]["id"],
            image_meta["material"]["checksum"],
            "prebuilt-document",
            include_secrets=True,
        )
        expect(private_cached and private_cached.get("continuation_token") == secret, "token stored privately")
    finally:
        CURRENT_RUN.reset(token)
        set_azure_client(AzureContentUnderstanding())

    class FakePoller:
        operation_id = "from-sdk-property"
        def continuation_token(self):
            return secret
        def result(self, timeout=None):
            raise TimeoutError("polling timed out")

    class FakeClient:
        def begin_analyze_binary(self, *args, **kwargs):
            return FakePoller()

    wrapped = AzureContentUnderstanding(client=FakeClient())
    timed = wrapped.analyze_bytes(b"abc", media_type="application/pdf")
    expect(timed["status"] in {"timeout", "running"}, timed)
    expect(timed["status"] != "succeeded", "timeout is not empty success")
    expect(timed["operation_id"] == "from-sdk-property", timed)
    expect(timed.get("derived") in (None, {}), timed)
    derived = derive_representation({"markdown": "abc", "contents": [{"markdown": "abc", "pageNumber": 1}]})
    expect(derived["coordinate_system"] == "azure_markdown", derived)
    expect(derived["original_coordinates"] == "unknown", derived)

    print("PASS: eight Stage 1 review findings")
    print(f"isolated_data_dir={TMP}")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
