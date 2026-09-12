"""Bounded Agent tools. No arbitrary path, URL, or code execution.

Reads bind to the frozen run snapshot. Continuation tokens stay in persistence,
never in tool payloads returned to the model or browser.
"""

from __future__ import annotations

import json
from typing import Any

from langchain.tools import tool
from langgraph.types import interrupt

from .. import ingest, store
from ..db import get_data_dir
from ..runtime_config import azure_settings
from . import persistence
from .azure_cu import AzureContentUnderstanding, AzureUnavailableError
from .context import require_run
from .draft import ModelingDraft
from .provenance import (
    MAX_EXCERPT,
    INCOMPLETE_COVERAGE,
    bound_text,
    coverage_state_after_read,
    select_span,
)
from .snapshot import (
    SnapshotIntegrityError,
    append_clarification_material,
    get_snapshot_material,
    list_snapshot_materials,
    list_snapshot_spans,
    read_snapshot_bytes,
)

_azure = AzureContentUnderstanding()


def set_azure_client(client: AzureContentUnderstanding) -> None:
    global _azure
    _azure = client


def resolve_material_path(project_id: str, material: dict[str, Any]):
    """Live Materials store path. Modeling tools must use snapshot bytes instead."""
    meta = material.get("metadata") or {}
    stored = meta.get("stored_path")
    if not isinstance(stored, str) or not stored.strip():
        raise store.NotFoundError("material bytes are not stored")
    root = (get_data_dir() / "materials" / project_id).resolve()
    path = (get_data_dir() / stored).resolve()
    if root not in path.parents and path != root:
        raise PermissionError("material path is outside the project store")
    if not path.is_file():
        raise store.NotFoundError("stored material file is missing")
    return path


def _snapshot_bytes_or_stale(run: dict[str, Any], material: dict[str, Any]) -> bytes:
    try:
        return read_snapshot_bytes(run, material)
    except SnapshotIntegrityError as exc:
        persistence.mark_stale_input(run["id"], reason=str(exc))
        raise

def _require_snapshot_material(run: dict[str, Any], material_id: str) -> dict[str, Any]:
    if material_id.startswith("/") or "://" in material_id:
        raise store.NotFoundError("material_id must be a project-scoped id, not a path or URL")
    material = get_snapshot_material(run, material_id)
    if material is None:
        raise store.NotFoundError("material not found in this run snapshot")
    return material


@tool
def inspect_evidence() -> str:
    """List snapshot Materials and processing/coverage state for this run. Use project-scoped IDs only."""
    ctx = require_run()
    persistence.increment_tool_count(ctx.run_id)
    run = persistence.get_run(ctx.run_id)
    coverage = {item.get("material_id"): item for item in run.get("coverage") or []}
    rows = []
    for material in list_snapshot_materials(run):
        meta = material.get("metadata") or {}
        material_spans = list_snapshot_spans(run, material["id"])
        rows.append(
            {
                "id": material["id"],
                "filename": material.get("filename"),
                "kind": material.get("kind"),
                "media_type": material.get("media_type"),
                "byte_size": material.get("byte_size"),
                "checksum": material.get("checksum"),
                "source_origin": meta.get("source_origin"),
                "needs_azure": bool(meta.get("needs_azure_content_understanding"))
                or material.get("kind") == "image"
                or (material.get("media_type") == "application/pdf"),
                "coverage": coverage.get(material["id"]),
                "span_count": len(material_spans),
                "span_ids": [span["id"] for span in material_spans[:12]],
            }
        )
    persistence.append_event(
        ctx.run_id,
        kind="tool_call",
        title="Inspected evidence snapshot",
        detail=f"{len(rows)} materials",
    )
    incomplete = any(
        (item.get("coverage") or {}).get("state") in INCOMPLETE_COVERAGE
        or item.get("coverage") is None
        for item in rows
    )
    return json.dumps(
        {
            "materials": rows,
            "coverage_incomplete": incomplete,
            "note": "This list is the frozen run snapshot. Later unrelated uploads are not part of this run.",
        },
        ensure_ascii=False,
    )


