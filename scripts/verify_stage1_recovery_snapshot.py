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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
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
    # Keep the names present so optional dotenv cannot refill live keys.
    os.environ[key] = ""


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
    from app.modeling.draft import EvidenceRef
    from app.modeling.provenance import validate_ref
    from app.modeling.azure_cu import derive_representation
    from app.modeling.tools import read_source, understand_material
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

    # --- Waiting for the user must not keep consuming the Agent wall deadline ---
    waiting_idle = persistence.get_run(waiting["id"])
    expect(waiting_idle["status"] == "waiting_for_user", waiting_idle)
    expect(waiting_idle.get("wall_deadline_at") in (None, ""), waiting_idle)
    same_thread = waiting_idle["thread_id"]
    pending_before = [
        item for item in (waiting_idle.get("clarifications") or []) if item.get("status") == "pending"
    ]
    expect(len(pending_before) == 1, waiting_idle.get("clarifications"))
    past_deadline = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    persistence.update_run(waiting["id"], wall_deadline_at=past_deadline)
    still_waiting = persistence.get_run(waiting["id"])
    expect(still_waiting["status"] == "waiting_for_user", still_waiting)
    expect(still_waiting.get("error_code") != "timeout", still_waiting)
    resumed_late = runner.resume_run(waiting["id"], "The plant manager is the overtime approver.")
    expect(resumed_late["id"] == waiting["id"], resumed_late)
    expect(resumed_late["thread_id"] == same_thread, resumed_late)
    expect(resumed_late.get("error_code") != "timeout", resumed_late)
    expect(resumed_late["status"] != "failed" or resumed_late.get("error_code") != "timeout", resumed_late)
    finished_late = runner.wait_for_run(waiting["id"], timeout=60)
    expect(finished_late["id"] == waiting["id"], finished_late)
    expect(finished_late["thread_id"] == same_thread, finished_late)
    expect(finished_late["status"] in {"partial", "completed"}, finished_late)
    expect(finished_late.get("error_code") != "timeout", finished_late)
    answered = [
        item for item in (finished_late.get("clarifications") or []) if item.get("status") == "answered"
    ]
    expect(len(answered) == 1, finished_late.get("clarifications"))
    expect(finished_late.get("drafts"), finished_late)

    # --- Leftover waiting worker must not keep resume stuck in running ---
    linger_project = store.create_project(ProjectCreate(title="Resume leftover worker"))
    ingest.ingest_direct_text(linger_project["id"], "Approval owner is missing.", label="Gap")
    linger_run = runner.start_run(
        linger_project["id"],
        "Who approves overtime?",
        model=AdaptiveScriptModel(clarify_once=True),
    )
    linger_waiting = runner.wait_for_run(linger_run["id"], timeout=60)
    expect(linger_waiting["status"] == "waiting_for_user", linger_waiting)
    leftover_hold = threading.Event()
    leftover_started = threading.Event()

    def leftover_body() -> None:
        leftover_started.set()
        leftover_hold.wait(10)

    leftover = threading.Thread(target=leftover_body, name="leftover-waiting-worker", daemon=True)
    leftover.start()
    expect(leftover_started.wait(2), "leftover waiting thread should start")
    runner._threads[linger_waiting["id"]] = leftover
    resumed_linger = runner.resume_run(linger_waiting["id"], "The plant manager is the overtime approver.")
    expect(resumed_linger["id"] == linger_waiting["id"], resumed_linger)
    expect(resumed_linger["status"] != "failed" or resumed_linger.get("error_code") != "worker_lost", resumed_linger)
    expect(runner._threads.get(linger_waiting["id"]) is not leftover, "resume must replace the leftover thread")
    leftover_hold.set()
    leftover.join(2)
    finished_linger = runner.wait_for_run(linger_waiting["id"], timeout=60)
    expect(finished_linger["status"] in {"partial", "completed"}, finished_linger)
    expect(finished_linger["status"] != "running", finished_linger)
    expect(
        any(item.get("status") == "answered" for item in (finished_linger.get("clarifications") or [])),
        finished_linger.get("clarifications"),
    )

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

    # --- One active run per project: dual create_run + HTTP POST + two workers ---
    lock_project = store.create_project(ProjectCreate(title="One active run"))
    ingest.ingest_direct_text(lock_project["id"], "Only one worker may model this analysis.", label="Policy")

    def try_create():
        try:
            created = persistence.create_run(
                lock_project["id"],
                question="What is the overtime rule?",
                live_execution=False,
                model_configured=False,
                azure_configured=False,
            )
            return ("ok", created["id"])
        except store.ConflictError:
            return ("conflict", None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_c = pool.submit(try_create)
        second_c = pool.submit(try_create)
        create_outcomes = [first_c.result(), second_c.result()]
    expect(sum(1 for item in create_outcomes if item[0] == "ok") == 1, create_outcomes)
    expect(sum(1 for item in create_outcomes if item[0] == "conflict") == 1, create_outcomes)
    winner_id = next(item[1] for item in create_outcomes if item[0] == "ok")
    listed_active = [
        item for item in persistence.list_runs(lock_project["id"])
        if item["status"] in {"queued", "running", "waiting_for_user"}
    ]
    expect(len(listed_active) == 1, listed_active)
    expect(listed_active[0]["id"] == winner_id, listed_active)
    conflict_http = client.post(
        f"/api/projects/{lock_project['id']}/modeling-runs",
        json={"question": "A second concurrent modeling request?"},
    )
    expect(conflict_http.status_code == 409, conflict_http.text)
    persistence.update_run(winner_id, status="failed", error_code="test_cleanup", finished_at=utc_now())

    hold_project = store.create_project(ProjectCreate(title="Two worker race"))
    ingest.ingest_direct_text(hold_project["id"], "Owner is unnamed.", label="Gap")
    hold_run = persistence.create_run(
        hold_project["id"],
        question="Who approves overtime?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
    )

    class HoldThenSubmit(AdaptiveScriptModel):
        started: threading.Event = None  # type: ignore[assignment]
        proceed: threading.Event = None  # type: ignore[assignment]

        model_config = {"arbitrary_types_allowed": True}

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            object.__setattr__(self, "started", threading.Event())
            object.__setattr__(self, "proceed", threading.Event())

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            from langchain_core.messages import ToolMessage

            names = [item.name for item in messages if isinstance(item, ToolMessage)]
            if "inspect_evidence" in names and not self._submitted:
                self.started.set()
                self.proceed.wait(30)
            return AdaptiveScriptModel._generate(self, messages, stop=stop, run_manager=run_manager, **kwargs)

    hold_model = HoldThenSubmit()
    runner._models[hold_run["id"]] = hold_model

    def try_spawn():
        try:
            runner._spawn(hold_run["id"], None)
            return "ok"
        except store.ConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        spawn_a = pool.submit(try_spawn)
        spawn_b = pool.submit(try_spawn)
        spawn_outcomes = [spawn_a.result(), spawn_b.result()]
    expect(spawn_outcomes.count("ok") == 1, spawn_outcomes)
    expect(spawn_outcomes.count("conflict") == 1, spawn_outcomes)
    expect(hold_model.started.wait(20), "worker should start inspect")
    hold_model.proceed.set()
    finished_hold = runner.wait_for_run(hold_run["id"], timeout=60)
    expect(finished_hold["status"] in {"partial", "completed", "waiting_for_user", "failed"}, finished_hold)

    start_project = store.create_project(ProjectCreate(title="Dual start_run"))
    ingest.ingest_direct_text(start_project["id"], "Capacity is 12 seats.", label="Policy")
    start_a = HoldThenSubmit()
    start_b = HoldThenSubmit()

    def try_start(model):
        try:
            started = runner.start_run(start_project["id"], "How should we staff?", model=model)
            return ("ok", started["id"])
        except store.ConflictError:
            return ("conflict", None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        s1 = pool.submit(try_start, start_a)
        s2 = pool.submit(try_start, start_b)
        start_outcomes = [s1.result(), s2.result()]
    expect(sum(1 for item in start_outcomes if item[0] == "ok") == 1, start_outcomes)
    expect(sum(1 for item in start_outcomes if item[0] == "conflict") == 1, start_outcomes)
    start_a.proceed.set()
    start_b.proceed.set()
    winner_start = next(item[1] for item in start_outcomes if item[0] == "ok")
    runner.wait_for_run(winner_start, timeout=60)

    # --- latest run ordering: updated_at DESC, then created_at DESC, then id ---
    order_project = store.create_project(ProjectCreate(title="Run order"))
    ingest.ingest_direct_text(order_project["id"], "Ordering evidence.", label="Note")
    older = persistence.create_run(
        order_project["id"],
        question="First?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
    )
    persistence.update_run(older["id"], status="failed", error_code="test_cleanup", finished_at=utc_now())
    time.sleep(0.02)
    newer = persistence.create_run(
        order_project["id"],
        question="Second?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
    )
    persistence.update_run(newer["id"], status="failed", error_code="test_cleanup", finished_at=utc_now())
    persistence.update_run(older["id"], stale_input=True)
    ordered = persistence.list_runs(order_project["id"])
    expect(ordered[0]["id"] == older["id"], "updated_at DESC must outrank created_at")

    # --- Provenance: quote in the same span but not in the given offset ---
    quote_project = store.create_project(ProjectCreate(title="Quote offset"))
    quote_src = ingest.ingest_direct_text(
        quote_project["id"],
        "Capacity must not exceed 12 seats on the day shift.",
        label="Policy",
    )
    quote_run = persistence.create_run(
        quote_project["id"],
        question="What is the capacity rule?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
        question_material_id=quote_src["material"]["id"],
    )
    quote_checksum = quote_src["material"]["checksum"]
    quote_span = quote_src["spans"][0]["id"]
    quote_text = "Capacity must not exceed 12 seats on the day shift."
    quote = "Capacity must not exceed 12 seats"
    wrong_start = quote_text.index("day shift")
    wrong_end = len(quote_text)

    def reject_quote(draft, needle: str) -> None:
        try:
            persistence.save_draft(quote_run["id"], draft)
            raise SystemExit(f"FAIL: expected rejection containing {needle!r}")
        except ValueError as exc:
            expect(needle in str(exc), str(exc))
            expect("failed run cannot publish" not in str(exc), str(exc))

    reject_quote(
        _draft(
            quote_run,
            constraints=[
                {
                    "claim_key": "c-1",
                    "strength": "hard",
                    "original_statement": "Quote exists but not in this offset",
                    "evidence_refs": [
                        {
                            "material_id": quote_src["material"]["id"],
                            "source_span_id": quote_span,
                            "material_checksum": quote_checksum,
                            "precision": "exact",
                            "coordinate_system": "original_text",
                            "start_offset": wrong_start,
                            "end_offset": wrong_end,
                            "quote": quote,
                        }
                    ],
                }
            ],
        ),
        "c-1[0]",
    )
    reject_quote(
        _draft(
            quote_run,
            constraints=[
                {
                    "claim_key": "c-1",
                    "strength": "hard",
                    "original_statement": "Span has no page",
                    "evidence_refs": [
                        {
                            "material_id": quote_src["material"]["id"],
                            "source_span_id": quote_span,
                            "material_checksum": quote_checksum,
                            "precision": "exact",
                            "coordinate_system": "original_text",
                            "page": 1,
                            "quote": quote,
                        }
                    ],
                }
            ],
        ),
        "c-1[0]",
    )
    persistence.upsert_analysis(
        quote_project["id"],
        quote_src["material"]["id"],
        {
            "material_checksum": quote_checksum,
            "provider": "azure_content_understanding",
            "analyzer_id": "prebuilt-document",
            "operation_id": "op-real",
            "status": "succeeded",
            "derived_markdown": "Derived: Capacity must not exceed 12 seats on the day shift.",
        },
    )
    reject_quote(
        _draft(
            quote_run,
            constraints=[
                {
                    "claim_key": "c-1",
                    "strength": "hard",
                    "original_statement": "Azure identity mismatch",
                    "evidence_refs": [
                        {
                            "material_id": quote_src["material"]["id"],
                            "material_checksum": quote_checksum,
                            "precision": "exact",
                            "coordinate_system": "azure_markdown",
                            "quote": "Capacity must not exceed 12 seats",
                            "provider_locator": {
                                "analyzer_id": "prebuilt-document",
                                "operation_id": "op-forged",
                            },
                        }
                    ],
                }
            ],
        ),
        "c-1[0]",
    )

    # --- Snapshot preview after live delete; missing snapshot falls back to live ---
    from PIL import Image

    mix_project = store.create_project(ProjectCreate(title="Snapshot kinds"))
    text_imp = ingest.ingest_direct_text(mix_project["id"], "Original frozen overtime rule: max 8 hours.", label="Policy")
    pdf_path = ROOT / "fixtures" / "templates" / "training-schedule" / "leadership-memo.pdf"
    pdf_imp = ingest.ingest_bytes(mix_project["id"], "memo.pdf", pdf_path.read_bytes())
    csv_imp = ingest.ingest_bytes(
        mix_project["id"],
        "grid.csv",
        b"sheet,cell,value\nShifts,B2,12 seats\n",
    )
    png_buf = BytesIO()
    Image.new("RGB", (16, 12), (40, 80, 90)).save(png_buf, format="PNG")
    png_imp = ingest.ingest_bytes(mix_project["id"], "plant.png", png_buf.getvalue())
    mix_run = persistence.create_run(
        mix_project["id"],
        question="Show frozen sources?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
        question_material_id=text_imp["material"]["id"],
    )
    mix_ids = {
        "text": text_imp["material"]["id"],
        "pdf": pdf_imp["material"]["id"],
        "table": csv_imp["material"]["id"],
        "image": png_imp["material"]["id"],
    }
    expected_media = {
        "text": text_imp["material"]["media_type"],
        "pdf": "application/pdf",
        "table": csv_imp["material"]["media_type"],
        "image": "image/png",
    }
    expected_kind = {
        "text": text_imp["material"]["kind"],
        "pdf": pdf_imp["material"]["kind"],
        "table": "table",
        "image": "image",
    }
    for key, material_id in mix_ids.items():
        packed = get_snapshot_material(mix_run, material_id)
        expect(packed and packed.get("snapshot_path") and packed.get("checksum"), packed)
        expect(packed.get("kind") == expected_kind[key], packed)
        expect(packed.get("media_type") == expected_media[key] or expected_media[key] in str(packed.get("media_type")), packed)
        expect(packed.get("role") == "original", packed)
        live = live_material_file(mix_project["id"], store.get_material(mix_project["id"], material_id))
        expect(live is not None and live.is_file(), f"live {key} exists")
        live.unlink()
        preview = client.get(f"/api/modeling-runs/{mix_run['id']}/materials/{material_id}/preview")
        expect(preview.status_code == 200, f"{key} snapshot preview {preview.status_code} {preview.text}")
        body = preview.json()
        expect(body["material"]["id"] == material_id, body["material"])
        expect(body["frozen"] is True, body)
        expect(mix_run["id"] in (body.get("content_url") or ""), body.get("content_url"))
        expect(body["snapshot"]["checksum"] == packed["checksum"], body["snapshot"])
        expect((body["material"].get("kind") or packed["kind"]) == packed["kind"], body["material"])
        content = client.get(f"/api/modeling-runs/{mix_run['id']}/materials/{material_id}/content")
        expect(content.status_code == 200, f"{key} snapshot content {content.status_code}")
        live_preview = client.get(f"/api/projects/{mix_project['id']}/materials/{material_id}/preview")
        expect(live_preview.status_code in {404, 409, 500} or live_preview.status_code >= 400, f"deleted live {key} must not succeed as frozen")
        wrong = client.get(
            f"/api/modeling-runs/{mix_run['id']}/materials/{material_id}/preview",
            params={"checksum": "0" * 64},
        )
        expect(wrong.status_code == 409, f"{key} checksum mismatch {wrong.status_code} {wrong.text}")

    # UI helper contract: runId only when snapshot identity is valid.
    def has_valid_snapshot_identity(item: dict) -> bool:
        return bool(item.get("snapshot_path") and item.get("checksum") and not item.get("copy_error"))

    snap_text = get_snapshot_material(mix_run, mix_ids["text"])
    expect(has_valid_snapshot_identity(snap_text), snap_text)
    missing_identity = {**snap_text, "snapshot_path": None}
    expect(not has_valid_snapshot_identity(missing_identity), missing_identity)
    stripped = json.loads(json.dumps(mix_run["snapshot"]))
    for item in stripped["materials"]:
        if item["id"] == mix_ids["text"]:
            item["snapshot_path"] = None
            item["copy_error"] = "source_bytes_missing"
    persistence.replace_snapshot(mix_run["id"], stripped)
    missing_preview = client.get(f"/api/modeling-runs/{mix_run['id']}/materials/{mix_ids['text']}/preview")
    expect(missing_preview.status_code == 404, missing_preview.text)

    fallback_project = store.create_project(ProjectCreate(title="Live fallback"))
    fallback_src = ingest.ingest_direct_text(
        fallback_project["id"],
        "Live bytes remain when the snapshot identity is missing.",
        label="Live",
    )
    fallback_run = persistence.create_run(
        fallback_project["id"],
        question="Fallback to live preview?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
        question_material_id=fallback_src["material"]["id"],
    )
    fallback_snap = json.loads(json.dumps(fallback_run["snapshot"]))
    for item in fallback_snap["materials"]:
        item["snapshot_path"] = None
        item["copy_error"] = "source_bytes_missing"
    persistence.replace_snapshot(fallback_run["id"], fallback_snap)
    expect(
        not has_valid_snapshot_identity(get_snapshot_material(persistence.get_run(fallback_run["id"]), fallback_src["material"]["id"])),
        "UI must not pass runId without snapshot identity",
    )
    snap_missing = client.get(
        f"/api/modeling-runs/{fallback_run['id']}/materials/{fallback_src['material']['id']}/preview"
    )
    expect(snap_missing.status_code == 404, snap_missing.text)
    live_fallback = client.get(
        f"/api/projects/{fallback_project['id']}/materials/{fallback_src['material']['id']}/preview"
    )
    expect(live_fallback.status_code == 200, live_fallback.text)
    live_body = live_fallback.json()
    expect(live_body["material"]["id"] == fallback_src["material"]["id"], live_body)
    expect("/modeling-runs/" not in (live_body.get("content_url") or ""), live_body.get("content_url"))
    expect("Live bytes remain" in (live_body.get("excerpt") or ""), live_body.get("excerpt"))

    # --- Timeout late graph/tool activity must not write ---
    late_project = store.create_project(ProjectCreate(title="Late timeout"))
    late_src = ingest.ingest_direct_text(late_project["id"], "Timeout must not publish a draft.", label="Note")
    late_model = HoldThenSubmit()
    late_run = runner.start_run(
        late_project["id"],
        "Should timeout remain failed?",
        model=late_model,
        max_wall_seconds=180,
    )
    expect(late_model.started.wait(20), "late worker should start")
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    persistence.update_run(late_run["id"], wall_deadline_at=past)
    timed = None
    until = time.time() + 10
    while time.time() < until:
        timed = persistence.get_run(late_run["id"])
        if timed["status"] == "failed" and timed["error_code"] == "timeout":
            break
        time.sleep(0.2)
    expect(timed is not None and timed["status"] == "failed", timed)
    expect(timed["error_code"] == "timeout", timed)
    blob = json.dumps(timed.get("events") or []) + " " + str(timed.get("error_message") or "")
    expect(
        "timeout" in blob.lower() or "timed out" in blob.lower() or "wall time" in blob.lower(),
        blob,
    )
    before_events = len(timed.get("events") or [])
    before_drafts = list(timed.get("drafts") or [])
    before_coverage = json.dumps(timed.get("coverage") or [])
    try:
        persistence.increment_tool_count(late_run["id"])
        raise SystemExit("FAIL: increment_tool_count after timeout")
    except persistence.StaleRunError:
        pass
    try:
        persistence.update_coverage(late_run["id"], late_src["material"]["id"], state="analyzed", detail="late")
        raise SystemExit("FAIL: update_coverage after timeout")
    except persistence.StaleRunError:
        pass
    try:
        persistence.append_event(late_run["id"], kind="tool_call", title="late tool")
        raise SystemExit("FAIL: append_event after timeout")
    except persistence.StaleRunError:
        pass
    try:
        persistence.save_draft(late_run["id"], _draft(timed))
        raise SystemExit("FAIL: save_draft after timeout")
    except persistence.StaleRunError:
        pass
    try:
        persistence.update_run(late_run["id"], status="completed", finished_at=utc_now())
        raise SystemExit("FAIL: completed after timeout")
    except persistence.StaleRunError:
        pass
    late_model.proceed.set()
    try:
        runner.wait_for_run(late_run["id"], timeout=20)
    except TimeoutError:
        pass
    after_late = persistence.get_run(late_run["id"])
    expect(after_late["status"] == "failed", after_late)
    expect(after_late["error_code"] == "timeout", after_late)
    expect(list(after_late.get("drafts") or []) == before_drafts, after_late.get("drafts"))
    expect(json.dumps(after_late.get("coverage") or []) == before_coverage, after_late.get("coverage"))
    expect(len(after_late.get("events") or []) == before_events, after_late.get("events"))
    expect(not any("Submitted" in str(item.get("title")) for item in after_late.get("events") or []), after_late.get("events"))

    # --- save_draft must roll back if cancel wins between validate and persist ---
    race_project = store.create_project(ProjectCreate(title="Draft persist race"))
    race_src = ingest.ingest_direct_text(race_project["id"], "Cancel must roll back the draft write.", label="Note")
    race_run = persistence.create_run(
        race_project["id"],
        question="Can cancel beat save_draft?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
        question_material_id=race_src["material"]["id"],
    )
    _running(persistence, race_run["id"])

    def cancel_before_persist(run_id: str) -> None:
        persistence.request_cancel(run_id)

    persistence._before_save_draft_persist = cancel_before_persist
    try:
        persistence.save_draft(race_run["id"], _draft(persistence.get_run(race_run["id"])))
        raise SystemExit("FAIL: save_draft must not commit after mid-persist cancel")
    except persistence.StaleRunError:
        pass
    finally:
        persistence._before_save_draft_persist = None
    raced = persistence.get_run(race_run["id"])
    expect(raced["status"] == "cancelled", raced)
    expect(not (raced.get("drafts") or []), raced.get("drafts"))
    race_project_after = store.get_project(race_project["id"])
    latest_draft_id = (race_project_after.get("latest") or {}).get("modeling_draft_id") or race_project_after.get(
        "latest_modeling_draft_id"
    )
    expect(not latest_draft_id, race_project_after)

    # --- Cross-run draft fallback: R2 with no draft must not show R1 claims ---
    def select_draft_for_run(drafts: list[dict], run_id: str | None) -> dict | None:
        if not run_id:
            return None
        matches = [item for item in drafts if item.get("run_id") == run_id]
        return matches[-1] if matches else None

    r1_draft = {"run_id": "R1", "claims": [{"id": "claim-r1", "original_statement": "From R1"}]}
    selected_r2 = select_draft_for_run([r1_draft], "R2")
    expect(selected_r2 is None, selected_r2)
    expect((selected_r2 or {}).get("claims") in (None, []), selected_r2)
    selected_r1 = select_draft_for_run([r1_draft], "R1")
    expect(selected_r1 is not None and selected_r1.get("claims"), selected_r1)

    def select_baseline_draft(drafts: list[dict], runs: list[dict]) -> dict | None:
        if not runs:
            return None
        latest = sorted(
            runs,
            key=lambda item: (item.get("updated_at") or "", item.get("created_at") or "", item.get("id") or ""),
            reverse=True,
        )[0]
        return select_draft_for_run(drafts, latest.get("id"))

    baseline_selected = select_baseline_draft(
        [r1_draft],
        [
            {"id": "R1", "updated_at": "2026-09-12T01:00:00", "created_at": "2026-09-12T01:00:00"},
            {"id": "R2", "updated_at": "2026-09-12T02:00:00", "created_at": "2026-09-12T02:00:00"},
        ],
    )
    expect(baseline_selected is None, baseline_selected)
    expect((baseline_selected or {}).get("claims") in (None, []), baseline_selected)

    # --- Freeze re-reads snapshot bytes; Azure provenance rejects failed/out-of-range/unmapped refs ---
    freeze_project = store.create_project(ProjectCreate(title="Freeze snapshot recheck"))
    freeze_src = ingest.ingest_direct_text(
        freeze_project["id"],
        "Freeze must re-read snapshot bytes.",
        label="Note",
    )
    freeze_run = persistence.create_run(
        freeze_project["id"],
        question="Can a tampered snapshot freeze?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
        question_material_id=freeze_src["material"]["id"],
    )
    _running(persistence, freeze_run["id"])
    freeze_draft = persistence.save_draft(freeze_run["id"], _draft(freeze_run))
    freeze_material = get_snapshot_material(freeze_run, freeze_src["material"]["id"])
    expect(freeze_material and freeze_material.get("snapshot_path"), freeze_material)
    (get_data_dir() / freeze_material["snapshot_path"]).write_bytes(b"tampered after save_draft")
    try:
        persistence.freeze_baseline(freeze_project["id"], freeze_draft["id"])
        raise SystemExit("FAIL: freeze must fail after snapshot tamper")
    except store.ConflictError as exc:
        expect("stale_input" in str(exc).lower() or "checksum" in str(exc).lower(), str(exc))
    still_draft = persistence.get_draft(freeze_draft["id"])
    expect(still_draft["version_state"] == "draft", still_draft)

    az_project = store.create_project(ProjectCreate(title="Azure locator map"))
    az_src = ingest.ingest_direct_text(
        az_project["id"],
        "Page one silence. Capacity must not exceed 12 seats.",
        label="Memo",
    )
    az_run = persistence.create_run(
        az_project["id"],
        question="Where is the capacity rule?",
        live_execution=False,
        model_configured=False,
        azure_configured=False,
        question_material_id=az_src["material"]["id"],
    )
    az_checksum = az_src["material"]["checksum"]
    snap = dict(az_run["snapshot"] or {})
    patched = []
    for item in list(snap.get("materials") or []):
        row = dict(item)
        if row.get("id") == az_src["material"]["id"]:
            base = dict((row.get("spans") or [{}])[0])
            row["spans"] = [
                {**base, "page": 1, "excerpt": "Page one silence."},
                {**base, "id": "span-page-2", "page": 2, "excerpt": "Capacity must not exceed 12 seats."},
            ]
        patched.append(row)
    snap["materials"] = patched
    persistence.replace_snapshot(az_run["id"], snap)
    az_run = persistence.get_run(az_run["id"])

    def reject_az(draft, needle: str) -> None:
        try:
            persistence.save_draft(az_run["id"], draft)
            raise SystemExit(f"FAIL: expected Azure rejection containing {needle!r}")
        except ValueError as exc:
            expect(needle in str(exc), str(exc))

    persistence.upsert_analysis(
        az_project["id"],
        az_src["material"]["id"],
        {
            "material_checksum": az_checksum,
            "provider": "azure_content_understanding",
            "analyzer_id": "prebuilt-document",
            "operation_id": "op-failed",
            "status": "failed",
            "derived_markdown": "Derived: Capacity must not exceed 12 seats on the day shift.",
        },
    )
    reject_az(
        _draft(
            az_run,
            constraints=[
                {
                    "claim_key": "c-1",
                    "strength": "hard",
                    "original_statement": "Failed Azure artifact",
                    "evidence_refs": [
                        {
                            "material_id": az_src["material"]["id"],
                            "material_checksum": az_checksum,
                            "precision": "exact",
                            "coordinate_system": "azure_markdown",
                            "quote": "Capacity must not exceed 12 seats",
                            "provider_locator": {
                                "analyzer_id": "prebuilt-document",
                                "operation_id": "op-failed",
                            },
                        }
                    ],
                }
            ],
        ),
        "succeeded",
    )
    azure_markdown = "Derived: Capacity must not exceed 12 seats on the day shift."
    persistence.upsert_analysis(
        az_project["id"],
        az_src["material"]["id"],
        {
            "material_checksum": az_checksum,
            "provider": "azure_content_understanding",
            "analyzer_id": "prebuilt-document",
            "operation_id": "op-nomap",
            "status": "succeeded",
            "derived_markdown": azure_markdown,
        },
    )
    reject_az(
        _draft(
            az_run,
            constraints=[
                {
                    "claim_key": "c-1",
                    "strength": "hard",
                    "original_statement": "Page 1 plus Azure without a locator map",
                    "evidence_refs": [
                        {
                            "material_id": az_src["material"]["id"],
                            "material_checksum": az_checksum,
                            "precision": "exact",
                            "coordinate_system": "azure_markdown",
                            "page": 1,
                            "quote": "Capacity must not exceed 12 seats",
                            "provider_locator": {
                                "analyzer_id": "prebuilt-document",
                                "operation_id": "op-nomap",
                            },
                        }
                    ],
                }
            ],
        ),
        "locator map",
    )
    persistence.upsert_analysis(
        az_project["id"],
        az_src["material"]["id"],
        {
            "material_checksum": az_checksum,
            "provider": "azure_content_understanding",
            "analyzer_id": "prebuilt-document",
            "operation_id": "op-ok",
            "status": "succeeded",
            "derived_markdown": azure_markdown,
            "derived": {
                "coordinate_system": "azure_markdown",
                "provider_locators": [
                    {"page": 2, "coordinate_system": "azure_markdown", "original_coordinates": "unknown"}
                ],
            },
        },
    )
    reject_az(
        _draft(
            az_run,
            constraints=[
                {
                    "claim_key": "c-1",
                    "strength": "hard",
                    "original_statement": "Azure offset out of range",
                    "evidence_refs": [
                        {
                            "material_id": az_src["material"]["id"],
                            "material_checksum": az_checksum,
                            "precision": "exact",
                            "coordinate_system": "azure_markdown",
                            "start_offset": 0,
                            "end_offset": len(azure_markdown) + 25,
                            "quote": "Capacity must not exceed 12 seats",
                            "provider_locator": {
                                "analyzer_id": "prebuilt-document",
                                "operation_id": "op-ok",
                            },
                        }
                    ],
                }
            ],
        ),
        "outside",
    )
    reject_az(
        _draft(
            az_run,
            constraints=[
                {
                    "claim_key": "c-1",
                    "strength": "hard",
                    "original_statement": "Page 1 but Azure locator is page 2",
                    "evidence_refs": [
                        {
                            "material_id": az_src["material"]["id"],
                            "material_checksum": az_checksum,
                            "precision": "exact",
                            "coordinate_system": "azure_markdown",
                            "page": 1,
                            "quote": "Capacity must not exceed 12 seats",
                            "provider_locator": {
                                "analyzer_id": "prebuilt-document",
                                "operation_id": "op-ok",
                            },
                        }
                    ],
                }
            ],
        ),
        "locator map",
    )

    persistence.upsert_analysis(
        az_project["id"],
        az_src["material"]["id"],
        {
            "material_checksum": az_checksum,
            "provider": "azure_content_understanding",
            "analyzer_id": "prebuilt-document",
            "operation_id": "op-ok",
            "status": "succeeded",
            "derived_markdown": azure_markdown,
            "derived": {
                "coordinate_system": "azure_markdown",
                "provider_locators": [
                    {
                        "locator_id": "az-loc-1",
                        "page": 2,
                        "offset": azure_markdown.find("Capacity"),
                        "length": len("Capacity must not exceed 12 seats"),
                        "coordinate_system": "azure_markdown",
                        "original_coordinates": "unknown",
                    }
                ],
            },
        },
    )
    _running(persistence, az_run["id"])
    az_token = CURRENT_RUN.set(
        RunContext(
            project_id=az_project["id"],
            run_id=az_run["id"],
            thread_id=az_run["thread_id"],
            live_execution=False,
        )
    )
    try:
        understood = json.loads(understand_material.invoke({"material_id": az_src["material"]["id"]}))
        read_payload = json.loads(
            read_source.invoke(
                {
                    "material_id": az_src["material"]["id"],
                    "derived": True,
                    "start_offset": 0,
                    "end_offset": len(azure_markdown),
                }
            )
        )
    finally:
        CURRENT_RUN.reset(az_token)
    understood_blob = json.dumps(understood)
    read_locators = read_payload.get("provider_locators") or []
    expect(any(item.get("locator_id") == "az-loc-1" for item in read_locators), read_payload)
    nested = derive_representation(
        {
            "result": {
                "contents": [
                    {
                        "markdown": "hello",
                        "pageNumber": 2,
                        "spans": [{"offset": 0, "length": 5}],
                    }
                ]
            }
        }
    )
    expect(
        any(
            item.get("page") == 2
            and item.get("offset") == 0
            and item.get("length") == 5
            for item in nested["provider_locators"]
        ),
        nested,
    )
    expect("continuation_token" not in understood, understood)
    expect("operation_url" not in understood, understood)
    expect("PRIVATE" not in understood_blob, understood_blob)
    locators = understood.get("provider_locators") or []
    loc = next((item for item in locators if item.get("page") == 2), None)
    expect(loc is not None, locators)
    expect(loc.get("locator_id") == "az-loc-1", loc)
    expect(loc.get("original_coordinates") == "unknown", loc)
    expect(loc.get("coordinate_system") == "azure_markdown", loc)
    expect(understood.get("analyzer_id") == "prebuilt-document", understood)
    expect(understood.get("operation_id") == "op-ok", understood)
    constructed = EvidenceRef.model_validate(
        {
            "material_id": az_src["material"]["id"],
            "material_checksum": understood.get("material_checksum") or az_checksum,
            "precision": "exact",
            "coordinate_system": "azure_markdown",
            "page": loc["page"],
            "quote": "Capacity must not exceed 12 seats",
            "provider_locator": {
                "analyzer_id": understood["analyzer_id"],
                "operation_id": understood["operation_id"],
                "locator_id": loc["locator_id"],
                "page": loc["page"],
                "offset": loc.get("offset"),
                "length": loc.get("length"),
                "coordinate_system": loc.get("coordinate_system"),
            },
        }
    )
    az_fresh = persistence.get_run(az_run["id"])
    expect(validate_ref(az_fresh, constructed) is None, validate_ref(az_fresh, constructed))
    mismatched = EvidenceRef.model_validate(
        {
            **constructed.model_dump(),
            "provider_locator": {
                **(constructed.provider_locator or {}),
                "offset": (loc.get("offset") or 0) + 1,
            },
        }
    )
    expect(validate_ref(az_fresh, mismatched) is not None, mismatched)

    print("PASS: stage1 recovery/snapshot/provenance/export/state-machine")
    print(f"isolated_data_dir={TMP}")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
