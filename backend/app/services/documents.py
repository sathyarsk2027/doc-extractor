"""Document repository service managing database records and file synchronization."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings
from app.errors import AppError
from app.schemas import (
    DocumentDetail,
    DocumentSummary,
    ErrorPayload,
    ExtractionMeta,
    InvoiceData,
    PagePreview,
)
from app.services.checks import run_checks
from app.services.db import get_db, utc_now_iso
from app.services.storage import delete_document, validate_document_id

logger = logging.getLogger("doc_extractor")


def _row_to_document_detail(row: Any) -> DocumentDetail:
    """Convert a database join row to DocumentDetail schema."""
    pages_raw = json.loads(row["pages_json"]) if row["pages_json"] else []
    pages = [PagePreview(**p) for p in pages_raw]

    original_raw = json.loads(row["original_json"]) if row["original_json"] else None
    original = InvoiceData(**original_raw) if original_raw else None

    reviewed_raw = json.loads(row["reviewed_json"]) if row["reviewed_json"] else None
    reviewed = InvoiceData(**reviewed_raw) if reviewed_raw else None

    flags = json.loads(row["flags_json"]) if row["flags_json"] else {}
    meta_raw = json.loads(row["meta_json"]) if row["meta_json"] else None
    meta = ExtractionMeta(**meta_raw) if meta_raw else None

    error_raw = json.loads(row["error_json"]) if row["error_json"] else None
    error = ErrorPayload(**error_raw) if error_raw else None

    status = row["status"]
    needs_review = status == "needs_review"

    return DocumentDetail(
        id=row["id"],
        filename=row["filename"],
        mime_type=row["mime_type"],
        page_count=row["page_count"],
        status=status,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        reviewed_at=row["reviewed_at"],
        pages=pages,
        original=original,
        reviewed=reviewed,
        flags=flags,
        needs_review=needs_review,
        meta=meta,
        error=error,
    )


def save_extracted_document(
    document_id: str,
    filename: str,
    mime_type: str,
    page_count: int,
    pages: list[PagePreview],
    source: str = "image",
    original_data: InvoiceData | None = None,
    flags: dict[str, Any] | None = None,
    meta: ExtractionMeta | None = None,
    error: ErrorPayload | dict[str, str] | None = None,
) -> DocumentDetail:
    """Insert newly uploaded and extracted document into database."""
    valid_id = validate_document_id(document_id)
    now_str = utc_now_iso()

    if flags is None:
        flags = {}

    error_payload = None
    if error:
        if isinstance(error, ErrorPayload):
            error_payload = error
        elif isinstance(error, dict):
            error_payload = ErrorPayload(
                code=error.get("code", "EXTRACTION_ERROR"),
                message=error.get("message", "Extraction failed."),
            )

    # Determine status: "needs_review" if flags or error, else "extracted"
    if error_payload or flags:
        status = "needs_review"
    else:
        status = "extracted"

    pages_json = json.dumps([p.model_dump() for p in pages])
    original_json = json.dumps(original_data.model_dump()) if original_data else None
    flags_json = json.dumps(flags)
    meta_json = json.dumps(meta.model_dump()) if meta else None
    error_json = json.dumps(error_payload.model_dump()) if error_payload else None

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO documents (
                id, filename, mime_type, page_count, pages_json, status, source,
                created_at, updated_at, reviewed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                valid_id,
                filename,
                mime_type,
                page_count,
                pages_json,
                status,
                source,
                now_str,
                now_str,
            ),
        )
        cursor.execute(
            """
            INSERT INTO extractions (
                document_id, original_json, reviewed_json, flags_json, meta_json, error_json
            ) VALUES (?, ?, NULL, ?, ?, ?)
            """,
            (
                valid_id,
                original_json,
                flags_json,
                meta_json,
                error_json,
            ),
        )

    doc = get_document_by_id(valid_id)
    if not doc:
        raise AppError(code="INTERNAL_ERROR", message="Failed to retrieve saved document.", status_code=500)
    return doc


def get_document_by_id(document_id: str) -> DocumentDetail | None:
    """Retrieve full document detail by ID."""
    valid_id = validate_document_id(document_id)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT d.id, d.filename, d.mime_type, d.page_count, d.pages_json,
                   d.status, d.source, d.created_at, d.updated_at, d.reviewed_at,
                   e.original_json, e.reviewed_json, e.flags_json, e.meta_json, e.error_json
            FROM documents d
            LEFT JOIN extractions e ON d.id = e.document_id
            WHERE d.id = ?
            """,
            (valid_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return _row_to_document_detail(row)


def list_documents(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[DocumentSummary]:
    """List documents with pagination and optional status filter, newest first."""
    clamped_limit = max(1, min(limit, 200))
    clamped_offset = max(0, offset)

    query = """
        SELECT d.id, d.filename, d.created_at, d.status, d.page_count,
               e.original_json, e.reviewed_json
        FROM documents d
        LEFT JOIN extractions e ON d.id = e.document_id
    """
    params: list[Any] = []

    if status:
        query += " WHERE d.status = ?"
        params.append(status)

    query += " ORDER BY d.created_at DESC, d.rowid DESC LIMIT ? OFFSET ?"
    params.extend([clamped_limit, clamped_offset])

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

    summaries = []
    for r in rows:
        data_json = r["reviewed_json"] or r["original_json"]
        vendor = None
        total = None
        currency = None
        if data_json:
            try:
                parsed = json.loads(data_json)
                vendor = parsed.get("vendor")
                total = parsed.get("total")
                currency = parsed.get("currency")
            except Exception:
                pass

        doc_status = r["status"]
        summaries.append(
            DocumentSummary(
                id=r["id"],
                filename=r["filename"],
                created_at=r["created_at"],
                status=doc_status,
                page_count=r["page_count"],
                vendor=vendor,
                total=total,
                currency=currency,
                needs_review=(doc_status == "needs_review"),
            )
        )
    return summaries


def update_document_data(
    document_id: str,
    data: InvoiceData,
    mark_reviewed: bool = False,
) -> DocumentDetail:
    """Update corrected invoice data, recompute validation flags, and set review status."""
    valid_id = validate_document_id(document_id)
    doc = get_document_by_id(valid_id)
    if not doc:
        raise AppError(code="NOT_FOUND", message="Document not found.", status_code=404)

    # Re-run validation checks on corrected data
    flags = run_checks(data)
    reviewed_json = json.dumps(data.model_dump())
    flags_json = json.dumps(flags)
    now_str = utc_now_iso()

    with get_db() as conn:
        cursor = conn.cursor()
        if mark_reviewed:
            status = "reviewed"
            cursor.execute(
                """
                UPDATE documents
                SET status = ?, updated_at = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (status, now_str, now_str, valid_id),
            )
        else:
            # Keep current status
            cursor.execute(
                """
                UPDATE documents
                SET updated_at = ?
                WHERE id = ?
                """,
                (now_str, valid_id),
            )

        cursor.execute(
            """
            UPDATE extractions
            SET reviewed_json = ?, flags_json = ?
            WHERE document_id = ?
            """,
            (reviewed_json, flags_json, valid_id),
        )

    updated = get_document_by_id(valid_id)
    if not updated:
        raise AppError(code="INTERNAL_ERROR", message="Failed to retrieve updated document.", status_code=500)
    return updated


def delete_document_record(document_id: str) -> None:
    """Delete a document from database and purge its directory from disk."""
    valid_id = validate_document_id(document_id)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM documents WHERE id = ?", (valid_id,))
        if cursor.rowcount == 0:
            raise AppError(code="NOT_FOUND", message="Document not found.", status_code=404)

    # Remove files from disk
    delete_document(valid_id)


def delete_all_documents() -> int:
    """Delete all documents from database and wipe all storage folders."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM documents")
        ids = [row[0] for row in cursor.fetchall()]
        cursor.execute("DELETE FROM documents")

    for doc_id in ids:
        delete_document(doc_id)

    return len(ids)


def purge_retention(retention_days: int | None = None) -> int:
    """Delete documents older than retention period (default 30 days). 0 disables."""
    if retention_days is None:
        retention_days = settings.retention_days

    if retention_days <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM documents WHERE created_at < ?", (cutoff_iso,))
        expired_ids = [row[0] for row in cursor.fetchall()]

    for doc_id in expired_ids:
        try:
            delete_document_record(doc_id)
        except Exception as exc:
            logger.warning("Error purging expired document %s: %s", doc_id, exc)

    return len(expired_ids)
