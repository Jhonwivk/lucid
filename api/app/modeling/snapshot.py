"""Frozen evidence snapshot for one modeling run.

Inspect/read/validate against this snapshot, not the live project Materials
table. Clarification may append explicitly linked evidence once.
"""

from __future__ import annotations

from typing import Any


def freeze_materials(materials: list[dict[str, Any]], spans: list[dict[str, Any]]) -> dict[str, Any]:
    by_material: dict[str, list[dict[str, Any]]] = {}
    for span in spans:
        by_material.setdefault(span["material_id"], []).append(_span_public(span))
    frozen = []
    for material in materials:
        frozen.append(
            {
                **_material_public(material),
                "spans": by_material.get(material["id"], []),
            }
        )
    return {
        "materials": frozen,
        "appended": [],
        "original_material_ids": [item["id"] for item in frozen],
    }


def _material_public(material: dict[str, Any]) -> dict[str, Any]:
    meta = dict(material.get("metadata") or {})
    return {
        "id": material["id"],
        "filename": material.get("filename"),
        "kind": material.get("kind"),
        "media_type": material.get("media_type"),
        "byte_size": material.get("byte_size"),
        "checksum": material.get("checksum"),
        "notes": material.get("notes"),
        "metadata": meta,
        "created_at": material.get("created_at"),
    }


def _span_public(span: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": span["id"],
        "material_id": span["material_id"],
        "locator_kind": span.get("locator_kind"),
        "page": span.get("page"),
        "start_offset": span.get("start_offset"),
        "end_offset": span.get("end_offset"),
        "sheet": span.get("sheet"),
        "cell_ref": span.get("cell_ref"),
        "region": span.get("region"),
        "excerpt": span.get("excerpt"),
        "created_at": span.get("created_at"),
    }


def snapshot_of(run: dict[str, Any]) -> dict[str, Any]:
    snap = run.get("snapshot") or {}
    if not isinstance(snap, dict):
        return {"materials": [], "appended": [], "original_material_ids": []}
    materials = snap.get("materials") or []
    return {
        "materials": materials,
        "appended": snap.get("appended") or [],
        "original_material_ids": snap.get("original_material_ids")
        or [item.get("id") for item in materials],
    }


def list_snapshot_materials(run: dict[str, Any]) -> list[dict[str, Any]]:
    return list(snapshot_of(run)["materials"])


def get_snapshot_material(run: dict[str, Any], material_id: str) -> dict[str, Any] | None:
    for item in list_snapshot_materials(run):
        if item.get("id") == material_id:
            return item
    return None


def list_snapshot_spans(run: dict[str, Any], material_id: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for material in list_snapshot_materials(run):
        if material_id is not None and material.get("id") != material_id:
            continue
        for span in material.get("spans") or []:
            rows.append(span)
    return rows


def append_clarification_material(
    snapshot: dict[str, Any],
    material: dict[str, Any],
    spans: list[dict[str, Any]],
    *,
    clarification_id: str,
) -> dict[str, Any]:
    """Append one explicitly linked clarification material. Idempotent on material id."""
    next_snap = {
        "materials": list(snapshot.get("materials") or []),
        "appended": list(snapshot.get("appended") or []),
        "original_material_ids": list(snapshot.get("original_material_ids") or []),
    }
    material_id = material["id"]
    if any(item.get("id") == material_id for item in next_snap["materials"]):
        return next_snap
    packed = {**_material_public(material), "spans": [_span_public(span) for span in spans]}
    next_snap["materials"].append(packed)
    next_snap["appended"].append(
        {
            "material_id": material_id,
            "clarification_id": clarification_id,
            "role": "clarification_answer",
        }
    )
    return next_snap


def original_ids(run: dict[str, Any]) -> set[str]:
    return {item for item in snapshot_of(run)["original_material_ids"] if item}
