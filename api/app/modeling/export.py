"""Pre-solver JSON + Markdown export built from explicit human review.

Rejected / not_applicable items are not active. Accepted edits change exported
semantics. needs_clarification is unresolved, never active. Original evidence
stays in history.
"""

from __future__ import annotations

from typing import Any

EXCLUDED_STATUSES = {"rejected", "not_applicable"}
UNRESOLVED_STATUSES = {"unreviewed", "needs_clarification"}
PARTITION_FIELDS = (
    "entities",
    "parameters",
    "decision_variables",
    "constraints",
    "objectives",
    "assumptions",
    "unknowns",
    "conflicts",
    "readiness_issues",
)
FIELD_CLAIM_KINDS = {
    "entities": "entity",
    "parameters": "parameter",
    "decision_variables": "variable",
    "constraints": "constraint",
    "objectives": "objective",
    "assumptions": "assumption",
    "unknowns": "unknown",
    "conflicts": "conflict",
    "readiness_issues": "readiness",
}
REVIEWABLE_CLAIM_KINDS = frozenset(FIELD_CLAIM_KINDS.values())


def _claims_by_key(draft: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item.get("claim_key"): item for item in draft.get("claims") or [] if item.get("claim_key")}


def _review_of(item: dict[str, Any], claims: dict[str, dict[str, Any]]) -> tuple[str, str | None, dict[str, Any]]:
    key = item.get("claim_key")
    claim = claims.get(key) or {}
    status = claim.get("review_status") or item.get("review_status") or "unreviewed"
    edited = claim.get("edited_statement")
    return status, edited, claim


def _apply_edit(item: dict[str, Any], status: str, edited: str | None, claim: dict[str, Any]) -> dict[str, Any]:
    effective = dict(item)
    effective["review_status"] = status
    if claim.get("evidence_refs"):
        effective["evidence_refs"] = claim["evidence_refs"]
    if edited:
        effective["edited_statement"] = edited
        effective["effective_statement"] = edited
        if "proposed_interpretation" in effective:
            effective["proposed_interpretation"] = edited
        if "raw_value" in effective:
            if effective.get("normalized_value") is not None and effective.get("raw_value") != edited:
                effective["normalized_value"] = None
                effective["needs_reinterpretation"] = True
            effective["raw_value"] = edited
        if "original_statement" in effective and not effective.get("original_statement"):
            effective["original_statement"] = edited
        if isinstance(item.get("original_statement"), str) and item.get("claim_kind") == "readiness":
            effective["original_statement"] = edited
    else:
        effective["effective_statement"] = (
            item.get("proposed_interpretation") or item.get("original_statement") or item.get("name")
        )
    return effective


def _as_items(raw: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw or []):
        if isinstance(item, dict):
            items.append(item)
        elif isinstance(item, str):
            items.append(
                {
                    "claim_key": f"readiness-{index + 1}",
                    "claim_kind": "readiness",
                    "original_statement": item,
                    "review_status": "unreviewed",
                }
            )
    return items


