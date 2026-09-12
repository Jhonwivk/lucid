"""Raw DOCX/PPTX intake. Bytes + provenance only; Azure understands them later."""

from __future__ import annotations

from .common import EVIDENCE_BOUNDARY, ImportResult, ParsedSpan, sha256_hex
from .zip_safety import assert_safe_ooxml

DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX_MEDIA = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def parse_office_raw(filename: str, content: bytes, *, suffix: str) -> ImportResult:
    kind_label = "DOCX" if suffix == ".docx" else "PPTX"
    media = DOCX_MEDIA if suffix == ".docx" else PPTX_MEDIA
    archive = assert_safe_ooxml(content, kind=kind_label)
    try:
        entry_count = len(archive.namelist())
    finally:
        archive.close()
    notes = (
        f"{EVIDENCE_BOUNDARY} {kind_label} bytes were stored as a raw Material. "
        "No custom semantic parser ran. Content Understanding is performed later by "
        "the Business Modeling Agent via Azure Content Understanding when configured."
    )
    return ImportResult(
        filename=filename,
        media_type=media,
        kind="document",
        byte_size=len(content),
        checksum=sha256_hex(content),
        notes=notes,
        metadata={
            "parser": "lucid.office_raw",
            "office_kind": kind_label.lower(),
            "zip_entry_count": entry_count,
            "semantic_extraction": "not_performed",
            "semantic_understanding": "not_performed",
            "needs_azure_content_understanding": True,
            "processing_capability": "azure_content_understanding",
            "processing_state": "pending",
            "evidence_role": "evidence_not_instruction",
        },
        spans=[
            ParsedSpan(
                locator_kind="unknown",
                excerpt=(
                    f"Whole-source {kind_label} package. "
                    "Original page/slide coordinates are unknown until Azure analysis."
                ),
                region={
                    "coordinate_space": "whole_source",
                    "region_state": "whole_source",
                    "precision": "whole_source",
                },
            )
        ],
        content=content,
    )