@tool
def read_source(
    material_id: str,
    source_span_id: str | None = None,
    start_offset: int | None = None,
    end_offset: int | None = None,
    page: int | None = None,
    sheet: str | None = None,
    cell_ref: str | None = None,
    derived: bool = False,
) -> str:
    """Read original or stored excerpts by snapshot material/span IDs. Never pass filesystem paths or URLs."""
    ctx = require_run()
    persistence.increment_tool_count(ctx.run_id)
    run = persistence.get_run(ctx.run_id)
    try:
        material = _require_snapshot_material(run, material_id)
    except store.NotFoundError as exc:
        return json.dumps({"error": str(exc)})
    spans = list_snapshot_spans(run, material_id)
    chosen = select_span(
        spans,
        source_span_id=source_span_id,
        page=page,
        sheet=sheet,
        cell_ref=cell_ref,
    )
    if source_span_id and chosen is None:
        return json.dumps({"error": "source_span_id not found in this run snapshot"})
    if (page is not None or sheet is not None or cell_ref is not None) and chosen is None and not source_span_id:
        return json.dumps(
            {
                "error": "requested page/sheet/cell does not match any snapshot span",
                "page": page,
                "sheet": sheet,
                "cell_ref": cell_ref,
            }
        )

    media = material.get("media_type") or ""
    is_text = media.startswith("text/") or media in {"application/json", "text/csv", "text/markdown"}
    excerpt = ""
    locator: dict[str, Any]
    bounded: dict[str, Any] | None = None
    derived_preview = None
    derived_bounded = None

    if is_text and not derived:
        try:
            text = _snapshot_bytes_or_stale(run, material).decode("utf-8", errors="replace")
        except SnapshotIntegrityError as exc:
            persistence.append_event(ctx.run_id, kind="tool_result", title="Read source stale_input", detail=str(exc))
            return json.dumps({"error": "stale_input", "detail": str(exc)})
        except Exception as exc:  # noqa: BLE001
            persistence.append_event(ctx.run_id, kind="tool_result", title="Read source failed", detail=type(exc).__name__)
            return json.dumps({"error": "stored bytes could not be read", "detail": type(exc).__name__})
        start = start_offset
        end = end_offset
        if chosen and chosen.get("start_offset") is not None and start_offset is None:
            start = int(chosen["start_offset"])
            end = int(chosen.get("end_offset") if chosen.get("end_offset") is not None else start)
        bounded = bound_text(text, start_offset=start, end_offset=end, max_chars=MAX_EXCERPT)
        excerpt = bounded["excerpt"]
        locator = {
            "precision": "exact" if start_offset is not None or chosen else ("whole_source" if bounded["whole_source"] else "approximate"),
            "coordinate_system": "original_text",
            "start_offset": bounded["start_offset"],
            "end_offset": bounded["end_offset"],
            "total_chars": bounded["total_chars"],
            "next_offset": bounded["next_offset"],
            "truncated": bounded["truncated"],
        }
    else:
        if chosen is None and spans:
            chosen = spans[0]
        excerpt = str((chosen or {}).get("excerpt") or "")[:MAX_EXCERPT]
        locator = {
            "precision": "approximate" if excerpt else "unresolved",
            "coordinate_system": (chosen or {}).get("locator_kind") or "source_span_excerpt",
            "page": (chosen or {}).get("page"),
            "sheet": (chosen or {}).get("sheet"),
            "cell_ref": (chosen or {}).get("cell_ref"),
            "source_span_id": (chosen or {}).get("id"),
            "truncated": len(str((chosen or {}).get("excerpt") or "")) > MAX_EXCERPT,
        }
        if page is not None and locator.get("page") != page:
            locator["requested_page"] = page
        if sheet is not None:
            locator["requested_sheet"] = sheet
        if cell_ref is not None:
            locator["requested_cell_ref"] = cell_ref
        if not excerpt:
            excerpt = "(no local text excerpt; use understand_material for provider-derived content)"

    analysis = persistence.get_cached_analysis(
        material_id,
        material.get("checksum"),
        azure_settings()["analyzer_id"] or "prebuilt-document",
        include_secrets=False,
    )
    if analysis and analysis.get("derived_markdown"):
        derived_text = str(analysis["derived_markdown"])
        derived_bounded = bound_text(
            derived_text,
            start_offset=start_offset if derived else 0,
            end_offset=end_offset if derived else None,
            max_chars=MAX_EXCERPT,
        )
        derived_preview = derived_bounded["excerpt"]

    whole = bool(bounded and bounded["whole_source"] and not bounded["truncated"]) if is_text and not derived else False
    state = coverage_state_after_read(media_is_text=is_text and not derived, whole_source=whole, truncated=bool(bounded and bounded["truncated"]) if bounded else True)
    if derived_bounded and (derived or not is_text):
        if derived_bounded["truncated"] or not derived_bounded["whole_source"]:
            state = "partially_processed"
    persistence.update_coverage(
        ctx.run_id,
        material_id,
        state=state,
        detail="Read a bounded source excerpt; this is not automatically whole-material analysis.",
    )
    persistence.append_event(
        ctx.run_id,
        kind="tool_result",
        title=f"Read {material.get('filename')}",
        payload={"material_id": material_id, "truncated": bool((bounded or {}).get("truncated") or (derived_bounded or {}).get("truncated"))},
    )
    return json.dumps(
        {
            "material_id": material_id,
            "filename": material.get("filename"),
            "locator": locator,
            "excerpt": excerpt,
            "total_chars": None if bounded is None else bounded["total_chars"],
            "next_offset": None if bounded is None else bounded["next_offset"],
            "truncated": bool((bounded or {}).get("truncated")),
            "derived_preview": derived_preview,
            "derived_locator": None
            if derived_bounded is None
            else {
                "coordinate_system": "azure_markdown",
                "start_offset": derived_bounded["start_offset"],
                "end_offset": derived_bounded["end_offset"],
                "total_chars": derived_bounded["total_chars"],
                "next_offset": derived_bounded["next_offset"],
                "truncated": derived_bounded["truncated"],
                "original_coordinates": "unknown",
            },
            "derived_labeled": bool(derived_preview),
            "note": (
                "Reading one excerpt does not mean the whole material was analyzed. "
                "Derived Azure markdown is not original file coordinates."
            ),
        },
        ensure_ascii=False,
    )


