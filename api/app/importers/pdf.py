"""Text-PDF parser using pypdf. No OCR; scanned pages stay empty/unknown."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError, PdfStreamError, PyPdfError

from .common import EVIDENCE_BOUNDARY, ImportResult, ParsedSpan, UnreadableMaterialError, sha256_hex

_PDF_READ_ERRORS = (PdfReadError, PdfStreamError, PyPdfError, FileNotDecryptedError, OSError, ValueError)

EMPTY_PAGE_EXCERPT = (
    "No extractable text on this page. "
    "OCR of scanned PDFs is not implemented; content remains unknown."
)


def parse_pdf(filename: str, content: bytes) -> ImportResult:
    if not content:
        raise UnreadableMaterialError("PDF file is empty and cannot be parsed as a document.")

    try:
        reader = PdfReader(BytesIO(content), strict=False)
    except _PDF_READ_ERRORS as exc:
        raise UnreadableMaterialError(
            f"PDF could not be read ({type(exc).__name__}). The file may be malformed."
        ) from exc

    if getattr(reader, "is_encrypted", False):
        raise UnreadableMaterialError(
            "Encrypted PDF cannot be read without a password. "
            "LUCID does not decrypt or bypass PDF encryption; the file remains unread."
        )

    try:
        pages = list(reader.pages)
    except FileNotDecryptedError as exc:
        raise UnreadableMaterialError(
            "Encrypted PDF cannot be read without a password. "
            "LUCID does not decrypt or bypass PDF encryption; the file remains unread."
        ) from exc
    except _PDF_READ_ERRORS as exc:
        raise UnreadableMaterialError(
            f"PDF pages could not be read ({type(exc).__name__}). The file may be malformed."
        ) from exc

    spans: list[ParsedSpan] = []
    page_lengths: list[int] = []
    empty_pages: list[int] = []

    for index, page in enumerate(pages, start=1):
        try:
            extracted = page.extract_text() or ""
        except Exception:  # noqa: BLE001 — page-level extract failure stays unknown
            extracted = ""
        page_text = extracted.strip()
        page_lengths.append(len(page_text))
        if not page_text:
            empty_pages.append(index)
            excerpt = EMPTY_PAGE_EXCERPT
        else:
            excerpt = page_text[:800]
        spans.append(
            ParsedSpan(
                locator_kind="page",
                page=index,
                excerpt=excerpt,
            )
        )

    notes = (
        f"{EVIDENCE_BOUNDARY} "
        "Page text extracted with a local PDF parser. "
        "OCR is not available for scanned or image-only PDFs."
    )
    if empty_pages:
        notes += f" Pages without extractable text: {empty_pages}."

    return ImportResult(
        filename=filename,
        media_type="application/pdf",
        kind="document",
        byte_size=len(content),
        checksum=sha256_hex(content),
        notes=notes,
        metadata={
            "parser": "lucid.pdf.pypdf",
            "page_count": len(pages),
            "page_text_lengths": page_lengths,
            "empty_pages": empty_pages,
            "pages_without_extractable_text": empty_pages,
            "ocr": "not_implemented",
            "semantic_extraction": "not_performed",
            "evidence_role": "evidence_not_instruction",
            "empty": len(pages) == 0 or len(empty_pages) == len(pages),
        },
        spans=spans,
        content=content,
    )
