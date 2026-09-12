"""Proof of the real T14 portfolio-selection solver path."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.app import store  # noqa: E402
from api.app.db import ensure_database  # noqa: E402
from api.app.schemas import (  # noqa: E402
    FormalModelIn,
    PortfolioSolveCreate,
    ProjectCreate,
    ScenarioCreate,
)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lucid-t14-proof-") as data_dir:
        os.environ["LUCID_DATA_DIR"] = data_dir
        ensure_database()
        project = store.create_project(ProjectCreate(title="T14 portfolio proof"))
        definition = {
            "schema_version": 1,
            "family": "portfolio",
            "variables": [{"key": "select", "name": "item selection"}],
            "parameters": [],
            "constraints": [
                {
                    "key": "budget",
                    "expression": "sum(cost) <= budget",
                    "strength": "hard",
                    "enabled": True,
                }
            ],
            "objectives": [
                {
                    "key": "value",
                    "expression": "maximize total value",
                    "direction": "maximize",
                    "priority": 1,
                }
            ],
            "portfolio": {
                "budget": 10,
                "items": [
                    {"key": "a", "name": "A", "cost": 6, "value": 10},
                    {
                        "key": "b",
                        "name": "B",
                        "cost": 5,
                        "value": 8,
                        "conflict_keys": ["c"],
                    },
                    {
                        "key": "c",
                        "name": "C",
                        "cost": 4,
                        "value": 7,
                        "conflict_keys": ["b"],
                    },
                    {"key": "d", "name": "D", "cost": 2, "value": 3, "required": True},
                ],
            },
        }
        scenario = store.create_scenario(
            project["id"],
            ScenarioCreate(name="portfolio", formal_model=FormalModelIn(definition=definition)),
        )
        revision_id = scenario["revisions"][0]["id"]
        solved = store.execute_portfolio(
            project["id"], PortfolioSolveCreate(scenario_revision_id=revision_id)
        )
        assert solved["execution"] in {"executed", "completed"}
        assert solved["run_state"] == "optimal"
        assert solved["candidates"][0]["result"]["selected_keys"] == ["a", "d"]
        assert solved["candidates"][0]["objective_value"] == 13.0

        impossible = dict(definition)
        impossible["portfolio"] = {
            "budget": 1,
            "items": [{"key": "required", "name": "Required", "cost": 2, "value": 1, "required": True}],
        }
        blocked = store.create_scenario(
            project["id"],
            ScenarioCreate(name="impossible", formal_model=FormalModelIn(definition=impossible)),
        )
        blocked_run = store.execute_portfolio(
            project["id"],
            PortfolioSolveCreate(scenario_revision_id=blocked["revisions"][0]["id"]),
        )
        assert blocked_run["run_state"] == "infeasible"
        assert blocked_run["candidates"][0]["explanation"]["required_keys"] == ["required"]
    print("PASS: T14 portfolio selection optimal/infeasible persisted solver paths")


if __name__ == "__main__":
    main()
