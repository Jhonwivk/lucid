"""Transaction-safe SQLite persistence for LUCID analysis objects.

Revision bodies (understanding, scenario, rules, formal models, materials,
source spans) are insert-only. Live latest-pointers live on analysis_project
and may be updated without rewriting historical snapshot rows.

Unknown numeric / boolean business values are stored as SQL NULL and must
never be coerced to 0 / false.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import connect, utc_now
from .schemas import (
    FormalModelIn,
    FormalElementChange,
    ConflictExplanationIn,
    MaterialCreate,
    ProjectCreate,
    ProjectPatch,
    ResultCandidateIn,
    RuleIn,
    ScenarioCreate,
    ScenarioFromBaselineCreate,
    ScenarioImpactPreviewCreate,
    WhatIfScenarioCreate,
    ScenarioRevisionCreate,
    SolveRunCreate,
    TrainingScheduleSolveCreate,
    PortfolioSolveCreate,
    SourceSpanCreate,
    UnderstandingCreate,
)
from .solver import solve_portfolio, solve_training_schedule

DEMO_TITLE = "[DEMO] Persistence reopen sample"
DEMO_NOTES = "DEMO DATA only. Not a training-scheduling answer and not a solver result."


class NotFoundError(LookupError):
    pass


class ConflictError(ValueError):
    pass


def _new_id() -> str:
    return str(uuid.uuid4())


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_json(value: str | None, default: Any) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)


def _bool_to_sql(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _sql_to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _require_project(conn: sqlite3.Connection, project_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM analysis_project WHERE id = ?", (project_id,)
    ).fetchone()
    if row is None:
        raise NotFoundError("project not found")
    return row


def _event(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    event_type: str,
    entity_kind: str,
    entity_id: str,
    summary: str,
    payload: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO change_event (
            id, project_id, event_type, entity_kind, entity_id,
            summary, payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _new_id(),
            project_id,
            event_type,
            entity_kind,
            entity_id,
            summary,
            None if payload is None else _dump_json(payload),
            utc_now(),
        ),
    )


def _touch_project(conn: sqlite3.Connection, project_id: str) -> None:
    conn.execute(
        "UPDATE analysis_project SET updated_at = ? WHERE id = ?",
        (utc_now(), project_id),
    )


def _rule_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "owner_kind": row["owner_kind"],
        "understanding_revision_id": row["understanding_revision_id"],
        "scenario_revision_id": row["scenario_revision_id"],
        "rule_kind": row["rule_kind"],
        "statement": row["statement"],
        "review_status": row["review_status"],
        "evidence_status": row["evidence_status"],
        "source_span_id": row["source_span_id"],
        "condition_kind": row["condition_kind"],
        "premise_status": row["premise_status"],
        "premise_text": row["premise_text"],
        "cost": row["cost"],
        "capacity": row["capacity"],
        "permission": _sql_to_bool(row["permission"]),
        "created_at": row["created_at"],
    }


def _insert_rules(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    owner_kind: str,
    understanding_revision_id: str | None,
    scenario_revision_id: str | None,
    rules: list[RuleIn],
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    now = utc_now()
    for rule in rules:
        premise_status = rule.premise_status
        condition_kind = rule.condition_kind
        if rule.rule_kind == "conditional":
            if condition_kind is None:
                condition_kind = "if_then"
            if premise_status is None:
                premise_status = "unknown"
        rule_id = _new_id()
        conn.execute(
            """
            INSERT INTO rule (
                id, project_id, owner_kind, understanding_revision_id,
                scenario_revision_id, rule_kind, statement, review_status,
                evidence_status, source_span_id, condition_kind, premise_status,
                premise_text, cost, capacity, permission, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rule_id,
                project_id,
                owner_kind,
                understanding_revision_id,
                scenario_revision_id,
                rule.rule_kind,
                rule.statement,
                rule.review_status,
                rule.evidence_status,
                rule.source_span_id,
                condition_kind,
                premise_status,
                rule.premise_text,
                rule.cost,
                rule.capacity,
                _bool_to_sql(rule.permission),
                now,
            ),
        )
        row = conn.execute("SELECT * FROM rule WHERE id = ?", (rule_id,)).fetchone()
        created.append(_rule_from_row(row))
    return created


def _rules_for_understanding(
    conn: sqlite3.Connection, revision_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM rule
        WHERE understanding_revision_id = ?
        ORDER BY created_at, id
        """,
        (revision_id,),
    ).fetchall()
    return [_rule_from_row(row) for row in rows]


def _rules_for_scenario(
    conn: sqlite3.Connection, revision_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM rule
        WHERE scenario_revision_id = ?
        ORDER BY created_at, id
        """,
        (revision_id,),
    ).fetchall()
    return [_rule_from_row(row) for row in rows]


def _understanding_from_row(
    conn: sqlite3.Connection, row: sqlite3.Row
) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "revision_no": row["revision_no"],
        "parent_revision_id": row["parent_revision_id"],
        "version_state": row["version_state"],
        "summary": row["summary"],
        "assumptions": _load_json(row["assumptions_json"], []),
        "unknowns": _load_json(row["unknowns_json"], []),
        "conflicts": _load_json(row["conflicts_json"], []),
        "rules": _rules_for_understanding(conn, row["id"]),
        "created_at": row["created_at"],
    }


def _definition_payload(payload: FormalModelIn | None) -> dict[str, Any] | None:
    if payload is None or payload.definition is None:
        return None
    return payload.definition.model_dump(mode="json")


def _definition_hash(definition: dict[str, Any] | None) -> str | None:
    if definition is None:
        return None
    encoded = json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _formal_definition_issues(definition: dict[str, Any] | None) -> list[str]:
    if not definition:
        return ["formal_model.definition is required"]
    issues: list[str] = []
    collections = ("variables", "parameters", "constraints", "objectives")
    keys: set[str] = set()
    for collection in collections:
        for item in definition.get(collection) or []:
            if not isinstance(item, dict):
                issues.append(f"{collection} item must be an object")
                continue
            key = str(item.get("key") or "")
            if not key:
                issues.append(f"{collection} item is missing key")
            elif key in keys:
                issues.append(f"duplicate formal definition key: {key}")
            else:
                keys.add(key)
    if not definition.get("variables"):
        issues.append("formal model has no variables")
    if not definition.get("constraints"):
        issues.append("formal model has no constraints")
    if not definition.get("objectives"):
        issues.append("formal model has no objectives")
    for objective in definition.get("objectives") or []:
        if isinstance(objective, dict):
            objective_key = objective.get("key") or "<unnamed>"
            if objective.get("direction") not in {"minimize", "maximize"}:
                issues.append(f"objective {objective_key} has no executable direction")
            if objective.get("priority") is None:
                issues.append(f"objective {objective_key} has no numeric priority")
    if definition.get("family") == "training_schedule" and not definition.get("training_schedule"):
        issues.append("training_schedule family requires training_schedule data")
    if definition.get("family") == "portfolio" and not definition.get("portfolio"):
        issues.append("portfolio family requires portfolio data")
    return issues


def _formal_model_validation(definition: dict[str, Any] | None) -> dict[str, Any]:
    issues = _formal_definition_issues(definition)
    return {"valid": not issues, "issues": issues}


def _formal_model_from_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "scenario_revision_id": row["scenario_revision_id"],
        "name": row["name"],
        "version_state": row["version_state"],
        "variable_count": row["variable_count"],
        "constraint_count": row["constraint_count"],
        "objective_text": row["objective_text"],
        "notes": row["notes"],
        "definition": _load_json(row["definition_json"], None) if "definition_json" in row.keys() else None,
        "definition_hash": row["definition_hash"] if "definition_hash" in row.keys() else None,
        "dependency_fingerprint": row["dependency_fingerprint"] if "dependency_fingerprint" in row.keys() else None,
        "validation": _formal_model_validation(_load_json(row["definition_json"], None) if "definition_json" in row.keys() else None),
        "created_at": row["created_at"],
    }


def _get_formal_model(conn: sqlite3.Connection, model_id: str | None) -> dict[str, Any] | None:
    if not model_id:
        return None
    row = conn.execute(
        "SELECT * FROM formal_model WHERE id = ?", (model_id,)
    ).fetchone()
    return _formal_model_from_row(row)


def _scenario_revision_from_row(
    conn: sqlite3.Connection, row: sqlite3.Row, *, include_body: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row["id"],
        "scenario_id": row["scenario_id"],
        "project_id": row["project_id"],
        "revision_no": row["revision_no"],
        "parent_revision_id": row["parent_revision_id"],
        "version_state": row["version_state"],
        "based_on_understanding_id": row["based_on_understanding_id"],
        "formal_model_id": row["formal_model_id"],
        "notes": row["notes"],
        "invalidation_reason": row["invalidation_reason"] if "invalidation_reason" in row.keys() else None,
        "invalidated_at": row["invalidated_at"] if "invalidated_at" in row.keys() else None,
        "created_at": row["created_at"],
    }
    if include_body:
        payload["formal_model"] = _get_formal_model(conn, row["formal_model_id"])
        payload["rules"] = _rules_for_scenario(conn, row["id"])
    return payload


def _material_from_row(row: sqlite3.Row) -> dict[str, Any]:
    keys = row.keys()
    metadata = None
    if "metadata_json" in keys:
        metadata = _load_json(row["metadata_json"], None)
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "filename": row["filename"],
        "media_type": row["media_type"],
        "kind": row["kind"],
        "byte_size": row["byte_size"],
        "checksum": row["checksum"],
        "notes": row["notes"],
        "metadata": metadata,
        "deleted_at": row["deleted_at"] if "deleted_at" in keys else None,
        "created_at": row["created_at"],
    }


def _source_span_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "material_id": row["material_id"],
        "locator_kind": row["locator_kind"],
        "page": row["page"],
        "start_offset": row["start_offset"],
        "end_offset": row["end_offset"],
        "sheet": row["sheet"],
        "cell_ref": row["cell_ref"],
        "region": _load_json(row["region_json"], None),
        "excerpt": row["excerpt"],
        "created_at": row["created_at"],
    }


def _candidate_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "solve_run_id": row["solve_run_id"],
        "label": row["label"],
        "objective_value": row["objective_value"],
        "is_selected": _sql_to_bool(row["is_selected"]),
        "notes": row["notes"],
        "details": _load_json(row["details_json"], None) if "details_json" in row.keys() else None,
        "result": _load_json(row["result_json"], None) if "result_json" in row.keys() else None,
        "explanation": _load_json(row["explanation_json"], None) if "explanation_json" in row.keys() else None,
        "provenance": _load_json(row["provenance_json"], None) if "provenance_json" in row.keys() else None,
        "created_at": row["created_at"],
    }


