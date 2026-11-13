"""File upload validation service."""

import os
import re
from dataclasses import dataclass
from fastapi import UploadFile

from app.config import settings
from app.errors import AppError

# Magic byte signatures
PDF_MAGIC = b"%PDF-"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"

CHUNK_SIZE = 64 * 1024  # 64 KB streaming chunks


@dataclass
class ValidationResult:
    """Result of file upload validation."""

    content: bytes
    mime_type: str
    sanitized_filename: str


def sanitize_filename(filename: str | None) -> str:
    """Sanitize original filename for display only.

    Strips path separators, control characters, and caps length at 100 characters.
    Never use this filename to construct filesystem paths.
    """
    if not filename:
        return "unnamed_document"

    # Remove directory paths (handling both Unix and Windows separators)
    clean = os.path.basename(filename.replace("\\", "/"))

    # Strip control characters (ASCII 0-31 and 127) and path separators
    clean = re.sub(r"[\x00-\x1f\x7f/\\]", "", clean).strip()

    if not clean:
        clean = "unnamed_document"

    # Cap length at 100 characters while preserving extension if possible
    if len(clean) > 100:
        base, ext = os.path.splitext(clean)
        clean = base[: 100 - len(ext)] + ext

    return clean[:100]


def detect_mime_type(header: bytes) -> str:
    """Detect MIME type from file header magic bytes.

    Raises:
        AppError: UNSUPPORTED_TYPE (415) if header doesn't match PDF, PNG, or JPEG.
    """
    if header.startswith(PDF_MAGIC):
        return "application/pdf"
    if header.startswith(PNG_MAGIC):
        return "image/png"
    if header.startswith(JPEG_MAGIC):
        return "image/jpeg"

    raise AppError(
        code="UNSUPPORTED_TYPE",
        message="Unsupported file type. Only PDF, PNG, and JPEG files are supported.",
        status_code=415,
    )


async def validate_upload(file: UploadFile) -> ValidationResult:
    """Validate uploaded file stream chunk-by-chunk.

    Enforces streaming size limits, rejects empty files, and identifies MIME type
    strictly via header magic bytes.

    Raises:
        AppError: EMPTY_FILE (400) if upload contains 0 bytes.
        AppError: FILE_TOO_LARGE (413) if size exceeds MAX_FILE_MB.
        AppError: UNSUPPORTED_TYPE (415) if magic bytes are not recognized.
    """
    max_bytes = settings.max_file_mb * 1024 * 1024
    chunks: list[bytes] = []
    total_bytes = 0

    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise AppError(
                code="FILE_TOO_LARGE",
                message=f"File exceeds {settings.max_file_mb} MB limit.",
                status_code=413,
            )
        chunks.append(chunk)

    if total_bytes == 0:
        raise AppError(
            code="EMPTY_FILE",
            message="Uploaded file is empty.",
            status_code=400,
        )

    file_bytes = b"".join(chunks)
    mime_type = detect_mime_type(file_bytes[:32])
    sanitized_name = sanitize_filename(file.filename)

    return ValidationResult(
        content=file_bytes,
        mime_type=mime_type,
        sanitized_filename=sanitized_name,
    )
