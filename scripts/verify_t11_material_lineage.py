#!/usr/bin/env python3
"""Prove that mixed Evidence Set inputs survive into the Stage 2 scenario.

This deliberately uses the real intake adapters (text, CSV, and PNG), then
constructs the smallest confirmed baseline handoff that the Stage 1 review
boundary persists.  It does not use an LLM double or invent OCR semantics.
The assertions focus on the contract between source-linked claims and the
formal model created by ``create_scenario_from_baseline``.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def main() -> None:
    tmp = tempfile.TemporaryDirectory(prefix="lucid-t11-material-lineage-")
    os.environ["LUCID_DATA_DIR"] = tmp.name
    root = Path(__file__).resolve().parents[1]
    import sys

    sys.path.insert(0, str(root / "api"))
    from PIL import Image

    from app import ingest, store
    from app.db import connect, ensure_database, utc_now
    from app.schemas import ProjectCreate, ScenarioFromBaselineCreate

    ensure_database()
    project = store.create_project(ProjectCreate(title="T11 mixed evidence lineage proof"))

    text = ingest.ingest_direct_text(
        project["id"],
        "Room policy: every session needs a room with enough seats.",
        label="policy.txt",
    )
    csv = ingest.ingest_bytes(
        project["id"],
        "rooms.csv",
        b"room,capacity\nA,24\nB,12\n",
    )
    image_buffer = io.BytesIO()
    Image.new("RGB", (32, 16), color="white").save(image_buffer, format="PNG")
    image = ingest.ingest_bytes(project["id"], "layout.png", image_buffer.getvalue())

    materials = store.list_materials(project["id"])
    spans = store.list_source_spans(project["id"])
    expect(len(materials) == 3, "all text/table/image materials persisted")
    expect(len(spans) >= 5, "each adapter persisted source spans")
    expect(
        {item["metadata"].get("evidence_role") for item in materials}
        == {"evidence_not_instruction"},
        "intake marks every input as evidence rather than executable instruction",
    )
    expect(
        any(item["sheet"] == "rooms" and item["cell_ref"] == "B2" for item in spans),
        "table cell provenance survives intake",
    )
    expect(
        any(item["locator_kind"] == "region" for item in spans),
        "image full-region provenance survives intake",
    )

    by_material = {item["material"]["id"]: item for item in (text, csv, image)}
    text_ref = by_material[text["material"]["id"]]["spans"][0]
    table_ref = by_material[csv["material"]["id"]]["spans"][0]
    image_ref = by_material[image["material"]["id"]]["spans"][0]
    refs = [
        {
            "material_id": text["material"]["id"],
            "source_span_id": text_ref["id"],
            "material_checksum": text["material"]["checksum"],
            "precision": "approximate",
            "quote": text_ref["excerpt"],
        },
        {
            "material_id": csv["material"]["id"],
            "source_span_id": table_ref["id"],
            "material_checksum": csv["material"]["checksum"],
            "precision": "exact",
            "sheet": table_ref["sheet"],
            "cell_ref": table_ref["cell_ref"],
            "quote": table_ref["excerpt"],
        },
        {
            "material_id": image["material"]["id"],
            "source_span_id": image_ref["id"],
            "material_checksum": image["material"]["checksum"],
            "precision": "whole_source",
            "region": image_ref["region"],
            "quote": image_ref["excerpt"],
        },
    ]
    now = utc_now()
    run_id, draft_id, baseline_id = "lineage-run", "lineage-draft", "lineage-baseline"
    handoff = {
        "kind": "lucid.pre_solver_handoff",
        "solver": "not_executed",
        "coverage": [
            {
                "material_id": item["id"],
                "filename": item["filename"],
                "state": "analyzed",
            }
            for item in materials
        ],
        "snapshot": {
            "frozen_at": now,
            "materials": [
                {
                    "id": item["id"],
                    "filename": item["filename"],
                    "checksum": item["checksum"],
                    "byte_size": item["byte_size"],
                }
                for item in materials
            ],
        },
        "decision_variables": [
            {
                "claim_key": "assign-room",
                "name": "session room assignment",
                "domain": "room_id",
                "evidence_refs": [refs[0], refs[1]],
            }
        ],
        "parameters": [
            {
                "claim_key": "layout-evidence",
                "name": "layout reference",
                "raw_value": "see layout image",
                "evidence_refs": [refs[2]],
            }
        ],
        "constraints": [
            {
                "claim_key": "room-capacity",
                "original_statement": "Room capacity must cover session attendees.",
                "effective_statement": "Room capacity must cover session attendees.",
                "strength": "hard",
                "evidence_refs": refs[:2],
            }
        ],
        "objectives": [
            {
                "claim_key": "minimize-room-change",
                "original_statement": "Minimize room changes.",
                "effective_statement": "Minimize room changes.",
                "direction": "minimize",
                "priority": "1",
                "evidence_refs": [refs[2]],
            }
        ],
    }

    conn = connect()
    try:
        conn.execute(
            "INSERT INTO modeling_run (id, project_id, thread_id, status, question, evidence_fingerprint, coverage_json, created_at, updated_at) VALUES (?, ?, ?, 'completed', ?, '', ?, ?, ?)",
            (run_id, project["id"], run_id, "schedule sessions", json.dumps(handoff["coverage"]), now, now),
        )
        conn.execute(
            "INSERT INTO modeling_draft (id, project_id, run_id, revision_no, version_state, completeness, draft_json, created_at) VALUES (?, ?, ?, 1, 'confirmed', 'complete', '{}', ?)",
            (draft_id, project["id"], run_id, now),
        )
        conn.execute(
            "INSERT INTO modeling_baseline (id, project_id, draft_id, understanding_revision_id, scenario_id, scenario_revision_id, export_json, export_markdown, created_at) VALUES (?, ?, ?, NULL, NULL, NULL, ?, ?, ?)",
            (baseline_id, project["id"], draft_id, json.dumps(handoff), "# confirmed mixed evidence baseline", now),
        )
        conn.commit()
    finally:
        conn.close()

    scenario = store.create_scenario_from_baseline(
        project["id"],
        baseline_id,
        ScenarioFromBaselineCreate(name="Mixed evidence schedule"),
    )
    revision = scenario["revisions"][0]
    definition = revision["formal_model"]["definition"]
    expect(revision["version_state"] == "draft", "baseline creates editable scenario v1")
    expect(revision["formal_model"]["validation"]["valid"], "formal definition passes structural validation")
    expect(
        {item["source_claim_key"] for field in ("variables", "parameters", "constraints", "objectives") for item in definition[field]}
        == {"assign-room", "layout-evidence", "room-capacity", "minimize-room-change"},
        "every formal element retains its originating claim key",
    )
    expect(
        definition["source_claims"]["room-capacity"][0]["source_span_id"] == refs[0]["source_span_id"],
        "formal model keeps claim-to-source-span evidence refs",
    )
    baseline = store.get_project(project["id"])
    expect(baseline["latest"]["scenario_revision_id"] == revision["id"], "project points at the bound scenario revision")
    print("PASS: mixed text/table/image evidence survives intake → confirmed baseline → scenario formalization")


if __name__ == "__main__":
    main()
