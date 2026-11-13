"""Document management and review routes."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Query

from app.errors import AppError
from app.schemas import (
    DocumentDetail,
    DocumentSummary,
    DocumentUpdateRequest,
    ErrorPayload,
)
from app.services.checks import run_checks
from app.services.db import get_db, utc_now_iso
from app.services.documents import (
    delete_all_documents,
    delete_document_record,
    get_document_by_id,
    list_documents,
    update_document_data,
)
from app.services.extractor import extract_document
from app.services.storage import validate_document_id

logger = logging.getLogger("doc_extractor")

router = APIRouter(prefix="/api/documents", tags=["Documents"])


@router.get("", response_model=list[DocumentSummary], summary="List documents")
def list_documents_endpoint(
    status: Optional[str] = Query(None, description="Optional status filter"),
    limit: int = Query(50, ge=1, le=200, description="Page limit (max 200)"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> list[DocumentSummary]:
    """Retrieve list of document summaries ordered newest first."""
    return list_documents(status=status, limit=limit, offset=offset)


@router.delete("", summary="Delete all documents")
def delete_all_endpoint(
    confirm: bool = Query(False, description="Confirmation flag required to purge all data"),
) -> dict:
    """Delete all documents and purge storage files."""
    if not confirm:
        raise AppError(
            code="CONFIRM_REQUIRED",
            message="Purging all data requires ?confirm=true.",
            status_code=400,
        )
    count = delete_all_documents()
    return {"deleted": count, "message": f"Successfully deleted {count} documents."}


@router.get("/{id}", response_model=DocumentDetail, summary="Get document detail")
def get_document_endpoint(id: str) -> DocumentDetail:
    """Retrieve full document detail by UUID."""
    validate_document_id(id)
    doc = get_document_by_id(id)
    if not doc:
        raise AppError(code="NOT_FOUND", message="Document not found.", status_code=404)
    return doc


@router.put("/{id}", response_model=DocumentDetail, summary="Update document extracted data")
def update_document_endpoint(id: str, payload: DocumentUpdateRequest) -> DocumentDetail:
    """Update corrected data, re-run checks, update flags, and optionally mark reviewed."""
    validate_document_id(id)
    return update_document_data(
        document_id=id,
        data=payload.data,
        mark_reviewed=payload.mark_reviewed,
    )


@router.post("/{id}/reextract", response_model=DocumentDetail, summary="Re-run extraction")
def reextract_document_endpoint(id: str) -> DocumentDetail:
    """Re-run extraction on existing preprocessed document files."""
    valid_id = validate_document_id(id)
    doc = get_document_by_id(valid_id)
    if not doc:
        raise AppError(code="NOT_FOUND", message="Document not found.", status_code=404)

    now_str = utc_now_iso()
    extraction_error = None
    invoice_data = None
    meta = None
    flags = {}

    try:
        invoice_data, meta = extract_document(valid_id)
        flags = run_checks(invoice_data)
        status = "needs_review" if flags else "extracted"
    except AppError as exc:
        logger.warning("Re-extraction failed for %s: [%s] %s", valid_id, exc.code, exc.message)
        extraction_error = {"code": exc.code, "message": exc.message}
        status = "needs_review"
    except Exception as exc:
        logger.exception("Unexpected re-extraction error for %s", valid_id)
        extraction_error = {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred during extraction.",
        }
        status = "needs_review"

    with get_db() as conn:
        cursor = conn.cursor()
        source = meta.source if meta else doc.mime_type
        cursor.execute(
            """
            UPDATE documents
            SET status = ?, source = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, source, now_str, valid_id),
        )

        original_json = json.dumps(invoice_data.model_dump()) if invoice_data else None
        flags_json = json.dumps(flags)
        meta_json = json.dumps(meta.model_dump()) if meta else None
        error_json = json.dumps(extraction_error) if extraction_error else None

        cursor.execute(
            """
            UPDATE extractions
            SET original_json = ?, flags_json = ?, meta_json = ?, error_json = ?
            WHERE document_id = ?
            """,
            (original_json, flags_json, meta_json, error_json, valid_id),
        )

    updated = get_document_by_id(valid_id)
    if not updated:
        raise AppError(code="INTERNAL_ERROR", message="Failed to retrieve reextracted document.", status_code=500)
    return updated


@router.delete("/{id}", summary="Delete single document")
def delete_document_endpoint(id: str) -> dict:
    """Delete a document and its storage directory."""
    validate_document_id(id)
    delete_document_record(id)
    return {"message": "Document deleted successfully."}