@tool
def understand_material(material_id: str) -> str:
    """Invoke or resume the single Azure Content Understanding service on one snapshot Material."""
    ctx = require_run()
    persistence.increment_tool_count(ctx.run_id)
    run = persistence.get_run(ctx.run_id)
    try:
        material = _require_snapshot_material(run, material_id)
    except store.NotFoundError as exc:
        return json.dumps({"error": str(exc)})
    analyzer_id = azure_settings()["analyzer_id"] or "prebuilt-document"
    cached = persistence.get_cached_analysis(
        material_id,
        material.get("checksum"),
        analyzer_id,
        include_secrets=True,
    )
    if cached and cached.get("status") == "succeeded":
        persistence.update_coverage(
            ctx.run_id,
            material_id,
            state="analyzed",
            detail="Reused cached Azure analysis",
            azure_operation_id=cached.get("operation_id"),
            needs_azure=True,
        )
        persistence.append_event(
            ctx.run_id,
            kind="tool_result",
            title=f"Reused Azure analysis for {material.get('filename')}",
            payload={"operation_id": cached.get("operation_id")},
        )
        markdown = cached.get("derived_markdown") or ""
        bounded = bound_text(str(markdown), start_offset=0, end_offset=None, max_chars=MAX_EXCERPT)
        return json.dumps(
            {
                "status": "cached",
                "operation_id": cached.get("operation_id"),
                "analyzer_id": cached.get("analyzer_id"),
                "derived_coordinate_system": "azure_markdown",
                "derived_markdown": bounded["excerpt"],
                "truncated": bounded["truncated"],
                "next_offset": bounded["next_offset"],
                "total_chars": bounded["total_chars"],
            },
            ensure_ascii=False,
        )
    if not _azure.configured():
        persistence.update_coverage(
            ctx.run_id,
            material_id,
            state="unavailable",
            detail="Azure Content Understanding is not configured",
            needs_azure=True,
        )
        persistence.append_event(
            ctx.run_id,
            kind="tool_result",
            title=f"Azure unavailable for {material.get('filename')}",
        )
        return json.dumps(
            {
                "status": "unavailable",
                "error_code": "azure_unavailable",
                "message": "Azure Content Understanding is not configured. Coverage for this material is incomplete.",
            }
        )
    try:
        content = _snapshot_bytes_or_stale(run, material)
        continuation = cached.get("continuation_token") if cached else None
        job = _azure.start_job(
            content,
            media_type=material.get("media_type"),
            continuation_token=continuation if cached and cached.get("status") in {"running", "timeout"} else None,
        )
    except SnapshotIntegrityError as exc:
        persistence.update_coverage(
            ctx.run_id,
            material_id,
            state="unavailable",
            detail=f"stale_input: {exc}",
            needs_azure=True,
        )
        return json.dumps({"status": "unavailable", "error_code": "stale_input", "message": str(exc)})
    except AzureUnavailableError as exc:
        persistence.update_coverage(
            ctx.run_id,
            material_id,
            state="unavailable",
            detail=str(exc),
            needs_azure=True,
        )
        return json.dumps({"status": "unavailable", "error_code": exc.code, "message": str(exc)})
    except Exception as exc:  # noqa: BLE001
        persistence.update_coverage(
            ctx.run_id,
            material_id,
            state="unavailable",
            detail=type(exc).__name__,
            needs_azure=True,
        )
        return json.dumps({"status": "unavailable", "message": type(exc).__name__})

    persistence.upsert_analysis(
        ctx.project_id,
        material_id,
        {
            "material_checksum": material.get("checksum"),
            "analyzer_id": job.analyzer_id,
            "api_version": job.api_version,
            "operation_id": job.operation_id,
            "continuation_token": job.continuation_token,
            "status": job.status,
            "raw": None,
            "derived": None,
            "error_message": job.error_message,
        },
    )
    if job.status == "running":
        job = _azure.wait(job, timeout_seconds=60)
        persistence.upsert_analysis(
            ctx.project_id,
            material_id,
            {
                "material_checksum": material.get("checksum"),
                "analyzer_id": job.analyzer_id,
                "api_version": job.api_version,
                "operation_id": job.operation_id,
                "continuation_token": job.continuation_token,
                "status": "running" if job.status == "timeout" else job.status,
                "raw": job.raw,
                "derived": job.derived,
                "derived_markdown": (job.derived or {}).get("markdown") if isinstance(job.derived, dict) else None,
                "error_message": job.error_message,
            },
        )

    if job.status in {"timeout", "running"}:
        state = "pending"
        detail = "Azure job still running or timed out; this is not an empty success."
    elif job.status == "succeeded":
        state = "analyzed"
        detail = "Azure succeeded"
    else:
        state = "unavailable"
        detail = job.error_message or f"Azure {job.status}"
    persistence.update_coverage(
        ctx.run_id,
        material_id,
        state=state,
        detail=detail,
        azure_operation_id=job.operation_id,
        needs_azure=True,
    )
    persistence.append_event(
        ctx.run_id,
        kind="tool_result",
        title=f"Azure analysis {job.status} for {material.get('filename')}",
        payload={"operation_id": job.operation_id, "status": job.status},
    )
    public = job.public_dict()
    markdown = public.get("derived_markdown") or ""
    bounded = bound_text(str(markdown), start_offset=0, end_offset=None, max_chars=MAX_EXCERPT) if markdown else None
    return json.dumps(
        {
            "status": public["status"],
            "operation_id": public["operation_id"],
            "analyzer_id": public["analyzer_id"],
            "api_version": public["api_version"],
            "derived_markdown": None if bounded is None else bounded["excerpt"],
            "derived_coordinate_system": "azure_markdown",
            "truncated": None if bounded is None else bounded["truncated"],
            "next_offset": None if bounded is None else bounded["next_offset"],
            "total_chars": None if bounded is None else bounded["total_chars"],
            "error_code": public.get("error_code"),
            "error_message": public.get("error_message"),
        },
        ensure_ascii=False,
    )


