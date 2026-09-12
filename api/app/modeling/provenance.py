"""Evidence-ref validation and honest bounded reads. Do not trust model-supplied exactness."""

from __future__ import annotations

from typing import Any

from .draft import EvidenceRef, ModelingDraft
from .snapshot import get_snapshot_material, list_snapshot_spans

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


def select_span(
    spans: list[dict[str, Any]],
    *,
    source_span_id: str | None = None,
    page: int | None = None,
    sheet: str | None = None,
    cell_ref: str | None = None,
) -> dict[str, Any] | None:
    if source_span_id:
        return next((span for span in spans if span.get("id") == source_span_id), None)
    candidates = list(spans)
    if page is not None:
        page_hits = [span for span in candidates if span.get("page") == page]
        if page_hits:
            candidates = page_hits
        else:
            return None
    if sheet is not None:
        needle = sheet.casefold()
        sheet_hits = [
            span
            for span in candidates
            if isinstance(span.get("sheet"), str) and str(span.get("sheet")).casefold() == needle
        ]
        if sheet_hits:
            candidates = sheet_hits
        else:
            return None
    if cell_ref is not None:
        cell_needle = cell_ref.casefold()
        cell_hits = [
            span
            for span in candidates
            if isinstance(span.get("cell_ref"), str)
            and str(span.get("cell_ref")).casefold() == cell_needle
        ]
        if cell_hits:
            candidates = cell_hits
        else:
            return None
    if page is None and sheet is None and cell_ref is None:
        return None
    return candidates[0] if candidates else None


def coverage_state_after_read(*, media_is_text: bool, whole_source: bool, truncated: bool) -> str:
    if media_is_text and whole_source and not truncated:
        return "analyzed"
    return "partially_processed"


def coverage_is_incomplete(state: str | None) -> bool:
    return (state or "pending") in INCOMPLETE_COVERAGE


def validate_draft(run: dict[str, Any], draft: ModelingDraft) -> None:
    keys: list[str] = []
    refs_groups: list[tuple[str, list[EvidenceRef]]] = [
        ("decision", []),
    ]
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


def validate_ref(run: dict[str, Any], ref: EvidenceRef) -> str | None:
    if ref.material_id.startswith("/") or "://" in ref.material_id:
        return "material_id must be a project-scoped id, not a path or URL"
    material = get_snapshot_material(run, ref.material_id)
    if material is None:
        return "material_id is not in this run snapshot"
    if run.get("project_id") and material.get("id"):
        pass
    if ref.material_checksum and material.get("checksum") and ref.material_checksum != material.get("checksum"):
        return "material_checksum does not match the frozen snapshot"
    spans = list_snapshot_spans(run, ref.material_id)
    chosen = None
    if ref.source_span_id:
        chosen = next((span for span in spans if span.get("id") == ref.source_span_id), None)
        if chosen is None:
            return "source_span_id is not in this run snapshot"
        if chosen.get("material_id") != ref.material_id:
            return "source_span_id does not belong to material_id"
    if ref.start_offset is not None and ref.end_offset is not None:
        if ref.start_offset < 0 or ref.end_offset < ref.start_offset:
            return "offset range is invalid"
        if chosen and chosen.get("start_offset") is not None and chosen.get("end_offset") is not None:
            span_start = int(chosen["start_offset"])
            span_end = int(chosen["end_offset"])
            if ref.start_offset < span_start or ref.end_offset > span_end:
                return "offset range is outside the source span coordinate space"
    if ref.page is not None and chosen and chosen.get("page") not in {None, ref.page}:
        return "page does not match the source span"
    if ref.sheet and chosen and chosen.get("sheet") and str(chosen.get("sheet")).casefold() != ref.sheet.casefold():
        return "sheet does not match the source span"
    if ref.cell_ref and chosen and chosen.get("cell_ref") and str(chosen.get("cell_ref")).casefold() != ref.cell_ref.casefold():
        return "cell_ref does not match the source span"
    if ref.quote:
        haystacks = []
        if chosen and chosen.get("excerpt"):
            haystacks.append(str(chosen["excerpt"]))
        if ref.coordinate_system == "azure_markdown":
            # Quote must be validated against derived content by the caller if needed.
            haystacks.append(ref.quote)
        if haystacks and ref.quote not in haystacks[0] and ref.coordinate_system != "azure_markdown":
            # Approximate quotes are allowed when precision is not exact.
            if ref.precision == "exact":
                return "exact quote was not found in the referenced span"
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
