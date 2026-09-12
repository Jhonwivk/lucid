"""Pydantic request/response schemas for the persistence contract."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .states import (
    ConditionKind,
    EvidenceStatus,
    LocatorKind,
    MaterialKind,
    OwnerKind,
    PremiseStatus,
    ReviewStatus,
    RuleKind,
    SolveRunState,
    VersionState,
    WorkflowMaturity,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleIn(StrictModel):
    rule_kind: RuleKind
    statement: str
    review_status: ReviewStatus = "unreviewed"
    evidence_status: EvidenceStatus = "unknown"
    source_span_id: str | None = None
    condition_kind: ConditionKind | None = None
    premise_status: PremiseStatus | None = None
    premise_text: str | None = None
    cost: float | None = None
    capacity: float | None = None
    permission: bool | None = None


class FormalModelIn(StrictModel):
    name: str = "untitled-model"
    version_state: VersionState = "draft"
    variable_count: int | None = None
    constraint_count: int | None = None
    objective_text: str | None = None
    notes: str | None = None


class ResultCandidateIn(StrictModel):
    label: str | None = None
    objective_value: float | None = None
    is_selected: bool | None = None
    notes: str | None = None


class ProjectCreate(StrictModel):
    title: str = Field(min_length=1)
    summary: str | None = None
    decision_question: str | None = None
    workflow_maturity: WorkflowMaturity = "open"


class ProjectPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1)
    summary: str | None = None
    decision_question: str | None = None
    workflow_maturity: WorkflowMaturity | None = None


class MaterialCreate(StrictModel):
    filename: str = Field(min_length=1)
    media_type: str | None = None
    kind: MaterialKind = "document"
    byte_size: int | None = None
    checksum: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] | None = None


class DirectTextCreate(StrictModel):
    text: str
    label: str | None = None


class SourceSpanCreate(StrictModel):
    material_id: str
    locator_kind: LocatorKind = "unknown"
    page: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    sheet: str | None = None
    cell_ref: str | None = None
    region: dict[str, Any] | None = None
    excerpt: str | None = None


class UnderstandingCreate(StrictModel):
    summary: str | None = None
    version_state: VersionState = "draft"
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    rules: list[RuleIn] = Field(default_factory=list)


class ScenarioCreate(StrictModel):
    name: str = Field(min_length=1)
    notes: str | None = None
    version_state: VersionState = "draft"
    based_on_understanding_id: str | None = None
    formal_model: FormalModelIn | None = None
    rules: list[RuleIn] = Field(default_factory=list)


class ScenarioRevisionCreate(StrictModel):
    notes: str | None = None
    version_state: VersionState = "draft"
    based_on_understanding_id: str | None = None
    formal_model: FormalModelIn | None = None
    rules: list[RuleIn] = Field(default_factory=list)


class SolveRunCreate(StrictModel):
    scenario_revision_id: str
    formal_model_id: str | None = None
    run_state: SolveRunState = "pending"
    message: str | None = None
    candidate: ResultCandidateIn | None = None


class RuleOut(StrictModel):
    id: str
    project_id: str
    owner_kind: OwnerKind
    understanding_revision_id: str | None
    scenario_revision_id: str | None
    rule_kind: RuleKind
    statement: str
    review_status: ReviewStatus
    evidence_status: EvidenceStatus
    source_span_id: str | None
    condition_kind: ConditionKind | None
    premise_status: PremiseStatus | None
    premise_text: str | None
    cost: float | None
    capacity: float | None
    permission: bool | None
    created_at: str


class MaterialOut(StrictModel):
    id: str
    project_id: str
    filename: str
    media_type: str | None
    kind: MaterialKind
    byte_size: int | None
    checksum: str | None
    notes: str | None
    metadata: dict[str, Any] | None = None
    created_at: str


class SourceSpanOut(StrictModel):
    id: str
    project_id: str
    material_id: str
    locator_kind: LocatorKind
    page: int | None
    start_offset: int | None
    end_offset: int | None
    sheet: str | None
    cell_ref: str | None
    region: dict[str, Any] | None
    excerpt: str | None
    created_at: str


class MaterialImportOut(StrictModel):
    material: MaterialOut
    spans: list[SourceSpanOut] = Field(default_factory=list)


class FormalModelOut(StrictModel):
    id: str
    project_id: str
    scenario_revision_id: str | None
    name: str
    version_state: VersionState
    variable_count: int | None
    constraint_count: int | None
    objective_text: str | None
    notes: str | None
    created_at: str


class UnderstandingOut(StrictModel):
    id: str
    project_id: str
    revision_no: int
    parent_revision_id: str | None
    version_state: VersionState
    summary: str | None
    assumptions: list[str]
    unknowns: list[str]
    conflicts: list[str]
    rules: list[RuleOut]
    created_at: str


class UnderstandingLineageItem(StrictModel):
    id: str
    revision_no: int
    parent_revision_id: str | None
    version_state: VersionState
    created_at: str


class ScenarioRevisionOut(StrictModel):
    id: str
    scenario_id: str
    project_id: str
    revision_no: int
    parent_revision_id: str | None
    version_state: VersionState
    based_on_understanding_id: str | None
    formal_model_id: str | None
    notes: str | None
    formal_model: FormalModelOut | None = None
    rules: list[RuleOut] = Field(default_factory=list)
    created_at: str


class ScenarioRevisionLineageItem(StrictModel):
    id: str
    revision_no: int
    parent_revision_id: str | None
    version_state: VersionState
    formal_model_id: str | None
    created_at: str


class ScenarioOut(StrictModel):
    id: str
    project_id: str
    name: str
    revisions: list[ScenarioRevisionOut]
    created_at: str


class ScenarioLineageItem(StrictModel):
    id: str
    name: str
    created_at: str
    revisions: list[ScenarioRevisionLineageItem]


class ResultCandidateOut(StrictModel):
    id: str
    project_id: str
    solve_run_id: str
    label: str | None
    objective_value: float | None
    is_selected: bool | None
    notes: str | None
    created_at: str


class SolveRunOut(StrictModel):
    id: str
    project_id: str
    scenario_revision_id: str
    formal_model_id: str | None
    run_state: SolveRunState
    claimed_execution: bool
    execution: str
    solver_name: str | None
    started_at: str | None
    finished_at: str | None
    message: str | None
    candidates: list[ResultCandidateOut] = Field(default_factory=list)
    created_at: str


class SolveRunLineageItem(StrictModel):
    id: str
    run_state: SolveRunState
    claimed_execution: bool
    execution: str
    created_at: str


class ChangeEventOut(StrictModel):
    id: str
    project_id: str
    event_type: str
    entity_kind: str
    entity_id: str
    summary: str
    payload: dict | list | None = None
    created_at: str


class LatestPointers(StrictModel):
    understanding_revision_id: str | None
    understanding_revision_no: int | None
    scenario_id: str | None
    scenario_revision_id: str | None
    scenario_revision_no: int | None
    formal_model_id: str | None
    solve_run_id: str | None
    modeling_run_id: str | None = None
    modeling_draft_id: str | None = None
    baseline_id: str | None = None


class ProjectLineage(StrictModel):
    understandings: list[UnderstandingLineageItem]
    scenarios: list[ScenarioLineageItem]
    solve_runs: list[SolveRunLineageItem]
    events: list[ChangeEventOut]


class TemplateSummary(StrictModel):
    id: str
    name_en: str
    name_zh: str
    category: str
    description_en: str
    description_zh: str
    source_types: list[str]
    source_count: int


class ProjectSummary(StrictModel):
    id: str
    title: str
    summary: str | None
    decision_question: str | None = None
    workflow_maturity: WorkflowMaturity
    is_demo: bool
    latest: LatestPointers
    created_at: str
    updated_at: str


class ProjectDetail(ProjectSummary):
    lineage: ProjectLineage
    materials: list[MaterialOut] = Field(default_factory=list)


class ModelingRunCreate(StrictModel):
    question: str = Field(min_length=1)


class ClarificationAnswer(StrictModel):
    answer: str = Field(min_length=1)

    @field_validator("answer")
    @classmethod
    def answer_must_be_nonblank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("a nonblank clarification answer is required")
        return stripped


class ClaimReviewIn(StrictModel):
    action: str
    edited_text: str | None = None


class BaselineFreezeIn(StrictModel):
    draft_id: str


class ComposerStartIn(StrictModel):
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)
    text: str | None = None
    text_label: str | None = None
