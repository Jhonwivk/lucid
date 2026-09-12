"""Minimal real API surface for the T03 persistence contract."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from . import ingest, store, template_catalog
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
    ScenarioOut,
    ScenarioRevisionCreate,
    ScenarioRevisionOut,
    SolveRunCreate,
    SolveRunOut,
    SourceSpanCreate,
    SourceSpanOut,
    UnderstandingCreate,
    UnderstandingOut,
    ChangeEventOut,
    TemplateSummary,
)

router = APIRouter()


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
    except store.NotFoundError as exc:
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


@router.get("/api/projects/{project_id}/solve-runs", response_model=list[SolveRunOut])
def list_solve_runs(project_id: str) -> list[SolveRunOut]:
    try:
        return [SolveRunOut.model_validate(item) for item in store.list_solve_runs(project_id)]
    except store.NotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/api/solve-runs/{run_id}", response_model=SolveRunOut)
def get_solve_run(run_id: str) -> SolveRunOut:
    try:
        return SolveRunOut.model_validate(store.get_solve_run(run_id))
    except store.NotFoundError as exc:
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
