"""Distinct state vocabularies for the T03 persistence contract.

These axes must not be collapsed into a single status field:

- workflow maturity (product/workspace progress)
- review / evidence status (human review of rules and sources)
- version state (scenario / model / understanding revisions)
- solver run state (SolveRun only; not a business-truth claim)
"""

from __future__ import annotations

from typing import Final, Literal, get_args

WorkflowMaturity = Literal[
    "open",
    "materials",
    "understanding",
    "scenarios",
    "results",
    "archived",
]

ReviewStatus = Literal[
    "unreviewed",
    "accepted",
    "rejected",
    "needs_clarification",
    "not_applicable",
]

EvidenceStatus = Literal[
    "present",
    "missing",
    "unknown",
    "conflicted",
]

PremiseStatus = Literal[
    "known_true",
    "known_false",
    "unknown",
    "missing",
]

ConditionKind = Literal["always", "if_then", "unknown"]

RuleKind = Literal["hard", "soft", "conditional", "objective", "assumption"]

VersionState = Literal["draft", "confirmed", "superseded", "invalidated"]

SolveRunState = Literal[
    "pending",
    "running",
    "feasible",
    "optimal",
    "infeasible",
    "unknown",
    "model_invalid",
    "failed",
    "cancelled",
]

MaterialKind = Literal["document", "table", "image", "other", "unknown"]

LocatorKind = Literal["text_range", "page", "cell", "region", "unknown"]

OwnerKind = Literal["understanding", "scenario"]


def _sql_in(values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{item}'" for item in values)
    return f"({quoted})"


WORKFLOW_MATURITY_VALUES: Final[tuple[str, ...]] = get_args(WorkflowMaturity)
REVIEW_STATUS_VALUES: Final[tuple[str, ...]] = get_args(ReviewStatus)
EVIDENCE_STATUS_VALUES: Final[tuple[str, ...]] = get_args(EvidenceStatus)
PREMISE_STATUS_VALUES: Final[tuple[str, ...]] = get_args(PremiseStatus)
CONDITION_KIND_VALUES: Final[tuple[str, ...]] = get_args(ConditionKind)
RULE_KIND_VALUES: Final[tuple[str, ...]] = get_args(RuleKind)
VERSION_STATE_VALUES: Final[tuple[str, ...]] = get_args(VersionState)
SOLVE_RUN_STATE_VALUES: Final[tuple[str, ...]] = get_args(SolveRunState)
MATERIAL_KIND_VALUES: Final[tuple[str, ...]] = get_args(MaterialKind)
LOCATOR_KIND_VALUES: Final[tuple[str, ...]] = get_args(LocatorKind)
OWNER_KIND_VALUES: Final[tuple[str, ...]] = get_args(OwnerKind)

WORKFLOW_MATURITY_SQL = _sql_in(WORKFLOW_MATURITY_VALUES)
REVIEW_STATUS_SQL = _sql_in(REVIEW_STATUS_VALUES)
EVIDENCE_STATUS_SQL = _sql_in(EVIDENCE_STATUS_VALUES)
PREMISE_STATUS_SQL = _sql_in(PREMISE_STATUS_VALUES)
CONDITION_KIND_SQL = _sql_in(CONDITION_KIND_VALUES)
RULE_KIND_SQL = _sql_in(RULE_KIND_VALUES)
VERSION_STATE_SQL = _sql_in(VERSION_STATE_VALUES)
SOLVE_RUN_STATE_SQL = _sql_in(SOLVE_RUN_STATE_VALUES)
MATERIAL_KIND_SQL = _sql_in(MATERIAL_KIND_VALUES)
LOCATOR_KIND_SQL = _sql_in(LOCATOR_KIND_VALUES)
OWNER_KIND_SQL = _sql_in(OWNER_KIND_VALUES)
