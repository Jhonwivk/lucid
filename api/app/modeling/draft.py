"""Generic modeling-draft contract. No business-specific extraction rules."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Precision = Literal["exact", "approximate", "whole_source", "unresolved"]
Grounding = Literal["explicit", "inferred", "assumed"]
ClaimKind = Literal[
    "decision",
    "entity",
    "parameter",
    "variable",
    "constraint",
    "objective",
    "assumption",
    "unknown",
    "conflict",
    "readiness",
]
ConstraintStrength = Literal["hard", "soft", "conditional"]
ObjectiveDirection = Literal["minimize", "maximize", "unknown"]
Completeness = Literal["complete", "partial"]
CoverageState = Literal[
    "analyzed",
    "partially_processed",
    "pending",
    "unavailable",
    "unsupported",
]
Modelability = Literal["ready", "blocked", "unknown", "not_applicable"]
ReviewAction = Literal["unreviewed", "accepted", "rejected", "needs_clarification", "not_applicable"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceRef(StrictModel):
    material_id: str
    source_span_id: str | None = None
    material_checksum: str | None = None
    precision: Precision = "unresolved"
    locator_kind: str | None = None
    coordinate_system: str = "unresolved"
    page: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    sheet: str | None = None
    cell_ref: str | None = None
    region: dict[str, Any] | None = None
    provider_locator: dict[str, Any] | None = None
    quote: str | None = None


class Claim(StrictModel):
    claim_key: str
    claim_kind: ClaimKind
    original_statement: str
    proposed_interpretation: str | None = None
    grounding: Grounding = "inferred"
    applicability: str | None = None
    review_status: ReviewAction = "unreviewed"
    modelability_status: Modelability = "unknown"
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class Parameter(StrictModel):
    claim_key: str
    name: str
    raw_value: str | None = None
    normalized_value: float | None = None
    unit: str | None = None
    grounding: Grounding = "explicit"
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class DecisionVariable(StrictModel):
    claim_key: str
    name: str
    domain: str | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class ConstraintClaim(StrictModel):
    claim_key: str
    strength: ConstraintStrength
    original_statement: str
    proposed_interpretation: str | None = None
    condition: str | None = None
    applicability: str | None = None
    exceptions: str | None = None
    grounding: Grounding = "inferred"
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    review_status: ReviewAction = "unreviewed"
    modelability_status: Modelability = "unknown"


class ObjectiveClaim(StrictModel):
    claim_key: str
    original_statement: str
    proposed_interpretation: str | None = None
    direction: ObjectiveDirection = "unknown"
    priority: str | None = None
    weight: float | None = None
    weight_stated: bool = False
    grounding: Grounding = "inferred"
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class MaterialCoverage(StrictModel):
    material_id: str
    filename: str
    state: CoverageState
    detail: str | None = None
    needs_azure: bool = False
    azure_operation_id: str | None = None


class DecisionBrief(StrictModel):
    what_to_decide: str
    scope: str | None = None
    time_horizon: str | None = None
    ambiguities: list[str] = Field(default_factory=list)


class ModelingDraft(StrictModel):
    completeness: Completeness = "partial"
    decision_brief: DecisionBrief
    entities: list[Claim] = Field(default_factory=list)
    parameters: list[Parameter] = Field(default_factory=list)
    decision_variables: list[DecisionVariable] = Field(default_factory=list)
    constraints: list[ConstraintClaim] = Field(default_factory=list)
    objectives: list[ObjectiveClaim] = Field(default_factory=list)
    assumptions: list[Claim] = Field(default_factory=list)
    unknowns: list[Claim] = Field(default_factory=list)
    conflicts: list[Claim] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    readiness_issues: list[str] = Field(default_factory=list)
    coverage: list[MaterialCoverage] = Field(default_factory=list)
    notes: str | None = None
