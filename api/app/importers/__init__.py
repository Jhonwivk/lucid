"""Dispatch real local parsers for supported material families.

Public file intake accepts TXT / Markdown / text-PDF / CSV / XLSX / PNG / JPEG.
Direct user-entered text is a peer Material via a dedicated API path.
Legacy .xls and other types are rejected honestly.

Adapters normalize source into Material + SourceSpan. They must not perform
semantic business understanding. Image intake records bytes, metadata, and
full-image provenance only.
"""

from __future__ import annotations

from pathlib import Path

from .common import ImportResult, UnreadableMaterialError, UnsupportedMaterialError
from .json_raw import parse_json_raw
from .office_raw import parse_office_raw
from .pdf import parse_pdf
from .text import parse_direct_text, parse_text

TEXT_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}
PDF_TYPES = {".pdf": "application/pdf"}
CSV_TYPES = {".csv": "text/csv"}
XLSX_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
JSON_TYPES = {".json": "application/json"}
OFFICE_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
LEGACY_TABLE_TYPES = {".xls", ".xlsm", ".xlsb"}

INTAKE_SUFFIXES = {
    **TEXT_TYPES,
    **PDF_TYPES,
    **CSV_TYPES,
    **XLSX_TYPES,
    **IMAGE_TYPES,
    **JSON_TYPES,
    **OFFICE_TYPES,
}
INTAKE_CAPABILITY = "txt_md_pdf_csv_xlsx_png_jpeg_json_docx_pptx"
INTAKE_TYPE_HELP = (
    "TXT, Markdown (.md/.markdown), text PDF, CSV, XLSX, PNG, JPEG, JSON, DOCX, or PPTX"
)

# Historical aliases used by T06 helpers.
T06_SUFFIXES = {**TEXT_TYPES, **PDF_TYPES}
T06_TYPE_HELP = INTAKE_TYPE_HELP


def sniff_media_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in LEGACY_TABLE_TYPES:
        raise UnsupportedMaterialError(
            f"Unsupported file type '{suffix}'. Legacy Excel ({suffix}) is not parsed; "
            "export as .xlsx. Nothing was stored."
        )
    media_type = INTAKE_SUFFIXES.get(suffix)
    if media_type is None:
        raise UnsupportedMaterialError(
            f"Unsupported file type '{suffix or filename}'. "
            f"Intake accepts {INTAKE_TYPE_HELP}."
        )
    return media_type


def sniff_t06_media_type(filename: str) -> str:
    """Public intake sniff (name kept for T06 call sites)."""
    return sniff_media_type(filename)


def parse_material(filename: str, content: bytes) -> ImportResult:
    suffix = Path(filename).suffix.lower()
    if suffix in TEXT_TYPES:
        return parse_text(filename, content, TEXT_TYPES[suffix])
    if suffix in PDF_TYPES:
        return parse_pdf(filename, content)
    if suffix in CSV_TYPES:
        from .tabular import parse_csv

        return parse_csv(filename, content)
    if suffix in XLSX_TYPES:
        from .tabular import parse_xlsx

        return parse_xlsx(filename, content)
    if suffix in IMAGE_TYPES:
        from .image import parse_image

        return parse_image(filename, content, IMAGE_TYPES[suffix])
    if suffix in JSON_TYPES:
        return parse_json_raw(filename, content)
    if suffix in OFFICE_TYPES:
        return parse_office_raw(filename, content, suffix=suffix)
    if suffix in LEGACY_TABLE_TYPES:
        raise UnsupportedMaterialError(
            f"Unsupported file type '{suffix}'. Legacy Excel ({suffix}) is not parsed; "
            "export as .xlsx."
        )
    raise UnsupportedMaterialError(
        f"Unsupported file type '{suffix or filename}'. Intake accepts {INTAKE_TYPE_HELP}."
    )


def parse_t06_material(filename: str, content: bytes) -> ImportResult:
    """Public intake parser (name kept for T06 call sites)."""
    return parse_material(filename, content)


__all__ = [
    "INTAKE_CAPABILITY",
    "INTAKE_SUFFIXES",
    "T06_SUFFIXES",
    "UnreadableMaterialError",
    "UnsupportedMaterialError",
    "parse_direct_text",
    "parse_material",
    "parse_t06_material",
    "sniff_media_type",
    "sniff_t06_media_type",
]
