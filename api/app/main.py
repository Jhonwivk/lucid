"""LUCID API — health, workspace shell metadata, persistence contract."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .db import ensure_database
from .importers import INTAKE_CAPABILITY
from .modeling.checkpointer import get_checkpointer
from .modeling_routes import router as modeling_router
from .routes import router as persistence_router
from .runtime_config import snapshot

WORKSPACES = (
    {
        "id": "materials",
        "label": "Materials",
        "title": "Materials",
        "summary": "Record whatever business evidence you currently have — entered text and/or uploaded files — as a non-empty Evidence Set. No source type is required.",
        "status": "ready",
    },
    {
        "id": "modeling",
        "label": "Modeling",
        "title": "Modeling",
        "summary": "One Business Modeling Agent drafts a source-grounded baseline for human review. This is not a solver.",
        "status": "ready",
    },
    {
        "id": "understanding",
        "label": "Understanding",
        "title": "Understanding",
        "summary": "Compatibility route for Modeling. Review provenance, conflicts, assumptions, and unknowns before confirming a baseline.",
        "status": "compat",
    },
    {
        "id": "baseline",
        "label": "Baseline",
        "title": "Baseline",
        "summary": "Confirmed immutable pre-solver handoff. Scenarios remain available as a compatibility name.",
        "status": "ready",
    },
    {
        "id": "scenarios",
        "label": "Scenarios",
        "title": "Scenarios",
        "summary": "Compatibility route for Baseline / versioned formalization metadata. Solver is not implemented.",
        "status": "compat",
    },
    {
        "id": "results",
        "label": "Results",
        "title": "Results",
        "summary": "Pre-solver boundary. Deterministic solving is Stage 2.",
        "status": "pre_solver",
    },
)


class HealthResponse(BaseModel):
    status: str
    service: str
    time: str
    database: str


class WorkspaceMeta(BaseModel):
    id: str
    label: str
    title: str
    summary: str
    status: str


class ShellResponse(BaseModel):
    product: str
    tagline: str
    mode: str
    workspaces: list[WorkspaceMeta]
    capabilities: dict[str, str]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_database()
    get_checkpointer()
    try:
        yield
    finally:
        from .modeling.checkpointer import close_checkpointer

        close_checkpointer()


app = FastAPI(title="LUCID API", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(persistence_router)
app.include_router(modeling_router)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_file = ensure_database()
    db_state = "ready" if Path(db_file).exists() else "missing"
    return HealthResponse(
        status="ok",
        service="lucid-api",
        time=datetime.now(timezone.utc).isoformat(),
        database=db_state,
    )


@app.get("/api/shell", response_model=ShellResponse)
def shell() -> ShellResponse:
    ready = snapshot()
    understanding = (
        "implemented"
        if ready["live_agent_possible"]
        else "implemented_awaiting_model_config"
    )
    return ShellResponse(
        product="LUCID",
        tagline="Business modeling workbench — pre-solver",
        mode="single-user",
        workspaces=[WorkspaceMeta(**item) for item in WORKSPACES],
        capabilities={
            "import": INTAKE_CAPABILITY,
            "direct_text": "implemented",
            "ocr": "not_implemented",
            "csv_xlsx": "implemented",
            "png_jpeg": "implemented",
            "json_office_raw": "implemented",
            "understanding": understanding,
            "modeling_agent": understanding,
            "azure_content_understanding": (
                "configured" if ready["live_azure_possible"] else "not_configured"
            ),
            "solver": "not_yet_implemented",
            "export": "baseline_handoff",
            "llm_assist": understanding,
        },
    )


__all__ = ["app", "ensure_database"]