@tool
def ask_clarification(question: str, reason: str, affected_claim_keys: list[str] | None = None) -> str:
    """Pause for one human clarification. The answer becomes new equal-status text evidence."""
    ctx = require_run()
    persistence.increment_tool_count(ctx.run_id)
    keys = affected_claim_keys or []
    clarification = persistence.ensure_clarification(
        ctx.run_id,
        question=question,
        reason=reason,
        affected_claim_keys=keys,
    )
    if clarification.get("status") == "answered" and clarification.get("answer_text"):
        return json.dumps(
            {
                "answer": clarification.get("answer_text"),
                "material_id": clarification.get("answer_material_id"),
                "note": "Reused idempotent clarification evidence.",
            },
            ensure_ascii=False,
        )
    persistence.update_run(ctx.run_id, status="waiting_for_user")
    persistence.append_event(
        ctx.run_id,
        kind="clarification",
        title="Asked a clarification",
        detail=question,
        payload={"reason": reason, "affected_claim_keys": keys},
    )
    answer = interrupt(
        {
            "type": "clarification",
            "question": question,
            "reason": reason,
            "affected_claim_keys": keys,
            "run_id": ctx.run_id,
        }
    )
    text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
    if not str(text).strip():
        return json.dumps({"error": "clarification answer was blank", "persisted": False})
    existing_material = clarification.get("answer_material_id") if clarification else None
    if existing_material and clarification.get("answer_text") == text:
        return json.dumps(
            {
                "answer": text,
                "material_id": existing_material,
                "note": "Reused idempotent clarification evidence.",
            },
            ensure_ascii=False,
        )
    try:
        imported = ingest.ingest_direct_text(
            ctx.project_id,
            text,
            label="Clarification answer",
        )
        material = imported["material"]
        material_id = material["id"]
        meta_note = "User clarification is equal-status text evidence; it does not overwrite earlier sources."
        persistence.answer_clarification(ctx.run_id, text, answer_material_id=material_id)
        run = persistence.get_run(ctx.run_id)
        snapshot = append_clarification_material(
            run.get("snapshot") or {},
            material,
            imported.get("spans") or [],
            clarification_id=clarification.get("id") or "",
            run_id=ctx.run_id,
            project_id=ctx.project_id,
        )
        persistence.replace_snapshot(ctx.run_id, snapshot)
        persistence.update_coverage(
            ctx.run_id,
            material_id,
            state="analyzed",
            detail=meta_note,
            needs_azure=False,
            filename="Clarification answer",
        )
        persistence.append_event(
            ctx.run_id,
            kind="user",
            title="Clarification answered",
            payload={"material_id": material_id},
        )
        return json.dumps(
            {
                "answer": text,
                "material_id": material_id,
                "note": meta_note,
            },
            ensure_ascii=False,
        )
    except Exception as exc:  # noqa: BLE001
        persistence.append_event(
            ctx.run_id,
            kind="status",
            title="Clarification persistence failed",
            detail=type(exc).__name__,
        )
        raise


