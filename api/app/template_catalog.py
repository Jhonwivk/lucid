"""Auditable built-in template fixtures for T05.

This module seeds known semantic ground truth from repository manifests. It is
not a general document parser, OCR pipeline, vision model, or LLM extractor.
Source files are still read as real bytes so persisted size/checksum metadata is
truthful and provenance locators point at actual fixture files.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from . import store
from .schemas import (
    FormalModelIn,
    MaterialCreate,
    ProjectCreate,
    ResultCandidateIn,
    RuleIn,
    ScenarioCreate,
    SolveRunCreate,
    SourceSpanCreate,
    UnderstandingCreate,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "templates"


class TemplateNotFoundError(LookupError):
    pass


TEMPLATE_ORDER = (
    "training-schedule",
    "vehicle-validation-bench",
    "factory-maintenance-window",
    "supplier-capacity-allocation",
    "product-portfolio-selection",
    "retail-campaign-slotting",
)

CATEGORIES = frozenset({"scheduling", "allocation", "portfolio"})
EXPECTED_KEYS = (
    "materials",
    "source_spans",
    "understandings",
    "understanding_rules",
    "scenarios",
    "scenario_revisions",
    "scenario_rules",
    "solve_runs",
    "media_types",
    "must_preserve_null",
    "solve_execution",
)

GENERATED_ASSETS = (
    "training-schedule/leadership-memo.pdf",
    "vehicle-validation-bench/validation-plan.xlsx",
    "vehicle-validation-bench/bench-requirements.pdf",
    "vehicle-validation-bench/bench-layout.png",
    "factory-maintenance-window/line-layout.png",
    "supplier-capacity-allocation/supplier-capacity.xlsx",
    "supplier-capacity-allocation/quality-note.pdf",
)


def ensure_binary_fixtures() -> None:
    if all((FIXTURE_ROOT / relative).is_file() for relative in GENERATED_ASSETS):
        return
    script = FIXTURE_ROOT.parents[1] / "scripts" / "generate_template_binary_fixtures.py"
    spec = importlib.util.spec_from_file_location("lucid_template_fixture_generator", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load template fixture generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()
    missing = [relative for relative in GENERATED_ASSETS if not (FIXTURE_ROOT / relative).is_file()]
    if missing:
        raise RuntimeError(f"template binary fixtures were not generated: {missing}")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"template payload must be an object: {path}")
    return payload


def _template_dir(template_id: str) -> Path:
    safe = template_id.strip()
    if not safe or safe != Path(safe).name or safe.startswith("."):
        raise TemplateNotFoundError("template not found")
    directory = FIXTURE_ROOT / safe
    if not directory.is_dir():
        raise TemplateNotFoundError("template not found")
    return directory


def _manifest(template_id: str) -> dict[str, Any]:
    path = _template_dir(template_id) / "template.json"
    if not path.is_file():
        raise TemplateNotFoundError("template not found")
    payload = _load_json(path)
    if payload.get("id") != template_id:
        raise ValueError(f"template id mismatch: {template_id}")
    return payload


def _localized(payload: dict[str, Any], field: str, template_id: str) -> None:
    value = payload.get(field)
    if not isinstance(value, dict) or not str(value.get("en") or "").strip() or not str(value.get("zh-CN") or "").strip():
        raise ValueError(f"{template_id}: {field} must include en and zh-CN")


def _validate_manifest(template_id: str, payload: dict[str, Any]) -> None:
    _localized(payload, "name", template_id)
    _localized(payload, "description", template_id)
    if payload.get("category") not in CATEGORIES:
        raise ValueError(f"{template_id}: unknown category {payload.get('category')!r}")
    project = payload.get("project")
    if not isinstance(project, dict) or not str(project.get("title", "")).startswith("[TEMPLATE]"):
        raise ValueError(f"{template_id}: project title must start with [TEMPLATE]")
    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) < 2:
        raise ValueError(f"{template_id}: mixed-material templates need at least two sources")
    directory = _template_dir(template_id)
    span_keys: set[str] = set()
    for source in sources:
        filename = source.get("filename")
        if not filename or not source.get("label") or not source.get("media_type") or not source.get("kind"):
            raise ValueError(f"{template_id}: source is missing filename/label/media_type/kind")
        path = directory / filename
        if not path.is_file():
            raise FileNotFoundError(f"{template_id}: source missing: {filename}")
        for span in source.get("spans") or []:
            key = span.get("key")
            if not key:
                raise ValueError(f"{template_id}: source span missing key in {filename}")
            if key in span_keys:
                raise ValueError(f"{template_id}: duplicate source span key {key}")
            span_keys.add(key)
    understanding = payload.get("understanding")
    if not isinstance(understanding, dict):
        raise ValueError(f"{template_id}: understanding is required")
    for field in ("assumptions", "unknowns", "conflicts", "rules"):
        items = understanding.get(field)
        if not isinstance(items, list) or len(items) == 0:
            raise ValueError(f"{template_id}: understanding.{field} must be a non-empty list")
    scenario = payload.get("scenario")
    if not isinstance(scenario, dict) or not scenario.get("name") or not scenario.get("formal_model"):
        raise ValueError(f"{template_id}: scenario with formal_model is required")
    rules = list(understanding.get("rules") or []) + list(scenario.get("rules") or [])
    for rule in rules:
        key = rule.get("source_span_key")
        if key is not None and key not in span_keys:
            raise ValueError(f"{template_id}: unknown source_span_key {key}")
    solve = payload.get("solve_run") or {}
    candidate = solve.get("candidate") or {}
    if candidate.get("objective_value") is not None:
        raise ValueError(f"{template_id}: template must not claim a solved objective")


def _validate_expected(template_id: str, manifest: dict[str, Any], expected: dict[str, Any]) -> None:
    missing = [key for key in EXPECTED_KEYS if key not in expected]
    if missing:
        raise ValueError(f"{template_id}: expected.json missing {missing}")
    if expected.get("solve_execution") != "not_executed":
        raise ValueError(f"{template_id}: expected solve_execution must be not_executed")
    if expected.get("materials") != len(manifest.get("sources") or []):
        raise ValueError(f"{template_id}: expected materials count does not match sources")
    if expected.get("understandings") < 1 or expected.get("scenarios") < 1:
        raise ValueError(f"{template_id}: expected understanding and scenario counts")
    if expected.get("understanding_rules") != len(manifest["understanding"]["rules"]):
        raise ValueError(f"{template_id}: expected understanding_rules does not match manifest")
    if expected.get("scenario_rules") != len(manifest["scenario"].get("rules") or []):
        raise ValueError(f"{template_id}: expected scenario_rules does not match manifest")


def validate_catalog() -> None:
    """Fail fast if any built-in template pack is incomplete or dishonest."""
    ensure_binary_fixtures()
    for template_id in TEMPLATE_ORDER:
        manifest = _manifest(template_id)
        _validate_manifest(template_id, manifest)
        _validate_expected(template_id, manifest, load_expected(template_id))


def list_templates() -> list[dict[str, Any]]:
    validate_catalog()
    rows: list[dict[str, Any]] = []
    for template_id in TEMPLATE_ORDER:
        payload = _manifest(template_id)
        sources = payload.get("sources", [])
        rows.append(
            {
                "id": payload["id"],
                "name_en": payload["name"]["en"],
                "name_zh": payload["name"]["zh-CN"],
                "category": payload["category"],
                "description_en": payload["description"]["en"],
                "description_zh": payload["description"]["zh-CN"],
                "source_types": [str(item["label"]) for item in sources],
                "source_count": len(sources),
            }
        )
    return rows


def _rule(payload: dict[str, Any], span_ids: dict[str, str]) -> RuleIn:
    values = dict(payload)
    span_key = values.pop("source_span_key", None)
    if span_key is not None:
        values["source_span_id"] = span_ids[span_key]
    return RuleIn(**values)


def instantiate_template(template_id: str) -> dict[str, Any]:
    validate_catalog()
    manifest = _manifest(template_id)
    directory = _template_dir(template_id)
    project_payload = manifest["project"]
    project = store.create_project(
        ProjectCreate(
            title=project_payload["title"],
            summary=project_payload.get("summary"),
            workflow_maturity=project_payload.get("workflow_maturity", "scenarios"),
        )
    )
    project_id = project["id"]

    span_ids: dict[str, str] = {}
    for source in manifest.get("sources", []):
        source_path = directory / source["filename"]
        if not source_path.is_file():
            raise FileNotFoundError(f"template source missing: {source_path}")
        content = source_path.read_bytes()
        material = store.create_material(
            project_id,
            MaterialCreate(
                filename=source["filename"],
                media_type=source.get("media_type"),
                kind=source.get("kind", "document"),
                byte_size=len(content),
                checksum=f"sha256:{hashlib.sha256(content).hexdigest()}",
                notes=source.get("notes"),
            ),
        )
        for span in source.get("spans", []):
            span_payload = dict(span)
            key = span_payload.pop("key")
            created = store.create_source_span(
                project_id,
                SourceSpanCreate(material_id=material["id"], **span_payload),
            )
            span_ids[key] = created["id"]

    understanding_payload = manifest["understanding"]
    understanding = store.create_understanding(
        project_id,
        UnderstandingCreate(
            summary=understanding_payload.get("summary"),
            version_state=understanding_payload.get("version_state", "draft"),
            assumptions=understanding_payload.get("assumptions", []),
            unknowns=understanding_payload.get("unknowns", []),
            conflicts=understanding_payload.get("conflicts", []),
            rules=[_rule(item, span_ids) for item in understanding_payload.get("rules", [])],
        ),
    )

    scenario_payload = manifest["scenario"]
    model_payload = scenario_payload.get("formal_model")
    scenario = store.create_scenario(
        project_id,
        ScenarioCreate(
            name=scenario_payload["name"],
            notes=scenario_payload.get("notes"),
            version_state=scenario_payload.get("version_state", "draft"),
            based_on_understanding_id=understanding["id"],
            formal_model=FormalModelIn(**model_payload) if model_payload else None,
            rules=[_rule(item, span_ids) for item in scenario_payload.get("rules", [])],
        ),
    )

    solve_payload = manifest.get("solve_run")
    if solve_payload:
        latest_revision = scenario["revisions"][-1]
        candidate_payload = solve_payload.get("candidate")
        store.create_solve_run(
            project_id,
            SolveRunCreate(
                scenario_revision_id=latest_revision["id"],
                formal_model_id=latest_revision.get("formal_model_id"),
                run_state=solve_payload.get("run_state", "pending"),
                message=solve_payload.get("message"),
                candidate=(
                    ResultCandidateIn(**candidate_payload)
                    if candidate_payload is not None
                    else None
                ),
            ),
        )

    return store.get_project(project_id)


def load_expected(template_id: str) -> dict[str, Any]:
    """Verification-only ground truth; not consumed by the instantiation path."""
    return _load_json(_template_dir(template_id) / "expected.json")
