#!/usr/bin/env python3
"""Focused T05 proof: six built-in fixtures instantiate through the real API.

This is intentionally one verifier, not a broad test suite. It uses a temporary
SQLite database and a real FastAPI process, so it exercises the same persistence
and HTTP paths used by the product without polluting the user's local database.
"""

from __future__ import annotations

import hashlib
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
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "api"
FIXTURE_ROOT = ROOT / "fixtures" / "templates"
VENV_PYTHON = API_ROOT / ".venv" / "bin" / "python"
sys.path.insert(0, str(API_ROOT))

TEMPLATE_IDS = (
    "training-schedule",
    "vehicle-validation-bench",
    "factory-maintenance-window",
    "supplier-capacity-allocation",
    "product-portfolio-selection",
    "retail-campaign-slotting",
)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def find_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(base: str, method: str, path: str) -> tuple[int, dict | list]:
    req = urllib.request.Request(
        base + path,
        data=b"{}" if method == "POST" else None,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
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
            if status == 200 and isinstance(body, dict) and body.get("status") == "ok":
                return
            last_error = f"status={status} body={body}"
        except Exception as exc:  # noqa: BLE001 — startup race
            last_error = str(exc)
        time.sleep(0.1)
    raise SystemExit(f"FAIL: API did not become healthy: {last_error}")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    expect(isinstance(value, dict), f"JSON object expected: {path}")
    return value


def verify_binary_shape(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        expect(path.read_bytes().startswith(b"%PDF-"), f"valid PDF signature: {path}")
    elif suffix == ".png":
        expect(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), f"valid PNG signature: {path}")
    elif suffix == ".xlsx":
        expect(path.read_bytes().startswith(b"PK"), f"XLSX is ZIP: {path}")
        with ZipFile(path) as workbook:
            expect("xl/workbook.xml" in workbook.namelist(), f"XLSX workbook part: {path}")
            expect("xl/worksheets/sheet1.xml" in workbook.namelist(), f"XLSX sheet part: {path}")


def verify_material_files(template_id: str, project: dict, expected_material_count: int) -> None:
    directory = FIXTURE_ROOT / template_id
    manifest = load_json(directory / "template.json")
    by_name = {item["filename"]: item for item in project["materials"]}
    expect(len(by_name) == len(manifest["sources"]), f"{template_id}: material count")
    expect(len(by_name) == expected_material_count, f"{template_id}: expected.json materials")
    for source in manifest["sources"]:
        filename = source["filename"]
        path = directory / filename
        expect(path.is_file(), f"{template_id}: source exists: {filename}")
        verify_binary_shape(path)
        content = path.read_bytes()
        persisted = by_name.get(filename)
        expect(persisted is not None, f"{template_id}: material persisted: {filename}")
        expect(persisted["byte_size"] == len(content), f"{template_id}: byte size {filename}")
        expected_sha = f"sha256:{hashlib.sha256(content).hexdigest()}"
        expect(persisted["checksum"] == expected_sha, f"{template_id}: checksum {filename}")
        expect(persisted["media_type"] == source.get("media_type"), f"{template_id}: media type {filename}")


def verify_template(base: str, template_id: str) -> dict:
    directory = FIXTURE_ROOT / template_id
    expected = load_json(directory / "expected.json")

    status, created = request(base, "POST", f"/api/templates/{template_id}/instantiate")
    expect(status == 200 and isinstance(created, dict), f"{template_id}: instantiate {status} {created}")
    project_id = created["id"]
    expect(created["title"].startswith("[TEMPLATE]"), f"{template_id}: template title marker")
    expect(created["is_demo"] is False, f"{template_id}: template is not persistence demo")
    verify_material_files(template_id, created, expected["materials"])

    status, reopened = request(base, "GET", f"/api/projects/{project_id}")
    expect(status == 200 and isinstance(reopened, dict), f"{template_id}: reopen")
    expect(reopened["id"] == project_id, f"{template_id}: same project id")

    status, spans = request(base, "GET", f"/api/projects/{project_id}/source-spans")
    expect(status == 200 and isinstance(spans, list), f"{template_id}: source spans")
    expect(len(spans) == expected["source_spans"], f"{template_id}: source span count")

    status, understandings = request(base, "GET", f"/api/projects/{project_id}/understandings")
    expect(status == 200 and isinstance(understandings, list), f"{template_id}: understandings")
    expect(len(understandings) == expected["understandings"], f"{template_id}: understanding count")
    understanding = understandings[-1]
    expect(len(understanding["rules"]) == expected["understanding_rules"], f"{template_id}: understanding rule count")
    expect(len(understanding["assumptions"]) > 0, f"{template_id}: assumptions present")
    expect(len(understanding["unknowns"]) > 0, f"{template_id}: unknowns present")
    expect(len(understanding["conflicts"]) > 0, f"{template_id}: conflicts present")
    for field in expected.get("must_preserve_null", []):
        expect(any(rule.get(field) is None for rule in understanding["rules"]), f"{template_id}: nullable {field} remains null")

    status, scenarios = request(base, "GET", f"/api/projects/{project_id}/scenarios")
    expect(status == 200 and isinstance(scenarios, list), f"{template_id}: scenarios")
    expect(len(scenarios) == expected["scenarios"], f"{template_id}: scenario count")
    revision_count = sum(len(item["revisions"]) for item in scenarios)
    expect(revision_count == expected["scenario_revisions"], f"{template_id}: scenario revision count")
    revision = scenarios[0]["revisions"][-1]
    expect(revision["formal_model"] is not None, f"{template_id}: formal model exists")
    expect(len(revision["rules"]) == expected["scenario_rules"], f"{template_id}: scenario rule count")

    status, runs = request(base, "GET", f"/api/projects/{project_id}/solve-runs")
    expect(status == 200 and isinstance(runs, list), f"{template_id}: solve runs")
    expect(len(runs) == expected["solve_runs"], f"{template_id}: solve run count")
    for run in runs:
        expect(run["claimed_execution"] is False, f"{template_id}: claimed_execution false")
        expect(run["execution"] == expected["solve_execution"] == "not_executed", f"{template_id}: not executed")
        for candidate in run["candidates"]:
            expect(candidate["objective_value"] is None, f"{template_id}: no fake objective")

    actual_media = sorted(item["media_type"] for item in created["materials"])
    expect(actual_media == sorted(expected["media_types"]), f"{template_id}: expected media types")
    return {
        "id": template_id,
        "project_id": project_id,
        "materials": len(created["materials"]),
        "source_spans": len(spans),
        "understanding_rules": len(understanding["rules"]),
        "scenario_rules": len(revision["rules"]),
        "solve_runs": len(runs),
        "media_types": actual_media,
    }


def main() -> None:
    tmp = tempfile.NamedTemporaryFile(prefix="lucid-t05-", suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    port = find_port()
    base = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["LUCID_DB_PATH"] = str(db_path)
    python = str(VENV_PYTHON if VENV_PYTHON.exists() else sys.executable)
    proc = subprocess.Popen(
        [python, "-m", "uvicorn", "app.main:app", "--app-dir", str(API_ROOT), "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(API_ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        wait_health(base)
        status, catalog = request(base, "GET", "/api/templates")
        expect(status == 200 and isinstance(catalog, list), f"template catalog status {status}")
        expect([item["id"] for item in catalog] == list(TEMPLATE_IDS), "catalog exposes exactly six templates in stable order")
        expect(all(item["name_en"] and item["name_zh"] for item in catalog), "catalog has bilingual names")
        expect(
            all(item["description_en"] and item["description_zh"] and item["source_types"] for item in catalog),
            "catalog has bilingual descriptions and source-type badges",
        )

        results = [verify_template(base, template_id) for template_id in TEMPLATE_IDS]
        expect(len({item["project_id"] for item in results}) == 6, "each template creates a unique project")

        status, projects = request(base, "GET", "/api/projects")
        expect(status == 200 and isinstance(projects, list), "list projects after templates")
        template_projects = [item for item in projects if item["title"].startswith("[TEMPLATE]")]
        expect(len(template_projects) == 6, "all six template projects persisted")

        print("PASS: T05 six templates through real FastAPI + SQLite")
        for item in results:
            print(json.dumps(item, ensure_ascii=False, sort_keys=True))
        print(f"temp_db={db_path}")
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