@tool
def submit_modeling_draft(draft: dict) -> str:
    """Submit a source-grounded modeling draft. Cannot confirm a baseline or run a solver."""
    ctx = require_run()
    persistence.increment_tool_count(ctx.run_id)
    parsed = ModelingDraft.model_validate(draft)
    run = persistence.get_run(ctx.run_id)
    if run.get("stale_input"):
        return json.dumps(
            {
                "ok": False,
                "error": "stale_input",
                "message": "Frozen snapshot bytes are missing or no longer match. The draft was not saved.",
            }
        )
    coverage = run.get("coverage") or []
    incomplete = [
        item
        for item in coverage
        if (item.get("state") or "pending") in INCOMPLETE_COVERAGE
    ]
    if incomplete and parsed.completeness == "complete":
        payload = parsed.model_dump()
        payload["completeness"] = "partial"
        payload.setdefault("readiness_issues", [])
        payload["readiness_issues"].append(
            "Draft marked complete while one or more sources are still incomplete."
        )
        parsed = ModelingDraft.model_validate(payload)
    try:
        saved = persistence.save_draft(ctx.run_id, parsed)
    except (ValueError, persistence.StaleRunError) as exc:
        return json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)})
    persistence.append_event(
        ctx.run_id,
        kind="tool_result",
        title=f"Submitted {parsed.completeness} modeling draft v{saved['revision_no']}",
        payload={"draft_id": saved["id"]},
    )
    return json.dumps(
        {
            "ok": True,
            "draft_id": saved["id"],
            "revision_no": saved["revision_no"],
            "completeness": saved["completeness"],
            "solver": "not_executed",
            "baseline_confirmed": False,
        }
    )


