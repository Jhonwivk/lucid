#!/usr/bin/env python3
"""Import the six template source files through the public intake APIs.

expected.json and template.json are never sent to the Agent or intake.
This is evidence that real fixture bytes can enter the Material model.
It is not a live model run.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "api"
FIXTURE_ROOT = ROOT / "fixtures" / "templates"
PUBLIC = ROOT / "fixtures" / "public_samples" / "us-federal-holidays-2026"
sys.path.insert(0, str(API_ROOT))

TMP = Path(tempfile.mkdtemp(prefix="lucid-stage1-intake-"))
os.environ["LUCID_DATA_DIR"] = str(TMP)
os.environ["LUCID_DB_PATH"] = str(TMP / "lucid.db")

TEMPLATE_IDS = (
    "training-schedule",
    "vehicle-validation-bench",
    "factory-maintenance-window",
    "supplier-capacity-allocation",
    "product-portfolio-selection",
    "retail-campaign-slotting",
)

SKIP_NAMES = {"expected.json", "template.json", "README.md"}


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def main() -> None:
    from fastapi.testclient import TestClient

    from app.db import ensure_database
    from app.main import app

    ensure_database()
    client = TestClient(app)

    text_only = client.post(
        "/api/analyses/start",
        json={
            "title": "Text-only intake",
            "question": "Should the plant close on New Year's Day, and who approves overtime?",
        },
    )
    expect(text_only.status_code == 200, text_only.text)
    project = text_only.json()
    materials = client.get(f"/api/projects/{project['id']}/materials").json()
    expect(len(materials) == 1, f"question-only should persist one material, got {len(materials)}")
    blocked = client.post(
        f"/api/projects/{project['id']}/modeling-runs",
        json={"question": project["decision_question"]},
    )
    expect(blocked.status_code == 200, blocked.text)
    expect(blocked.json()["error_code"] == "model_not_configured", blocked.json())
    expect(blocked.json().get("drafts") in (None, []), "no fake draft")

    coverage: dict[str, list[str]] = {}
    for template_id in TEMPLATE_IDS:
        folder = FIXTURE_ROOT / template_id
        sources = sorted(
            path
            for path in folder.iterdir()
            if path.is_file() and path.name not in SKIP_NAMES and not path.name.startswith(".")
        )
        expect(sources, f"{template_id} must have real source files")
        created = client.post(
            "/api/analyses/start",
            json={
                "title": f"Intake {template_id}",
                "question": f"What constraints are stated for the {template_id} case?",
            },
        )
        expect(created.status_code == 200, created.text)
        pid = created.json()["id"]
        imported_names = []
        for path in sources:
            with path.open("rb") as handle:
                response = client.post(
                    f"/api/projects/{pid}/materials/import",
                    files={"file": (path.name, handle, "application/octet-stream")},
                )
            expect(response.status_code == 200, f"{template_id}/{path.name}: {response.text}")
            body = response.json()
            expect("expected.json" not in str(body).lower(), "expected.json must not appear in intake")
            imported_names.append(path.name)
        listed = client.get(f"/api/projects/{pid}/materials").json()
        stored = {item["filename"] for item in listed}
        for name in imported_names:
            expect(name in stored, f"{template_id} missing {name} in materials")
        coverage[template_id] = imported_names
        print(f"INTAKE {template_id}: {', '.join(imported_names)}")

    public = client.post(
        "/api/analyses/start",
        json={
            "title": "Public holidays sample",
            "question": "Which federal holidays should close the fictional plant in 2026?",
            "text": (PUBLIC / "plant-shutdown.md").read_text(encoding="utf-8"),
        },
    )
    expect(public.status_code == 200, public.text)
    pid = public.json()["id"]
    holidays = PUBLIC / "federal-holidays-2026.json"
    with holidays.open("rb") as handle:
        uploaded = client.post(
            f"/api/projects/{pid}/materials/import",
            files={"file": (holidays.name, handle, "application/json")},
        )
    expect(uploaded.status_code == 200, uploaded.text)
    print("INTAKE public-sample: plant-shutdown.md + federal-holidays-2026.json")
    print("NOTE: fixtures are fictional cases in genuine files; public sample is US federal holiday dates.")
    print("PASS: six templates + text-only + public sample via public intake")
    print("coverage=" + str({key: len(value) for key, value in coverage.items()}))


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
