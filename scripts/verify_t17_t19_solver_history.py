"""Focused proof for solve history, worker leases, exports, and project boundaries."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lucid-t17-t19-") as directory:
        os.environ["LUCID_DATA_DIR"] = directory
        os.environ["LUCID_DB_PATH"] = str(Path(directory) / "lucid.db")
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
        from app.db import connect, ensure_database
        from app import store
        from app.schemas import (
            ProjectCreate,
            FormalModelIn,
            ResultCandidateIn,
            ScenarioCreate,
            SolveRunCreate,
        )

        ensure_database()
        project = store.create_project(ProjectCreate(title="history-boundary"))
        other = store.create_project(ProjectCreate(title="other-project"))
        scenario = store.create_scenario(project["id"], ScenarioCreate(name="v1"))
        revision_id = scenario["revisions"][0]["id"]
        run = store.create_solve_run(
            project["id"], SolveRunCreate(scenario_revision_id=revision_id)
        )

        first = store.claim_solve_run(run["id"], owner="worker-a", stale_after_seconds=1)
        assert first["run_state"] == "running"
        assert first["claim_owner"] == "worker-a"
        assert first["claim_token"]
        try:
            store.claim_solve_run(run["id"], owner="worker-a", stale_after_seconds=1)
        except store.ConflictError:
            pass
        else:
            raise AssertionError("a live lease was re-claimed by its current owner")
        try:
            store.heartbeat_solve_run(run["id"], owner="worker-a", claim_token="")
        except store.ConflictError:
            pass
        else:
            raise AssertionError("empty heartbeat token was accepted")

        # Simulate a crashed worker. The old lease can be reclaimed, but the
        # old token is forbidden from writing a result afterwards.
        with connect() as conn:
            conn.execute(
                "UPDATE solve_run SET heartbeat_at = ? WHERE id = ?",
                ("2000-01-01T00:00:00+00:00", run["id"]),
            )
            conn.commit()
        resumed = store.claim_solve_run(
            run["id"], owner="worker-b", stale_after_seconds=1
        )
        assert resumed["claim_owner"] == "worker-b"
        assert resumed["resume_count"] == 1
        assert resumed["claim_token"] != first["claim_token"]
        try:
            store.complete_solve_run(run["id"], owner="worker-b", run_state="optimal", claim_token="")
        except store.ConflictError:
            pass
        else:
            raise AssertionError("empty completion token was accepted")
        try:
            store.complete_solve_run(
                run["id"],
                owner="worker-a",
                claim_token=first["claim_token"],
                run_state="optimal",
            )
        except store.ConflictError:
            pass
        else:
            raise AssertionError("stale worker was allowed to write a result")

        completed = store.complete_solve_run(
            run["id"],
            owner="worker-b",
            claim_token=resumed["claim_token"],
            run_state="optimal",
            solver_name="deterministic-test-solver",
            candidates=[
                ResultCandidateIn(
                    label="candidate-1",
                    objective_value=3.5,
                    is_selected=True,
                    details={"assignments": [{"session": "S1", "slot": "T1"}]},
                    result={"assignments": [{"session": "S1", "slot": "T1"}]},
                    explanation={"hard_constraints": ["no-overlap"]},
                    provenance={"source_claim_keys": ["claim-1"]},
                )
            ],
        )
        assert completed["run_state"] == "optimal"
        assert completed["candidates"][0]["details"]["assignments"]
        assert completed["candidates"][0]["result"]["assignments"]
        assert completed["candidates"][0]["explanation"]["hard_constraints"]
        assert completed["candidates"][0]["provenance"]["source_claim_keys"]

        exported = store.export_solve_run(run["id"], project_id=project["id"])
        assert exported["export_schema"] == "lucid.solve-run.v1"
        assert exported["project"]["id"] == project["id"]
        assert exported["scenario_revision"]["id"] == revision_id
        assert exported["solve_run"]["candidates"][0]["details"]
        assert exported["solve_run"]["candidates"][0]["result"]
        assert "provenance" in exported and "materials" in exported["provenance"]

        # A real solver-family run can be reclaimed and re-executed from its
        # persisted formal model after the original worker disappears.
        executable = store.create_scenario(
            project["id"],
            ScenarioCreate(
                name="resumable-training",
                formal_model=FormalModelIn(
                    name="training",
                    version_state="confirmed",
                    definition={
                        "family": "training_schedule",
                        "variables": [{"key": "assignment", "name": "assignment"}],
                        "constraints": [{"key": "capacity", "expression": "room capacity", "strength": "hard"}],
                        "objectives": [{"key": "late", "expression": "minimize late sessions", "direction": "minimize", "priority": 1}],
                        "training_schedule": {
                            "sessions": [{"key": "s1", "name": "S1", "duration_minutes": 60, "attendees": 2}],
                            "time_slots": [{"key": "t1", "day": "Mon", "start_minute": 540, "end_minute": 660}],
                            "rooms": [{"key": "r1", "name": "R1", "capacity": 4, "available_slot_keys": ["t1"]}],
                            "instructors": [{"key": "i1", "name": "I1", "skills": [], "available_slot_keys": ["t1"], "max_daily_sessions": 2}],
                        },
                    },
                ),
            ),
        )
        resumable = store.create_solve_run(
            project["id"],
            SolveRunCreate(scenario_revision_id=executable["revisions"][0]["id"]),
        )
        crashed = store.claim_solve_run(resumable["id"], owner="crashed-worker", stale_after_seconds=1)
        with connect() as conn:
            conn.execute("UPDATE solve_run SET heartbeat_at = ? WHERE id = ?", ("2000-01-01T00:00:00+00:00", resumable["id"]))
            conn.commit()
        resumed_result = store.resume_solve_run(project["id"], resumable["id"], owner="recovery-worker", stale_after_seconds=1)
        assert resumed_result["run_state"] == "optimal", resumed_result
        assert resumed_result["execution"] == "completed", resumed_result
        assert resumed_result["resume_count"] == 1, resumed_result

        try:
            store.export_solve_run(run["id"], project_id=other["id"])
        except store.NotFoundError:
            pass
        else:
            raise AssertionError("cross-project export was allowed")

    print("PASS: T17 solve history/export, T18 lease recovery, T19 project boundary")


if __name__ == "__main__":
    main()
