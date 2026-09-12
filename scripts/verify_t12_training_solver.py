"""Focused executable proof for the T12 training-schedule vertical slice."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _definition(*, capacity: int) -> dict:
    return {
        "schema_version": 1,
        "family": "training_schedule",
        "variables": [{"key": "assignment", "name": "session assignment"}],
        "parameters": [],
        "constraints": [
            {"key": "capacity", "expression": "room capacity >= attendees", "strength": "hard", "enabled": True, "source_claim_key": "claim-capacity"},
            {"key": "skill", "expression": "instructor has required skill", "strength": "hard", "enabled": True, "source_claim_key": "claim-skill"},
        ],
        "objectives": [{"key": "late", "expression": "minimize late sessions", "direction": "minimize", "priority": 1}],
        "training_schedule": {
            "sessions": [{"key": "controls-301", "name": "Controls 301", "duration_minutes": 60, "attendees": 20, "required_skill": "controls"}],
            "time_slots": [
                {"key": "mon-am", "day": "Mon", "start_minute": 540, "end_minute": 660},
                {"key": "mon-pm", "day": "Mon", "start_minute": 780, "end_minute": 900},
            ],
            "rooms": [{"key": "atlas", "name": "Atlas", "capacity": capacity, "available_slot_keys": ["mon-am", "mon-pm"]}],
            "instructors": [{"key": "lee", "name": "Lee", "skills": ["controls"], "available_slot_keys": ["mon-am", "mon-pm"], "max_daily_sessions": 2}],
            "allow_evening": False,
        },
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lucid-t12-") as data_dir:
        os.environ["LUCID_DATA_DIR"] = data_dir
        from api.app.db import ensure_database
        from api.app import store
        from api.app.schemas import FormalModelIn, ProjectCreate, ScenarioCreate, TrainingScheduleSolveCreate

        ensure_database()
        project = store.create_project(ProjectCreate(title="T12 executable proof"))
        model = FormalModelIn(name="training-week", version_state="confirmed", definition=_definition(capacity=24))
        scenario = store.create_scenario(project["id"], ScenarioCreate(name="feasible week", version_state="confirmed", formal_model=model))
        revision = scenario["revisions"][0]
        run = store.execute_training_schedule(project["id"], TrainingScheduleSolveCreate(scenario_revision_id=revision["id"], max_candidates=3))
        assert run["run_state"] == "optimal", run
        assert run["execution"] in {"executed", "completed"}, run
        details = run["candidates"][0]["details"]
        assert details["assignments"][0]["room_key"] == "atlas", details
        assert details["candidate_count"] == 2, details
        assert len(run["candidates"]) == 2, run
        provenance = run["candidates"][0]["provenance"] or details.get("provenance", {})
        assert provenance["constraint_source_claims"] == ["claim-capacity", "claim-skill"], run

        bad_model = FormalModelIn(name="infeasible-week", version_state="confirmed", definition=_definition(capacity=10))
        bad_scenario = store.create_scenario(project["id"], ScenarioCreate(name="infeasible week", version_state="confirmed", formal_model=bad_model))
        bad_revision = bad_scenario["revisions"][0]
        bad_run = store.execute_training_schedule(project["id"], TrainingScheduleSolveCreate(scenario_revision_id=bad_revision["id"]))
        assert bad_run["run_state"] == "infeasible", bad_run
        explanation = bad_run["candidates"][0]["details"]["explanation"]
        assert "controls-301" in explanation["empty_sessions"], explanation
        assert explanation["blockers"]["controls-301"]["room_capacity"] > 0, explanation

        generic_model = FormalModelIn(name="generic", version_state="confirmed", definition={"family": "generic", "variables": [{"key": "x", "name": "x"}], "constraints": [{"key": "c", "expression": "x"}], "objectives": [{"key": "o", "expression": "x", "direction": "minimize", "priority": 1}]})
        generic_scenario = store.create_scenario(project["id"], ScenarioCreate(name="generic", version_state="confirmed", formal_model=generic_model))
        generic_revision = generic_scenario["revisions"][0]
        generic_run = store.execute_training_schedule(project["id"], TrainingScheduleSolveCreate(scenario_revision_id=generic_revision["id"]))
        assert generic_run["run_state"] == "model_invalid", generic_run

    print("PASS: T12 deterministic training solver feasible/infeasible/model-invalid paths")


if __name__ == "__main__":
    main()
