"""SQLite persistence for modeling runs, Azure cache, drafts, claims, baselines."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from ..db import connect, utc_now
from .. import ingest, store
from ..schemas import RuleIn, UnderstandingCreate
from .draft import ModelingDraft
from .provenance import INCOMPLETE_COVERAGE, validate_draft
from .snapshot import freeze_materials

RUN_STATUSES = (
    "queued",
    "running",
    "waiting_for_user",
    "partial",
    "completed",
    "failed",
    "cancelled",
)


class StaleRunError(store.ConflictError):
    pass


def _new_id() -> str:
    return str(uuid.uuid4())


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(value: str | None, default: Any) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)


def evidence_fingerprint(materials: list[dict[str, Any]]) -> str:
    parts = []
    for item in sorted(materials, key=lambda row: row.get("id") or ""):
        parts.append(f"{item.get('id')}:{item.get('checksum') or ''}")
    return "|".join(parts)


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def ensure_question_material(project_id: str, question: str) -> dict[str, Any]:
    """Persist a nonblank decision question as equal-status direct-text evidence."""
    text = question.strip()
    if not text:
        raise ValueError("a decision question is required")
    from ..importers.common import sha256_hex

    digest = sha256_hex(text.encode("utf-8"))
    for material in store.list_materials(project_id):
        if material.get("checksum") == digest:
            return material
    imported = ingest.ingest_direct_text(project_id, text, label="Decision question")
    return imported["material"]


def create_run(
    project_id: str,
    *,
    question: str,
    live_execution: bool,
    model_configured: bool,
    azure_configured: bool,
    max_tool_calls: int = 24,
    max_wall_seconds: int = 180,
    question_material_id: str | None = None,
) -> dict[str, Any]:
    materials = store.list_materials(project_id)
    spans = store.list_source_spans(project_id)
    fingerprint = evidence_fingerprint(materials)
    coverage = initial_coverage(materials, azure_configured=azure_configured)
    snapshot = freeze_materials(materials, spans)
    snapshot["frozen_at"] = utc_now()
    run_id = _new_id()
    now = utc_now()
    conn = connect()
    try:
        with conn:
            store._require_project(conn, project_id)
            conn.execute(
                """
                INSERT INTO modeling_run (
                    id, project_id, thread_id, status, question, evidence_fingerprint,
                    coverage_json, tool_call_count, max_tool_calls, live_execution,
                    model_configured, azure_configured, snapshot_json, question_material_id,
                    max_wall_seconds, created_at, updated_at
                ) VALUES (?, ?, ?, 'queued', ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    project_id,
                    run_id,
                    question,
                    fingerprint,
                    _dump(coverage),
                    max_tool_calls,
                    1 if live_execution else 0,
                    1 if model_configured else 0,
                    1 if azure_configured else 0,
                    _dump(snapshot),
                    question_material_id,
                    max_wall_seconds,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE analysis_project
                SET latest_modeling_run_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (run_id, now, project_id),
            )
            store._event(
                conn,
                project_id=project_id,
                event_type="modeling_run.created",
                entity_kind="modeling_run",
                entity_id=run_id,
                summary="Queued a business modeling run",
                payload={"live_execution": live_execution},
            )
        return get_run(run_id)
    finally:
        conn.close()


def initial_coverage(materials: list[dict[str, Any]], *, azure_configured: bool) -> list[dict[str, Any]]:
    rows = []
    for material in materials:
        meta = material.get("metadata") or {}
        needs_azure = bool(meta.get("needs_azure_content_understanding"))
        kind = material.get("kind")
        media = material.get("media_type") or ""
        origin = meta.get("source_origin")
        if origin == "direct_text" or media.startswith("text/") or media == "application/json":
            state = "pending"
            needs_azure = False
            detail = "Readable as text without Azure."
        elif kind == "table":
            state = "partially_processed"
            detail = "Local table structure stored. Azure not required for cell evidence."
            needs_azure = False
        elif kind == "image":
            state = "pending" if azure_configured else "unavailable"
            needs_azure = True
            detail = (
                "Image pixels stored. Azure Content Understanding required for visual content."
                if azure_configured
                else "Azure Content Understanding is not configured; image content is unavailable."
            )
        elif media == "application/pdf":
            empty = bool(meta.get("empty"))
            state = "partially_processed" if not empty else ("pending" if azure_configured else "unavailable")
            needs_azure = True
            detail = (
                "Local PDF text extraction is structural only. Azure may add missing pages."
                if not empty
                else "PDF has no extractable text. Azure is required; currently unavailable."
                if not azure_configured
                else "PDF has no extractable text. Azure analysis is pending."
            )
        elif meta.get("office_kind") in {"docx", "pptx"}:
            state = "pending" if azure_configured else "unavailable"
            needs_azure = True
            detail = (
                "Raw OOXML stored. Azure Content Understanding required."
                if azure_configured
                else "Raw OOXML stored. Azure is not configured, so this source is unavailable."
            )
        else:
            state = "pending"
            detail = "Material recorded; coverage not yet assessed by the Agent."
        rows.append(
            {
                "material_id": material["id"],
                "filename": material.get("filename"),
                "state": state,
                "detail": detail,
                "needs_azure": needs_azure,
                "azure_operation_id": None,
            }
        )
    return rows