def _partition(
    items: list[Any],
    claims: dict[str, dict[str, Any]],
    *,
    accepted_only: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    active: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for item in _as_items(items):
        status, edited, claim = _review_of(item, claims)
        record = _apply_edit(item, status, edited, claim)
        if status in EXCLUDED_STATUSES:
            excluded.append(record)
            continue
        if status in UNRESOLVED_STATUSES:
            unresolved.append(record)
            if status == "needs_clarification":
                continue
            if not accepted_only and status == "unreviewed":
                active.append(record)
            continue
        if status == "accepted":
            active.append(record)
    return active, excluded, unresolved


def _filename_index(draft: dict[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    body = draft.get("draft") or {}
    for item in body.get("coverage") or []:
        material_id = item.get("material_id")
        filename = item.get("filename")
        if material_id and filename:
            names[str(material_id)] = str(filename)
    snapshot = (draft.get("snapshot") or {}) if isinstance(draft.get("snapshot"), dict) else {}
    for item in snapshot.get("materials") or []:
        material_id = item.get("id")
        filename = item.get("filename")
        if material_id and filename:
            names.setdefault(str(material_id), str(filename))
    return names


def _format_ref(ref: dict[str, Any], filenames: dict[str, str] | None = None) -> str:
    material_id = str(ref.get("material_id") or "")
    label = (filenames or {}).get(material_id) or material_id
    parts = [f"source “{label}”"]
    if ref.get("coordinate_system"):
        parts.append(str(ref.get("coordinate_system")))
    if ref.get("precision"):
        parts.append(str(ref.get("precision")))
    if ref.get("page") is not None:
        parts.append(f"page {ref.get('page')}")
    if ref.get("sheet"):
        parts.append(f"sheet {ref.get('sheet')}")
    if ref.get("cell_ref"):
        parts.append(f"cell {ref.get('cell_ref')}")
    if ref.get("start_offset") is not None and ref.get("end_offset") is not None:
        parts.append(f"offsets {ref.get('start_offset')}–{ref.get('end_offset')}")
    if ref.get("quote"):
        quote = str(ref["quote"]).replace("\n", " ")
        parts.append(f'quote “{quote[:160]}”')
    return ", ".join(parts)


def structured_handoff(draft: dict[str, Any], *, for_baseline: bool = False) -> dict[str, Any]:
    body = draft.get("draft") or {}
    claims = _claims_by_key(draft)
    accepted_only = for_baseline
    partitioned: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for field in PARTITION_FIELDS:
        active, excluded, unresolved = _partition(body.get(field) or [], claims, accepted_only=accepted_only)
        partitioned[field] = {"active": active, "excluded": excluded, "unresolved": unresolved}
    critical_unresolved = []
    for field in ("constraints", "objectives"):
        for item in partitioned[field]["unresolved"]:
            if item.get("review_status") == "needs_clarification":
                critical_unresolved.append(item.get("claim_key"))
    for field in PARTITION_FIELDS:
        for item in partitioned[field]["unresolved"]:
            if item.get("review_status") == "needs_clarification" and item.get("claim_key") not in critical_unresolved:
                if field not in {"constraints", "objectives"}:
                    continue
    coverage = draft.get("run_coverage") or body.get("coverage") or []
    return {
        "kind": "lucid.pre_solver_handoff",
        "solver": "not_executed",
        "draft_id": draft.get("id"),
        "revision_no": draft.get("revision_no"),
        "completeness": draft.get("completeness"),
        "decision_brief": body.get("decision_brief"),
        "entities": partitioned["entities"]["active"],
        "parameters": partitioned["parameters"]["active"],
        "decision_variables": partitioned["decision_variables"]["active"],
        "constraints": partitioned["constraints"]["active"],
        "objectives": partitioned["objectives"]["active"],
        "assumptions": partitioned["assumptions"]["active"],
        "unknowns": partitioned["unknowns"]["active"],
        "conflicts": partitioned["conflicts"]["active"],
        "readiness_issues": [
            item.get("effective_statement") or item.get("original_statement")
            for item in partitioned["readiness_issues"]["active"]
        ],
        "coverage": coverage,
        "excluded": {field: partitioned[field]["excluded"] for field in PARTITION_FIELDS},
        "unresolved": {
            **{field: partitioned[field]["unresolved"] for field in PARTITION_FIELDS},
            "critical_claim_keys": [key for key in critical_unresolved if key],
        },
        "original_draft": {field: body.get(field) for field in PARTITION_FIELDS},
        "claim_reviews": [
            {
                "claim_key": item.get("claim_key"),
                "claim_kind": item.get("claim_kind"),
                "review_status": item.get("review_status"),
                "edited_statement": item.get("edited_statement"),
                "original_statement": item.get("original_statement"),
                "evidence_refs": item.get("evidence_refs") or [],
            }
            for item in draft.get("claims") or []
        ],
    }


def render_markdown(draft: dict[str, Any], handoff: dict[str, Any] | None = None) -> str:
    handoff = handoff or structured_handoff(draft, for_baseline=True)
    brief = handoff.get("decision_brief") or {}
    filenames = _filename_index(draft)
    lines = [
        "# LUCID pre-solver modeling brief",
        "",
        "This is a confirmed business baseline / modeling handoff. No solver was executed.",
        "",
        f"Draft revision {draft.get('revision_no')} ({draft.get('completeness')}).",
        "",
        "## Decision",
        brief.get("what_to_decide") or "(unknown)",
        "",
    ]
    if brief.get("scope"):
        lines.extend(["### Scope", str(brief["scope"]), ""])
    if brief.get("time_horizon"):
        lines.extend(["### Time horizon", str(brief["time_horizon"]), ""])
    if brief.get("ambiguities"):
        lines.append("### Ambiguities")
        lines.extend(f"- {item}" for item in brief["ambiguities"])
        lines.append("")
    lines.extend(_section("Active entities", handoff.get("entities") or [], filenames))
    lines.extend(_section("Active parameters", handoff.get("parameters") or [], filenames))
    lines.extend(_section("Candidate decision variables", handoff.get("decision_variables") or [], filenames))
    lines.extend(_section("Active constraints", handoff.get("constraints") or [], filenames))
    lines.extend(_section("Active objectives", handoff.get("objectives") or [], filenames))
    lines.extend(_section("Active assumptions", handoff.get("assumptions") or [], filenames))
    lines.extend(_section("Unknowns (not every unknown blocks every scenario)", handoff.get("unknowns") or [], filenames))
    lines.extend(_section("Conflicts", handoff.get("conflicts") or [], filenames))
    if handoff.get("readiness_issues"):
        lines.append("## Readiness issues")
        lines.extend(f"- {item}" for item in handoff.get("readiness_issues") or [])
        lines.append("")
    excluded = handoff.get("excluded") or {}
    lines.extend(_section("Excluded constraints (rejected / not applicable)", excluded.get("constraints") or [], filenames))
    lines.extend(_section("Excluded objectives (rejected / not applicable)", excluded.get("objectives") or [], filenames))
    lines.extend(_section("Excluded assumptions", excluded.get("assumptions") or [], filenames))
    lines.extend(_section("Excluded unknowns", excluded.get("unknowns") or [], filenames))
    lines.extend(_section("Excluded conflicts", excluded.get("conflicts") or [], filenames))
    unresolved = handoff.get("unresolved") or {}
    if unresolved.get("critical_claim_keys"):
        lines.append("## Critical unresolved questions")
        lines.extend(f"- `{key}`" for key in unresolved["critical_claim_keys"])
        lines.append("")
    needs = []
    for field in PARTITION_FIELDS:
        for item in unresolved.get(field) or []:
            if item.get("review_status") == "needs_clarification":
                needs.append(item)
    if needs:
        lines.extend(_section("Needs clarification", needs, filenames))
    lines.append("## Coverage")
    for item in handoff.get("coverage") or []:
        name = item.get("filename") or filenames.get(str(item.get("material_id") or ""), "unnamed source")
        lines.append(f"- {name}: {item.get('state')} — {item.get('detail') or ''}")
    lines.extend(["", "## Claim review", ""])
    for item in handoff.get("claim_reviews") or []:
        edited = item.get("edited_statement")
        refs = item.get("evidence_refs") or []
        ref_text = "; ".join(_format_ref(ref, filenames) for ref in refs) if refs else "no source ref"
        lines.append(
            f"- `{item.get('claim_key')}` [{item.get('review_status')}] {item.get('original_statement')}"
            + (f" → {edited}" if edited else "")
            + f" — {ref_text}"
        )
    lines.extend(["", "Solver: not executed.", ""])
    return "\n".join(lines)


def _section(title: str, items: list[Any], filenames: dict[str, str] | None = None) -> list[str]:
    lines = [f"## {title}"]
    if not items:
        lines.extend(["(none)", ""])
        return lines
    for item in items:
        if isinstance(item, dict):
            text = (
                item.get("effective_statement")
                or item.get("original_statement")
                or item.get("raw_value")
                or item.get("name")
                or ""
            )
            refs = item.get("evidence_refs") or []
            ref_note = "; ".join(_format_ref(ref, filenames) for ref in refs) if refs else "no evidence ref"
            extra = ""
            if item.get("needs_reinterpretation"):
                extra = " (normalized value cleared pending re-interpretation)"
            lines.append(f"- {text} — {ref_note}{extra}")
        else:
            lines.append(f"- {item}")
    lines.append("")
    return lines
