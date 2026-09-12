"""Bounded ZIP inspection for OOXML uploads. No semantic parse."""

from __future__ import annotations

import io
import zipfile

from .common import UnreadableMaterialError

MAX_ZIP_FILES = 512
MAX_UNCOMPRESSED_BYTES = 40 * 1024 * 1024
MAX_RATIO = 200


def assert_safe_ooxml(content: bytes, *, kind: str) -> zipfile.ZipFile:
    if not content:
        raise UnreadableMaterialError(f"{kind} file is empty.")
    if content[:2] != b"PK":
        raise UnreadableMaterialError(
            f"{kind} is not a ZIP/OOXML package. Nothing was stored as a parsed document."
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise UnreadableMaterialError(
            f"{kind} could not be opened as ZIP ({type(exc).__name__})."
        ) from exc
    infos = archive.infolist()
    if len(infos) > MAX_ZIP_FILES:
        archive.close()
        raise UnreadableMaterialError(
            f"{kind} has too many ZIP entries ({len(infos)} > {MAX_ZIP_FILES})."
        )
    total = 0
    for item in infos:
        if item.file_size < 0 or item.compress_size < 0:
            archive.close()
            raise UnreadableMaterialError(f"{kind} ZIP entry sizes are invalid.")
        total += item.file_size
        if item.compress_size and item.file_size // max(item.compress_size, 1) > MAX_RATIO:
            archive.close()
            raise UnreadableMaterialError(
                f"{kind} looks like a compression bomb and was not opened."
            )
        if total > MAX_UNCOMPRESSED_BYTES:
            archive.close()
            raise UnreadableMaterialError(
                f"{kind} uncompressed size exceeds the {MAX_UNCOMPRESSED_BYTES} byte safety limit."
            )
    names = set(archive.namelist())
    if "[Content_Types].xml" not in names:
        archive.close()
        raise UnreadableMaterialError(
            f"{kind} is a ZIP archive but is missing OOXML [Content_Types].xml. "
            "It was not stored as a valid office package."
        )
    return archive
