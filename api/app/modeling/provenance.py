"""Evidence-ref validation and honest bounded reads. Do not trust model-supplied exactness."""

from __future__ import annotations

from typing import Any

from .draft import EvidenceRef, ModelingDraft
from .snapshot import (
    SnapshotIntegrityError,
    get_snapshot_material,
    list_snapshot_materials,
    list_snapshot_spans,
    read_snapshot_bytes,
)

MAX_EXCERPT = 8000
INCOMPLETE_COVERAGE = {"pending", "unavailable", "unsupported", "partially_processed"}


def bound_text(
    text: str,
    *,
    start_offset: int | None = None,
    end_offset: int | None = None,
    max_chars: int = MAX_EXCERPT,
) -> dict[str, Any]:
    total = len(text)
    start = 0 if start_offset is None else max(0, int(start_offset))
    if start > total:
        start = total
    requested_end = total if end_offset is None else max(start, int(end_offset))
    requested_end = min(total, requested_end)
    window_end = min(requested_end, start + max_chars)
    excerpt = text[start:window_end]
    actual_end = start + len(excerpt)
    truncated = actual_end < requested_end or (end_offset is None and actual_end < total and max_chars < total - start)
    if end_offset is None and actual_end < total:
        truncated = True
    next_offset = actual_end if actual_end < total else None
    whole = start == 0 and actual_end == total and not truncated
    return {
        "excerpt": excerpt,
        "start_offset": start,
        "end_offset": actual_end,
        "requested_end_offset": requested_end if end_offset is not None else None,
        "total_chars": total,
        "next_offset": next_offset,
        "truncated": truncated,
        "whole_source": whole,
        "max_chars": max_chars,
    }


