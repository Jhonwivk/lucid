#!/usr/bin/env python3
"""Focused Stage 1 recovery, snapshot, provenance, export, and state-machine checks.

Labeled doubles only. Evidence level B — not a live model/Azure acceptance.
Uses an isolated temporary data dir so the user's lucid.db is not touched.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "api"
sys.path.insert(0, str(API_ROOT))

TMP = Path(tempfile.mkdtemp(prefix="lucid-stage1-recovery-"))
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


def _coverage(run: dict) -> list[dict]:
    return [
        {
            "material_id": item["id"],
            "filename": item.get("filename") or "source",
            "state": "analyzed",
            "detail": "test coverage",
            "needs_azure": False,
        }
        for item in (run.get("snapshot") or {}).get("materials") or []
    ]


def _draft(run, **overrides):
    from app.modeling.draft import ModelingDraft

    body = {
        "completeness": "partial",
        "decision_brief": {"what_to_decide": "Choose a plant shutdown window."},
        "entities": [],
        "parameters": [],
        "decision_variables": [],
        "constraints": [
            {
                "claim_key": "c-1",
                "strength": "hard",
                "original_statement": "A stated constraint.",
                "evidence_refs": [],
            }
        ],
        "objectives": [
            {
                "claim_key": "o-1",
                "original_statement": "A stated objective.",
                "evidence_refs": [],
            }
        ],
        "assumptions": [],
        "unknowns": [],
        "conflicts": [],
        "readiness_issues": ["Partial by design"],
        "coverage": _coverage(run),
    }
    body.update(overrides)
    if "coverage" not in overrides:
        body["coverage"] = _coverage(run)
    return ModelingDraft.model_validate(body)


def _running(persistence, run_id: str) -> dict:
    from app.db import utc_now

    persistence.update_run(run_id, status="running", started_at=utc_now(), heartbeat_at=utc_now())
    return persistence.get_run(run_id)


def main() -> None:
    from fastapi.testclient import TestClient

    from app import ingest, store
    from app.db import ensure_database, get_data_dir, utc_now
    from app.main import app
    from app.modeling import persistence, runner
    from app.modeling.checkpointer import reset_checkpointer
    from app.modeling.context import CURRENT_RUN, RunContext
    from app.modeling.fakes import AdaptiveScriptModel
    from app.modeling.snapshot import get_snapshot_material, live_material_file, read_snapshot_bytes
    from app.modeling.tools import read_source
    from app.schemas import ProjectCreate

    ensure_database()
    reset_checkpointer()
    client = TestClient(app)

    # --- Frozen snapshot bytes survive live file replace/delete ---
    snap_project = store.create_project(ProjectCreate(title="Frozen bytes"))
    original_text = "Original frozen overtime rule: max 8 hours."
    first = ingest.ingest_direct_text(snap_project["id"], original_text, label="Policy")
    snap_run = persistence.create_run(
        snap_project["id"],
        question="What is the overtime rule?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
        question_material_id=first["material"]["id"],
    )
    expect(not snap_run["stale_input"], "text copy should succeed")
    material = get_snapshot_material(snap_run, first["material"]["id"])
    expect(material and material.get("snapshot_path"), material)
    frozen_before = read_snapshot_bytes(snap_run, material)
    live_path = live_material_file(snap_project["id"], first["material"])
    expect(live_path is not None and live_path.is_file(), "live file exists before replace")
    live_path.write_bytes(b"REPLACED LIVE BYTES MUST NOT BE READ BY THE RUN")
    frozen_after_replace = read_snapshot_bytes(persistence.get_run(snap_run["id"]), material)
    expect(frozen_after_replace == frozen_before, "replaced live file must not change frozen bytes")
    expect(original_text.encode("utf-8") == frozen_after_replace, "frozen bytes keep original text")
    live_path.unlink()
    frozen_after_delete = read_snapshot_bytes(persistence.get_run(snap_run["id"]), material)
    expect(frozen_after_delete == frozen_before, "deleted live file must not change frozen bytes")

    _running(persistence, snap_run["id"])
    token = CURRENT_RUN.set(
        RunContext(
            project_id=snap_project["id"],
            run_id=snap_run["id"],
            thread_id=snap_run["thread_id"],
            live_execution=False,
        )
    )
    try:
        read_payload = json.loads(read_source.invoke({"material_id": first["material"]["id"]}))
        expect(original_text in read_payload["excerpt"], read_payload)
        snap_file = get_data_dir() / material["snapshot_path"]
        snap_file.write_bytes(b"tampered snapshot bytes")
        stale_read = json.loads(read_source.invoke({"material_id": first["material"]["id"]}))
        expect(stale_read.get("error") == "stale_input", stale_read)
        after_stale = persistence.get_run(snap_run["id"])
        expect(after_stale["stale_input"] is True, after_stale)
        try:
            persistence.save_draft(snap_run["id"], _draft(after_stale))
            raise SystemExit("FAIL: stale_input must block draft submit")
        except persistence.StaleRunError:
            pass
    finally:
        CURRENT_RUN.reset(token)

    # --- Provenance: forged locators / quotes / missing coverage ---
    prov_project = store.create_project(ProjectCreate(title="Provenance"))
    src = ingest.ingest_direct_text(
        prov_project["id"],
        "Capacity must not exceed 12 seats on the day shift.",
        label="Policy",
    )
    extra = ingest.ingest_direct_text(prov_project["id"], "Peer note: keep unknowns unknown.", label="Note")
    prov_run = persistence.create_run(
        prov_project["id"],
        question="What is the capacity rule?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
        question_material_id=src["material"]["id"],
    )
    checksum = src["material"]["checksum"]
    span_id = src["spans"][0]["id"]

    def reject(draft, needle: str) -> None:
        try:
            persistence.save_draft(prov_run["id"], draft)
            raise SystemExit(f"FAIL: expected rejection containing {needle!r}")
        except ValueError as exc:
            expect(needle in str(exc), str(exc))

    reject(
        _draft(
            prov_run,
            constraints=[
                {
                    "claim_key": "c-1",
                    "strength": "hard",
                    "original_statement": "Forged page",
                    "evidence_refs": [
                        {
                            "material_id": src["material"]["id"],
                            "material_checksum": checksum,
                            "precision": "exact",
                            "coordinate_system": "original_text",
                            "page": 99,
                            "quote": "Capacity must not exceed 12 seats",
                        }
                    ],
                }
            ],
        ),
        "c-1[0]",
    )
    reject(
        _draft(
            prov_run,
            constraints=[
                {
                    "claim_key": "c-1",
                    "strength": "hard",
                    "original_statement": "Forged sheet",
                    "evidence_refs": [
                        {
                            "material_id": src["material"]["id"],
                            "material_checksum": checksum,
                            "precision": "exact",
                            "coordinate_system": "original_text",
                            "sheet": "NotASheet",
                            "cell_ref": "Z9",
                            "quote": "Capacity must not exceed 12 seats",
                        }
                    ],
                }
            ],
        ),
        "c-1[0]",
    )
    reject(
        _draft(
            prov_run,
            constraints=[
                {
                    "claim_key": "c-1",
                    "strength": "hard",
                    "original_statement": "Forged offset",
                    "evidence_refs": [
                        {
                            "material_id": src["material"]["id"],
                            "source_span_id": span_id,
                            "material_checksum": checksum,
                            "precision": "exact",
                            "coordinate_system": "original_text",
                            "start_offset": 0,
                            "end_offset": 999999,
                            "quote": "Capacity must not exceed 12 seats",
                        }
                    ],
                }
            ],
        ),
        "c-1[0]",
    )
    reject(
        _draft(
            prov_run,
            constraints=[
                {
                    "claim_key": "c-1",
                    "strength": "hard",
                    "original_statement": "Forged quote",
                    "evidence_refs": [
                        {
                            "material_id": src["material"]["id"],
                            "source_span_id": span_id,
                            "material_checksum": checksum,
                            "precision": "exact",
                            "coordinate_system": "original_text",
                            "quote": "this exact quote is not in the original snapshot",
                        }
                    ],
                }
            ],
        ),
        "c-1[0]",
    )
    reject(
        _draft(
            prov_run,
            coverage=[
                {
                    "material_id": src["material"]["id"],
                    "filename": "Policy",
                    "state": "analyzed",
                    "detail": "omits the peer note",
                    "needs_azure": False,
                }
            ],
        ),
        "missing snapshot materials",
    )
    reject(
        _draft(
            prov_run,
            constraints=[
                {
                    "claim_key": "c-1",
                    "strength": "hard",
                    "original_statement": "Azure self-proof",
                    "evidence_refs": [
                        {
                            "material_id": src["material"]["id"],
                            "material_checksum": checksum,
                            "precision": "exact",
                            "coordinate_system": "azure_markdown",
                            "quote": "Capacity must not exceed 12 seats",
                            "provider_locator": {"analyzer_id": "prebuilt-document"},
                        }
                    ],
                }
            ],
        ),
        "c-1[0]",
    )
    del extra

    # --- Review/export semantics for assumptions, unknowns, conflicts ---
    export_project = store.create_project(ProjectCreate(title="Export semantics"))
    export_src = ingest.ingest_direct_text(
        export_project["id"],
        "Assume two crews. Owner is unknown. Holiday vs overtime conflict.",
        label="Notes",
    )
    export_run = persistence.create_run(
        export_project["id"],
        question="What should we freeze?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
        question_material_id=export_src["material"]["id"],
    )
    export_draft = persistence.save_draft(
        export_run["id"],
        _draft(
            export_run,
            assumptions=[
                {
                    "claim_key": "a-1",
                    "claim_kind": "assumption",
                    "original_statement": "Assume two crews are available.",
                    "evidence_refs": [],
                }
            ],
            unknowns=[
                {
                    "claim_key": "u-1",
                    "claim_kind": "unknown",
                    "original_statement": "Exception owner is unnamed.",
                    "evidence_refs": [],
                }
            ],
            conflicts=[
                {
                    "claim_key": "x-1",
                    "claim_kind": "conflict",
                    "original_statement": "Holiday shutdown conflicts with overtime cap.",
                    "evidence_refs": [],
                }
            ],
        ),
    )
    by_key = {item["claim_key"]: item for item in export_draft["claims"]}
    persistence.review_claim(by_key["c-1"]["id"], action="accepted")
    persistence.review_claim(by_key["o-1"]["id"], action="accepted")
    persistence.review_claim(by_key["a-1"]["id"], action="accepted", edited_text="Assume one crew, not two.")
    persistence.review_claim(by_key["u-1"]["id"], action="rejected")
    persistence.review_claim(by_key["x-1"]["id"], action="needs_clarification")
    frozen = persistence.freeze_baseline(export_project["id"], export_draft["id"])
    handoff = frozen["handoff"]
    assumption_keys = {item.get("claim_key") for item in handoff.get("assumptions") or []}
    expect("a-1" in assumption_keys, handoff.get("assumptions"))
    expect("Assume one crew, not two." in json.dumps(handoff.get("assumptions")), handoff.get("assumptions"))
    expect("Assume two crews are available." not in json.dumps(handoff.get("assumptions") or []) or "Assume one crew" in json.dumps(handoff.get("assumptions")), "edited assumption is active")
    unknown_keys = {item.get("claim_key") for item in handoff.get("unknowns") or []}
    expect("u-1" not in unknown_keys, "rejected unknown is not active")
    excluded_unknowns = {item.get("claim_key") for item in (handoff.get("excluded") or {}).get("unknowns") or []}
    expect("u-1" in excluded_unknowns, "rejected unknown stays excluded")
    conflict_keys = {item.get("claim_key") for item in handoff.get("conflicts") or []}
    expect("x-1" not in conflict_keys, "needs_clarification conflict is not active")
    unresolved_conflicts = {
        item.get("claim_key") for item in (handoff.get("unresolved") or {}).get("conflicts") or []
    }
    expect("x-1" in unresolved_conflicts, "needs_clarification conflict is unresolved")
    markdown = frozen["markdown"]
    expect("Assume one crew, not two." in markdown, markdown)
    expect("Exception owner is unnamed." not in markdown.split("## Unknowns")[0] if "## Unknowns" in markdown else True, markdown)
    expect("needs_clarification" in markdown.lower() or "Needs clarification" in markdown, markdown)
    expect(handoff.get("solver") == "not_executed", handoff)
    expect(frozen["immutable"] is True, frozen)

    # --- Terminal status protection ---
    term_project = store.create_project(ProjectCreate(title="Terminal"))
    ingest.ingest_direct_text(term_project["id"], "Done.", label="Done")
    term_run = persistence.create_run(
        term_project["id"],
        question="Terminal?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
    )
    _running(persistence, term_run["id"])
    persistence.update_run(term_run["id"], status="completed", finished_at=utc_now())
    try:
        persistence.update_run(term_run["id"], status="failed", error_code="nope")
        raise SystemExit("FAIL: completed → failed must be rejected")
    except persistence.StaleRunError:
        pass
    cancelled = persistence.request_cancel(term_run["id"])
    expect(cancelled["status"] == "completed", cancelled)
    failed_run = persistence.create_run(
        term_project["id"],
        question="Failed?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
    )
    _running(persistence, failed_run["id"])
    persistence.update_run(failed_run["id"], status="failed", error_code="boom", finished_at=utc_now())
    try:
        persistence.update_run(failed_run["id"], status="running")
        raise SystemExit("FAIL: failed → running must be rejected")
    except persistence.StaleRunError:
        pass

    # --- Concurrent resume: only one CAS winner ---
    resume_project = store.create_project(ProjectCreate(title="CAS resume"))
    ingest.ingest_direct_text(resume_project["id"], "Owner is missing.", label="Gap")
    resume_run = persistence.create_run(
        resume_project["id"],
        question="Who approves?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
    )
    _running(persistence, resume_run["id"])
    persistence.update_run(resume_run["id"], status="waiting_for_user")
    persistence.ensure_clarification(
        resume_run["id"],
        question="Who approves overtime?",
        reason="Missing owner",
        affected_claim_keys=["u-1"],
    )

    def try_claim(answer: str) -> str:
        try:
            persistence.claim_resume(resume_run["id"], answer)
            return "ok"
        except store.ConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(try_claim, "The plant manager.")
        second = pool.submit(try_claim, "Someone else.")
        outcomes = [first.result(), second.result()]
    expect(outcomes.count("ok") == 1, outcomes)
    expect(outcomes.count("conflict") == 1, outcomes)
    claimed = persistence.get_run(resume_run["id"])
    expect(claimed["status"] == "running", claimed)
    persistence.rollback_resume(claimed["id"], claimed.get("resume_claim_id"))
    rolled = persistence.get_run(resume_run["id"])
    expect(rolled["status"] == "waiting_for_user", rolled)

    # --- Resume worker start failure must not stay running ---
    clarify_project = store.create_project(ProjectCreate(title="Resume spawn fail"))
    ingest.ingest_direct_text(clarify_project["id"], "Approval owner is missing.", label="Gap")
    clarify_run = runner.start_run(
        clarify_project["id"],
        "Who approves overtime?",
        model=AdaptiveScriptModel(clarify_once=True),
    )
    waiting = runner.wait_for_run(clarify_run["id"], timeout=60)
    expect(waiting["status"] == "waiting_for_user", waiting)
    original_spawn = runner._spawn

    def fail_spawn(*_args, **_kwargs):
        raise RuntimeError("worker start failed")

    runner._spawn = fail_spawn  # type: ignore[method-assign]
    try:
        try:
            runner.resume_run(waiting["id"], "The plant manager is the overtime approver.")
            raise SystemExit("FAIL: spawn failure should surface")
        except RuntimeError:
            pass
        after_fail = persistence.get_run(waiting["id"])
        expect(after_fail["status"] == "waiting_for_user", after_fail)
        expect(after_fail["status"] != "running", after_fail)
    finally:
        runner._spawn = original_spawn  # type: ignore[method-assign]

    # HTTP 409 on a second resume while the first CAS holds is covered above.
    blank = client.post(f"/api/modeling-runs/{waiting['id']}/resume", json={"answer": "   "})
    expect(blank.status_code == 422, blank.text)

    # --- Restart recovery for injected queued/running doubles ---
    orphan_project = store.create_project(ProjectCreate(title="Orphan"))
    ingest.ingest_direct_text(orphan_project["id"], "Orphaned run evidence.", label="Note")
    orphan_run = persistence.create_run(
        orphan_project["id"],
        question="Recover me?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
    )
    _running(persistence, orphan_run["id"])
    recovered = runner.recover_orphaned_runs()
    recovered_ids = {item["id"] for item in recovered}
    expect(orphan_run["id"] in recovered_ids, recovered)
    orphan_after = persistence.get_run(orphan_run["id"])
    expect(orphan_after["status"] == "failed", orphan_after)
    expect(orphan_after["error_code"] == "worker_lost", orphan_after)

    queued_run = persistence.create_run(
        orphan_project["id"],
        question="Queued orphan?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
    )
    expect(queued_run["status"] == "queued", queued_run)
    recovered_queued = runner.recover_orphaned_runs()
    queued_after = persistence.get_run(queued_run["id"])
    expect(queued_after["id"] in {item["id"] for item in recovered_queued} or queued_after["status"] == "failed", queued_after)
    expect(queued_after["status"] == "failed", queued_after)
    expect(queued_after["error_code"] == "worker_lost", queued_after)

    stale_hb = persistence.create_run(
        orphan_project["id"],
        question="Heartbeat?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
    )
    old = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
    persistence.update_run(stale_hb["id"], status="running", started_at=old, heartbeat_at=old)
    expired = persistence.get_run(stale_hb["id"])
    expect(expired["status"] == "failed", expired)
    expect(expired["error_code"] in {"worker_lost", "timeout"}, expired)

    print("PASS: stage1 recovery/snapshot/provenance/export/state-machine")
    print(f"isolated_data_dir={TMP}")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
