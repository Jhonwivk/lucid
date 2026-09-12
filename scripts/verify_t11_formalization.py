#!/usr/bin/env python3
"""Focused T11 proof: bind a confirmed baseline, version a formal model, and invalidate safely."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def main() -> None:
    tmp = tempfile.TemporaryDirectory(prefix="lucid-t11-")
    os.environ["LUCID_DATA_DIR"] = tmp.name
    root = Path(__file__).resolve().parents[1]
    import sys

    sys.path.insert(0, str(root / "api"))
    from app import store
    from app.db import connect, ensure_database, utc_now
    from app.modeling import persistence
    from app.schemas import FormalModelIn, ProjectCreate, ScenarioFromBaselineCreate, ScenarioRevisionCreate

    ensure_database()
    project = store.create_project(ProjectCreate(title="T11 formalization proof"))
    now = utc_now()
    run_id = "proof-run"
    draft_id = "proof-draft"
    baseline_id = "proof-baseline"
    handoff = {
        "decision_variables": [
            {"claim_key": "assign-room", "name": "room assignment", "domain": "room_id"}
        ],
        "parameters": [
            {"claim_key": "capacity", "name": "room capacity", "raw_value": "12", "unit": "seats"}
        ],
        "constraints": [
            {
                "claim_key": "capacity-limit",
                "original_statement": "Room capacity must cover attendees",
                "strength": "hard",
                "evidence_refs": [],
            }
        ],
        "objectives": [
            {
                "claim_key": "minimize-distance",
                "original_statement": "Minimize total walking distance",
                "direction": "minimize",
                "priority": "1",
                "evidence_refs": [],
            }
        ],
    }
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO modeling_run (id, project_id, thread_id, status, question, evidence_fingerprint, coverage_json, created_at, updated_at) VALUES (?, ?, ?, 'completed', ?, '', '[]', ?, ?)",
            (run_id, project["id"], run_id, "proof question", now, now),
        )
        conn.execute(
            "INSERT INTO modeling_draft (id, project_id, run_id, revision_no, version_state, completeness, draft_json, created_at) VALUES (?, ?, ?, 1, 'confirmed', 'complete', '{}', ?)",
            (draft_id, project["id"], run_id, now),
        )
        conn.execute(
            "INSERT INTO modeling_baseline (id, project_id, draft_id, understanding_revision_id, scenario_id, scenario_revision_id, export_json, export_markdown, created_at) VALUES (?, ?, ?, NULL, NULL, NULL, ?, ?, ?)",
            (baseline_id, project["id"], draft_id, json.dumps(handoff), "# confirmed baseline", now),
        )
        conn.commit()
    finally:
        conn.close()

    scenario = store.create_scenario_from_baseline(
        project["id"], baseline_id, ScenarioFromBaselineCreate(name="Training proof")
    )
    v1 = scenario["revisions"][0]
    expect(v1["revision_no"] == 1, "baseline creates scenario revision v1")
    expect(v1["parent_revision_id"] is None, "v1 has no parent")
    expect(v1["formal_model"]["definition"]["variables"][0]["key"] == "assign-room", "formal definition roundtrip")
    expect(v1["formal_model"]["definition_hash"], "formal definition hash persisted")
    expect(v1["formal_model"]["validation"]["valid"], "baseline formal definition is structurally valid")
    expect(persistence.get_baseline(baseline_id)["scenario_revision_id"] == v1["id"], "baseline binding persisted")

    v2_model = FormalModelIn(
        name="Training proof v2",
        version_state="confirmed",
        definition={
            "family": "training_schedule",
            "variables": [{"key": "assign-room", "name": "room assignment", "domain": "room_id"}],
            "constraints": [{"key": "capacity-limit", "expression": "room.capacity >= attendees", "strength": "hard"}],
            "objectives": [{"key": "minimize-distance", "expression": "total_distance", "direction": "minimize"}],
        },
        dependency_fingerprint=v1["formal_model"]["dependency_fingerprint"],
    )
    v2 = store.create_scenario_revision(
        scenario["id"],
        ScenarioRevisionCreate(expected_parent_revision_id=v1["id"], formal_model=v2_model),
    )
    expect(v2["revision_no"] == 2 and v2["parent_revision_id"] == v1["id"], "v2 parent CAS")
    old = store.get_scenario_revision(v1["id"])
    expect(old["revision_no"] == 1 and old["formal_model"]["name"].endswith("model"), "v1 body remains immutable")
    try:
        store.create_scenario_revision(
            scenario["id"], ScenarioRevisionCreate(expected_parent_revision_id=v1["id"])
        )
    except store.ConflictError:
        pass
    else:
        raise SystemExit("FAIL: stale parent was accepted")

    invalidated = store.invalidate_scenario_revision(v2["id"], reason="missing room availability")
    expect(invalidated["version_state"] == "invalidated", "revision invalidated")
    expect(invalidated["invalidation_reason"] == "missing room availability", "invalidation reason persisted")
    expect(invalidated["formal_model"]["version_state"] == "invalidated", "attached formal model invalidated")
    project_after = store.get_project(project["id"])
    expect(project_after["latest"]["scenario_revision_id"] == v1["id"], "invalid head rolls back to parent")
    v3 = store.create_scenario_revision(
        scenario["id"], ScenarioRevisionCreate(expected_parent_revision_id=v1["id"])
    )
    expect(v3["revision_no"] == 3 and v3["parent_revision_id"] == v1["id"], "new revision resumes from rolled-back head")
    conn = connect()
    try:
        events = [row["event_type"] for row in conn.execute("SELECT event_type FROM change_event WHERE project_id = ?", (project["id"],))]
    finally:
        conn.close()
    expect("baseline.bound_to_scenario" in events, "baseline binding event")
    expect("scenario.revision_invalidated" in events, "invalidation event")
    print("PASS: T11 baseline binding/formalization/revision CAS/invalidation")
    tmp.cleanup()


if __name__ == "__main__":
    main()
