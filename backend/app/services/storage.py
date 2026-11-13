"""Document storage service managing temporary files and TTL cleanup."""

import os
import shutil
import time
import uuid
from pathlib import Path

from app.config import settings
from app.errors import AppError

MIME_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}


def validate_document_id(document_id: str | uuid.UUID) -> str:
    """Validate that document_id is a valid UUID4, guarding against path traversal attacks.

    Raises:
        AppError: NOT_FOUND (404) if document_id is not a valid UUID string.
    """
    try:
        val = uuid.UUID(str(document_id), version=4)
        return str(val)
    except (ValueError, TypeError, AttributeError):
        raise AppError(code="NOT_FOUND", message="Document not found.", status_code=404)


def get_document_dir(document_id: str | uuid.UUID) -> Path:
    """Return the absolute path for a document directory after validating the UUID."""
    valid_id = validate_document_id(document_id)
    return settings.storage_path / valid_id


def create_document_dir(document_id: str | uuid.UUID) -> Path:
    """Create and return the directory for a specific document."""
    doc_dir = get_document_dir(document_id)
    doc_dir.mkdir(parents=True, exist_ok=True)
    return doc_dir


def save_original(document_id: str | uuid.UUID, content: bytes, mime_type: str) -> Path:
    """Save original raw document bytes using extension derived strictly from MIME type.

    The user's original filename or extension is never used for disk storage.
    """
    ext = MIME_EXTENSIONS.get(mime_type)
    if not ext:
        raise AppError(
            code="UNSUPPORTED_TYPE",
            message=f"Cannot store unsupported MIME type: {mime_type}",
            status_code=415,
        )

    doc_dir = create_document_dir(document_id)
    target_path = doc_dir / f"original{ext}"
    target_path.write_bytes(content)
    return target_path


def get_page_path(document_id: str | uuid.UUID, page_number: int) -> Path | None:
    """Retrieve Path to a rendered page PNG if it exists.

    Validates document_id and page number to prevent directory traversal.
    Returns None if the document directory or page preview does not exist.
    """
    if page_number < 1:
        return None

    doc_dir = get_document_dir(document_id)
    page_path = doc_dir / f"page_{page_number}.png"

    # Confirm the resolved path stays inside doc_dir and exists
    try:
        resolved = page_path.resolve()
        if not resolved.is_relative_to(doc_dir.resolve()):
            return None
    except (ValueError, RuntimeError):
        return None

    if page_path.is_file():
        return page_path
    return None


def delete_document(document_id: str | uuid.UUID) -> None:
    """Safely delete a document directory and all its contents."""
    try:
        doc_dir = get_document_dir(document_id)
        if doc_dir.exists() and doc_dir.is_dir():
            shutil.rmtree(doc_dir, ignore_errors=True)
    except AppError:
        pass


def cleanup_expired(ttl_minutes: int | None = None) -> int:
    """Remove document directories older than FILE_TTL_MINUTES.

    Inspects folder modification times against current timestamp.
    Returns the count of deleted directories.
    """
    if ttl_minutes is None:
        ttl_minutes = settings.file_ttl_minutes

    ttl_seconds = ttl_minutes * 60
    now = time.time()
    deleted_count = 0

    storage_root = settings.storage_path
    if not storage_root.exists() or not storage_root.is_dir():
        return 0

    for entry in storage_root.iterdir():
        if entry.is_dir():
            try:
                # Validate that folder name is a valid UUID before touching
                uuid.UUID(entry.name, version=4)
                mtime = entry.stat().st_mtime
                if (now - mtime) > ttl_seconds:
                    shutil.rmtree(entry, ignore_errors=True)
                    deleted_count += 1
            except (ValueError, OSError):
                # Ignore non-UUID folders or transient filesystem errors
                continue

    return deleted_count
