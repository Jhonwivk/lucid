"""PNG/JPEG ingest: validate bytes, record image metadata, full-image provenance.

Importers preserve evidence. Semantic understanding belongs to T09 and must
never be added here just because a model can consume images.
"""

from __future__ import annotations

import importlib.metadata
from io import BytesIO

from PIL import Image, ImageFile, UnidentifiedImageError
from PIL import Image as PILImage

from .common import EVIDENCE_BOUNDARY, ImportResult, ParsedSpan, UnreadableMaterialError, sha256_hex

ImageFile.LOAD_TRUNCATED_IMAGES = False
PILImage.MAX_IMAGE_PIXELS = 40_000_000
EXPECTED_FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG"}

FULL_IMAGE_REGION = {
    "coordinate_space": "normalized_top_left",
    "region_state": "full_image",
    "x": 0.0,
    "y": 0.0,
    "width": 1.0,
    "height": 1.0,
    "confidence": None,
}


def _pillow_version() -> str:
    try:
        return importlib.metadata.version("Pillow")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def parse_image(filename: str, content: bytes, media_type: str) -> ImportResult:
    if not content:
        raise UnreadableMaterialError("Image file is empty and cannot be parsed.")
    expected = EXPECTED_FORMATS.get(media_type)
    if expected is None:
        raise UnreadableMaterialError("Only PNG and JPEG images are accepted.")
    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            width, height = image.size
            detected_format = image.format
            mode = image.mode
    except Image.DecompressionBombError as exc:
        raise UnreadableMaterialError("Image exceeds the pixel safety limit and was not opened.") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise UnreadableMaterialError(
            f"Image could not be read ({type(exc).__name__}). The file may be malformed."
        ) from exc
    if detected_format != expected:
        raise UnreadableMaterialError(
            f"File extension declares {expected} but the bytes are {detected_format or 'unknown'}."
        )

    notes = (
        f"{EVIDENCE_BOUNDARY} PNG/JPEG bytes, checksum, and dimensions were recorded. "
        "Semantic understanding is not performed during image intake; T09 consumes the Evidence Set."
    )
    return ImportResult(
        filename=filename,
        media_type=media_type,
        kind="image",
        byte_size=len(content),
        checksum=sha256_hex(content),
        notes=notes,
        metadata={
            "parser": "lucid.image.pillow",
            "parser_version": _pillow_version(),
            "pixel_width": width,
            "pixel_height": height,
            "image_format": detected_format,
            "image_mode": mode,
            "ocr": "not_implemented",
            "pdf_ocr": "not_implemented",
            "image_text_recognition": "not_performed",
            "semantic_extraction": "not_performed",
            "semantic_understanding": "not_performed",
            "understanding_layer": "t09",
            "evidence_role": "evidence_not_instruction",
        },
        spans=[
            ParsedSpan(
                locator_kind="region",
                region=dict(FULL_IMAGE_REGION),
                excerpt=(
                    "Full-image provenance only. "
                    "Semantic understanding is not performed during image intake."
                ),
            )
        ],
        content=content,
    )
