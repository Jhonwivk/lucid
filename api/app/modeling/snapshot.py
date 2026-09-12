"""Frozen evidence snapshot for one modeling run.

Inspect/read/validate against this snapshot, not the live project Materials
table. Clarification may append explicitly linked evidence once.

Each original Material is copied to a run-owned path under
``data/modeling_snapshots/{run_id}/{material_id}/content``. Paths are generated
by the server; Agent input cannot choose them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..db import get_data_dir
from ..importers.common import sha256_hex

SNAPSHOT_ROOT = "modeling_snapshots"


class SnapshotIntegrityError(ValueError):
    """Snapshot bytes are missing or no longer match the frozen checksum."""


def _safe_id(value: str) -> str:
    cleaned = "".join(ch for ch in str(value) if ch.isalnum() or ch in "-_")
    if not cleaned or cleaned != str(value):
        raise SnapshotIntegrityError("snapshot path ids must be opaque server tokens")
    return cleaned


def snapshot_content_relpath(run_id: str, material_id: str) -> str:
    return f"{SNAPSHOT_ROOT}/{_safe_id(run_id)}/{_safe_id(material_id)}/content"


def snapshot_root_dir() -> Path:
    return (get_data_dir() / SNAPSHOT_ROOT).resolve()


def resolve_snapshot_file(run_id: str, relpath: str) -> Path:
    if not isinstance(relpath, str) or not relpath.strip():
        raise SnapshotIntegrityError("snapshot_path is missing")
    if relpath.startswith("/") or "://" in relpath or ".." in Path(relpath).parts:
        raise SnapshotIntegrityError("snapshot_path is not a server-owned relative path")
    expected_prefix = f"{SNAPSHOT_ROOT}/{_safe_id(run_id)}/"
    if not relpath.startswith(expected_prefix):
        raise SnapshotIntegrityError("snapshot_path does not belong to this run")
    root = snapshot_root_dir()
    path = (get_data_dir() / relpath).resolve()
    if root not in path.parents and path != root:
        raise SnapshotIntegrityError("snapshot_path is outside the snapshot store")
    return path


def live_material_file(project_id: str, material: dict[str, Any]) -> Path | None:
    meta = material.get("metadata") or {}
    stored = meta.get("stored_path")
    if not isinstance(stored, str) or not stored.strip():
        return None
    if stored.startswith("/") or "://" in stored or ".." in Path(stored).parts:
        return None
    root = (get_data_dir() / "materials" / project_id).resolve()
    path = (get_data_dir() / stored).resolve()
    if root not in path.parents and path != root:
        return None
    if not path.is_file():
        return None
    return path


def copy_material_into_run(
    run_id: str,
    project_id: str,
    material: dict[str, Any],
) -> dict[str, Any]:
    """Copy live Material bytes into the run snapshot directory. Server-owned path."""
    relpath = snapshot_content_relpath(run_id, material["id"])
    dest = get_data_dir() / relpath
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = live_material_file(project_id, material)
    if source is None:
        return {
            "snapshot_path": None,
            "checksum": material.get("checksum"),
            "byte_size": material.get("byte_size"),
            "copy_error": "source_bytes_missing",
        }
    content = source.read_bytes()
    dest.write_bytes(content)
    digest = sha256_hex(content)
    return {
        "snapshot_path": relpath,
        "checksum": digest,
        "byte_size": len(content),
        "original_checksum": material.get("checksum"),
        "copy_error": None if (not material.get("checksum") or material.get("checksum") == digest) else "checksum_mismatch_on_copy",
    }


def read_snapshot_bytes(run: dict[str, Any], material: dict[str, Any]) -> bytes:
    """Read frozen bytes only. Never follow a later live Material replacement."""
    relpath = material.get("snapshot_path")
    expected = material.get("checksum")
    if relpath:
        path = resolve_snapshot_file(str(run["id"]), str(relpath))
        if not path.is_file():
            raise SnapshotIntegrityError("frozen snapshot file is missing")
        content = path.read_bytes()
        digest = sha256_hex(content)
        if expected and digest != expected:
            raise SnapshotIntegrityError("frozen snapshot checksum does not match")
        return content
    # Legacy snapshots without a copy: re-hash the current live file and compare.
    live = live_material_file(str(run["project_id"]), material)
    if live is None:
        raise SnapshotIntegrityError("snapshot bytes are missing")
    content = live.read_bytes()
    digest = sha256_hex(content)
    if expected and digest != expected:
        raise SnapshotIntegrityError("live material bytes no longer match the frozen checksum")
    return content


def freeze_materials(
    materials: list[dict[str, Any]],
    spans: list[dict[str, Any]],
    *,
    run_id: str,
    project_id: str,
) -> dict[str, Any]:
    by_material: dict[str, list[dict[str, Any]]] = {}
    for span in spans:
        by_material.setdefault(span["material_id"], []).append(_span_public(span))
    frozen = []
    copy_failures = 0
    for material in materials:
        copied = copy_material_into_run(run_id, project_id, material)
        if copied.get("copy_error") or not copied.get("snapshot_path"):
            copy_failures += 1
        frozen.append(
            {
                **_material_public(material),
                "snapshot_path": copied.get("snapshot_path"),
                "checksum": copied.get("checksum") or material.get("checksum"),
                "byte_size": copied.get("byte_size") if copied.get("byte_size") is not None else material.get("byte_size"),
                "original_material_id": material["id"],
                "original_checksum": copied.get("original_checksum") or material.get("checksum"),
                "role": "original",
                "copy_error": copied.get("copy_error"),
                "spans": by_material.get(material["id"], []),
            }
        )
    return {
        "materials": frozen,
        "appended": [],
        "original_material_ids": [item["id"] for item in frozen],
        "copy_failures": copy_failures,
        "snapshot_root": f"{SNAPSHOT_ROOT}/{run_id}",
    }


def _material_public(material: dict[str, Any]) -> dict[str, Any]:
    meta = dict(material.get("metadata") or {})
    # Live stored_path is not an Agent-addressable snapshot path.
    meta.pop("stored_path", None)
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
        "copy_failures": snap.get("copy_failures") or 0,
        "frozen_at": snap.get("frozen_at"),
        "snapshot_root": snap.get("snapshot_root"),
    }


def assert_snapshot_bytes(run: dict[str, Any]) -> None:
    """Re-read every frozen file. Missing, copy_error, or checksum mismatch fail."""
    materials = list_snapshot_materials(run)
    if not materials:
        raise SnapshotIntegrityError("snapshot materials are missing")
    for material in materials:
        if material.get("copy_error"):
            raise SnapshotIntegrityError(f"snapshot copy failed for {material.get('id')}")
        if not material.get("snapshot_path"):
            raise SnapshotIntegrityError(f"snapshot file is missing for {material.get('id')}")
        read_snapshot_bytes(run, material)


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
    run_id: str,
    project_id: str,
) -> dict[str, Any]:
    """Append one explicitly linked clarification material. Idempotent on material id."""
    next_snap = {
        "materials": list(snapshot.get("materials") or []),
        "appended": list(snapshot.get("appended") or []),
        "original_material_ids": list(snapshot.get("original_material_ids") or []),
        "copy_failures": snapshot.get("copy_failures") or 0,
        "frozen_at": snapshot.get("frozen_at"),
        "snapshot_root": snapshot.get("snapshot_root") or f"{SNAPSHOT_ROOT}/{run_id}",
    }
    material_id = material["id"]
    if any(item.get("id") == material_id for item in next_snap["materials"]):
        return next_snap
    copied = copy_material_into_run(run_id, project_id, material)
    packed = {
        **_material_public(material),
        "snapshot_path": copied.get("snapshot_path"),
        "checksum": copied.get("checksum") or material.get("checksum"),
        "byte_size": copied.get("byte_size") if copied.get("byte_size") is not None else material.get("byte_size"),
        "original_material_id": material_id,
        "original_checksum": copied.get("original_checksum") or material.get("checksum"),
        "role": "clarification_answer",
        "copy_error": copied.get("copy_error"),
        "spans": [_span_public(span) for span in spans],
    }
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


def snapshot_public_meta(material: dict[str, Any] | None) -> dict[str, Any] | None:
    if not material:
        return None
    return {
        "material_id": material.get("id"),
        "filename": material.get("filename"),
        "checksum": material.get("checksum"),
        "original_checksum": material.get("original_checksum"),
        "byte_size": material.get("byte_size"),
        "snapshot_path": material.get("snapshot_path"),
        "role": material.get("role") or "original",
        "frozen": bool(material.get("snapshot_path")),
        "copy_error": material.get("copy_error"),
    }