def list_runs(project_id: str) -> list[dict[str, Any]]:
    conn = connect()
    try:
        store._require_project(conn, project_id)
        rows = conn.execute(
            """
            SELECT * FROM modeling_run
            WHERE project_id = ?
            ORDER BY created_at DESC, id
            """,
            (project_id,),
        ).fetchall()
        return [_run_from_row(conn, row) for row in rows]
    finally:
        conn.close()


def get_run(run_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM modeling_run WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise store.NotFoundError("modeling run not found")
        return _run_from_row(conn, row)
    finally:
        conn.close()


def _run_from_row(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    events = conn.execute(
        """
        SELECT * FROM modeling_run_event
        WHERE run_id = ?
        ORDER BY created_at, id
        """,
        (row["id"],),
    ).fetchall()
    clarifications = conn.execute(
        """
        SELECT * FROM modeling_clarification
        WHERE run_id = ?
        ORDER BY created_at, id
        """,
        (row["id"],),
    ).fetchall()
    drafts = conn.execute(
        """
        SELECT id, revision_no, version_state, completeness, created_at
        FROM modeling_draft
        WHERE run_id = ?
        ORDER BY revision_no
        """,
        (row["id"],),
    ).fetchall()
    keys = set(row.keys())
    snapshot = _load(row["snapshot_json"], {}) if "snapshot_json" in keys else {}
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "thread_id": row["thread_id"],
        "status": row["status"],
        "question": row["question"],
        "evidence_fingerprint": row["evidence_fingerprint"],
        "coverage": _load(row["coverage_json"], []),
        "snapshot": snapshot,
        "question_material_id": row["question_material_id"] if "question_material_id" in keys else None,
        "resume_claim_id": row["resume_claim_id"] if "resume_claim_id" in keys else None,
        "wall_deadline_at": row["wall_deadline_at"] if "wall_deadline_at" in keys else None,
        "max_wall_seconds": int(row["max_wall_seconds"]) if "max_wall_seconds" in keys and row["max_wall_seconds"] is not None else 180,
        "error_code": row["error_code"],
        "error_message": row["error_message"],
        "tool_call_count": row["tool_call_count"],
        "max_tool_calls": row["max_tool_calls"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "heartbeat_at": row["heartbeat_at"],
        "cancel_requested": bool(row["cancel_requested"]),
        "stale_input": bool(row["stale_input"]),
        "live_execution": bool(row["live_execution"]),
        "model_configured": bool(row["model_configured"]),
        "azure_configured": bool(row["azure_configured"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "events": [_event_out(item) for item in events],
        "clarifications": [_clarification_out(item) for item in clarifications],
        "drafts": [_row_dict(item) for item in drafts],
    }


def _event_out(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "project_id": row["project_id"],
        "kind": row["kind"],
        "title": row["title"],
        "detail": row["detail"],
        "payload": _load(row["payload_json"], None),
        "created_at": row["created_at"],
    }


def _clarification_out(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "run_id": row["run_id"],
        "question": row["question"],
        "reason": row["reason"],
        "affected_claim_keys": _load(row["affected_claim_keys_json"], []),
        "status": row["status"],
        "answer_text": row["answer_text"],
        "answer_material_id": row["answer_material_id"],
        "created_at": row["created_at"],
        "answered_at": row["answered_at"],
    }


def append_event(
    run_id: str,
    *,
    kind: str,
    title: str,
    detail: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    conn = connect()
    try:
        with conn:
            run = conn.execute("SELECT project_id FROM modeling_run WHERE id = ?", (run_id,)).fetchone()
            if run is None:
                raise store.NotFoundError("modeling run not found")
            conn.execute(
                """
                INSERT INTO modeling_run_event (
                    id, run_id, project_id, kind, title, detail, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id(),
                    run_id,
                    run["project_id"],
                    kind,
                    title,
                    detail,
                    None if payload is None else _dump(payload),
                    utc_now(),
                ),
            )
            conn.execute(
                "UPDATE modeling_run SET heartbeat_at = ?, updated_at = ? WHERE id = ?",
                (utc_now(), utc_now(), run_id),
            )
    finally:
        conn.close()


def update_run(run_id: str, **fields: Any) -> dict[str, Any]:
    allowed = {
        "status",
        "coverage_json",
        "error_code",
        "error_message",
        "tool_call_count",
        "started_at",
        "finished_at",
        "heartbeat_at",
        "cancel_requested",
        "stale_input",
        "snapshot_json",
        "question_material_id",
        "resume_claim_id",
        "wall_deadline_at",
        "max_wall_seconds",
    }
    conn = connect()
    try:
        with conn:
            row = conn.execute("SELECT * FROM modeling_run WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise store.NotFoundError("modeling run not found")
            current_status = row["status"]
            if "status" in fields:
                _assert_status_transition(current_status, fields["status"], row)
            assignments = []
            values: list[Any] = []
            for key, value in fields.items():
                if key not in allowed:
                    raise ValueError(f"cannot update {key}")
                if key in {"coverage_json", "snapshot_json"} and not isinstance(value, str):
                    value = _dump(value)
                if key in {"cancel_requested", "stale_input"}:
                    value = 1 if value else 0
                assignments.append(f"{key} = ?")
                values.append(value)
            assignments.append("updated_at = ?")
            values.append(utc_now())
            values.append(run_id)
            conn.execute(
                f"UPDATE modeling_run SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
        return get_run(run_id)
    finally:
        conn.close()


def _assert_status_transition(current: str, nxt: str, row: sqlite3.Row) -> None:
    if current == nxt:
        return
    terminal = {"completed", "failed", "cancelled"}
    if current in terminal and nxt == "completed":
        raise StaleRunError("a finished or cancelled run cannot be published as completed")
    if current == "completed" and nxt in terminal - {"completed"}:
        # failed/cancelled after complete is not used to overwrite a newer published draft
        if nxt == "completed":
            raise StaleRunError("completed run cannot be rewritten")
    if current in terminal and nxt not in {"failed", "cancelled"} and nxt != current:
        raise StaleRunError(f"cannot move {current} run to {nxt}")


def request_cancel(run_id: str) -> dict[str, Any]:
    run = get_run(run_id)
    if run["status"] in {"completed", "failed", "cancelled"}:
        return run
    return update_run(run_id, cancel_requested=True, status="cancelled", finished_at=utc_now())


def increment_tool_count(run_id: str) -> int:
    conn = connect()
    try:
        with conn:
            row = conn.execute(
                "SELECT * FROM modeling_run WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise store.NotFoundError("modeling run not found")
            if row["cancel_requested"] or row["status"] == "cancelled":
                raise StaleRunError("run cancelled")
            if row["status"] in {"failed", "completed"}:
                raise StaleRunError("stale run cannot accept further tool writes")
            keys = set(row.keys())
            deadline = row["wall_deadline_at"] if "wall_deadline_at" in keys else None
            if deadline and deadline < utc_now():
                raise StaleRunError("wall time exhausted")
            nxt = int(row["tool_call_count"]) + 1
            if nxt > int(row["max_tool_calls"]):
                raise StaleRunError("tool budget exhausted")
            conn.execute(
                "UPDATE modeling_run SET tool_call_count = ?, heartbeat_at = ?, updated_at = ? WHERE id = ?",
                (nxt, utc_now(), utc_now(), run_id),
            )
            return nxt
    finally:
        conn.close()


def update_coverage(run_id: str, material_id: str, **changes: Any) -> None:
    conn = connect()
    try:
        with conn:
            row = conn.execute(
                "SELECT coverage_json FROM modeling_run WHERE id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise store.NotFoundError("modeling run not found")
            coverage = _load(row["coverage_json"], [])
            found = False
            for item in coverage:
                if item.get("material_id") == material_id:
                    item.update(changes)
                    found = True
                    break
            if not found:
                coverage.append({"material_id": material_id, **changes})
            conn.execute(
                "UPDATE modeling_run SET coverage_json = ?, updated_at = ? WHERE id = ?",
                (_dump(coverage), utc_now(), run_id),
            )
    finally:
        conn.close()


def get_cached_analysis(
    material_id: str,
    checksum: str | None,
    analyzer_id: str,
    *,
    include_secrets: bool = False,
) -> dict[str, Any] | None:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT * FROM material_analysis
            WHERE material_id = ? AND IFNULL(material_checksum,'') = IFNULL(?, '')
              AND analyzer_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (material_id, checksum, analyzer_id),
        ).fetchone()
        return _analysis_out(row, include_secrets=include_secrets) if row else None
    finally:
        conn.close()


def upsert_analysis(project_id: str, material_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    analysis_id = _new_id()
    now = utc_now()
    conn = connect()
    try:
        with conn:
            existing = conn.execute(
                """
                SELECT id FROM material_analysis
                WHERE material_id = ? AND IFNULL(material_checksum,'') = IFNULL(?, '')
                  AND analyzer_id = ?
                """,
                (
                    material_id,
                    payload.get("material_checksum"),
                    payload.get("analyzer_id"),
                ),
            ).fetchone()
            fields = (
                payload.get("provider") or "azure_content_understanding",
                payload.get("analyzer_id"),
                payload.get("api_version"),
                payload.get("operation_id"),
                payload.get("operation_url"),
                payload.get("continuation_token"),
                payload.get("status"),
                None if payload.get("raw") is None else _dump(payload.get("raw")),
                payload.get("derived_markdown"),
                None if payload.get("derived") is None else _dump(payload.get("derived")),
                payload.get("error_message"),
                now,
            )
            if existing:
                analysis_id = existing["id"]
                conn.execute(
                    """
                    UPDATE material_analysis SET
                        provider=?, analyzer_id=?, api_version=?, operation_id=?,
                        operation_url=?, continuation_token=?, status=?,
                        raw_response_json=?, derived_markdown=?, locator_map_json=?,
                        error_message=?, updated_at=?
                    WHERE id=?
                    """,
                    (*fields, analysis_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO material_analysis (
                        id, project_id, material_id, material_checksum, provider,
                        analyzer_id, api_version, operation_id, operation_url,
                        continuation_token, status, raw_response_json, derived_markdown,
                        locator_map_json, error_message, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        analysis_id,
                        project_id,
                        material_id,
                        payload.get("material_checksum"),
                        *fields[:-1],
                        now,
                        now,
                    ),
                )
        return get_analysis(analysis_id)
    finally:
        conn.close()


def get_analysis(analysis_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM material_analysis WHERE id = ?", (analysis_id,)).fetchone()
        if row is None:
            raise store.NotFoundError("material analysis not found")
        return _analysis_out(row)
    finally:
        conn.close()


def _analysis_out(row: sqlite3.Row, *, include_secrets: bool = False) -> dict[str, Any]:
    payload = {
        "id": row["id"],
        "project_id": row["project_id"],
        "material_id": row["material_id"],
        "material_checksum": row["material_checksum"],
        "provider": row["provider"],
        "analyzer_id": row["analyzer_id"],
        "api_version": row["api_version"],
        "operation_id": row["operation_id"],
        "status": row["status"],
        "raw": _load(row["raw_response_json"], None),
        "derived_markdown": row["derived_markdown"],
        "derived": _load(row["locator_map_json"], None),
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if include_secrets:
        payload["continuation_token"] = row["continuation_token"]
        payload["operation_url"] = row["operation_url"]
    return payload


def pending_clarification(run_id: str) -> dict[str, Any] | None:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT * FROM modeling_clarification
            WHERE run_id = ? AND status = 'pending'
            ORDER BY created_at DESC LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        return _clarification_out(row) if row else None
    finally:
        conn.close()


def replace_snapshot(run_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    return update_run(run_id, snapshot_json=_dump(snapshot))


def claim_resume(run_id: str, answer: str) -> dict[str, Any]:
    """Atomically claim a waiting_for_user interrupt. Reject duplicate/conflicting resume."""
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("a nonblank clarification answer is required")
    conn = connect()
    try:
        with conn:
            row = conn.execute("SELECT * FROM modeling_run WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise store.NotFoundError("modeling run not found")
            if row["status"] != "waiting_for_user":
                raise store.ConflictError("run is not waiting for a clarification")
            claim_id = _new_id()
            now = utc_now()
            cursor = conn.execute(
                """
                UPDATE modeling_run
                SET status = 'running', resume_claim_id = ?, heartbeat_at = ?, updated_at = ?
                WHERE id = ? AND status = 'waiting_for_user'
                """,
                (claim_id, now, now, run_id),
            )
            if cursor.rowcount != 1:
                raise store.ConflictError("duplicate or conflicting resume")
        return get_run(run_id)
    finally:
        conn.close()


def ensure_clarification(
    run_id: str,
    *,
    question: str,
    reason: str | None,
    affected_claim_keys: list[str],
) -> dict[str, Any]:
    existing = pending_clarification(run_id)
    if existing and existing["question"] == question:
        return existing
    conn = connect()
    try:
        with conn:
            answered = conn.execute(
                """
                SELECT * FROM modeling_clarification
                WHERE run_id = ? AND question = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (run_id, question),
            ).fetchone()
            if answered is not None:
                return _clarification_out(answered)
            run = conn.execute(
                "SELECT project_id FROM modeling_run WHERE id = ?", (run_id,)
            ).fetchone()
            if run is None:
                raise store.NotFoundError("modeling run not found")
            clarification_id = _new_id()
            conn.execute(
                """
                INSERT INTO modeling_clarification (
                    id, project_id, run_id, question, reason, affected_claim_keys_json,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    clarification_id,
                    run["project_id"],
                    run_id,
                    question,
                    reason,
                    _dump(affected_claim_keys),
                    utc_now(),
                ),
            )
        return pending_clarification(run_id) or {}
    finally:
        conn.close()


def answer_clarification(
    run_id: str,
    answer_text: str,
    *,
    answer_material_id: str | None,
) -> dict[str, Any]:
    conn = connect()
    try:
        with conn:
            answered = conn.execute(
                """
                SELECT * FROM modeling_clarification
                WHERE run_id = ? AND status = 'answered' AND answer_text = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (run_id, answer_text),
            ).fetchone()
            if answered is not None:
                if answer_material_id and not answered["answer_material_id"]:
                    conn.execute(
                        """
                        UPDATE modeling_clarification
                        SET answer_material_id = ?
                        WHERE id = ?
                        """,
                        (answer_material_id, answered["id"]),
                    )
                return get_run(run_id)
            row = conn.execute(
                """
                SELECT * FROM modeling_clarification
                WHERE run_id = ? AND status = 'pending'
                ORDER BY created_at DESC LIMIT 1
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                raise store.NotFoundError("no pending clarification")
            conn.execute(
                """
                UPDATE modeling_clarification
                SET status = 'answered', answer_text = ?, answer_material_id = ?, answered_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (answer_text, answer_material_id, utc_now(), row["id"]),
            )
        return get_run(run_id)
    finally:
        conn.close()


def _may_update_project_heads(conn: sqlite3.Connection, project_id: str, run_id: str) -> bool:
    project = store._require_project(conn, project_id)
    keys = set(project.keys())
    latest_run_id = project["latest_modeling_run_id"] if "latest_modeling_run_id" in keys else None
    if latest_run_id in {None, run_id}:
        return True
    latest = conn.execute(
        "SELECT created_at FROM modeling_run WHERE id = ?", (latest_run_id,)
    ).fetchone()
    current = conn.execute(
        "SELECT created_at FROM modeling_run WHERE id = ?", (run_id,)
    ).fetchone()
    if latest and current and latest["created_at"] > current["created_at"]:
        return False
    return True


def save_draft(run_id: str, draft: ModelingDraft, *, completeness: str | None = None) -> dict[str, Any]:
    payload = draft.model_dump()
    if completeness:
        payload["completeness"] = completeness
        draft = ModelingDraft.model_validate(payload)
    run = get_run(run_id)
    if run["status"] in {"cancelled", "failed"}:
        raise StaleRunError(f"{run['status']} run cannot publish a draft")
    if run["cancel_requested"]:
        raise StaleRunError("cancelled run cannot publish a draft")
    if run["stale_input"]:
        raise StaleRunError("stale run cannot publish a draft over a newer project head")
    validate_draft(run, draft)
    coverage = run.get("coverage") or []
    incomplete = [item for item in coverage if (item.get("state") or "pending") in INCOMPLETE_COVERAGE]
    if incomplete and draft.completeness == "complete":
        payload["completeness"] = "partial"
        payload.setdefault("readiness_issues", [])
        if "Draft marked complete while one or more sources are still incomplete." not in payload["readiness_issues"]:
            payload["readiness_issues"].append(
                "Draft marked complete while one or more sources are still incomplete."
            )
        draft = ModelingDraft.model_validate(payload)
    project_id = run["project_id"]
    conn = connect()
    try:
        with conn:
            understanding = _persist_understanding(conn, project_id, draft, update_project_head=False)
            parent = conn.execute(
                """
                SELECT id, revision_no FROM modeling_draft
                WHERE project_id = ?
                ORDER BY revision_no DESC LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            revision_no = 1 if parent is None else int(parent["revision_no"]) + 1
            draft_id = _new_id()
            now = utc_now()
            conn.execute(
                """
                INSERT INTO modeling_draft (
                    id, project_id, run_id, revision_no, parent_draft_id, version_state,
                    completeness, understanding_revision_id, draft_json, created_at
                ) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)
                """,
                (
                    draft_id,
                    project_id,
                    run_id,
                    revision_no,
                    None if parent is None else parent["id"],
                    draft.completeness,
                    understanding["id"],
                    _dump(payload),
                    now,
                ),
            )
            _insert_claims(conn, project_id, draft_id, draft, understanding.get("rules") or [])
            if _may_update_project_heads(conn, project_id, run_id):
                conn.execute(
                    """
                    UPDATE analysis_project
                    SET latest_modeling_draft_id = ?, latest_understanding_revision_id = ?,
                        workflow_maturity = CASE WHEN workflow_maturity IN ('open','materials')
                            THEN 'understanding' ELSE workflow_maturity END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (draft_id, understanding["id"], now, project_id),
                )
            store._event(
                conn,
                project_id=project_id,
                event_type="modeling_draft.created",
                entity_kind="modeling_draft",
                entity_id=draft_id,
                summary=f"Stored modeling draft v{revision_no} ({draft.completeness})",
            )
        return get_draft(draft_id)
    finally:
        conn.close()


def _persist_understanding(
    conn: sqlite3.Connection,
    project_id: str,
    draft: ModelingDraft,
    *,
    update_project_head: bool,
) -> dict[str, Any]:
    rules: list[RuleIn] = []
    for item in draft.constraints:
        kind = item.strength if item.strength in {"hard", "soft", "conditional"} else "hard"
        span_id = item.evidence_refs[0].source_span_id if item.evidence_refs else None
        rules.append(
            RuleIn(
                rule_kind=kind,  # type: ignore[arg-type]
                statement=item.original_statement,
                review_status="unreviewed",
                evidence_status="present" if item.evidence_refs else "unknown",
                source_span_id=span_id,
                condition_kind="if_then" if item.strength == "conditional" else "always",
                premise_status="unknown" if item.strength == "conditional" else None,
                premise_text=item.condition,
            )
        )
    for item in draft.objectives:
        span_id = item.evidence_refs[0].source_span_id if item.evidence_refs else None
        rules.append(
            RuleIn(
                rule_kind="objective",
                statement=item.original_statement,
                review_status="unreviewed",
                evidence_status="present" if item.evidence_refs else "unknown",
                source_span_id=span_id,
            )
        )
    for item in draft.assumptions:
        span_id = item.evidence_refs[0].source_span_id if item.evidence_refs else None
        rules.append(
            RuleIn(
                rule_kind="assumption",
                statement=item.original_statement,
                review_status="unreviewed",
                evidence_status="present" if item.evidence_refs else "unknown",
                source_span_id=span_id,
            )
        )
    payload = UnderstandingCreate(
        summary=draft.decision_brief.what_to_decide,
        version_state="draft",
        assumptions=[item.original_statement for item in draft.assumptions],
        unknowns=[item.original_statement for item in draft.unknowns],
        conflicts=[item.original_statement for item in draft.conflicts],
        rules=rules,
    )
    return store.insert_understanding(
        conn, project_id, payload, update_project_head=update_project_head
    )


def _insert_claims(
    conn: sqlite3.Connection,
    project_id: str,
    draft_id: str,
    draft: ModelingDraft,
    rules: list[dict[str, Any]],
) -> None:
    now = utc_now()
    rule_by_statement = {item["statement"]: item["id"] for item in rules}

    def add(
        *,
        key: str,
        kind: str,
        original: str,
        interpretation: str | None,
        grounding: str,
        refs: list[Any],
        review: str = "unreviewed",
        modelability: str = "unknown",
        applicability: str | None = None,
    ) -> None:
        del review  # New AI claims are always unreviewed; the model cannot accept its own rules.
        conn.execute(
            """
            INSERT INTO modeling_claim (
                id, project_id, draft_id, claim_key, claim_kind, original_statement,
                proposed_interpretation, grounding, review_status, modelability_status,
                applicability, evidence_refs_json, rule_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id(),
                project_id,
                draft_id,
                key,
                kind,
                original,
                interpretation,
                grounding,
                "unreviewed",
                modelability,
                applicability,
                _dump([ref.model_dump() if hasattr(ref, "model_dump") else ref for ref in refs]),
                rule_by_statement.get(original),
                now,
                now,
            ),
        )

    add(
        key="decision",
        kind="decision",
        original=draft.decision_brief.what_to_decide,
        interpretation=draft.decision_brief.scope,
        grounding="explicit",
        refs=[],
    )
    for item in draft.entities:
        add(
            key=item.claim_key,
            kind="entity",
            original=item.original_statement,
            interpretation=item.proposed_interpretation,
            grounding=item.grounding,
            refs=item.evidence_refs,
            review=item.review_status,
            modelability=item.modelability_status,
            applicability=item.applicability,
        )
    for item in draft.parameters:
        add(
            key=item.claim_key,
            kind="parameter",
            original=item.name,
            interpretation=item.raw_value,
            grounding=item.grounding,
            refs=item.evidence_refs,
        )
    for item in draft.decision_variables:
        add(
            key=item.claim_key,
            kind="variable",
            original=item.name,
            interpretation=item.domain,
            grounding="inferred",
            refs=item.evidence_refs,
        )
    for item in draft.constraints:
        add(
            key=item.claim_key,
            kind="constraint",
            original=item.original_statement,
            interpretation=item.proposed_interpretation,
            grounding=item.grounding,
            refs=item.evidence_refs,
            review=item.review_status,
            modelability=item.modelability_status,
            applicability=item.applicability,
        )
    for item in draft.objectives:
        add(
            key=item.claim_key,
            kind="objective",
            original=item.original_statement,
            interpretation=item.proposed_interpretation,
            grounding=item.grounding,
            refs=item.evidence_refs,
        )
    for item in draft.assumptions:
        add(
            key=item.claim_key,
            kind="assumption",
            original=item.original_statement,
            interpretation=item.proposed_interpretation,
            grounding=item.grounding,
            refs=item.evidence_refs,
        )
    for item in draft.unknowns:
        add(
            key=item.claim_key,
            kind="unknown",
            original=item.original_statement,
            interpretation=item.proposed_interpretation,
            grounding=item.grounding,
            refs=item.evidence_refs,
            modelability="blocked",
        )
    for item in draft.conflicts:
        add(
            key=item.claim_key,
            kind="conflict",
            original=item.original_statement,
            interpretation=item.proposed_interpretation,
            grounding=item.grounding,
            refs=item.evidence_refs,
            modelability="blocked",
        )
    for index, issue in enumerate(draft.readiness_issues):
        add(
            key=f"readiness-{index+1}",
            kind="readiness",
            original=issue,
            interpretation=None,
            grounding="inferred",
            refs=[],
        )


def get_draft(draft_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM modeling_draft WHERE id = ?", (draft_id,)).fetchone()
        if row is None:
            raise store.NotFoundError("modeling draft not found")
        claims = conn.execute(
            """
            SELECT * FROM modeling_claim
            WHERE draft_id = ?
            ORDER BY created_at, id
            """,
            (draft_id,),
        ).fetchall()
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "run_id": row["run_id"],
            "revision_no": row["revision_no"],
            "parent_draft_id": row["parent_draft_id"],
            "version_state": row["version_state"],
            "completeness": row["completeness"],
            "understanding_revision_id": row["understanding_revision_id"],
            "draft": _load(row["draft_json"], {}),
            "claims": [_claim_out(item) for item in claims],
            "created_at": row["created_at"],
        }
    finally:
        conn.close()


def list_drafts(project_id: str) -> list[dict[str, Any]]:
    conn = connect()
    try:
        store._require_project(conn, project_id)
        rows = conn.execute(
            """
            SELECT id FROM modeling_draft
            WHERE project_id = ?
            ORDER BY revision_no
            """,
            (project_id,),
        ).fetchall()
        return [get_draft(row["id"]) for row in rows]
    finally:
        conn.close()


def _claim_out(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "draft_id": row["draft_id"],
        "claim_key": row["claim_key"],
        "claim_kind": row["claim_kind"],
        "original_statement": row["original_statement"],
        "proposed_interpretation": row["proposed_interpretation"],
        "edited_statement": row["edited_statement"],
        "grounding": row["grounding"],
        "review_status": row["review_status"],
        "modelability_status": row["modelability_status"],
        "applicability": row["applicability"],
        "evidence_refs": _load(row["evidence_refs_json"], []),
        "rule_id": row["rule_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def review_claim(
    claim_id: str,
    *,
    action: str,
    edited_text: str | None = None,
) -> dict[str, Any]:
    if action not in {"accepted", "rejected", "needs_clarification", "not_applicable"}:
        raise ValueError("invalid review action")
    conn = connect()
    try:
        with conn:
            row = conn.execute("SELECT * FROM modeling_claim WHERE id = ?", (claim_id,)).fetchone()
            if row is None:
                raise store.NotFoundError("claim not found")
            draft = conn.execute(
                "SELECT version_state FROM modeling_draft WHERE id = ?",
                (row["draft_id"],),
            ).fetchone()
            if draft and draft["version_state"] == "confirmed":
                raise store.ConflictError("confirmed baseline claims are immutable")
            previous_status = row["review_status"]
            previous_edited = row["edited_statement"]
            conn.execute(
                """
                UPDATE modeling_claim
                SET review_status = ?, edited_statement = ?, updated_at = ?
                WHERE id = ?
                """,
                (action, edited_text, utc_now(), claim_id),
            )
            conn.execute(
                """
                INSERT INTO modeling_claim_review_event (
                    id, project_id, draft_id, claim_id, previous_status, new_status,
                    previous_edited_statement, new_edited_statement, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _new_id(),
                    row["project_id"],
                    row["draft_id"],
                    claim_id,
                    previous_status,
                    action,
                    previous_edited,
                    edited_text,
                    utc_now(),
                ),
            )
            if row["rule_id"]:
                mapped = action
                if action == "not_applicable" and not store.rule_table_allows_status(conn, "not_applicable"):
                    mapped = "rejected"
                conn.execute(
                    "UPDATE rule SET review_status = ? WHERE id = ?",
                    (mapped, row["rule_id"]),
                )
        return get_claim(claim_id)
    finally:
        conn.close()


def get_claim(claim_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM modeling_claim WHERE id = ?", (claim_id,)).fetchone()
        if row is None:
            raise store.NotFoundError("claim not found")
        return _claim_out(row)
    finally:
        conn.close()


def freeze_baseline(project_id: str, draft_id: str) -> dict[str, Any]:
    from .export import render_markdown, structured_handoff

    draft = get_draft(draft_id)
    if draft["project_id"] != project_id:
        raise store.NotFoundError("draft not found")
    if draft["version_state"] == "confirmed":
        raise store.ConflictError("draft already frozen")
    run = get_run(draft["run_id"])
    if run["status"] in {"cancelled", "failed"}:
        raise StaleRunError("cancelled or failed runs cannot freeze a baseline")
    coverage = (draft.get("draft") or {}).get("coverage") or run.get("coverage") or []
    incomplete = [item for item in coverage if (item.get("state") or "pending") in INCOMPLETE_COVERAGE]
    if draft.get("completeness") == "complete" and incomplete:
        raise store.ConflictError(
            "a complete baseline cannot be frozen while source coverage is still incomplete"
        )
    claims = draft["claims"]
    for claim in claims:
        refs = claim.get("evidence_refs") or []
        if claim["claim_kind"] in {"constraint", "objective"} and refs:
            if claim["review_status"] == "unreviewed":
                raise store.ConflictError(
                    "source-backed constraints and objectives must be reviewed before freezing a baseline"
                )
            if claim["review_status"] == "needs_clarification":
                raise store.ConflictError(
                    "unresolved critical clarification blocks baseline freeze"
                )
    export_draft = dict(draft)
    export_draft["snapshot"] = run.get("snapshot") or {}
    handoff = structured_handoff(export_draft, for_baseline=True)
    markdown = render_markdown(export_draft, handoff)
    conn = connect()
    try:
        with conn:
            now = utc_now()
            cursor = conn.execute(
                """
                UPDATE modeling_draft
                SET version_state = 'confirmed'
                WHERE id = ? AND version_state = 'draft'
                """,
                (draft_id,),
            )
            if cursor.rowcount != 1:
                raise store.ConflictError("draft already frozen")
            understanding_id = draft.get("understanding_revision_id")
            baseline_id = _new_id()
            conn.execute(
                """
                INSERT INTO modeling_baseline (
                    id, project_id, draft_id, understanding_revision_id,
                    scenario_id, scenario_revision_id, export_json, export_markdown, created_at
                ) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?)
                """,
                (
                    baseline_id,
                    project_id,
                    draft_id,
                    understanding_id,
                    _dump(handoff),
                    markdown,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE analysis_project
                SET latest_baseline_id = ?, workflow_maturity = 'scenarios', updated_at = ?
                WHERE id = ?
                """,
                (baseline_id, now, project_id),
            )
            store._event(
                conn,
                project_id=project_id,
                event_type="baseline.frozen",
                entity_kind="modeling_baseline",
                entity_id=baseline_id,
                summary="Froze an immutable pre-solver business baseline",
            )
        return get_baseline(baseline_id)
    finally:
        conn.close()


def get_baseline(baseline_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM modeling_baseline WHERE id = ?", (baseline_id,)).fetchone()
        if row is None:
            raise store.NotFoundError("baseline not found")
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "draft_id": row["draft_id"],
            "understanding_revision_id": row["understanding_revision_id"],
            "scenario_id": row["scenario_id"],
            "scenario_revision_id": row["scenario_revision_id"],
            "handoff": _load(row["export_json"], {}),
            "markdown": row["export_markdown"],
            "created_at": row["created_at"],
            "solver": "not_executed",
        }
    finally:
        conn.close()


def list_baselines(project_id: str) -> list[dict[str, Any]]:
    conn = connect()
    try:
        store._require_project(conn, project_id)
        rows = conn.execute(
            """
            SELECT id FROM modeling_baseline
            WHERE project_id = ?
            ORDER BY created_at
            """,
            (project_id,),
        ).fetchall()
        return [get_baseline(row["id"]) for row in rows]
    finally:
        conn.close()


def list_claim_review_events(claim_id: str) -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM modeling_claim_review_event
            WHERE claim_id = ?
            ORDER BY created_at, id
            """,
            (claim_id,),
        ).fetchall()
        return [_row_dict(row) for row in rows]
    finally:
        conn.close()
