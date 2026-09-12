#!/usr/bin/env python3
"""Minimal T03 persistence proof runner (not a full test suite)."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "api"
VENV_PYTHON = API_ROOT / ".venv" / "bin" / "python"
sys.path.insert(0, str(API_ROOT))


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def find_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(base: str, method: str, path: str, body: dict | None = None) -> tuple[int, dict | list]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed: dict | list = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed


def wait_health(base: str) -> None:
    deadline = time.time() + 15
    last_error = "timeout"
    while time.time() < deadline:
        try:
            status, body = request(base, "GET", "/api/health")
            if status == 200 and body.get("status") == "ok":
                return
            last_error = f"status={status} body={body}"
        except Exception as exc:  # noqa: BLE001 — startup race
            last_error = str(exc)
        time.sleep(0.1)
    raise SystemExit(f"FAIL: API did not become healthy: {last_error}")


def main() -> None:
    tmp = tempfile.NamedTemporaryFile(prefix="lucid-t03-", suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    port = find_port()
    base = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["LUCID_DB_PATH"] = str(db_path)
    python = str(VENV_PYTHON if VENV_PYTHON.exists() else sys.executable)
    proc = subprocess.Popen(
        [
            python,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(API_ROOT),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(API_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        wait_health(base)

        from app.db import SCHEMA_VERSION, connect

        os.environ["LUCID_DB_PATH"] = str(db_path)
        conn = connect()
        try:
            version = conn.execute(
                "SELECT value FROM app_meta WHERE key='schema_version'"
            ).fetchone()
            expect(int(version["value"]) == SCHEMA_VERSION, "schema_version is 1")
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            required = {
                "app_meta",
                "analysis_project",
                "material",
                "source_span",
                "understanding_revision",
                "rule",
                "scenario",
                "scenario_revision",
                "formal_model",
                "solve_run",
                "result_candidate",
                "change_event",
            }
            expect(required.issubset(tables), f"missing tables: {required - tables}")
        finally:
            conn.close()

        status, health_body = request(base, "GET", "/api/health")
        expect(status == 200, f"health status {status}")
        expect(health_body["status"] == "ok", "health status ok")
        expect(health_body["service"] == "lucid-api", "health service name")
        expect(health_body["database"] == "ready", "health database ready")
        expect(
            set(health_body) >= {"status", "service", "time", "database"},
            "health shape",
        )

        status, shell_body = request(base, "GET", "/api/shell")
        expect(status == 200, f"shell status {status}")
        expect(shell_body["mode"] == "single-user", "shell remains single-user")
        ids = [item["id"] for item in shell_body["workspaces"]]
        expect("materials" in ids, "materials workspace")
        expect("understanding" in ids, "understanding workspace")
        expect("scenarios" in ids, "scenarios workspace")
        expect("results" in ids, "results workspace")
        expect(
            shell_body["capabilities"]["solver"] == "deterministic_training_schedule",
            "deterministic solver capability is advertised",
        )

        status, project = request(
            base,
            "POST",
            "/api/projects",
            {"title": "Proof project", "summary": "reopen proof"},
        )
        expect(status == 200, f"create project {status} {project}")
        project_id = project["id"]

        status, understanding_v1 = request(
            base,
            "POST",
            f"/api/projects/{project_id}/understandings",
            {
                "summary": "V1 summary must stay",
                "unknowns": ["external overtime permission"],
                "rules": [
                    {
                        "rule_kind": "conditional",
                        "statement": "If overtime is permitted, apply overtime cost.",
                        "evidence_status": "unknown",
                        "condition_kind": "if_then",
                        "premise_status": "unknown",
                        "premise_text": "overtime permitted",
                        "cost": None,
                        "capacity": None,
                        "permission": None,
                    }
                ],
            },
        )
        expect(status == 200, f"create understanding v1 {status} {understanding_v1}")
        v1_id = understanding_v1["id"]
        rule_v1 = understanding_v1["rules"][0]
        expect(rule_v1["premise_status"] == "unknown", "v1 premise stored as unknown")
        expect(rule_v1["cost"] is None, "v1 cost stored as null")
        expect(rule_v1["permission"] is None, "v1 permission stored as null")

        status, scenario = request(
            base,
            "POST",
            f"/api/projects/{project_id}/scenarios",
            {
                "name": "Proof scenario",
                "notes": "scenario V1 notes",
                "based_on_understanding_id": v1_id,
                "formal_model": {"name": "proof-model-v1", "variable_count": None},
            },
        )
        expect(status == 200, f"create scenario {status} {scenario}")
        scenario_id = scenario["id"]
        scenario_v1_id = scenario["revisions"][0]["id"]
        scenario_v1_notes = scenario["revisions"][0]["notes"]

        status, reopened = request(base, "GET", f"/api/projects/{project_id}")
        expect(status == 200, "reopen project")
        expect(reopened["id"] == project_id, "same project id")
        expect(
            reopened["latest"]["understanding_revision_id"] == v1_id,
            "latest understanding after v1",
        )
        expect(
            reopened["latest"]["scenario_revision_id"] == scenario_v1_id,
            "latest scenario after v1",
        )

        status, understanding_v2 = request(
            base,
            "POST",
            f"/api/projects/{project_id}/understandings",
            {
                "summary": "V2 summary is different",
                "unknowns": ["external overtime permission", "capacity still unknown"],
                "rules": [
                    {
                        "rule_kind": "hard",
                        "statement": "Do not invent capacity.",
                        "capacity": None,
                    }
                ],
            },
        )
        expect(status == 200, f"create understanding v2 {status} {understanding_v2}")
        expect(understanding_v2["revision_no"] == 2, "understanding revision 2")
        expect(understanding_v2["parent_revision_id"] == v1_id, "v2 parents v1")

        status, scenario_v2 = request(
            base,
            "POST",
            f"/api/scenarios/{scenario_id}/revisions",
            {"notes": "scenario V2 notes", "formal_model": {"name": "proof-model-v2"}},
        )
        expect(status == 200, f"create scenario v2 {status} {scenario_v2}")
        expect(scenario_v2["revision_no"] == 2, "scenario revision 2")
        expect(
            scenario_v2["parent_revision_id"] == scenario_v1_id,
            "scenario v2 parents v1",
        )

        status, v1_body = request(base, "GET", f"/api/understandings/{v1_id}")
        expect(status == 200, "get understanding v1")
        expect(v1_body["summary"] == "V1 summary must stay", "v1 summary unchanged")
        expect(v1_body["revision_no"] == 1, "v1 revision_no unchanged")
        expect(len(v1_body["rules"]) == 1, "v1 still has original rule")
        expect(
            v1_body["rules"][0]["statement"] == rule_v1["statement"],
            "v1 rule statement",
        )
        status, sv1_again = request(
            base, "GET", f"/api/scenario-revisions/{scenario_v1_id}"
        )
        expect(status == 200, "get scenario v1")
        expect(sv1_again["notes"] == scenario_v1_notes, "scenario v1 notes unchanged")
        expect(sv1_again["revision_no"] == 1, "scenario v1 revision_no")

        expect(v1_body["rules"][0]["premise_status"] == "unknown", "premise still unknown")
        expect("cost" in v1_body["rules"][0], "cost key present")
        expect(v1_body["rules"][0]["cost"] is None, "cost is JSON null, not zero")
        expect(v1_body["rules"][0]["capacity"] is None, "capacity is JSON null")
        expect(v1_body["rules"][0]["permission"] is None, "permission is JSON null")
        expect(v1_body["rules"][0]["cost"] != 0, "cost is not 0")
        raw = json.dumps(v1_body["rules"][0])
        expect('"cost": null' in raw, f"serialized cost is null: {raw}")

        status, pending_body = request(
            base,
            "POST",
            f"/api/projects/{project_id}/solve-runs",
            {
                "scenario_revision_id": scenario_v2["id"],
                "run_state": "pending",
                "candidate": {"label": "no-solution-yet", "objective_value": None},
            },
        )
        expect(status == 200, f"pending solve run {pending_body}")
        expect(pending_body["run_state"] == "pending", "pending state")
        expect(pending_body["claimed_execution"] is False, "pending not executed")
        expect(pending_body["execution"] == "not_executed", "pending execution flag")
        expect(
            pending_body["candidates"][0]["objective_value"] is None,
            "candidate objective null",
        )

        for state in (
            "running",
            "feasible",
            "optimal",
            "infeasible",
            "unknown",
            "model_invalid",
            "failed",
            "cancelled",
        ):
            status, body = request(
                base,
                "POST",
                f"/api/projects/{project_id}/solve-runs",
                {"scenario_revision_id": scenario_v2["id"], "run_state": state},
            )
            expect(status == 200, f"solve run {state}: {body}")
            expect(body["run_state"] == state, f"stored {state}")
            expect(body["claimed_execution"] is False, f"{state} claimed_execution")
            expect(body["execution"] == "not_executed", f"{state} execution")

        status, reopened2 = request(base, "GET", f"/api/projects/{project_id}")
        expect(status == 200, "reopen after v2")
        latest = reopened2["latest"]
        expect(
            latest["understanding_revision_id"] == understanding_v2["id"],
            "latest is v2",
        )
        expect(latest["understanding_revision_no"] == 2, "latest understanding no")
        expect(
            latest["scenario_revision_id"] == scenario_v2["id"],
            "latest scenario is v2",
        )
        expect(
            len(reopened2["lineage"]["understandings"]) == 2,
            "two understanding revisions",
        )
        expect(
            reopened2["lineage"]["scenarios"][0]["revisions"][0]["id"] == scenario_v1_id,
            "lineage still lists v1",
        )

        status, listed = request(base, "GET", "/api/projects")
        expect(status == 200, "list projects")
        expect(any(item["id"] == project_id for item in listed), "listed created project")

        status, seed = request(base, "POST", "/api/dev/seed-demo", {})
        expect(status == 200, f"seed demo {seed}")
        expect(seed["is_demo"] is True, "demo flag")
        expect(seed["title"].startswith("[DEMO]"), "demo title marker")

        print("PASS: T03 persistence proof scenarios")
        print(f"temp_db={db_path}")
        print(f"project_id={project_id}")
        print(f"understanding_v1={v1_id}")
        print(f"understanding_v2={understanding_v2['id']}")
        print(f"scenario_v1={scenario_v1_id}")
        print(f"scenario_v2={scenario_v2['id']}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        for path in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
            try:
                path.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    main()