def build_preview_payload(
    *,
    material: dict[str, Any],
    spans: list[dict[str, Any]],
    raw: bytes,
    content_url: str,
    start: int = 0,
    end: int = 4000,
    page: int | None = None,
    sheet: str | None = None,
    cell_ref: str | None = None,
    snapshot_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from .provenance import bound_text, select_matching_spans

    media = material.get("media_type") or ""
    derived = False
    lo = max(0, start)
    matched_spans = spans
    locator_hits = select_matching_spans(spans, page=page, sheet=sheet, cell_ref=cell_ref)
    if locator_hits:
        matched_spans = locator_hits
    elif page is not None or sheet or cell_ref:
        matched_spans = spans
    excerpt = ""
    coordinate_system = "unresolved"
    locator: dict[str, Any]
    if media.startswith("text/") or media in {"application/json", "text/csv", "text/markdown"}:
        text = raw.decode("utf-8", errors="replace")
        bounded = bound_text(text, start_offset=lo, end_offset=end, max_chars=4000)
        excerpt = bounded["excerpt"]
        coordinate_system = "original_text"
        locator = {
            "precision": "exact" if start or (end and end < bounded["total_chars"]) else (
                "whole_source" if bounded.get("whole_source") else "approximate"
            ),
            "start_offset": bounded["start_offset"],
            "end_offset": bounded["end_offset"],
            "total_chars": bounded["total_chars"],
            "next_offset": bounded["next_offset"],
            "truncated": bounded["truncated"],
            "window_start": bounded["start_offset"],
            "coordinate_system": coordinate_system,
        }
    elif media == "application/pdf":
        chosen = matched_spans[0] if matched_spans else (spans[0] if spans else None)
        excerpt = str((chosen or {}).get("excerpt") or "")
        shown_page = page if page is not None else (chosen or {}).get("page")
        coordinate_system = "pdf_page" if shown_page is not None else "source_span_excerpt"
        locator = {
            "precision": "exact" if shown_page is not None else "whole_source",
            "page": shown_page,
            "coordinate_system": coordinate_system,
            "in_page_highlight": False,
            "truncated": False,
        }
        if shown_page is not None:
            content_url = f"{content_url}#page={shown_page}"
    elif media.startswith("image/"):
        chosen = matched_spans[0] if matched_spans else (spans[0] if spans else None)
        region = (chosen or {}).get("region")
        excerpt = str((chosen or {}).get("excerpt") or "")
        coordinate_system = "image_region" if region else "full_image"
        locator = {
            "precision": "exact" if region else "whole_source",
            "region": region,
            "region_state": "full_image" if not region else "region",
            "coordinate_system": coordinate_system,
        }
    else:
        chosen = matched_spans[0] if matched_spans else (spans[0] if spans else None)
        excerpt = str((chosen or {}).get("excerpt") or "")
        coordinate_system = (chosen or {}).get("locator_kind") or "source_span_excerpt"
        locator = {
            "precision": "approximate" if excerpt else "whole_source",
            "page": (chosen or {}).get("page"),
            "sheet": (chosen or {}).get("sheet"),
            "cell_ref": (chosen or {}).get("cell_ref"),
            "source_span_id": (chosen or {}).get("id"),
            "region": (chosen or {}).get("region"),
            "coordinate_system": coordinate_system,
        }
    return {
        "material": material,
        "spans": matched_spans or spans,
        "coordinate_system": coordinate_system,
        "excerpt": excerpt,
        "derived": derived,
        "byte_size": len(raw),
        "locator": locator,
        "content_url": content_url,
        "snapshot": snapshot_meta,
        "frozen": bool(snapshot_meta and snapshot_meta.get("frozen")),
    }


TOOLS = [
    inspect_evidence,
    understand_material,
    read_source,
    ask_clarification,
    submit_modeling_draft,
]