def _norm_sheet(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.casefold()


def _region_key(region: Any) -> str | None:
    if not isinstance(region, dict) or not region:
        return None
    keys = ("x", "y", "width", "height", "left", "top", "right", "bottom")
    parts = []
    for key in keys:
        if key in region and region[key] is not None:
            parts.append(f"{key}={region[key]}")
    return "|".join(parts) if parts else None


def select_span(
    spans: list[dict[str, Any]],
    *,
    source_span_id: str | None = None,
    page: int | None = None,
    sheet: str | None = None,
    cell_ref: str | None = None,
    region: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    hits = select_matching_spans(
        spans,
        source_span_id=source_span_id,
        page=page,
        sheet=sheet,
        cell_ref=cell_ref,
        region=region,
    )
    if source_span_id:
        return hits[0] if hits else None
    if page is None and sheet is None and cell_ref is None and not region:
        return None
    return hits[0] if hits else None


def select_matching_spans(
    spans: list[dict[str, Any]],
    *,
    source_span_id: str | None = None,
    page: int | None = None,
    sheet: str | None = None,
    cell_ref: str | None = None,
    region: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if source_span_id:
        return [span for span in spans if span.get("id") == source_span_id]
    candidates = list(spans)
    if page is not None:
        candidates = [span for span in candidates if span.get("page") == page]
    if sheet is not None:
        needle = _norm_sheet(sheet)
        candidates = [span for span in candidates if _norm_sheet(span.get("sheet")) == needle]
    if cell_ref is not None:
        cell_needle = str(cell_ref).casefold()
        candidates = [
            span
            for span in candidates
            if isinstance(span.get("cell_ref"), str) and str(span.get("cell_ref")).casefold() == cell_needle
        ]
    if region:
        wanted = _region_key(region)
        candidates = [span for span in candidates if _region_key(span.get("region")) == wanted]
    if page is None and sheet is None and cell_ref is None and not region:
        return []
    return candidates


def coverage_state_after_read(*, media_is_text: bool, whole_source: bool, truncated: bool) -> str:
    if media_is_text and whole_source and not truncated:
        return "analyzed"
    return "partially_processed"


def coverage_is_incomplete(state: str | None) -> bool:
    return (state or "pending") in INCOMPLETE_COVERAGE


def _authoritative_coverage(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item.get("material_id"): item for item in (run.get("coverage") or []) if item.get("material_id")}


def validate_draft(run: dict[str, Any], draft: ModelingDraft) -> None:
    snapshot_ids = [item.get("id") for item in list_snapshot_materials(run) if item.get("id")]
    snapshot_set = set(snapshot_ids)
    coverage_ids: list[str] = []
    seen_coverage: set[str] = set()
    dup_coverage: list[str] = []
    unknown_coverage: list[str] = []
    for item in draft.coverage:
        material_id = item.material_id
        coverage_ids.append(material_id)
        if material_id in seen_coverage:
            dup_coverage.append(material_id)
        seen_coverage.add(material_id)
        if material_id not in snapshot_set:
            unknown_coverage.append(material_id)
    missing = [material_id for material_id in snapshot_ids if material_id not in seen_coverage]
    if dup_coverage:
        raise ValueError(f"coverage material_id values are duplicated: {sorted(set(dup_coverage))}")
    if unknown_coverage:
        raise ValueError(f"coverage points at materials outside this run snapshot: {sorted(set(unknown_coverage))}")
    if missing:
        raise ValueError(f"draft coverage is missing snapshot materials: {missing}")
    for material in list_snapshot_materials(run):
        try:
            read_snapshot_bytes(run, material)
        except SnapshotIntegrityError as exc:
            raise ValueError(f"stale_input: {exc}") from exc
        if material.get("copy_error"):
            raise ValueError(f"stale_input: snapshot copy failed for {material.get('id')}")

    keys: list[str] = []
    refs_groups: list[tuple[str, list[EvidenceRef]]] = [("decision", [])]
    for item in draft.entities:
        keys.append(item.claim_key)
        refs_groups.append((item.claim_key, item.evidence_refs))
    for item in draft.parameters:
        keys.append(item.claim_key)
        refs_groups.append((item.claim_key, item.evidence_refs))
    for item in draft.decision_variables:
        keys.append(item.claim_key)
        refs_groups.append((item.claim_key, item.evidence_refs))
    for item in draft.constraints:
        keys.append(item.claim_key)
        refs_groups.append((item.claim_key, item.evidence_refs))
    for item in draft.objectives:
        keys.append(item.claim_key)
        refs_groups.append((item.claim_key, item.evidence_refs))
    for item in draft.assumptions:
        keys.append(item.claim_key)
        refs_groups.append((item.claim_key, item.evidence_refs))
    for item in draft.unknowns:
        keys.append(item.claim_key)
        refs_groups.append((item.claim_key, item.evidence_refs))
    for item in draft.conflicts:
        keys.append(item.claim_key)
        refs_groups.append((item.claim_key, item.evidence_refs))

    seen: set[str] = set()
    duplicates = []
    for key in keys:
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    if duplicates:
        raise ValueError(f"duplicate claim_key values: {sorted(set(duplicates))}")

    errors: list[str] = []
    for claim_key, refs in refs_groups:
        for index, ref in enumerate(refs):
            error = validate_ref(run, ref)
            if error:
                errors.append(f"{claim_key}[{index}]: {error}")
    if errors:
        raise ValueError("invalid evidence_refs: " + "; ".join(errors[:12]))


def _snapshot_text(run: dict[str, Any], material: dict[str, Any]) -> str | None:
    media = material.get("media_type") or ""
    origin = (material.get("metadata") or {}).get("source_origin")
    if not (
        origin == "direct_text"
        or str(media).startswith("text/")
        or media in {"application/json", "text/csv", "text/markdown"}
    ):
        return None
    try:
        return read_snapshot_bytes(run, material).decode("utf-8", errors="replace")
    except SnapshotIntegrityError:
        return None


def _derived_markdown(run: dict[str, Any], material: dict[str, Any], ref: EvidenceRef) -> dict[str, Any] | None:
    from . import persistence
    from ..runtime_config import azure_settings

    analyzer = None
    operation_id = None
    if isinstance(ref.provider_locator, dict):
        analyzer = ref.provider_locator.get("analyzer_id")
        operation_id = ref.provider_locator.get("operation_id")
    analyzer = analyzer or azure_settings()["analyzer_id"] or "prebuilt-document"
    cached = persistence.get_cached_analysis(
        material["id"],
        material.get("checksum"),
        str(analyzer),
        include_secrets=False,
    )
    if cached is None:
        return None
    if operation_id and cached.get("operation_id") and cached.get("operation_id") != operation_id:
        return None
    return cached


def validate_ref(run: dict[str, Any], ref: EvidenceRef) -> str | None:
    if ref.material_id.startswith("/") or "://" in ref.material_id:
        return "material_id must be a project-scoped id, not a path or URL"
    material = get_snapshot_material(run, ref.material_id)
    if material is None:
        return "material_id is not in this run snapshot"
    expected_checksum = material.get("checksum")
    if not ref.material_checksum:
        return "material_checksum is required and must match the frozen snapshot"
    if not expected_checksum or ref.material_checksum != expected_checksum:
        return "material_checksum does not match the frozen snapshot"
    if (ref.start_offset is None) ^ (ref.end_offset is None):
        return "start_offset and end_offset must both be set"
    spans = list_snapshot_spans(run, ref.material_id)
    chosen = None
    if ref.source_span_id:
        hits = [span for span in spans if span.get("id") == ref.source_span_id]
        if not hits:
            return "source_span_id is not in this run snapshot"
        chosen = hits[0]
        if chosen.get("material_id") != ref.material_id:
            return "source_span_id does not belong to material_id"
    else:
        locator_used = any(
            value is not None for value in (ref.page, ref.sheet, ref.cell_ref, ref.region)
        )
        if locator_used:
            hits = select_matching_spans(
                spans,
                page=ref.page,
                sheet=ref.sheet,
                cell_ref=ref.cell_ref,
                region=ref.region,
            )
            if len(hits) == 0:
                return "page/sheet/cell_ref/region did not match a snapshot span"
            if len(hits) > 1:
                return "page/sheet/cell_ref/region is not unique in this snapshot"
            chosen = hits[0]
        elif ref.precision not in {"whole_source", "unresolved"} or ref.start_offset is not None:
            if ref.start_offset is None:
                return "without source_span_id, page/sheet/cell_ref/region must uniquely match a snapshot span"

    if ref.start_offset is not None and ref.end_offset is not None:
        if ref.start_offset < 0 or ref.end_offset < ref.start_offset:
            return "offset range is invalid"
        if chosen and chosen.get("start_offset") is not None and chosen.get("end_offset") is not None:
            span_start = int(chosen["start_offset"])
            span_end = int(chosen["end_offset"])
            if ref.start_offset < span_start or ref.end_offset > span_end:
                return "offset range is outside the source span coordinate space"
        else:
            text = _snapshot_text(run, material)
            if text is not None and (ref.start_offset > len(text) or ref.end_offset > len(text)):
                return "offset range is outside the original snapshot text"

    if ref.page is not None and chosen and chosen.get("page") not in {None, ref.page}:
        return "page does not match the source span"
    if ref.sheet and chosen and chosen.get("sheet") and str(chosen.get("sheet")).casefold() != ref.sheet.casefold():
        return "sheet does not match the source span"
    if ref.cell_ref and chosen and chosen.get("cell_ref") and str(chosen.get("cell_ref")).casefold() != ref.cell_ref.casefold():
        return "cell_ref does not match the source span"

    if ref.coordinate_system == "azure_markdown":
        cached = _derived_markdown(run, material, ref)
        if cached is None or not cached.get("derived_markdown"):
            return "azure_markdown evidence requires analyzer_id/operation_id and a persisted derived artifact"
        if ref.precision == "exact" and ref.quote:
            if ref.quote not in str(cached.get("derived_markdown") or ""):
                return "exact quote was not found in the persisted Azure derived markdown"
        return None

    if ref.quote and ref.precision == "exact":
        haystacks: list[str] = []
        if chosen and chosen.get("excerpt"):
            haystacks.append(str(chosen["excerpt"]))
        text = _snapshot_text(run, material)
        if text:
            if ref.start_offset is not None and ref.end_offset is not None:
                haystacks.append(text[ref.start_offset:ref.end_offset])
            haystacks.append(text)
        if not haystacks or not any(ref.quote in haystack for haystack in haystacks):
            return "exact quote was not found in the referenced snapshot excerpt"

    if ref.coordinate_system == "original_text":
        media = material.get("media_type") or ""
        origin = (material.get("metadata") or {}).get("source_origin")
        if not (
            origin == "direct_text"
            or str(media).startswith("text/")
            or media in {"application/json", "text/csv", "text/markdown"}
        ):
            if ref.precision == "exact":
                return "original_text coordinates are not valid for this material"
    return None


def stamp_run_coverage(run: dict[str, Any], draft_payload: dict[str, Any]) -> dict[str, Any]:
    """Replace draft-supplied coverage with the run's authoritative coverage."""
    payload = dict(draft_payload)
    payload["coverage"] = list(run.get("coverage") or [])
    return payload
