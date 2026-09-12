"""Transaction-safe SQLite persistence for LUCID analysis objects.

Revision bodies (understanding, scenario, rules, formal models, materials,
source spans) are insert-only. Live latest-pointers live on analysis_project
and may be updated without rewriting historical snapshot rows.

Unknown numeric / boolean business values are stored as SQL NULL and must
never be coerced to 0 / false.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from .db import connect, utc_now
from .schemas import (
    FormalModelIn,
    MaterialCreate,
    ProjectCreate,
    ProjectPatch,
    ResultCandidateIn,
    RuleIn,
    ScenarioCreate,
    ScenarioRevisionCreate,
    SolveRunCreate,
    SourceSpanCreate,
    UnderstandingCreate,
)

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
        "claimed_execution": bool(row["claimed_execution"]),
        "execution": row["execution"],
        "solver_name": row["solver_name"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "message": row["message"],
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
    model_id = _new_id()
    conn.execute(
        """
        INSERT INTO formal_model (
            id, project_id, scenario_revision_id, name, version_state,
            variable_count, constraint_count, objective_text, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            model_id,
            project_id,
            scenario_revision_id,
            payload.name,
            payload.version_state,
            payload.variable_count,
            payload.constraint_count,
            payload.objective_text,
            payload.notes,
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
        WHERE scenario_id = ?
        ORDER BY revision_no DESC
        LIMIT 1
        """,
        (scenario_id,),
    ).fetchone()
    revision_no = 1 if latest is None else latest["revision_no"] + 1
    parent_id = None if latest is None else latest["id"]
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
        },
    )
    row = conn.execute(
        "SELECT * FROM scenario_revision WHERE id = ?", (revision_id,)
    ).fetchone()
    return _scenario_revision_from_row(conn, row, include_body=True)


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


def create_solve_run(project_id: str, payload: SolveRunCreate) -> dict[str, Any]:
    conn = connect()
    try:
        with conn:
            _require_project(conn, project_id)
            revision = conn.execute(
                """
                SELECT id, formal_model_id FROM scenario_revision
                WHERE id = ? AND project_id = ?
                """,
                (payload.scenario_revision_id, project_id),
            ).fetchone()
            if revision is None:
                raise NotFoundError("scenario revision not found")
            formal_model_id = payload.formal_model_id or revision["formal_model_id"]
            if formal_model_id is not None:
                model = conn.execute(
                    "SELECT id FROM formal_model WHERE id = ? AND project_id = ?",
                    (formal_model_id, project_id),
                ).fetchone()
                if model is None:
                    raise NotFoundError("formal model not found")
            run_id = _new_id()
            message = payload.message or (
                "SolveRun metadata recorded without executing a solver."
            )
            conn.execute(
                """
                INSERT INTO solve_run (
                    id, project_id, scenario_revision_id, formal_model_id,
                    run_state, claimed_execution, execution, solver_name,
                    started_at, finished_at, message, created_at
                ) VALUES (?, ?, ?, ?, ?, 0, 'not_executed', NULL, NULL, NULL, ?, ?)
                """,
                (
                    run_id,
                    project_id,
                    payload.scenario_revision_id,
                    formal_model_id,
                    payload.run_state,
                    message,
                    utc_now(),
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
            is_selected, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate_id,
            project_id,
            solve_run_id,
            payload.label,
            payload.objective_value,
            _bool_to_sql(payload.is_selected),
            payload.notes,
            utc_now(),
        ),
    )
    row = conn.execute(
        "SELECT * FROM result_candidate WHERE id = ?", (candidate_id,)
    ).fetchone()
    return _candidate_from_row(row)


def get_solve_run(run_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM solve_run WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise NotFoundError("solve run not found")
        return _solve_run_from_row(conn, row, include_candidates=True)
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
