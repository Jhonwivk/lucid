"""Minimal real API surface for the T03 persistence contract."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

from . import ingest, store, template_catalog
from .db import get_data_dir
from .schemas import (
    DirectTextCreate,
    MaterialCreate,
    MaterialImportOut,
    MaterialOut,
    ProjectCreate,
    ProjectDetail,
    ProjectPatch,
    ProjectSummary,
    ScenarioCreate,
    ScenarioFromBaselineCreate,
    ScenarioImpactPreviewCreate,
    ScenarioInvalidationCreate,
    ScenarioOut,
    ScenarioRevisionCreate,
    ScenarioRevisionOut,
    SolveRunCreate,
    SolveRunClaimCreate,
    SolveRunHeartbeatCreate,
    SolveRunCompleteCreate,
    SolveRunResumeCreate,
    SolveRunOut,
    ConflictExplanationIn,
    ScenarioImpactOut,
    ScenarioComparisonOut,
    WhatIfScenarioCreate,
    TrainingScheduleSolveCreate,
    PortfolioSolveCreate,
    SourceSpanCreate,
    SourceSpanOut,
    UnderstandingCreate,
    UnderstandingOut,
    ChangeEventOut,
    TemplateSummary,
)

router = APIRouter()


def resolve_material_path(project_id: str, material: dict) -> Path | None:
    """Resolve an imported material path without allowing traversal outside data/."""
    metadata = material.get("metadata") or {}
    stored_path = metadata.get("stored_path")
    if not isinstance(stored_path, str) or not stored_path.strip():
        return None
    data_root = get_data_dir().resolve()
    project_root = (data_root / "materials" / project_id).resolve()
    candidate = (data_root / stored_path).resolve()
    if project_root not in candidate.parents:
        return None
    return candidate


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, store.NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, store.ConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    raise exc


@router.post("/api/projects", response_model=ProjectDetail)
def create_project(payload: ProjectCreate) -> ProjectDetail:
    return ProjectDetail.model_validate(store.create_project(payload))


@router.get("/api/projects", response_model=list[ProjectSummary])
def list_projects() -> list[ProjectSummary]:
    return [ProjectSummary.model_validate(item) for item in store.list_projects()]


@router.get("/api/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str) -> ProjectDetail:
    try:
        return ProjectDetail.model_validate(store.get_project(project_id))
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.patch("/api/projects/{project_id}", response_model=ProjectDetail)
def patch_project(project_id: str, payload: ProjectPatch) -> ProjectDetail:
    try:
        return ProjectDetail.model_validate(store.patch_project(project_id, payload))
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.post("/api/projects/{project_id}/materials", response_model=MaterialOut)
def create_material(project_id: str, payload: MaterialCreate) -> MaterialOut:
    try:
        return MaterialOut.model_validate(store.create_material(project_id, payload))
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/projects/{project_id}/materials/import",
    response_model=MaterialImportOut,
)
async def import_material(
    project_id: str,
    file: UploadFile = File(..., description="Single source file. Field name: file."),
) -> MaterialImportOut:
    """Public file intake: TXT, Markdown, text-PDF, CSV, XLSX, PNG, or JPEG.

    Direct user-entered text uses POST /materials/text. No source family is
    required. Image intake records bytes and full-image provenance only;
    semantic understanding is T09.
    """
    try:
        store.get_project(project_id)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc

    filename = file.filename or ""
    try:
        ingest.sniff_media_type(filename)
    except ingest.UnsupportedMaterialError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    content = await file.read()
    try:
        result = ingest.ingest_bytes(project_id, filename, content)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc
    except ingest.ImportTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ingest.UnsupportedMaterialError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except ingest.UnreadableMaterialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MaterialImportOut.model_validate(result)


@router.post(
    "/api/projects/{project_id}/materials/text",
    response_model=MaterialImportOut,
)
def create_direct_text_material(
    project_id: str,
    payload: DirectTextCreate,
) -> MaterialImportOut:
    """Record pasted/typed text as a first-class Material in the Evidence Set."""
    try:
        store.get_project(project_id)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc
    try:
        result = ingest.ingest_direct_text(project_id, payload.text, payload.label)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc
    except ingest.ImportTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ingest.UnreadableMaterialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MaterialImportOut.model_validate(result)


@router.get("/api/projects/{project_id}/materials", response_model=list[MaterialOut])
def list_materials(project_id: str) -> list[MaterialOut]:
    try:
        return [MaterialOut.model_validate(item) for item in store.list_materials(project_id)]
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.delete("/api/projects/{project_id}/materials/{material_id}", response_model=MaterialOut)
def delete_material(project_id: str, material_id: str) -> MaterialOut:
    try:
        material = store.delete_material(project_id, material_id)
        try:
            path = resolve_material_path(project_id, material)
            if path is not None:
                path.unlink(missing_ok=True)
        except (FileNotFoundError, OSError, PermissionError):
            pass
        return MaterialOut.model_validate(material)
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/api/projects/{project_id}/source-spans", response_model=list[SourceSpanOut])
def list_source_spans(project_id: str) -> list[SourceSpanOut]:
    try:
        return [
            SourceSpanOut.model_validate(item)
            for item in store.list_source_spans(project_id)
        ]
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.post("/api/projects/{project_id}/source-spans", response_model=SourceSpanOut)
def create_source_span(project_id: str, payload: SourceSpanCreate) -> SourceSpanOut:
    try:
        return SourceSpanOut.model_validate(store.create_source_span(project_id, payload))
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/projects/{project_id}/understandings",
    response_model=UnderstandingOut,
)
def create_understanding(
    project_id: str, payload: UnderstandingCreate
) -> UnderstandingOut:
    try:
        return UnderstandingOut.model_validate(
            store.create_understanding(project_id, payload)
        )
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/api/projects/{project_id}/understandings",
    response_model=list[UnderstandingOut],
)
def list_understandings(project_id: str) -> list[UnderstandingOut]:
    try:
        return [
            UnderstandingOut.model_validate(item)
            for item in store.list_understandings(project_id)
        ]
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/api/understandings/{revision_id}", response_model=UnderstandingOut)
def get_understanding(revision_id: str) -> UnderstandingOut:
    try:
        return UnderstandingOut.model_validate(store.get_understanding(revision_id))
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/projects/{project_id}/scenarios/from-baseline/{baseline_id}",
    response_model=ScenarioOut,
)
def create_scenario_from_baseline(
    project_id: str, baseline_id: str, payload: ScenarioFromBaselineCreate
) -> ScenarioOut:
    try:
        return ScenarioOut.model_validate(
            store.create_scenario_from_baseline(project_id, baseline_id, payload)
        )
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.post("/api/projects/{project_id}/scenarios", response_model=ScenarioOut)
def create_scenario(project_id: str, payload: ScenarioCreate) -> ScenarioOut:
    try:
        return ScenarioOut.model_validate(store.create_scenario(project_id, payload))
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/api/projects/{project_id}/scenarios", response_model=list[ScenarioOut])
def list_scenarios(project_id: str) -> list[ScenarioOut]:
    try:
        return [
            ScenarioOut.model_validate(item) for item in store.list_scenarios(project_id)
        ]
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/api/scenarios/{scenario_id}", response_model=ScenarioOut)
def get_scenario(scenario_id: str) -> ScenarioOut:
    try:
        return ScenarioOut.model_validate(store.get_scenario(scenario_id))
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/scenarios/{scenario_id}/revisions",
    response_model=ScenarioRevisionOut,
)
def create_scenario_revision(
    scenario_id: str, payload: ScenarioRevisionCreate
) -> ScenarioRevisionOut:
    try:
        return ScenarioRevisionOut.model_validate(
            store.create_scenario_revision(scenario_id, payload)
        )
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/scenarios/{scenario_id}/what-if",
    response_model=ScenarioRevisionOut,
)
def create_what_if_scenario(
    scenario_id: str, payload: WhatIfScenarioCreate
) -> ScenarioRevisionOut:
    try:
        return ScenarioRevisionOut.model_validate(
            store.create_what_if_scenario(scenario_id, payload)
        )
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/scenarios/{scenario_id}/impact-preview",
    response_model=ScenarioImpactOut,
)
def preview_scenario_impact(
    scenario_id: str, payload: ScenarioImpactPreviewCreate
) -> ScenarioImpactOut:
    try:
        return ScenarioImpactOut.model_validate(
            store.preview_scenario_impact(scenario_id, payload)
        )
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.get(
    "/api/scenarios/{scenario_id}/compare",
    response_model=ScenarioComparisonOut,
)
def compare_scenario_revisions(
    scenario_id: str, left_revision_id: str, right_revision_id: str
) -> ScenarioComparisonOut:
    try:
        return ScenarioComparisonOut.model_validate(
            store.compare_scenario_revisions(
                scenario_id, left_revision_id, right_revision_id
            )
        )
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/scenario-revisions/{revision_id}/invalidate",
    response_model=ScenarioRevisionOut,
)
def invalidate_scenario_revision(
    revision_id: str, payload: ScenarioInvalidationCreate
) -> ScenarioRevisionOut:
    try:
        return ScenarioRevisionOut.model_validate(
            store.invalidate_scenario_revision(
                revision_id,
                reason=payload.reason,
                expected_version_state=payload.expected_version_state,
            )
        )
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.get(
    "/api/scenario-revisions/{revision_id}",
    response_model=ScenarioRevisionOut,
)
def get_scenario_revision(revision_id: str) -> ScenarioRevisionOut:
    try:
        return ScenarioRevisionOut.model_validate(
            store.get_scenario_revision(revision_id)
        )
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.post("/api/projects/{project_id}/solve-runs", response_model=SolveRunOut)
def create_solve_run(project_id: str, payload: SolveRunCreate) -> SolveRunOut:
    try:
        return SolveRunOut.model_validate(store.create_solve_run(project_id, payload))
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/projects/{project_id}/solve-training-schedule",
    response_model=SolveRunOut,
)
def execute_training_schedule(
    project_id: str, payload: TrainingScheduleSolveCreate
) -> SolveRunOut:
    try:
        return SolveRunOut.model_validate(
            store.execute_training_schedule(project_id, payload)
        )
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/projects/{project_id}/solve-portfolio",
    response_model=SolveRunOut,
)
def execute_portfolio(
    project_id: str, payload: PortfolioSolveCreate
) -> SolveRunOut:
    try:
        return SolveRunOut.model_validate(
            store.execute_portfolio(project_id, payload)
        )
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.get("/api/projects/{project_id}/solve-runs", response_model=list[SolveRunOut])
def list_solve_runs(project_id: str) -> list[SolveRunOut]:
    try:
        return [SolveRunOut.model_validate(item) for item in store.list_solve_runs(project_id)]
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/api/solve-runs/{run_id}", response_model=SolveRunOut)
def get_solve_run(run_id: str, project_id: str | None = None) -> SolveRunOut:
    try:
        return SolveRunOut.model_validate(store.get_solve_run(run_id, project_id=project_id))
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.post("/api/solve-runs/{run_id}/claim", response_model=SolveRunOut)
def claim_solve_run(
    run_id: str, payload: SolveRunClaimCreate, project_id: str | None = None
) -> SolveRunOut:
    try:
        return SolveRunOut.model_validate(
            store.claim_solve_run(
                run_id,
                owner=payload.owner,
                stale_after_seconds=payload.stale_after_seconds,
                project_id=project_id,
            )
        )
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.post("/api/solve-runs/{run_id}/heartbeat", response_model=SolveRunOut)
def heartbeat_solve_run(
    run_id: str, payload: SolveRunHeartbeatCreate, project_id: str | None = None
) -> SolveRunOut:
    try:
        return SolveRunOut.model_validate(
            store.heartbeat_solve_run(
                run_id, owner=payload.owner, claim_token=payload.claim_token, project_id=project_id
            )
        )
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.post("/api/solve-runs/{run_id}/complete", response_model=SolveRunOut)
def complete_solve_run(
    run_id: str, payload: SolveRunCompleteCreate, project_id: str | None = None
) -> SolveRunOut:
    try:
        return SolveRunOut.model_validate(
            store.complete_solve_run(
                run_id,
                owner=payload.owner,
                claim_token=payload.claim_token,
                run_state=payload.run_state,
                message=payload.message,
                solver_name=payload.solver_name,
                candidates=payload.candidates,
                project_id=project_id,
            )
        )
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.post("/api/projects/{project_id}/solve-runs/{run_id}/resume", response_model=SolveRunOut)
def resume_solve_run(
    project_id: str, run_id: str, payload: SolveRunResumeCreate
) -> SolveRunOut:
    try:
        return SolveRunOut.model_validate(
            store.resume_solve_run(
                project_id,
                run_id,
                owner=payload.owner,
                stale_after_seconds=payload.stale_after_seconds,
            )
        )
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.get("/api/projects/{project_id}/solve-runs/{run_id}/export.json")
def export_solve_run(project_id: str, run_id: str) -> dict:
    try:
        return store.export_solve_run(run_id, project_id=project_id)
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.get("/api/projects/{project_id}/solve-runs/{run_id}/export.md")
def export_solve_run_markdown(project_id: str, run_id: str) -> PlainTextResponse:
    try:
        document = store.export_solve_run(run_id, project_id=project_id)
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc
    solve = document["solve_run"]
    lines = [
        f"# LUCID solve run {solve['id'][:8]}",
        "",
        f"- Project: {document['project']['title']} ({document['project']['id']})",
        f"- Scenario revision: {document['scenario_revision']['revision_no']}",
        f"- State: {solve['run_state']}",
        f"- Solver: {solve.get('solver_name') or 'unknown'}",
        f"- Input fingerprint: {solve.get('input_fingerprint') or 'unknown'}",
        "",
        "## Candidates",
        "",
    ]
    for candidate in solve.get("candidates", []):
        lines.extend(
            [
                f"### {candidate.get('label') or candidate['id']}",
                f"- Objective value: {candidate.get('objective_value')}",
                "```json",
                json.dumps(candidate.get("result") or candidate.get("details") or {}, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Scenario input",
            "",
            "```json",
            json.dumps(
                {
                    "scenario": document.get("scenario"),
                    "scenario_revision": document.get("scenario_revision"),
                    "formal_model": document.get("formal_model"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
            "## Solver explanation",
            "",
            "```json",
            json.dumps(solve.get("explanation"), ensure_ascii=False, indent=2),
            "```",
            "",
            "## Provenance",
            "",
            f"- Materials: {len(document['provenance'].get('materials', []))} (full metadata is included below)",
            f"- Source spans: {len(document['provenance'].get('source_spans', []))}",
            f"- Related events: {len(document.get('events', []))}",
            "",
            "```json",
            json.dumps(document["provenance"], ensure_ascii=False, indent=2),
            "```",
        ]
    )
    filename = f'lucid-solve-run-{run_id[:8]}.md'
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/api/solve-runs/{run_id}/explanation",
    response_model=SolveRunOut,
)
def record_solver_explanation(
    run_id: str, payload: ConflictExplanationIn, project_id: str | None = None
) -> SolveRunOut:
    try:
        return SolveRunOut.model_validate(
            store.record_solver_explanation(run_id, payload, project_id=project_id)
        )
    except (store.NotFoundError, store.ConflictError) as exc:
        raise _http_error(exc) from exc


@router.get("/api/projects/{project_id}/events", response_model=list[ChangeEventOut])
def list_events(project_id: str) -> list[ChangeEventOut]:
    try:
        return [ChangeEventOut.model_validate(item) for item in store.list_events(project_id)]
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/api/templates", response_model=list[TemplateSummary])
def list_templates() -> list[TemplateSummary]:
    try:
        return [TemplateSummary.model_validate(item) for item in template_catalog.list_templates()]
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/templates/{template_id}/instantiate", response_model=ProjectDetail)
def instantiate_template(template_id: str) -> ProjectDetail:
    try:
        return ProjectDetail.model_validate(template_catalog.instantiate_template(template_id))
    except template_catalog.TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/dev/seed-demo", response_model=ProjectDetail)
def seed_demo() -> ProjectDetail:
    """Explicit demo path. Marked is_demo; not a real planning result."""
    return ProjectDetail.model_validate(store.seed_demo_project())
