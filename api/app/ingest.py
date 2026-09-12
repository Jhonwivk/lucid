"""Copy upload bytes, parse them, and persist Material + SourceSpan rows.

T05 built-in templates do not use this module. Template semantics stay
manifest-driven in ``template_catalog``. This path is the public Materials
intake for direct text plus TXT / Markdown / text-PDF / CSV / XLSX / PNG / JPEG.
Adapters preserve evidence; they do not perform semantic understanding.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from . import store
from .db import get_data_dir
from .importers import (
    UnreadableMaterialError,
    UnsupportedMaterialError,
    parse_direct_text,
    parse_material,
    sniff_media_type,
)
from .schemas import MaterialCreate, SourceSpanCreate

MAX_IMPORT_BYTES = 12 * 1024 * 1024
DIRECT_TEXT_STORED_NAME = "direct-text.txt"


class ImportTooLargeError(ValueError):
    http_status = 413


def safe_filename(name: str) -> str:
    base = Path(name).name.strip()
    if not base or base in {".", ".."}:
        raise UnsupportedMaterialError("invalid filename")
    return base


def _stored_relative(path: Path) -> str:
    try:
        return str(path.relative_to(get_data_dir()))
    except ValueError:
        return str(path)


def _write_collision_safe(project_id: str, filename: str, content: bytes) -> tuple[Path, str]:
    dest_dir = get_data_dir() / "materials" / project_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{uuid.uuid4().hex}-{filename}"
    dest.write_bytes(content)
    return dest, _stored_relative(dest)


def ingest_bytes(project_id: str, filename: str, content: bytes) -> dict:
    """Parse and persist one public intake file with a collision-safe stored path."""
    if len(content) > MAX_IMPORT_BYTES:
        raise ImportTooLargeError(
            f"File exceeds the {MAX_IMPORT_BYTES} byte (12 MiB) import limit."
        )
    safe = safe_filename(filename)
    sniff_media_type(safe)
    parsed = parse_material(safe, content)
    dest, stored = _write_collision_safe(project_id, safe, content)
    metadata = dict(parsed.metadata)
    metadata["stored_path"] = stored
    metadata["original_filename"] = safe
    metadata["storage_name"] = dest.name
    metadata["evidence_role"] = "evidence_not_instruction"
    try:
        return store.persist_imported_material(
            project_id,
            MaterialCreate(
                filename=safe,
                media_type=parsed.media_type,
                kind=parsed.kind,  # type: ignore[arg-type]
                byte_size=parsed.byte_size,
                checksum=parsed.checksum,
                notes=parsed.notes,
                metadata=metadata,
            ),
            [
                SourceSpanCreate(
                    material_id="pending",
                    locator_kind=span.locator_kind,  # type: ignore[arg-type]
                    page=span.page,
                    start_offset=span.start_offset,
                    end_offset=span.end_offset,
                    sheet=span.sheet,
                    cell_ref=span.cell_ref,
                    region=span.region,
                    excerpt=span.excerpt,
                )
                for span in parsed.spans
            ],
        )
    except Exception:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def ingest_direct_text(project_id: str, text: str, label: str | None = None) -> dict:
    """Persist pasted/typed user text through the same Material + SourceSpan contract."""
    parsed = parse_direct_text(text, label)
    if len(parsed.content) > MAX_IMPORT_BYTES:
        raise ImportTooLargeError(
            f"Text exceeds the {MAX_IMPORT_BYTES} byte (12 MiB) import limit."
        )
    dest, stored = _write_collision_safe(project_id, DIRECT_TEXT_STORED_NAME, parsed.content)
    metadata = dict(parsed.metadata)
    metadata["stored_path"] = stored
    metadata["original_filename"] = parsed.filename
    metadata["storage_name"] = dest.name
    metadata["evidence_role"] = "evidence_not_instruction"
    try:
        return store.persist_imported_material(
            project_id,
            MaterialCreate(
                filename=parsed.filename,
                media_type=parsed.media_type,
                kind=parsed.kind,  # type: ignore[arg-type]
                byte_size=parsed.byte_size,
                checksum=parsed.checksum,
                notes=parsed.notes,
                metadata=metadata,
            ),
            [
                SourceSpanCreate(
                    material_id="pending",
                    locator_kind=span.locator_kind,  # type: ignore[arg-type]
                    page=span.page,
                    start_offset=span.start_offset,
                    end_offset=span.end_offset,
                    sheet=span.sheet,
                    cell_ref=span.cell_ref,
                    region=span.region,
                    excerpt=span.excerpt,
                )
                for span in parsed.spans
            ],
        )
    except Exception:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def ingest_t06_bytes(project_id: str, filename: str, content: bytes) -> dict:
    """Historical alias for the public intake path."""
    return ingest_bytes(project_id, filename, content)


__all__ = [
    "ImportTooLargeError",
    "UnreadableMaterialError",
    "UnsupportedMaterialError",
    "ingest_bytes",
    "ingest_direct_text",
    "ingest_t06_bytes",
    "safe_filename",
    "sniff_media_type",
]
