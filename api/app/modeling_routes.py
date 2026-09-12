"""Modeling Agent, review, baseline, and material content routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response

from . import store
from .modeling import persistence, runner
from .modeling.snapshot import SnapshotIntegrityError, get_snapshot_material, list_snapshot_spans, read_snapshot_bytes, snapshot_public_meta
from .modeling.tools import build_preview_payload, resolve_material_path
from .runtime_config import snapshot
from .schemas import (
    BaselineFreezeIn,
    ClaimReviewIn,
    ClarificationAnswer,
    ComposerStartIn,
    ModelingRunCreate,
    ProjectCreate,
)

router = APIRouter()


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, store.NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, store.ConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    raise exc


@router.get("/api/readiness")
def readiness() -> dict:
    return snapshot()


@router.post("/api/projects/{project_id}/modeling-runs")
def start_modeling_run(project_id: str, payload: ModelingRunCreate) -> dict:
    try:
        return runner.start_run(project_id, payload.question)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/api/projects/{project_id}/modeling-runs")
def list_modeling_runs(project_id: str) -> list[dict]:
    try:
        return persistence.list_runs(project_id)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/api/modeling-runs/{run_id}")
def get_modeling_run(run_id: str) -> dict:
    try:
        return persistence.get_run(run_id)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.post("/api/modeling-runs/{run_id}/resume")
def resume_modeling_run(run_id: str, payload: ClarificationAnswer) -> dict:
    try:
        return runner.resume_run(run_id, payload.answer)
    except (store.NotFoundError, store.ConflictError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post("/api/modeling-runs/{run_id}/cancel")
def cancel_modeling_run(run_id: str) -> dict:
    try:
        return runner.cancel_run(run_id)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/api/projects/{project_id}/drafts")
def list_drafts(project_id: str) -> list[dict]:
    try:
        return persistence.list_drafts(project_id)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/api/drafts/{draft_id}")
def get_draft(draft_id: str) -> dict:
    try:
        return persistence.get_draft(draft_id)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.post("/api/claims/{claim_id}/review")
def review_claim(claim_id: str, payload: ClaimReviewIn) -> dict:
    try:
        return persistence.review_claim(
            claim_id, action=payload.action, edited_text=payload.edited_text
        )
    except (store.NotFoundError, store.ConflictError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.get("/api/claims/{claim_id}/history")
def claim_history(claim_id: str) -> list[dict]:
    try:
        persistence.get_claim(claim_id)
        return persistence.list_claim_review_events(claim_id)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.post("/api/projects/{project_id}/baseline/freeze")
def freeze_baseline(project_id: str, payload: BaselineFreezeIn) -> dict:
    try:
        return persistence.freeze_baseline(project_id, payload.draft_id)
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.get("/api/projects/{project_id}/baselines")
def list_baselines(project_id: str) -> list[dict]:
    try:
        return persistence.list_baselines(project_id)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/api/baselines/{baseline_id}")
def get_baseline(baseline_id: str) -> dict:
    try:
        return persistence.get_baseline(baseline_id)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/api/baselines/{baseline_id}/export.md")
def export_baseline_markdown(baseline_id: str) -> PlainTextResponse:
    try:
        baseline = persistence.get_baseline(baseline_id)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc
    filename = f"lucid-baseline-{baseline_id[:8]}.md"
    return PlainTextResponse(
        baseline["markdown"],
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/baselines/{baseline_id}/export.json")
def export_baseline_json(baseline_id: str) -> JSONResponse:
    try:
        baseline = persistence.get_baseline(baseline_id)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc
    filename = f"lucid-baseline-{baseline_id[:8]}.json"
    return JSONResponse(
        baseline["handoff"],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/projects/{project_id}/materials/{material_id}/content")
def material_content(project_id: str, material_id: str) -> FileResponse:
    try:
        material = store.get_material(project_id, material_id)
        path = resolve_material_path(project_id, material)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="material path is not readable") from exc
    media = material.get("media_type") or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media,
        filename=material.get("filename") or path.name,
        content_disposition_type="inline",
    )


@router.get("/api/projects/{project_id}/materials/{material_id}/preview")
def material_preview(
    project_id: str,
    material_id: str,
    start: int = 0,
    end: int = 4000,
    page: int | None = None,
    sheet: str | None = None,
    cell_ref: str | None = None,
) -> dict:
    try:
        material = store.get_material(project_id, material_id)
        spans = [
            span
            for span in store.list_source_spans(project_id)
            if span["material_id"] == material_id
        ]
        path = resolve_material_path(project_id, material)
        raw = path.read_bytes()
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="material path is not readable") from exc
    return build_preview_payload(
        material=material,
        spans=spans,
        raw=raw,
        content_url=f"/api/projects/{project_id}/materials/{material_id}/content",
        start=start,
        end=end,
        page=page,
        sheet=sheet,
        cell_ref=cell_ref,
        snapshot_meta={"frozen": False, "role": "live"},
    )


@router.get("/api/modeling-runs/{run_id}/materials/{material_id}/content")
def snapshot_material_content(run_id: str, material_id: str) -> FileResponse:
    try:
        run = persistence.get_run(run_id)
        material = get_snapshot_material(run, material_id)
        if material is None:
            raise store.NotFoundError("material not found in this run snapshot")
        raw = read_snapshot_bytes(run, material)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc
    except SnapshotIntegrityError as exc:
        persistence.mark_stale_input(run_id, reason=str(exc))
        raise HTTPException(status_code=409, detail=f"stale_input: {exc}") from exc
    media = material.get("media_type") or "application/octet-stream"
    filename = material.get("filename") or "snapshot"
    return Response(
        content=raw,
        media_type=media,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/api/modeling-runs/{run_id}/materials/{material_id}/preview")
def snapshot_material_preview(
    run_id: str,
    material_id: str,
    start: int = 0,
    end: int = 4000,
    page: int | None = None,
    sheet: str | None = None,
    cell_ref: str | None = None,
) -> dict:
    try:
        run = persistence.get_run(run_id)
        material = get_snapshot_material(run, material_id)
        if material is None:
            raise store.NotFoundError("material not found in this run snapshot")
        spans = list_snapshot_spans(run, material_id)
        raw = read_snapshot_bytes(run, material)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc
    except SnapshotIntegrityError as exc:
        persistence.mark_stale_input(run_id, reason=str(exc))
        raise HTTPException(status_code=409, detail=f"stale_input: {exc}") from exc
    return build_preview_payload(
        material=material,
        spans=spans,
        raw=raw,
        content_url=f"/api/modeling-runs/{run_id}/materials/{material_id}/content",
        start=start,
        end=end,
        page=page,
        sheet=sheet,
        cell_ref=cell_ref,
        snapshot_meta=snapshot_public_meta(material),
    )

@router.post("/api/analyses/start")
def composer_start(payload: ComposerStartIn) -> dict:
    """Create an analysis from a question, optional extra text, then existing peer intake for files."""
    from . import ingest

    created = store.create_project(
        ProjectCreate(
            title=payload.title,
            summary=payload.question,
            decision_question=payload.question,
        )
    )
    persistence.ensure_question_material(created["id"], payload.question)
    if payload.text and payload.text.strip() and payload.text.strip() != payload.question.strip():
        ingest.ingest_direct_text(
            created["id"],
            payload.text,
            label=payload.text_label or "Pasted text",
        )
    return store.get_project(created["id"])