def _solve_run_from_row(
    conn: sqlite3.Connection, row: sqlite3.Row, *, include_candidates: bool
) -> dict[str, Any]:
    payload = {
        "id": row["id"],
        "project_id": row["project_id"],
        "scenario_revision_id": row["scenario_revision_id"],
        "formal_model_id": row["formal_model_id"],
        "run_state": row["run_state"],
        "claimed_execution": bool(row["claimed_execution"]) or bool(row["claim_owner"] if "claim_owner" in row.keys() else None),
        "execution": row["execution"],
        "solver_name": row["solver_name"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "message": row["message"],
        "input_fingerprint": row["input_fingerprint"] if "input_fingerprint" in row.keys() else None,
        "claim_owner": row["claim_owner"] if "claim_owner" in row.keys() else None,
        "claim_token": row["claim_token"] if "claim_token" in row.keys() else None,
        "heartbeat_at": row["heartbeat_at"] if "heartbeat_at" in row.keys() else None,
        "stale_at": row["stale_at"] if "stale_at" in row.keys() else None,
        "resume_count": int(row["resume_count"] or 0) if "resume_count" in row.keys() else 0,
        "lease_timeout_seconds": int(row["lease_timeout_seconds"] or 120) if "lease_timeout_seconds" in row.keys() else 120,
        "explanation": _load_json(row["explanation_json"], None) if "explanation_json" in row.keys() else None,
        "created_at": row["created_at"],
    }
    if include_candidates:
        candidates = conn.execute(
            """
            SELECT * FROM result_candidate
            WHERE solve_run_id = ?
            ORDER BY created_at, id
            """,
            (row["id"],),
        ).fetchall()
        payload["candidates"] = [_candidate_from_row(item) for item in candidates]
    return payload


def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "event_type": row["event_type"],
        "entity_kind": row["entity_kind"],
        "entity_id": row["entity_id"],
        "summary": row["summary"],
        "payload": _load_json(row["payload_json"], None),
        "created_at": row["created_at"],
    }


def _latest_pointers(conn: sqlite3.Connection, project: sqlite3.Row) -> dict[str, Any]:
    understanding_no = None
    if project["latest_understanding_revision_id"]:
        row = conn.execute(
            "SELECT revision_no FROM understanding_revision WHERE id = ?",
            (project["latest_understanding_revision_id"],),
        ).fetchone()
        if row:
            understanding_no = row["revision_no"]
    scenario_no = None
    if project["latest_scenario_revision_id"]:
        row = conn.execute(
            "SELECT revision_no FROM scenario_revision WHERE id = ?",
            (project["latest_scenario_revision_id"],),
        ).fetchone()
        if row:
            scenario_no = row["revision_no"]
    return {
        "understanding_revision_id": project["latest_understanding_revision_id"],
        "understanding_revision_no": understanding_no,
        "scenario_id": project["latest_scenario_id"],
        "scenario_revision_id": project["latest_scenario_revision_id"],
        "scenario_revision_no": scenario_no,
        "formal_model_id": project["latest_formal_model_id"],
        "solve_run_id": project["latest_solve_run_id"],
        "modeling_run_id": project["latest_modeling_run_id"] if "latest_modeling_run_id" in project.keys() else None,
        "modeling_draft_id": project["latest_modeling_draft_id"] if "latest_modeling_draft_id" in project.keys() else None,
        "baseline_id": project["latest_baseline_id"] if "latest_baseline_id" in project.keys() else None,
    }


def _project_lineage(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    understandings = conn.execute(
        """
        SELECT id, revision_no, parent_revision_id, version_state, created_at
        FROM understanding_revision
        WHERE project_id = ?
        ORDER BY revision_no
        """,
        (project_id,),
    ).fetchall()
    scenarios = conn.execute(
        """
        SELECT id, name, created_at
        FROM scenario
        WHERE project_id = ?
        ORDER BY created_at, id
        """,
        (project_id,),
    ).fetchall()
    scenario_items = []
    for scenario in scenarios:
        revisions = conn.execute(
            """
            SELECT id, revision_no, parent_revision_id, version_state,
                   formal_model_id, created_at
            FROM scenario_revision
            WHERE scenario_id = ?
            ORDER BY revision_no
            """,
            (scenario["id"],),
        ).fetchall()
        scenario_items.append(
            {
                "id": scenario["id"],
                "name": scenario["name"],
                "created_at": scenario["created_at"],
                "revisions": [dict(row) for row in revisions],
            }
        )
    solve_runs = conn.execute(
        """
        SELECT id, run_state, claimed_execution, execution, created_at
        FROM solve_run
        WHERE project_id = ?
        ORDER BY created_at, id
        """,
        (project_id,),
    ).fetchall()
    events = conn.execute(
        """
        SELECT * FROM change_event
        WHERE project_id = ?
        ORDER BY created_at, id
        """,
        (project_id,),
    ).fetchall()
    return {
        "understandings": [dict(row) for row in understandings],
        "scenarios": scenario_items,
        "solve_runs": [
            {
                "id": row["id"],
                "run_state": row["run_state"],
                "claimed_execution": bool(row["claimed_execution"]),
                "execution": row["execution"],
                "created_at": row["created_at"],
            }
            for row in solve_runs
        ],
        "events": [_event_from_row(row) for row in events],
    }


def _project_summary(conn: sqlite3.Connection, project: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": project["id"],
        "title": project["title"],
        "summary": project["summary"],
        "decision_question": project["decision_question"] if "decision_question" in project.keys() else None,
        "workflow_maturity": project["workflow_maturity"],
        "is_demo": bool(project["is_demo"]),
        "latest": _latest_pointers(conn, project),
        "created_at": project["created_at"],
        "updated_at": project["updated_at"],
    }


def _list_materials(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM material
        WHERE project_id = ?
        ORDER BY created_at, id
        """,
        (project_id,),
    ).fetchall()
    return [_material_from_row(row) for row in rows]


def _project_detail(conn: sqlite3.Connection, project: sqlite3.Row) -> dict[str, Any]:
    detail = _project_summary(conn, project)
    detail["lineage"] = _project_lineage(conn, project["id"])
    detail["materials"] = _list_materials(conn, project["id"])
    return detail


def create_project(payload: ProjectCreate, *, is_demo: bool = False) -> dict[str, Any]:
    project_id = _new_id()
    now = utc_now()
    conn = connect()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO analysis_project (
                    id, title, summary, decision_question, workflow_maturity, is_demo,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    payload.title,
                    payload.summary,
                    getattr(payload, "decision_question", None),
                    payload.workflow_maturity,
                    1 if is_demo else 0,
                    now,
                    now,
                ),
            )
            _event(
                conn,
                project_id=project_id,
                event_type="project.created",
                entity_kind="project",
                entity_id=project_id,
                summary=f"Created analysis project '{payload.title}'",
                payload={"is_demo": is_demo},
            )
            project = _require_project(conn, project_id)
            return _project_detail(conn, project)
    finally:
        conn.close()


def list_projects() -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM analysis_project ORDER BY updated_at DESC, id"
        ).fetchall()
        return [_project_summary(conn, row) for row in rows]
    finally:
        conn.close()


def get_project(project_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        project = _require_project(conn, project_id)
        return _project_detail(conn, project)
    finally:
        conn.close()


def patch_project(project_id: str, payload: ProjectPatch) -> dict[str, Any]:
    conn = connect()
    try:
        with conn:
            project = _require_project(conn, project_id)
            title = payload.title if payload.title is not None else project["title"]
            summary = project["summary"] if payload.summary is None else payload.summary
            question = (
                project["decision_question"]
                if getattr(payload, "decision_question", None) is None
                else payload.decision_question
            )
            if "decision_question" not in project.keys():
                question = getattr(payload, "decision_question", None)
            maturity = (
                payload.workflow_maturity
                if payload.workflow_maturity is not None
                else project["workflow_maturity"]
            )
            conn.execute(
                """
                UPDATE analysis_project
                SET title = ?, summary = ?, decision_question = ?, workflow_maturity = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, summary, question, maturity, utc_now(), project_id),
            )
            _event(
                conn,
                project_id=project_id,
                event_type="project.updated",
                entity_kind="project",
                entity_id=project_id,
                summary="Updated analysis project live fields (not a historical snapshot rewrite)",
            )
            return _project_detail(conn, _require_project(conn, project_id))
    finally:
        conn.close()


def create_material(project_id: str, payload: MaterialCreate) -> dict[str, Any]:
    conn = connect()
    try:
        with conn:
            _require_project(conn, project_id)
            material_id = _new_id()
            conn.execute(
                """
                INSERT INTO material (
                    id, project_id, filename, media_type, kind,
                    byte_size, checksum, notes, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    material_id,
                    project_id,
                    payload.filename,
                    payload.media_type,
                    payload.kind,
                    payload.byte_size,
                    payload.checksum,
                    payload.notes,
                    None if payload.metadata is None else _dump_json(payload.metadata),
                    utc_now(),
                ),
            )
            _touch_project(conn, project_id)
            _event(
                conn,
                project_id=project_id,
                event_type="material.created",
                entity_kind="material",
                entity_id=material_id,
                summary=f"Recorded material metadata '{payload.filename}'",
            )
            row = conn.execute(
                "SELECT * FROM material WHERE id = ?", (material_id,)
            ).fetchone()
            return _material_from_row(row)
    finally:
        conn.close()


def list_materials(project_id: str) -> list[dict[str, Any]]:
    conn = connect()
    try:
        _require_project(conn, project_id)
        return _list_materials(conn, project_id)
    finally:
        conn.close()


def get_material(project_id: str, material_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        _require_project(conn, project_id)
        row = conn.execute(
            "SELECT * FROM material WHERE id = ? AND project_id = ?",
            (material_id, project_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("material not found")
        return _material_from_row(row)
    finally:
        conn.close()


def delete_material(project_id: str, material_id: str) -> dict[str, Any]:
    """Soft-delete material content while retaining provenance for old results."""
    conn = connect()
    try:
        with conn:
            _require_project(conn, project_id)
            row = conn.execute(
                "SELECT * FROM material WHERE id = ? AND project_id = ?",
                (material_id, project_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("material not found")
            deleted_at = row["deleted_at"] if "deleted_at" in row.keys() else None
            if deleted_at is None:
                deleted_at = utc_now()
                conn.execute(
                    "UPDATE material SET deleted_at = ? WHERE id = ? AND project_id = ?",
                    (deleted_at, material_id, project_id),
                )
                _touch_project(conn, project_id)
                _event(
                    conn,
                    project_id=project_id,
                    event_type="material.deleted",
                    entity_kind="material",
                    entity_id=material_id,
                    summary="Deleted material content while retaining provenance metadata",
                )
            row = conn.execute("SELECT * FROM material WHERE id = ?", (material_id,)).fetchone()
            return _material_from_row(row)
    finally:
        conn.close()


def list_source_spans(project_id: str) -> list[dict[str, Any]]:
    conn = connect()
    try:
        _require_project(conn, project_id)
        rows = conn.execute(
            """
            SELECT * FROM source_span
            WHERE project_id = ?
            ORDER BY created_at, id
            """,
            (project_id,),
        ).fetchall()
        return [_source_span_from_row(row) for row in rows]
    finally:
        conn.close()


def persist_imported_material(
    project_id: str,
    payload: MaterialCreate,
    spans: list[SourceSpanCreate],
) -> dict[str, Any]:
    """Insert one Material and its SourceSpan rows in a single transaction."""
    conn = connect()
    try:
        with conn:
            _require_project(conn, project_id)
            material_id = _new_id()
            created_at = utc_now()
            conn.execute(
                """
                INSERT INTO material (
                    id, project_id, filename, media_type, kind,
                    byte_size, checksum, notes, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    material_id,
                    project_id,
                    payload.filename,
                    payload.media_type,
                    payload.kind,
                    payload.byte_size,
                    payload.checksum,
                    payload.notes,
                    None if payload.metadata is None else _dump_json(payload.metadata),
                    created_at,
                ),
            )
            created_spans: list[dict[str, Any]] = []
            for span in spans:
                span_id = _new_id()
                conn.execute(
                    """
                    INSERT INTO source_span (
                        id, project_id, material_id, locator_kind, page,
                        start_offset, end_offset, sheet, cell_ref, region_json,
                        excerpt, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        span_id,
                        project_id,
                        material_id,
                        span.locator_kind,
                        span.page,
                        span.start_offset,
                        span.end_offset,
                        span.sheet,
                        span.cell_ref,
                        None if span.region is None else _dump_json(span.region),
                        span.excerpt,
                        created_at,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM source_span WHERE id = ?", (span_id,)
                ).fetchone()
                created_spans.append(_source_span_from_row(row))
            _touch_project(conn, project_id)
            origin = (payload.metadata or {}).get("source_origin")
            if origin == "direct_text":
                summary = (
                    f"Recorded direct-text evidence '{payload.filename}' "
                    f"with {len(created_spans)} source spans"
                )
            else:
                summary = (
                    f"Imported evidence file '{payload.filename}' "
                    f"with {len(created_spans)} source spans"
                )
            _event(
                conn,
                project_id=project_id,
                event_type="material.imported",
                entity_kind="material",
                entity_id=material_id,
                summary=summary,
                payload={
                    "filename": payload.filename,
                    "span_count": len(created_spans),
                    "source_origin": origin,
                },
            )
            material_row = conn.execute(
                "SELECT * FROM material WHERE id = ?", (material_id,)
            ).fetchone()
            return {
                "material": _material_from_row(material_row),
                "spans": created_spans,
            }
    finally:
        conn.close()


def create_source_span(project_id: str, payload: SourceSpanCreate) -> dict[str, Any]:
    conn = connect()
    try:
        with conn:
            _require_project(conn, project_id)
            material = conn.execute(
                "SELECT id FROM material WHERE id = ? AND project_id = ?",
                (payload.material_id, project_id),
            ).fetchone()
            if material is None:
                raise NotFoundError("material not found")
            span_id = _new_id()
            conn.execute(
                """
                INSERT INTO source_span (
                    id, project_id, material_id, locator_kind, page,
                    start_offset, end_offset, sheet, cell_ref, region_json,
                    excerpt, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    span_id,
                    project_id,
                    payload.material_id,
                    payload.locator_kind,
                    payload.page,
                    payload.start_offset,
                    payload.end_offset,
                    payload.sheet,
                    payload.cell_ref,
                    None if payload.region is None else _dump_json(payload.region),
                    payload.excerpt,
                    utc_now(),
                ),
            )
            _touch_project(conn, project_id)
            _event(
                conn,
                project_id=project_id,
                event_type="source_span.created",
                entity_kind="source_span",
                entity_id=span_id,
                summary="Recorded provenance source span (metadata only)",
            )
            row = conn.execute(
                "SELECT * FROM source_span WHERE id = ?", (span_id,)
            ).fetchone()
            return _source_span_from_row(row)
    finally:
        conn.close()


