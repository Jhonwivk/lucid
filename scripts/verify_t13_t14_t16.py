"""Focused proof for T13/T14/T16 scenario impact and solver evidence contracts."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.app import store
from api.app.db import ensure_database
from api.app.solver import solve_training_schedule
from api.app.schemas import (
    ConflictExplanationIn,
    FormalElementChange,
    FormalModelIn,
    ProjectCreate,
    ScenarioCreate,
    ScenarioImpactPreviewCreate,
    SolveRunCreate,
    WhatIfScenarioCreate,
)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lucid-t13-proof-") as data_dir:
        os.environ["LUCID_DATA_DIR"] = data_dir
        ensure_database()
        project = store.create_project(ProjectCreate(title="T13/T14/T16 proof"))
        definition = {
            "schema_version": 1,
            "family": "generic",
            "variables": [{"key": "x", "name": "x", "domain": "integer"}],
            "parameters": [],
            "constraints": [
                {"key": "capacity", "expression": "x <= 10", "strength": "hard", "enabled": True}
            ],
            "objectives": [
                {"key": "cost", "expression": "x", "direction": "minimize", "priority": 1}
            ],
        }
        scenario = store.create_scenario(
            project["id"],
            ScenarioCreate(name="base", formal_model=FormalModelIn(definition=definition)),
        )
        base = scenario["revisions"][0]
        change = FormalElementChange(
            collection="constraints",
            key="capacity",
            value={"expression": "x <= 8", "strength": "hard", "enabled": True},
        )
        impact = store.preview_scenario_impact(
            scenario["id"],
            ScenarioImpactPreviewCreate(base_revision_id=base["id"], changes=[change]),
        )
        assert impact["invalidation_required"]
        assert impact["solver_ready_after_change"] is False
        what_if = store.create_what_if_scenario(
            scenario["id"],
            WhatIfScenarioCreate(
                name="capacity-8",
                expected_parent_revision_id=base["id"],
                changes=[change],
            ),
        )
        comparison = store.compare_scenario_revisions(
            scenario["id"], base["id"], what_if["id"]
        )
        assert any(item["key"] == "capacity" for item in comparison["changed_elements"])
        assert comparison["changed_rules"] == []
        run = store.create_solve_run(
            project["id"], SolveRunCreate(scenario_revision_id=what_if["id"])
        )
        recorded = store.record_solver_explanation(
            run["id"],
            ConflictExplanationIn(
                provenance="solver",
                solver_name="proof-solver",
                status="infeasible",
                summary="The solver returned an infeasible model.",
                conflicts=[{"constraint_key": "capacity", "reason": "no domain value"}],
            ),
        )
        assert recorded["run_state"] == "infeasible"
        assert recorded["explanation"]["provenance"] == "solver"

        ranked = solve_training_schedule(
            {
                "family": "training_schedule",
                "variables": [{"key": "assignment", "name": "assignment"}],
                "constraints": [
                    {"key": "capacity", "expression": "room capacity", "enabled": True},
                    {"key": "availability", "expression": "room availability", "enabled": True},
                ],
                "objectives": [{"key": "late", "expression": "late sessions", "direction": "minimize", "priority": 1}],
                "training_schedule": {
                    "sessions": [{"key": "s1", "name": "Session 1", "duration_minutes": 60, "attendees": 5}],
                    "time_slots": [
                        {"key": "am", "day": "Mon", "start_minute": 540, "end_minute": 600},
                        {"key": "pm", "day": "Mon", "start_minute": 780, "end_minute": 840},
                    ],
                    "rooms": [{"key": "room", "name": "Room", "capacity": 10, "available_slot_keys": ["am", "pm"]}],
                    "instructors": [{"key": "instructor", "name": "Instructor", "skills": [], "available_slot_keys": ["am", "pm"]}],
                },
            },
            max_candidates=2,
        )
        assert ranked["state"] == "optimal" and len(ranked["candidates"]) == 2, ranked
    print("PASS: T13 conflict evidence, T14 comparison, T16 what-if impact")


if __name__ == "__main__":
    main()