def create_understanding(
    project_id: str, payload: UnderstandingCreate
) -> dict[str, Any]:
    conn = connect()
    try:
        with conn:
            return insert_understanding(conn, project_id, payload, update_project_head=True)
    finally:
        conn.close()


def insert_understanding(
    conn: sqlite3.Connection,
    project_id: str,
    payload: UnderstandingCreate,
    *,
    update_project_head: bool = True,
) -> dict[str, Any]:
    """Insert an understanding revision on an existing connection/transaction."""
    project = _require_project(conn, project_id)
    latest = conn.execute(
        """
        SELECT id, revision_no FROM understanding_revision
        WHERE project_id = ?
        ORDER BY revision_no DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    revision_no = 1 if latest is None else latest["revision_no"] + 1
    parent_id = None if latest is None else latest["id"]
    revision_id = _new_id()
    conn.execute(
        """
        INSERT INTO understanding_revision (
            id, project_id, revision_no, parent_revision_id,
            version_state, summary, assumptions_json, unknowns_json,
            conflicts_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            revision_id,
            project_id,
            revision_no,
            parent_id,
            payload.version_state,
            payload.summary,
            _dump_json(payload.assumptions),
            _dump_json(payload.unknowns),
            _dump_json(payload.conflicts),
            utc_now(),
        ),
    )
    _insert_rules(
        conn,
        project_id=project_id,
        owner_kind="understanding",
        understanding_revision_id=revision_id,
        scenario_revision_id=None,
        rules=payload.rules,
    )
    if update_project_head:
        conn.execute(
            """
            UPDATE analysis_project
            SET latest_understanding_revision_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (revision_id, utc_now(), project_id),
        )
    _event(
        conn,
        project_id=project_id,
        event_type="understanding.revision_created",
        entity_kind="understanding_revision",
        entity_id=revision_id,
        summary=f"Created understanding revision v{revision_no}",
        payload={
            "revision_no": revision_no,
            "parent_revision_id": parent_id,
            "previous_latest_id": project["latest_understanding_revision_id"],
        },
    )
    row = conn.execute(
        "SELECT * FROM understanding_revision WHERE id = ?",
        (revision_id,),
    ).fetchone()
    return _understanding_from_row(conn, row)


def rule_table_allows_status(conn: sqlite3.Connection, status: str) -> bool:
    if status != "not_applicable":
        return True
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='rule'"
    ).fetchone()
    sql = (row["sql"] if row else "") or ""
    return "not_applicable" in sql


def get_understanding(revision_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM understanding_revision WHERE id = ?", (revision_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("understanding revision not found")
        return _understanding_from_row(conn, row)
    finally:
        conn.close()


def list_understandings(project_id: str) -> list[dict[str, Any]]:
    conn = connect()
    try:
        _require_project(conn, project_id)
        rows = conn.execute(
            """
            SELECT * FROM understanding_revision
            WHERE project_id = ?
            ORDER BY revision_no
            """,
            (project_id,),
        ).fetchall()
        return [_understanding_from_row(conn, row) for row in rows]
    finally:
        conn.close()


def _insert_formal_model(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    scenario_revision_id: str,
    payload: FormalModelIn | None,
) -> str | None:
    if payload is None:
        return None
    definition = _definition_payload(payload)
    model_id = _new_id()
    conn.execute(
        """
        INSERT INTO formal_model (
            id, project_id, scenario_revision_id, name, version_state,
            variable_count, constraint_count, objective_text, notes,
            definition_json, definition_hash, dependency_fingerprint, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            model_id,
            project_id,
            scenario_revision_id,
            payload.name,
            payload.version_state,
            payload.variable_count if payload.variable_count is not None else len((definition or {}).get("variables") or []),
            payload.constraint_count if payload.constraint_count is not None else len((definition or {}).get("constraints") or []),
            payload.objective_text,
            payload.notes,
            _dump_json(definition) if definition is not None else None,
            _definition_hash(definition),
            payload.dependency_fingerprint,
            utc_now(),
        ),
    )
    return model_id


def _create_scenario_revision(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    scenario_id: str,
    payload: ScenarioRevisionCreate,
) -> dict[str, Any]:
    latest = conn.execute(
        """
        SELECT id, revision_no FROM scenario_revision
        WHERE scenario_id = ? AND version_state != 'invalidated'
        ORDER BY revision_no DESC
        LIMIT 1
        """,
        (scenario_id,),
    ).fetchone()
    max_revision = conn.execute(
        "SELECT MAX(revision_no) AS revision_no FROM scenario_revision WHERE scenario_id = ?",
        (scenario_id,),
    ).fetchone()["revision_no"]
    revision_no = 1 if max_revision is None else max_revision + 1
    parent_id = None if latest is None else latest["id"]
    expected_parent = payload.expected_parent_revision_id
    if latest is None:
        if expected_parent is not None:
            raise ConflictError("scenario has no parent revision; expected_parent_revision_id must be null")
    elif expected_parent is not None and expected_parent != latest["id"]:
        raise ConflictError("scenario revision parent is stale; reload the latest revision")
    based_on = payload.based_on_understanding_id
    if based_on is None:
        project = _require_project(conn, project_id)
        based_on = project["latest_understanding_revision_id"]
    elif conn.execute(
        "SELECT id FROM understanding_revision WHERE id = ? AND project_id = ?",
        (based_on, project_id),
    ).fetchone() is None:
        raise NotFoundError("understanding revision not found")

    revision_id = _new_id()
    model_id = _insert_formal_model(
        conn,
        project_id=project_id,
        scenario_revision_id=revision_id,
        payload=payload.formal_model,
    )
    conn.execute(
        """
        INSERT INTO scenario_revision (
            id, scenario_id, project_id, revision_no, parent_revision_id,
            version_state, based_on_understanding_id, formal_model_id,
            notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            revision_id,
            scenario_id,
            project_id,
            revision_no,
            parent_id,
            payload.version_state,
            based_on,
            model_id,
            payload.notes,
            utc_now(),
        ),
    )
    _insert_rules(
        conn,
        project_id=project_id,
        owner_kind="scenario",
        understanding_revision_id=None,
        scenario_revision_id=revision_id,
        rules=payload.rules,
    )
    if payload.version_state != "invalidated":
        conn.execute(
            """
            UPDATE analysis_project
            SET latest_scenario_id = ?,
                latest_scenario_revision_id = ?,
                latest_formal_model_id = COALESCE(?, latest_formal_model_id),
                updated_at = ?
            WHERE id = ?
            """,
            (scenario_id, revision_id, model_id, utc_now(), project_id),
        )
    _event(
        conn,
        project_id=project_id,
        event_type="scenario.revision_created",
        entity_kind="scenario_revision",
        entity_id=revision_id,
        summary=f"Created scenario revision v{revision_no}",
        payload={
            "scenario_id": scenario_id,
            "revision_no": revision_no,
            "parent_revision_id": parent_id,
            "version_state": payload.version_state,
            "formal_model_id": model_id,
        },
    )
    row = conn.execute(
        "SELECT * FROM scenario_revision WHERE id = ?", (revision_id,)
    ).fetchone()
    return _scenario_revision_from_row(conn, row, include_body=True)


def _baseline_rule(item: dict[str, Any], *, rule_kind: str) -> RuleIn:
    refs = item.get("evidence_refs") or []
    ref = refs[0] if refs and isinstance(refs[0], dict) else {}
    statement = item.get("effective_statement") or item.get("proposed_interpretation") or item.get("original_statement") or item.get("name") or ""
    return RuleIn(
        rule_kind=rule_kind,
        statement=str(statement),
        review_status="accepted",
        evidence_status="present" if refs else "unknown",
        source_span_id=ref.get("source_span_id"),
        condition_kind="if_then" if item.get("condition") else "always",
        premise_text=item.get("condition"),
        cost=item.get("weight"),
        capacity=None,
        permission=None,
    )


def _formal_from_handoff(
    handoff: dict[str, Any],
    *,
    name: str,
    dependency_fingerprint: str,
    understanding_revision_id: str | None = None,
) -> tuple[FormalModelIn, list[RuleIn]]:
    variables = []
    for item in handoff.get("decision_variables") or []:
        key = str(item.get("claim_key") or item.get("name") or f"variable-{len(variables) + 1}")
        variables.append(
            {
                "key": key,
                "name": str(item.get("name") or item.get("effective_statement") or key),
                "domain": item.get("domain"),
                "unit": item.get("unit"),
                "source_claim_key": item.get("claim_key"),
            }
        )
    parameters = []
    for item in handoff.get("parameters") or []:
        key = str(item.get("claim_key") or item.get("name") or f"parameter-{len(parameters) + 1}")
        parameters.append(
            {
                "key": key,
                "name": str(item.get("name") or key),
                "value": item.get("normalized_value") if item.get("normalized_value") is not None else item.get("raw_value"),
                "unit": item.get("unit"),
                "source_claim_key": item.get("claim_key"),
            }
        )
    constraints = []
    rules: list[RuleIn] = []
    for item in handoff.get("constraints") or []:
        key = str(item.get("claim_key") or f"constraint-{len(constraints) + 1}")
        constraints.append(
            {
                "key": key,
                "expression": str(item.get("effective_statement") or item.get("proposed_interpretation") or item.get("original_statement") or ""),
                "strength": item.get("strength") or "hard",
                "enabled": True,
                "source_claim_key": item.get("claim_key"),
                "binding": item.get("binding"),
            }
        )
        rules.append(_baseline_rule(item, rule_kind=item.get("strength") or "hard"))
    objectives = []
    for item in handoff.get("objectives") or []:
        key = str(item.get("claim_key") or f"objective-{len(objectives) + 1}")
        raw_priority = item.get("priority")
        priority: int | None = None
        if isinstance(raw_priority, int) and raw_priority >= 1:
            priority = raw_priority
        elif isinstance(raw_priority, str) and raw_priority.strip().isdigit() and int(raw_priority.strip()) >= 1:
            priority = int(raw_priority.strip())
        objectives.append(
            {
                "key": key,
                "expression": str(item.get("effective_statement") or item.get("proposed_interpretation") or item.get("original_statement") or ""),
                "direction": item.get("direction") if item.get("direction") in {"minimize", "maximize"} else "unknown",
                "priority": priority,
                "weight": item.get("weight"),
                "source_claim_key": item.get("claim_key"),
                "binding": item.get("binding"),
            }
        )
        rules.append(_baseline_rule(item, rule_kind="objective"))
    # Preserve a typed schedule payload only when the confirmed baseline
    # explicitly contains one.  Generic claims must remain generic until a
    # user supplies the missing schedule entities; inventing sessions, rooms,
    # or availability here would make the first solver run untrustworthy.
    typed_schedule = handoff.get("training_schedule")
    source_claims: dict[str, list[dict[str, Any]]] = {}
    for collection in ("entities", "parameters", "decision_variables", "constraints", "objectives", "assumptions", "unknowns", "conflicts"):
        for item in handoff.get(collection) or []:
            if not isinstance(item, dict) or not item.get("claim_key"):
                continue
            refs = item.get("evidence_refs") or []
            if isinstance(refs, list):
                source_claims[str(item["claim_key"])] = refs
    definition = {
        "schema_version": 1,
        "family": "training_schedule" if isinstance(typed_schedule, dict) else "generic",
        "variables": variables,
        "parameters": parameters,
        "constraints": constraints,
        "objectives": objectives,
        "source_claims": source_claims,
    }
    if isinstance(typed_schedule, dict):
        definition["training_schedule"] = typed_schedule
    formal = FormalModelIn(
        name=name,
        version_state="draft",
        variable_count=len(variables),
        constraint_count=len(constraints),
        objective_text="; ".join(item["expression"] for item in objectives) or None,
        notes="Derived from a confirmed pre-solver baseline. Human formalization is still required before solving.",
        definition=definition,
        understanding_revision_id=understanding_revision_id,
        dependency_fingerprint=dependency_fingerprint,
    )
    return formal, rules


def create_scenario_from_baseline(
    project_id: str,
    baseline_id: str,
    payload: ScenarioFromBaselineCreate,
) -> dict[str, Any]:
    conn = connect()
    try:
        with conn:
            project = _require_project(conn, project_id)
            baseline = conn.execute(
                "SELECT * FROM modeling_baseline WHERE id = ? AND project_id = ?",
                (baseline_id, project_id),
            ).fetchone()
            if baseline is None:
                raise NotFoundError("baseline not found")
            if payload.expected_baseline_id is not None and payload.expected_baseline_id != baseline_id:
                raise ConflictError("baseline binding is stale")
            if baseline["scenario_revision_id"] is not None:
                raise ConflictError("baseline is already bound to a scenario")
            handoff = _load_json(baseline["export_json"], {})
            fingerprint = hashlib.sha256(
                json.dumps(handoff, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            formal, rules = _formal_from_handoff(
                handoff,
                name=f"{payload.name} model",
                dependency_fingerprint=fingerprint,
                understanding_revision_id=baseline["understanding_revision_id"],
            )
            scenario_id = _new_id()
            conn.execute(
                "INSERT INTO scenario (id, project_id, name, created_at) VALUES (?, ?, ?, ?)",
                (scenario_id, project_id, payload.name, utc_now()),
            )
            revision = _create_scenario_revision(
                conn,
                project_id=project_id,
                scenario_id=scenario_id,
                payload=ScenarioRevisionCreate(
                    notes=payload.notes,
                    version_state="draft",
                    based_on_understanding_id=baseline["understanding_revision_id"],
                    formal_model=formal,
                    rules=rules,
                    expected_parent_revision_id=None,
                ),
            )
            cursor = conn.execute(
                """
                UPDATE modeling_baseline
                SET scenario_id = ?, scenario_revision_id = ?
                WHERE id = ? AND scenario_revision_id IS NULL
                """,
                (scenario_id, revision["id"], baseline_id),
            )
            if cursor.rowcount != 1:
                raise ConflictError("baseline was bound concurrently")
            _event(
                conn,
                project_id=project_id,
                event_type="baseline.bound_to_scenario",
                entity_kind="modeling_baseline",
                entity_id=baseline_id,
                summary="Bound confirmed baseline to a Stage 2 scenario",
                payload={"scenario_id": scenario_id, "scenario_revision_id": revision["id"], "definition_hash": revision.get("formal_model", {}).get("definition_hash")},
            )
            return get_scenario_with_conn(conn, scenario_id)
    finally:
        conn.close()


def create_scenario(project_id: str, payload: ScenarioCreate) -> dict[str, Any]:
    conn = connect()
    try:
        with conn:
            _require_project(conn, project_id)
            scenario_id = _new_id()
            conn.execute(
                """
                INSERT INTO scenario (id, project_id, name, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (scenario_id, project_id, payload.name, utc_now()),
            )
            _event(
                conn,
                project_id=project_id,
                event_type="scenario.created",
                entity_kind="scenario",
                entity_id=scenario_id,
                summary=f"Created scenario '{payload.name}'",
            )
            revision_payload = ScenarioRevisionCreate(
                notes=payload.notes,
                version_state=payload.version_state,
                based_on_understanding_id=payload.based_on_understanding_id,
                formal_model=payload.formal_model,
                rules=payload.rules,
            )
            _create_scenario_revision(
                conn,
                project_id=project_id,
                scenario_id=scenario_id,
                payload=revision_payload,
            )
            return get_scenario_with_conn(conn, scenario_id)
    finally:
        conn.close()


def get_scenario_with_conn(conn: sqlite3.Connection, scenario_id: str) -> dict[str, Any]:
    scenario = conn.execute(
        "SELECT * FROM scenario WHERE id = ?", (scenario_id,)
    ).fetchone()
    if scenario is None:
        raise NotFoundError("scenario not found")
    revisions = conn.execute(
        """
        SELECT * FROM scenario_revision
        WHERE scenario_id = ?
        ORDER BY revision_no
        """,
        (scenario_id,),
    ).fetchall()
    return {
        "id": scenario["id"],
        "project_id": scenario["project_id"],
        "name": scenario["name"],
        "created_at": scenario["created_at"],
        "revisions": [
            _scenario_revision_from_row(conn, row, include_body=True)
            for row in revisions
        ],
    }


def get_scenario(scenario_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        return get_scenario_with_conn(conn, scenario_id)
    finally:
        conn.close()


def list_scenarios(project_id: str) -> list[dict[str, Any]]:
    conn = connect()
    try:
        _require_project(conn, project_id)
        rows = conn.execute(
            """
            SELECT id FROM scenario
            WHERE project_id = ?
            ORDER BY created_at, id
            """,
            (project_id,),
        ).fetchall()
        return [get_scenario_with_conn(conn, row["id"]) for row in rows]
    finally:
        conn.close()


def create_scenario_revision(
    scenario_id: str, payload: ScenarioRevisionCreate
) -> dict[str, Any]:
    conn = connect()
    try:
        with conn:
            scenario = conn.execute(
                "SELECT * FROM scenario WHERE id = ?", (scenario_id,)
            ).fetchone()
            if scenario is None:
                raise NotFoundError("scenario not found")
            return _create_scenario_revision(
                conn,
                project_id=scenario["project_id"],
                scenario_id=scenario_id,
                payload=payload,
            )
    finally:
        conn.close()


def _formal_definition_for_revision(
    conn: sqlite3.Connection, revision: sqlite3.Row
) -> dict[str, Any]:
    if not revision["formal_model_id"]:
        raise ConflictError("scenario revision has no formal model")
    model = conn.execute(
        "SELECT * FROM formal_model WHERE id = ?", (revision["formal_model_id"],)
    ).fetchone()
    definition = None if model is None else _load_json(model["definition_json"], None)
    if not definition:
        raise ConflictError("scenario revision formal model has no structured definition")
    return definition


def _apply_formal_element_changes(
    definition: dict[str, Any], changes: list[FormalElementChange]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply explicit key-based edits without evaluating or inventing rules."""
    result = json.loads(json.dumps(definition, ensure_ascii=False))
    changed: list[dict[str, Any]] = []
    for change in changes:
        collection = change.collection
        nested_collection = None
        nested_key = None
        if collection == "portfolio":
            if change.key != "portfolio":
                raise ConflictError("portfolio changes must use key 'portfolio'")
            before = result.get("portfolio")
            if change.operation == "remove":
                after = None
            else:
                if change.value is None:
                    raise ConflictError("upsert requires a portfolio value")
                after = dict(change.value)
            result["portfolio"] = after
            changed.append(
                {
                    "collection": collection,
                    "key": change.key,
                    "operation": change.operation,
                    "before": before,
                    "after": after,
                }
            )
            continue
        if collection == "training_schedule":
            if "." not in change.key:
                raise ConflictError(
                    "training_schedule changes must use '<resource>.<key>'"
                )
            nested_collection, nested_key = change.key.split(".", 1)
            if nested_collection not in {"sessions", "time_slots", "rooms", "instructors"}:
                raise ConflictError(f"unknown training_schedule resource: {nested_collection}")
            schedule = result.get("training_schedule")
            if not isinstance(schedule, dict):
                raise ConflictError("formal model has no training_schedule definition")
            items = list(schedule.get(nested_collection) or [])
        else:
            items = list(result.get(collection) or [])
            nested_key = change.key
        before = next((item for item in items if item.get("key") == nested_key), None)
        if change.operation == "remove":
            if before is None:
                raise ConflictError(f"cannot remove missing formal element: {collection}.{change.key}")
            items = [item for item in items if item.get("key") != nested_key]
            after = None
        else:
            if change.value is None:
                raise ConflictError(f"upsert requires a value for {collection}.{change.key}")
            # Resource edits are partial by design (for example, changing only
            # room capacity must preserve its name and availability). Merge an
            # existing element before validating the typed formal definition.
            after = {**before, **dict(change.value)} if isinstance(before, dict) else dict(change.value)
            after["key"] = nested_key
            replaced = False
            for index, item in enumerate(items):
                if item.get("key") == nested_key:
                    items[index] = after
                    replaced = True
                    break
            if not replaced:
                items.append(after)
        if collection == "training_schedule":
            result["training_schedule"][nested_collection] = items
        else:
            result[collection] = items
        changed.append(
            {
                "collection": collection,
                "key": change.key,
                "operation": change.operation,
                "before": before,
                "after": after,
            }
        )
    return result, changed


def _formal_definition_diff(
    left: dict[str, Any] | None, right: dict[str, Any] | None
) -> list[dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    for collection in ("variables", "parameters", "constraints", "objectives"):
        left_items = {item.get("key"): item for item in (left or {}).get(collection) or []}
        right_items = {item.get("key"): item for item in (right or {}).get(collection) or []}
        for key in sorted(set(left_items) | set(right_items)):
            before = left_items.get(key)
            after = right_items.get(key)
            if before != after:
                changed.append(
                    {
                        "collection": collection,
                        "key": key,
                        "status": "added" if before is None else "removed" if after is None else "changed",
                        "before": before,
                        "after": after,
                    }
                )
    left_schedule = (left or {}).get("training_schedule") or {}
    right_schedule = (right or {}).get("training_schedule") or {}
    for nested_collection in ("sessions", "time_slots", "rooms", "instructors"):
        left_items = {
            item.get("key"): item for item in left_schedule.get(nested_collection) or []
        }
        right_items = {
            item.get("key"): item for item in right_schedule.get(nested_collection) or []
        }
        for key in sorted(set(left_items) | set(right_items)):
            before = left_items.get(key)
            after = right_items.get(key)
            if before != after:
                changed.append(
                    {
                        "collection": "training_schedule",
                        "key": f"{nested_collection}.{key}",
                        "status": "added" if before is None else "removed" if after is None else "changed",
                        "before": before,
                        "after": after,
                    }
                )
    if (left or {}).get("portfolio") != (right or {}).get("portfolio"):
        left_portfolio = (left or {}).get("portfolio")
        right_portfolio = (right or {}).get("portfolio")
        changed.append(
            {
                "collection": "portfolio",
                "key": "portfolio",
                "status": "added" if left_portfolio is None else "removed" if right_portfolio is None else "changed",
                "before": left_portfolio,
                "after": right_portfolio,
            }
        )
    return changed


def _copy_revision_rules(conn: sqlite3.Connection, revision_id: str) -> list[RuleIn]:
    return [
        RuleIn(
            rule_kind=row["rule_kind"],
            statement=row["statement"],
            review_status=row["review_status"],
            evidence_status=row["evidence_status"],
            source_span_id=row["source_span_id"],
            condition_kind=row["condition_kind"],
            premise_status=row["premise_status"],
            premise_text=row["premise_text"],
            cost=row["cost"],
            capacity=row["capacity"],
            permission=_sql_to_bool(row["permission"]),
        )
        for row in conn.execute(
            "SELECT * FROM rule WHERE scenario_revision_id = ? ORDER BY created_at, id",
            (revision_id,),
        ).fetchall()
    ]


def preview_scenario_impact(
    scenario_id: str, payload: ScenarioImpactPreviewCreate
) -> dict[str, Any]:
    conn = connect()
    try:
        scenario = conn.execute("SELECT * FROM scenario WHERE id = ?", (scenario_id,)).fetchone()
        if scenario is None:
            raise NotFoundError("scenario not found")
        revision = conn.execute(
            "SELECT * FROM scenario_revision WHERE id = ? AND scenario_id = ?",
            (payload.base_revision_id, scenario_id),
        ).fetchone()
        if revision is None:
            raise NotFoundError("base scenario revision not found")
        definition = _formal_definition_for_revision(conn, revision)
        proposed, changed = _apply_formal_element_changes(definition, payload.changes)
        validation = _formal_model_validation(proposed)
        claim_keys = sorted(
            {
                str(item.get("source_claim_key"))
                for diff in changed
                for item in (diff.get("before"), diff.get("after"))
                if isinstance(item, dict) and item.get("source_claim_key")
            }
        )
        solver_ready = False
        if proposed.get("family") == "training_schedule":
            # Probe the real deterministic compiler without persisting a run or
            # presenting its result as a user-visible solve.
            probe = solve_training_schedule(proposed, max_candidates=1)
            validation["solver_compilation"] = probe.get("state")
            validation["solver_message"] = probe.get("message")
            solver_ready = probe.get("state") != "model_invalid"
        else:
            validation["solver_compilation"] = "unsupported_family"
        return {
            "scenario_id": scenario_id,
            "base_revision_id": revision["id"],
            "base_revision_no": revision["revision_no"],
            "changed_elements": changed,
            "affected_claim_keys": claim_keys,
            "invalidation_required": bool(changed),
            "solver_ready_after_change": solver_ready,
            "validation": validation,
        }
    finally:
        conn.close()


def create_what_if_scenario(
    scenario_id: str, payload: WhatIfScenarioCreate
) -> dict[str, Any]:
    conn = connect()
    try:
        with conn:
            scenario = conn.execute("SELECT * FROM scenario WHERE id = ?", (scenario_id,)).fetchone()
            if scenario is None:
                raise NotFoundError("scenario not found")
            parent = conn.execute(
                "SELECT * FROM scenario_revision WHERE id = ? AND scenario_id = ?",
                (payload.expected_parent_revision_id, scenario_id),
            ).fetchone()
            if parent is None:
                raise NotFoundError("parent scenario revision not found")
            definition = _formal_definition_for_revision(conn, parent)
            proposed, changed = _apply_formal_element_changes(definition, payload.changes)
            # Pydantic validation is the contract gate; no solver result is produced here.
            formal = FormalModelIn(
                name=f"{payload.name} model",
                version_state="draft",
                variable_count=len(proposed.get("variables") or []),
                constraint_count=len(proposed.get("constraints") or []),
                objective_text="; ".join(item.get("expression", "") for item in proposed.get("objectives") or []) or None,
                notes="What-if revision; solver must be rerun against this snapshot.",
                definition=proposed,
                understanding_revision_id=parent["based_on_understanding_id"],
                dependency_fingerprint=hashlib.sha256(
                    json.dumps(
                        {"parent": parent["formal_model_id"], "changes": changed},
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
            )
            revision = _create_scenario_revision(
                conn,
                project_id=scenario["project_id"],
                scenario_id=scenario_id,
                payload=ScenarioRevisionCreate(
                    notes=payload.notes,
                    version_state="draft",
                    based_on_understanding_id=parent["based_on_understanding_id"],
                    formal_model=formal,
                    rules=_copy_revision_rules(conn, parent["id"]),
                    expected_parent_revision_id=payload.expected_parent_revision_id,
                ),
            )
            _event(
                conn,
                project_id=scenario["project_id"],
                event_type="scenario.what_if_created",
                entity_kind="scenario_revision",
                entity_id=revision["id"],
                summary="Created a what-if scenario revision; solver rerun required",
                payload={"parent_revision_id": parent["id"], "changed_elements": changed},
            )
            return revision
    finally:
        conn.close()


def compare_scenario_revisions(
    scenario_id: str, left_revision_id: str, right_revision_id: str
) -> dict[str, Any]:
    conn = connect()
    try:
        scenario = conn.execute("SELECT * FROM scenario WHERE id = ?", (scenario_id,)).fetchone()
        if scenario is None:
            raise NotFoundError("scenario not found")
        revisions = conn.execute(
            "SELECT * FROM scenario_revision WHERE id IN (?, ?) AND scenario_id = ?",
            (left_revision_id, right_revision_id, scenario_id),
        ).fetchall()
        by_id = {row["id"]: row for row in revisions}
        if left_revision_id not in by_id or right_revision_id not in by_id:
            raise NotFoundError("scenario revision not found")
        left, right = by_id[left_revision_id], by_id[right_revision_id]
        left_def = _formal_definition_for_revision(conn, left)
        right_def = _formal_definition_for_revision(conn, right)
        left_rows = conn.execute(
            "SELECT * FROM rule WHERE scenario_revision_id = ? ORDER BY created_at, id",
            (left["id"],),
        ).fetchall()
        right_rows = conn.execute(
            "SELECT * FROM rule WHERE scenario_revision_id = ? ORDER BY created_at, id",
            (right["id"],),
        ).fetchall()
        rule_fields = ("rule_kind", "statement", "review_status", "evidence_status", "source_span_id")
        left_rules = {
            tuple(row[field] for field in rule_fields): row for row in left_rows
        }
        right_rules = {
            tuple(row[field] for field in rule_fields): row for row in right_rows
        }
        changed_rules = []
        for signature in sorted(set(left_rules) | set(right_rules)):
            before = left_rules.get(signature)
            after = right_rules.get(signature)
            if before is None or after is None:
                changed_rules.append(
                    {
                        "rule_id": None if after is None else after["id"],
                        "before": None if before is None else {key: before[key] for key in rule_fields},
                        "after": None if after is None else {key: after[key] for key in rule_fields},
                    }
                )
        runs = []
        for revision_id in (left_revision_id, right_revision_id):
            for row in conn.execute("SELECT * FROM solve_run WHERE scenario_revision_id = ? ORDER BY created_at, id", (revision_id,)).fetchall():
                runs.append(_solve_run_from_row(conn, row, include_candidates=True))
        return {
            "scenario_id": scenario_id,
            "left_revision_id": left_revision_id,
            "right_revision_id": right_revision_id,
            "left_revision_no": left["revision_no"],
            "right_revision_no": right["revision_no"],
            "changed_elements": _formal_definition_diff(left_def, right_def),
            "changed_rules": changed_rules,
            "solve_runs": runs,
        }
    finally:
        conn.close()


def invalidate_scenario_revision(
    revision_id: str,
    *,
    reason: str,
    expected_version_state: str = "draft",
) -> dict[str, Any]:
    conn = connect()
    try:
        with conn:
            row = conn.execute(
                "SELECT * FROM scenario_revision WHERE id = ?", (revision_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError("scenario revision not found")
            if row["version_state"] != expected_version_state:
                raise ConflictError("scenario revision state is stale; reload before invalidating")
            now = utc_now()
            cursor = conn.execute(
                """
                UPDATE scenario_revision
                SET version_state = 'invalidated', invalidation_reason = ?, invalidated_at = ?
                WHERE id = ? AND version_state = ?
                """,
                (reason, now, revision_id, expected_version_state),
            )
            if cursor.rowcount != 1:
                raise ConflictError("scenario revision changed while invalidating")
            if row["formal_model_id"]:
                conn.execute(
                    "UPDATE formal_model SET version_state = 'invalidated' WHERE id = ? AND version_state != 'invalidated'",
                    (row["formal_model_id"],),
                )
            project = conn.execute(
                "SELECT latest_scenario_revision_id, latest_formal_model_id FROM analysis_project WHERE id = ?",
                (row["project_id"],),
            ).fetchone()
            if project is not None and project["latest_scenario_revision_id"] == revision_id:
                parent = row["parent_revision_id"]
                parent_model = None
                if parent:
                    parent_model = conn.execute(
                        "SELECT formal_model_id FROM scenario_revision WHERE id = ?", (parent,)
                    ).fetchone()
                conn.execute(
                    """
                    UPDATE analysis_project
                    SET latest_scenario_revision_id = ?, latest_formal_model_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (parent, None if parent_model is None else parent_model["formal_model_id"], now, row["project_id"]),
                )
            _event(
                conn,
                project_id=row["project_id"],
                event_type="scenario.revision_invalidated",
                entity_kind="scenario_revision",
                entity_id=revision_id,
                summary="Invalidated a scenario revision",
                payload={"reason": reason, "previous_version_state": expected_version_state},
            )
        return get_scenario_revision(revision_id)
    finally:
        conn.close()


def get_scenario_revision(revision_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM scenario_revision WHERE id = ?", (revision_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("scenario revision not found")
        return _scenario_revision_from_row(conn, row, include_body=True)
    finally:
        conn.close()


def _solve_input_fingerprint(
    conn: sqlite3.Connection,
    project_id: str,
    revision_id: str,
    formal_model_id: str | None,
) -> str:
    revision = conn.execute(
        "SELECT id, project_id, revision_no, version_state, formal_model_id FROM scenario_revision WHERE id = ? AND project_id = ?",
        (revision_id, project_id),
    ).fetchone()
    if revision is None:
        raise NotFoundError("scenario revision not found")
    model_hash = None
    if formal_model_id:
        model = conn.execute(
            "SELECT id, project_id, definition_hash, definition_json, version_state FROM formal_model WHERE id = ? AND project_id = ?",
            (formal_model_id, project_id),
        ).fetchone()
        if model is None:
            raise NotFoundError("formal model not found")
        model_hash = model["definition_hash"] or hashlib.sha256(
            (model["definition_json"] or "").encode("utf-8")
        ).hexdigest()
    payload = {
        "project_id": project_id,
        "revision_id": revision["id"],
        "revision_no": revision["revision_no"],
        "version_state": revision["version_state"],
        "formal_model_id": formal_model_id,
        "formal_model_hash": model_hash,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def create_solve_run(project_id: str, payload: SolveRunCreate) -> dict[str, Any]:
    conn = connect()
    try:
        with conn:
            _require_project(conn, project_id)
            revision = conn.execute(
                """
                SELECT id, formal_model_id, version_state FROM scenario_revision
                WHERE id = ? AND project_id = ?
                """,
                (payload.scenario_revision_id, project_id),
            ).fetchone()
            if revision is None:
                raise NotFoundError("scenario revision not found")
            if revision["version_state"] == "invalidated":
                raise ConflictError("cannot create a solve run for an invalidated scenario revision")
            formal_model_id = payload.formal_model_id or revision["formal_model_id"]
            if formal_model_id is not None and formal_model_id != revision["formal_model_id"]:
                raise ConflictError("formal model does not belong to scenario revision")
            if formal_model_id is not None:
                model = conn.execute(
                    "SELECT id FROM formal_model WHERE id = ? AND project_id = ?",
                    (formal_model_id, project_id),
                ).fetchone()
                if model is None:
                    raise NotFoundError("formal model not found")
            input_fingerprint = _solve_input_fingerprint(
                conn, project_id, payload.scenario_revision_id, formal_model_id
            )
            run_id = _new_id()
            message = payload.message or (
                "SolveRun metadata recorded without executing a solver."
            )
            conn.execute(
                """
                INSERT INTO solve_run (
                    id, project_id, scenario_revision_id, formal_model_id,
                    run_state, claimed_execution, execution, solver_name,
                    started_at, finished_at, message, created_at, input_fingerprint,
                    claim_owner, claim_token, heartbeat_at, stale_at, resume_count
                ) VALUES (?, ?, ?, ?, ?, 0, 'not_executed', NULL, NULL, NULL, ?, ?, ?, NULL, NULL, NULL, NULL, 0)
                """,
                (
                    run_id,
                    project_id,
                    payload.scenario_revision_id,
                    formal_model_id,
                    payload.run_state,
                    message,
                    utc_now(),
                    input_fingerprint,
                ),
            )
            if payload.candidate is not None:
                _insert_candidate(conn, project_id, run_id, payload.candidate)
            conn.execute(
                """
                UPDATE analysis_project
                SET latest_solve_run_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (run_id, utc_now(), project_id),
            )
            _event(
                conn,
                project_id=project_id,
                event_type="solve_run.created",
                entity_kind="solve_run",
                entity_id=run_id,
                summary=(
                    f"Recorded SolveRun state '{payload.run_state}' "
                    "without executing a solver"
                ),
                payload={
                    "run_state": payload.run_state,
                    "claimed_execution": False,
                    "execution": "not_executed",
                },
            )
            row = conn.execute(
                "SELECT * FROM solve_run WHERE id = ?", (run_id,)
            ).fetchone()
            return _solve_run_from_row(conn, row, include_candidates=True)
    finally:
        conn.close()


def _prepare_solver_execution(
    project_id: str,
    *,
    scenario_revision_id: str,
    formal_model_id: str | None,
    owner_prefix: str,
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    """Snapshot and claim a solver run before executing outside SQLite."""
    conn = connect()
    try:
        _require_project(conn, project_id)
        revision = conn.execute(
            "SELECT * FROM scenario_revision WHERE id = ? AND project_id = ?",
            (scenario_revision_id, project_id),
        ).fetchone()
        if revision is None:
            raise NotFoundError("scenario revision not found")
        if revision["version_state"] == "invalidated":
            raise ConflictError("cannot solve an invalidated scenario revision")
        model_id = formal_model_id or revision["formal_model_id"]
        if not model_id:
            raise ConflictError("scenario revision has no formal model")
        if revision["formal_model_id"] != model_id:
            raise ConflictError("formal model does not belong to scenario revision")
        model_row = conn.execute(
            "SELECT * FROM formal_model WHERE id = ? AND project_id = ?",
            (model_id, project_id),
        ).fetchone()
        if model_row is None:
            raise NotFoundError("formal model not found")
        model = _formal_model_from_row(model_row)
        if model is None:
            raise NotFoundError("formal model not found")
    finally:
        conn.close()
    run = create_solve_run(
        project_id,
        SolveRunCreate(
            scenario_revision_id=scenario_revision_id,
            formal_model_id=model_id,
            run_state="pending",
            message="Solver input snapshot created; execution lease pending.",
        ),
    )
    owner = f"{owner_prefix}:{run['id']}"
    claimed = claim_solve_run(
        run["id"], owner=owner, stale_after_seconds=120, project_id=project_id
    )
    return claimed, model, model_id, owner


def _solver_candidates(
    result: dict[str, Any],
    *,
    family: str,
    model: dict[str, Any],
) -> list[ResultCandidateIn]:
    provenance = {
        "definition_hash": model.get("definition_hash"),
        "source_claims": (model.get("definition") or {}).get("source_claims") or {},
        "constraint_source_claims": [
            item.get("source_claim_key")
            for item in (model.get("definition") or {}).get("constraints", [])
            if item.get("source_claim_key")
        ],
        "objective_source_claims": [
            item.get("source_claim_key")
            for item in (model.get("definition") or {}).get("objectives", [])
            if item.get("source_claim_key")
        ],
    }
    raw_candidates = result.get("candidates") or []
    if not raw_candidates:
        raw_candidates = [
            {
                "assignments": result.get("assignments", []),
                "objective_value": result.get("objective_value"),
                "objective_breakdown": result.get("objective_breakdown", {}),
            }
        ]
    candidates: list[ResultCandidateIn] = []
    for index, candidate in enumerate(raw_candidates):
        objective = candidate.get("objective_value")
        if objective is None:
            objective = candidate.get("value")
        label = (
            f"portfolio-{index + 1}"
            if family == "portfolio"
            else ("best-schedule" if index == 0 and result.get("state") == "optimal" else f"candidate-{index + 1}")
        )
        candidates.append(
            ResultCandidateIn(
                label=label,
                objective_value=objective,
                is_selected=index == 0 and result.get("state") == "optimal",
                notes=result.get("message"),
                details={**result, **candidate, "formal_model_id": model["id"]},
                result=candidate,
                explanation=result.get("explanation"),
                provenance=provenance,
            )
        )
    return candidates


def _finish_solver_execution(
    project_id: str,
    *,
    run_id: str,
    owner: str,
    claim_token: str,
    result: dict[str, Any],
    model: dict[str, Any],
    family: str,
) -> dict[str, Any]:
    completed = complete_solve_run(
        run_id,
        owner=owner,
        claim_token=claim_token,
        run_state=result.get("state", "failed"),
        message=result.get("message"),
        solver_name=result.get("solver_name"),
        candidates=_solver_candidates(result, family=family, model=model),
        project_id=project_id,
    )
    conn = connect()
    try:
        with conn:
            now = utc_now()
            conn.execute(
                "UPDATE analysis_project SET latest_solve_run_id = ?, workflow_maturity = 'results', updated_at = ? WHERE id = ?",
                (run_id, now, project_id),
            )
            _event(
                conn,
                project_id=project_id,
                event_type="solve_run.executed",
                entity_kind="solve_run",
                entity_id=run_id,
                summary=f"Executed deterministic {family} solver ({result.get('state')})",
                payload={"run_state": result.get("state"), "solver_name": result.get("solver_name"), "scenario_revision_id": completed["scenario_revision_id"], "formal_model_id": completed["formal_model_id"]},
            )
    finally:
        conn.close()
    return get_solve_run(run_id, project_id=project_id)


def _run_solver_for_model(
    model: dict[str, Any],
    *,
    family: str,
    max_candidates: int,
    max_search_nodes: int = 100_000,
) -> dict[str, Any]:
    if family == "training_schedule":
        return solve_training_schedule(
            model.get("definition"),
            max_candidates=max_candidates,
            max_search_nodes=max_search_nodes,
        )
    if family == "portfolio":
        return solve_portfolio(model.get("definition"), max_candidates=max_candidates)
    return {"state": "model_invalid", "solver_name": "lucid.dispatch.v1", "message": f"unsupported solver family: {family}", "explanation": {"issues": [f"unsupported solver family: {family}"]}}


def execute_training_schedule(
    project_id: str, payload: TrainingScheduleSolveCreate
) -> dict[str, Any]:
    claimed, model, _model_id, owner = _prepare_solver_execution(
        project_id,
        scenario_revision_id=payload.scenario_revision_id,
        formal_model_id=payload.formal_model_id,
        owner_prefix="training",
    )
    try:
        result = _run_solver_for_model(
            model,
            family="training_schedule",
            max_candidates=payload.max_candidates,
            max_search_nodes=payload.max_search_nodes,
        )
    except Exception as exc:  # Persist a recoverable failed run rather than losing history.
        result = {"state": "failed", "solver_name": "lucid.training_backtracking.v1", "message": str(exc), "explanation": {"issues": [str(exc)]}}
    return _finish_solver_execution(
        project_id,
        run_id=claimed["id"], owner=owner, claim_token=claimed["claim_token"],
        result=result, model=model, family="training_schedule",
    )


def execute_portfolio(
    project_id: str, payload: PortfolioSolveCreate
) -> dict[str, Any]:
    claimed, model, _model_id, owner = _prepare_solver_execution(
        project_id,
        scenario_revision_id=payload.scenario_revision_id,
        formal_model_id=payload.formal_model_id,
        owner_prefix="portfolio",
    )
    try:
        result = _run_solver_for_model(model, family="portfolio", max_candidates=payload.max_candidates)
    except Exception as exc:
        result = {"state": "failed", "solver_name": "lucid.portfolio.v1", "message": str(exc), "explanation": {"issues": [str(exc)]}}
    return _finish_solver_execution(
        project_id,
        run_id=claimed["id"], owner=owner, claim_token=claimed["claim_token"],
        result=result, model=model, family="portfolio",
    )


def resume_solve_run(
    project_id: str,
    run_id: str,
    *,
    owner: str,
    stale_after_seconds: int = 120,
) -> dict[str, Any]:
    """Reclaim and rerun a pending/stale deterministic solver snapshot."""
    run = get_solve_run(run_id, project_id=project_id)
    if run["run_state"] in {"feasible", "optimal", "infeasible", "unknown", "model_invalid", "failed", "cancelled"}:
        raise ConflictError("solve run is already terminal")
    conn = connect()
    try:
        revision = conn.execute(
            "SELECT version_state, formal_model_id FROM scenario_revision WHERE id = ? AND project_id = ?",
            (run["scenario_revision_id"], project_id),
        ).fetchone()
        if revision is None:
            raise NotFoundError("scenario revision not found")
        if revision["version_state"] == "invalidated":
            raise ConflictError("cannot resume a run for an invalidated scenario revision")
        current_fingerprint = _solve_input_fingerprint(
            conn, project_id, run["scenario_revision_id"], run["formal_model_id"]
        )
        if run.get("input_fingerprint") and current_fingerprint != run["input_fingerprint"]:
            raise ConflictError("solver input fingerprint is stale; create a new solve run")
    finally:
        conn.close()
    claimed = claim_solve_run(
        run_id, owner=owner, stale_after_seconds=stale_after_seconds, project_id=project_id
    )
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM formal_model WHERE id = ? AND project_id = ?",
            (claimed["formal_model_id"], project_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("formal model not found")
        model = _formal_model_from_row(row)
        family = ((model or {}).get("definition") or {}).get("family")
        if family not in {"training_schedule", "portfolio"}:
            raise ConflictError("solve run does not reference a resumable solver family")
    finally:
        conn.close()
    try:
        result = _run_solver_for_model(model, family=family, max_candidates=3 if family == "training_schedule" else 5)
    except Exception as exc:
        result = {"state": "failed", "solver_name": f"lucid.{family}.v1", "message": str(exc), "explanation": {"issues": [str(exc)]}}
    return _finish_solver_execution(
        project_id, run_id=run_id, owner=owner, claim_token=claimed["claim_token"],
        result=result, model=model, family=family,
    )


def _insert_candidate(
    conn: sqlite3.Connection,
    project_id: str,
    solve_run_id: str,
    payload: ResultCandidateIn,
) -> dict[str, Any]:
    candidate_id = _new_id()
    conn.execute(
        """
        INSERT INTO result_candidate (
            id, project_id, solve_run_id, label, objective_value,
            is_selected, notes, details_json, result_json, explanation_json,
            provenance_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate_id,
            project_id,
            solve_run_id,
            payload.label,
            payload.objective_value,
            _bool_to_sql(payload.is_selected),
            payload.notes,
            _dump_json(payload.details) if payload.details is not None else None,
            _dump_json(payload.result) if payload.result is not None else None,
            _dump_json(payload.explanation) if payload.explanation is not None else None,
            _dump_json(payload.provenance) if payload.provenance is not None else None,
            utc_now(),
        ),
    )
    row = conn.execute(
        "SELECT * FROM result_candidate WHERE id = ?", (candidate_id,)
    ).fetchone()
    return _candidate_from_row(row)


def _claim_is_stale(row: sqlite3.Row, stale_after_seconds: int) -> bool:
    heartbeat = row["heartbeat_at"] if "heartbeat_at" in row.keys() else None
    if not heartbeat:
        return bool(row["claim_owner"] if "claim_owner" in row.keys() else None)
    try:
        at = datetime.fromisoformat(heartbeat)
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - at > timedelta(seconds=stale_after_seconds)
    except ValueError:
        return True


def claim_solve_run(
    run_id: str,
    *,
    owner: str,
    stale_after_seconds: int = 120,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Atomically claim a pending run, or reclaim a stale worker lease."""
    conn = connect()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM solve_run WHERE id = ?", (run_id,)).fetchone()
            if row is None or (project_id is not None and row["project_id"] != project_id):
                raise NotFoundError("solve run not found")
            terminal = {"feasible", "optimal", "infeasible", "unknown", "model_invalid", "failed", "cancelled"}
            if row["run_state"] in terminal:
                raise ConflictError("solve run is already terminal")
            current_owner = row["claim_owner"] if "claim_owner" in row.keys() else None
            if current_owner and not _claim_is_stale(row, stale_after_seconds):
                raise ConflictError("solve run is claimed by another live worker")
            now = utc_now()
            # A new lease always receives a new token. Caller-supplied tokens
            # are deliberately not accepted, so a stale worker cannot revive
            # its old capability by replaying a request.
            token = _new_id()
            resumed = 1 if current_owner else 0
            old_heartbeat = row["heartbeat_at"] if "heartbeat_at" in row.keys() else None
            if current_owner:
                where_sql = "id = ? AND claim_owner = ? AND heartbeat_at IS ?"
                where_params: tuple[Any, ...] = (run_id, current_owner, old_heartbeat)
            else:
                where_sql = "id = ? AND claim_owner IS NULL"
                where_params = (run_id,)
            cursor = conn.execute(
                f"""
                UPDATE solve_run
                SET run_state = 'running', execution = 'claimed', claim_owner = ?,
                    claim_token = ?, heartbeat_at = ?, stale_at = NULL,
                    started_at = COALESCE(started_at, ?), resume_count = resume_count + ?,
                    lease_timeout_seconds = ?
                WHERE {where_sql}
                """,
                (owner, token, now, now, resumed, stale_after_seconds, *where_params),
            )
            if cursor.rowcount != 1:
                raise ConflictError("solve run changed while claiming")
            _event(
                conn,
                project_id=row["project_id"],
                event_type="solve_run.claimed",
                entity_kind="solve_run",
                entity_id=run_id,
                summary="Claimed solver execution lease",
                payload={"owner": owner, "resumed": bool(resumed), "input_fingerprint": row["input_fingerprint"] if "input_fingerprint" in row.keys() else None},
            )
            return _solve_run_from_row(conn, conn.execute("SELECT * FROM solve_run WHERE id = ?", (run_id,)).fetchone(), include_candidates=True)
    finally:
        conn.close()


def heartbeat_solve_run(
    run_id: str,
    *,
    owner: str,
    claim_token: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    conn = connect()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM solve_run WHERE id = ?", (run_id,)).fetchone()
            if row is None or (project_id is not None and row["project_id"] != project_id):
                raise NotFoundError("solve run not found")
            if not claim_token or row["claim_owner"] != owner or row["claim_token"] != claim_token:
                raise ConflictError("solver lease is not owned by this worker")
            if _claim_is_stale(row, int(row["lease_timeout_seconds"] or 120)):
                raise ConflictError("solver lease is stale; reclaim it before continuing")
            now = utc_now()
            cursor = conn.execute(
                "UPDATE solve_run SET heartbeat_at = ? WHERE id = ? AND claim_owner = ? AND claim_token = ?",
                (now, run_id, owner, claim_token),
            )
            if cursor.rowcount != 1:
                raise ConflictError("solver lease changed while heartbeating")
            return _solve_run_from_row(conn, conn.execute("SELECT * FROM solve_run WHERE id = ?", (run_id,)).fetchone(), include_candidates=True)
    finally:
        conn.close()


def complete_solve_run(
    run_id: str,
    *,
    owner: str,
    run_state: str,
    message: str | None = None,
    solver_name: str | None = None,
    candidates: list[ResultCandidateIn] | None = None,
    claim_token: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    conn = connect()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM solve_run WHERE id = ?", (run_id,)).fetchone()
            if row is None or (project_id is not None and row["project_id"] != project_id):
                raise NotFoundError("solve run not found")
            if not claim_token or row["claim_owner"] != owner or row["claim_token"] != claim_token:
                raise ConflictError("solver lease is not owned by this worker")
            if _claim_is_stale(row, int(row["lease_timeout_seconds"] or 120)):
                raise ConflictError("solver lease is stale; reclaim it before completing")
            now = utc_now()
            conn.execute(
                """
                UPDATE solve_run
                SET run_state = ?, execution = 'completed', solver_name = COALESCE(?, solver_name),
                    message = COALESCE(?, message), finished_at = ?, heartbeat_at = ?,
                    claim_owner = NULL, claim_token = NULL
                WHERE id = ? AND claim_owner = ? AND claim_token = ?
                """,
                (run_state, solver_name, message, now, now, run_id, owner, claim_token),
            )
            if conn.execute("SELECT changes() AS n").fetchone()["n"] != 1:
                raise ConflictError("solver lease changed while completing")
            for candidate in candidates or []:
                _insert_candidate(conn, row["project_id"], run_id, candidate)
            _event(
                conn,
                project_id=row["project_id"],
                event_type="solve_run.completed",
                entity_kind="solve_run",
                entity_id=run_id,
                summary=f"Completed solver run with state '{run_state}'",
                payload={"run_state": run_state, "candidate_count": len(candidates or [])},
            )
            return _solve_run_from_row(conn, conn.execute("SELECT * FROM solve_run WHERE id = ?", (run_id,)).fetchone(), include_candidates=True)
    finally:
        conn.close()


def mark_stale_solve_runs(project_id: str | None = None, *, stale_after_seconds: int = 120) -> int:
    """Mark abandoned worker leases without changing the solver truth state."""
    conn = connect()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            query = "SELECT * FROM solve_run WHERE claim_owner IS NOT NULL AND execution = 'claimed'"
            params: tuple[Any, ...] = ()
            if project_id is not None:
                query += " AND project_id = ?"
                params = (project_id,)
            rows = conn.execute(query, params).fetchall()
            count = 0
            now = utc_now()
            for row in rows:
                if _claim_is_stale(row, stale_after_seconds):
                    conn.execute(
                        "UPDATE solve_run SET execution = 'stale', stale_at = ?, claim_owner = NULL, claim_token = NULL WHERE id = ? AND claim_owner = ? AND heartbeat_at IS ?",
                        (now, row["id"], row["claim_owner"], row["heartbeat_at"]),
                    )
                    if conn.execute("SELECT changes() AS n").fetchone()["n"] == 1:
                        _event(conn, project_id=row["project_id"], event_type="solve_run.stale", entity_kind="solve_run", entity_id=row["id"], summary="Marked abandoned solver lease stale")
                        count += 1
            return count
    finally:
        conn.close()


def get_solve_run(run_id: str, *, project_id: str | None = None) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM solve_run WHERE id = ?", (run_id,)).fetchone()
        if row is None or (project_id is not None and row["project_id"] != project_id):
            raise NotFoundError("solve run not found")
        return _solve_run_from_row(conn, row, include_candidates=True)
    finally:
        conn.close()


def record_solver_explanation(
    run_id: str, payload: ConflictExplanationIn, *, project_id: str | None = None
) -> dict[str, Any]:
    """Attach evidence emitted by a real solver adapter to a SolveRun.

    This does not claim that this API executed the solver. It only persists a
    solver-produced status and explanation so the UI can show the evidence.
    """
    conn = connect()
    try:
        with conn:
            row = conn.execute("SELECT * FROM solve_run WHERE id = ?", (run_id,)).fetchone()
            if row is None or (project_id is not None and row["project_id"] != project_id):
                raise NotFoundError("solve run not found")
            explanation = payload.model_dump(mode="json")
            conn.execute(
                """
                UPDATE solve_run
                SET run_state = ?, solver_name = ?, explanation_json = ?, message = ?
                WHERE id = ?
                """,
                (
                    payload.status,
                    payload.solver_name,
                    _dump_json(explanation),
                    payload.summary,
                    run_id,
                ),
            )
            _event(
                conn,
                project_id=row["project_id"],
                event_type="solve_run.explanation_recorded",
                entity_kind="solve_run",
                entity_id=run_id,
                summary="Recorded solver-produced feasibility evidence",
                payload={"solver_name": payload.solver_name, "status": payload.status},
            )
            updated = conn.execute("SELECT * FROM solve_run WHERE id = ?", (run_id,)).fetchone()
            return _solve_run_from_row(conn, updated, include_candidates=True)
    finally:
        conn.close()


def export_solve_run(run_id: str, *, project_id: str | None = None) -> dict[str, Any]:
    """Return an immutable, self-contained decision-result export.

    Every entity is loaded through the same project boundary. The export keeps
    the exact scenario revision, formal model, solver input fingerprint,
    candidates, and provenance snapshot together so a result is reviewable
    after the live workspace changes.
    """
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM solve_run WHERE id = ?", (run_id,)).fetchone()
        if row is None or (project_id is not None and row["project_id"] != project_id):
            raise NotFoundError("solve run not found")
        project = _require_project(conn, row["project_id"])
        revision = conn.execute(
            "SELECT * FROM scenario_revision WHERE id = ? AND project_id = ?",
            (row["scenario_revision_id"], row["project_id"]),
        ).fetchone()
        if revision is None:
            raise ConflictError("solve run references a missing scenario revision")
        scenario = conn.execute(
            "SELECT * FROM scenario WHERE id = ? AND project_id = ?",
            (revision["scenario_id"], row["project_id"]),
        ).fetchone()
        materials = [
            _material_from_row(item)
            for item in conn.execute(
                "SELECT * FROM material WHERE project_id = ? ORDER BY created_at, id",
                (row["project_id"],),
            ).fetchall()
        ]
        spans = [
            _source_span_from_row(item)
            for item in conn.execute(
                "SELECT * FROM source_span WHERE project_id = ? ORDER BY created_at, id",
                (row["project_id"],),
            ).fetchall()
        ]
        baseline = None
        baseline_row = conn.execute(
            "SELECT * FROM modeling_baseline WHERE scenario_revision_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT 1",
            (revision["id"], row["project_id"]),
        ).fetchone()
        if baseline_row is not None:
            baseline = {
                "id": baseline_row["id"],
                "draft_id": baseline_row["draft_id"],
                "understanding_revision_id": baseline_row["understanding_revision_id"],
                "scenario_id": baseline_row["scenario_id"],
                "scenario_revision_id": baseline_row["scenario_revision_id"],
                "handoff": _load_json(baseline_row["export_json"], {}),
                "created_at": baseline_row["created_at"],
                "immutable": True,
            }
        related_entity_ids = [run_id, revision["id"], revision["scenario_id"]]
        if row["formal_model_id"]:
            related_entity_ids.append(row["formal_model_id"])
        if baseline is not None:
            related_entity_ids.append(baseline["id"])
        placeholders = ", ".join("?" for _ in related_entity_ids)
        events = [
            _event_from_row(item)
            for item in conn.execute(
                f"SELECT * FROM change_event WHERE project_id = ? AND entity_id IN ({placeholders}) ORDER BY created_at, id",
                (row["project_id"], *related_entity_ids),
            ).fetchall()
        ]
        return {
            "export_schema": "lucid.solve-run.v1",
            "exported_at": utc_now(),
            "project": {
                "id": project["id"],
                "title": project["title"],
                "decision_question": project["decision_question"] if "decision_question" in project.keys() else None,
            },
            "scenario": None if scenario is None else {"id": scenario["id"], "name": scenario["name"], "created_at": scenario["created_at"]},
            "scenario_revision": _scenario_revision_from_row(conn, revision, include_body=True),
            "formal_model": _formal_model_from_row(
                None if row["formal_model_id"] is None else conn.execute("SELECT * FROM formal_model WHERE id = ? AND project_id = ?", (row["formal_model_id"], row["project_id"])).fetchone()
            ),
            "solve_run": _solve_run_from_row(conn, row, include_candidates=True),
            "provenance": {"baseline": baseline, "materials": materials, "source_spans": spans},
            "events": events,
        }
    finally:
        conn.close()


def list_solve_runs(project_id: str) -> list[dict[str, Any]]:
    conn = connect()
    try:
        _require_project(conn, project_id)
        rows = conn.execute(
            """
            SELECT * FROM solve_run
            WHERE project_id = ?
            ORDER BY created_at, id
            """,
            (project_id,),
        ).fetchall()
        return [
            _solve_run_from_row(conn, row, include_candidates=True) for row in rows
        ]
    finally:
        conn.close()


def list_events(project_id: str) -> list[dict[str, Any]]:
    conn = connect()
    try:
        _require_project(conn, project_id)
        rows = conn.execute(
            """
            SELECT * FROM change_event
            WHERE project_id = ?
            ORDER BY created_at, id
            """,
            (project_id,),
        ).fetchall()
        return [_event_from_row(row) for row in rows]
    finally:
        conn.close()


def get_demo_project() -> dict[str, Any] | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM analysis_project WHERE is_demo = 1 LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return _project_detail(conn, row)
    finally:
        conn.close()


def seed_demo_project() -> dict[str, Any]:
    existing = get_demo_project()
    if existing is not None:
        return existing

    project = create_project(
        ProjectCreate(
            title=DEMO_TITLE,
            summary=DEMO_NOTES,
            workflow_maturity="open",
        ),
        is_demo=True,
    )
    project_id = project["id"]
    material = create_material(
        project_id,
        MaterialCreate(
            filename="demo-notes.txt",
            media_type="text/plain",
            kind="document",
            byte_size=None,
            notes=DEMO_NOTES,
        ),
    )
    create_source_span(
        project_id,
        SourceSpanCreate(
            material_id=material["id"],
            locator_kind="text_range",
            start_offset=None,
            end_offset=None,
            excerpt="External premise still unknown in source notes.",
        ),
    )
    v1 = create_understanding(
        project_id,
        UnderstandingCreate(
            summary="V1 baseline draft — demo data only.",
            version_state="draft",
            assumptions=["Demo fixture; not a real business baseline."],
            unknowns=["External premise for overtime eligibility"],
            conflicts=[],
            rules=[
                RuleIn(
                    rule_kind="conditional",
                    statement="If overtime is permitted, apply the overtime cost.",
                    review_status="unreviewed",
                    evidence_status="unknown",
                    condition_kind="if_then",
                    premise_status="unknown",
                    premise_text="overtime permitted (external, unresolved)",
                    cost=None,
                    capacity=None,
                    permission=None,
                )
            ],
        ),
    )
    create_understanding(
        project_id,
        UnderstandingCreate(
            summary="V2 baseline draft — still demo data; V1 must remain queryable.",
            version_state="draft",
            assumptions=[
                "Demo fixture; not a real business baseline.",
                "V2 adds a second assumption without rewriting V1.",
            ],
            unknowns=["External premise for overtime eligibility"],
            conflicts=[],
            rules=[
                RuleIn(
                    rule_kind="conditional",
                    statement="If overtime is permitted, apply the overtime cost.",
                    review_status="unreviewed",
                    evidence_status="unknown",
                    condition_kind="if_then",
                    premise_status="unknown",
                    premise_text="overtime permitted (external, unresolved)",
                    cost=None,
                    capacity=None,
                    permission=None,
                ),
                RuleIn(
                    rule_kind="hard",
                    statement="Do not invent a staffing number when capacity is unknown.",
                    review_status="unreviewed",
                    evidence_status="missing",
                    capacity=None,
                ),
            ],
        ),
    )
    scenario = create_scenario(
        project_id,
        ScenarioCreate(
            name="Demo scenario",
            notes="V1 scenario revision (demo).",
            version_state="draft",
            based_on_understanding_id=v1["id"],
            formal_model=FormalModelIn(
                name="demo-model-v1",
                version_state="draft",
                variable_count=None,
                constraint_count=None,
                objective_text=None,
                notes=DEMO_NOTES,
            ),
            rules=[
                RuleIn(
                    rule_kind="soft",
                    statement="Prefer fewer open unknowns before solving.",
                    review_status="unreviewed",
                    evidence_status="unknown",
                    cost=None,
                )
            ],
        ),
    )
    create_scenario_revision(
        scenario["id"],
        ScenarioRevisionCreate(
            notes="V2 scenario revision (demo). V1 snapshot stays.",
            version_state="draft",
            based_on_understanding_id=v1["id"],
            formal_model=FormalModelIn(
                name="demo-model-v2",
                version_state="draft",
                variable_count=None,
                constraint_count=None,
                notes=DEMO_NOTES,
            ),
            rules=[
                RuleIn(
                    rule_kind="soft",
                    statement="Prefer fewer open unknowns before solving.",
                    review_status="unreviewed",
                    evidence_status="unknown",
                    cost=None,
                )
            ],
        ),
    )
    latest_revision_id = get_scenario(scenario["id"])["revisions"][-1]["id"]
    create_solve_run(
        project_id,
        SolveRunCreate(
            scenario_revision_id=latest_revision_id,
            run_state="pending",
            message="DEMO DATA: pending SolveRun metadata; solver not executed.",
            candidate=ResultCandidateIn(
                label="unsolved-placeholder",
                objective_value=None,
                is_selected=None,
                notes=DEMO_NOTES,
            ),
        ),
    )
    create_solve_run(
        project_id,
        SolveRunCreate(
            scenario_revision_id=latest_revision_id,
            run_state="unknown",
            message="DEMO DATA: unknown SolveRun state label; solver not executed.",
        ),
    )
    return get_project(project_id)
