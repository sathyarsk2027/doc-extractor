"""Document extraction route definitions."""

import logging
import uuid
from fastapi import APIRouter, File, UploadFile

from app.errors import AppError
from app.schemas import ExtractResponse, PagePreview
from app.services.validation import validate_upload
from app.services.extractor import extract_document
from app.services.storage import (
    save_original,
    delete_document,
    cleanup_expired,
    get_document_dir,
)
from app.services.preprocessing import preprocess_document

logger = logging.getLogger("doc_extractor")

router = APIRouter(prefix="/api", tags=["Extraction"])


@router.post("/extract", response_model=ExtractResponse, summary="Upload document for extraction")
def extract_endpoint(file: UploadFile = File(...)) -> ExtractResponse:
    """Validate uploaded document, preprocess pages, and execute extraction pipeline.

    This is a sync def so FastAPI runs it in a thread pool, allowing the
    blocking Groq SDK call without starving the async event loop.
    """
    # Run cleanup of expired document folders on each upload request
    cleanup_expired()

    # Generate unique UUID4 identifier for this upload
    document_id = str(uuid.uuid4())

    # Read file bytes synchronously (sync route, no await needed)
    file_bytes = file.file.read()

    # Validate the file content
    from app.services.validation import (
        detect_mime_type,
        sanitize_filename,
    )

    if len(file_bytes) == 0:
        raise AppError(
            code="EMPTY_FILE",
            message="Uploaded file is empty.",
            status_code=400,
        )

    max_bytes = __import__("app.config", fromlist=["settings"]).settings.max_file_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        from app.config import settings as _s
        raise AppError(
            code="FILE_TOO_LARGE",
            message=f"File exceeds {_s.max_file_mb} MB limit.",
            status_code=413,
        )

    mime_type = detect_mime_type(file_bytes[:32])
    sanitized_filename = sanitize_filename(file.filename)

    try:
        # Save original untouched bytes
        save_original(document_id, file_bytes, mime_type)

        # Preprocess document (renders previews: page_1.png, page_2.png, ...)
        doc_dir = get_document_dir(document_id)
        pages_meta = preprocess_document(doc_dir, file_bytes, mime_type)

        pages = [
            PagePreview(
                page=p["page"],
                preview_url=f"/api/files/{document_id}/pages/{p['page']}.png",
                width=p["width"],
                height=p["height"],
            )
            for p in pages_meta
        ]
    except Exception:
        # If preprocessing fails midway, delete partially created folder
        delete_document(document_id)
        raise

    # Attempt LLM extraction — failures here return 200 with extraction_error
    extraction = None
    extraction_meta = None
    extraction_error = None

    try:
        invoice_data, meta = extract_document(document_id)
        extraction = invoice_data.model_dump()
        extraction_meta = meta.model_dump()
    except AppError as exc:
        logger.warning("Extraction failed for %s: [%s] %s", document_id, exc.code, exc.message)
        extraction_error = {"code": exc.code, "message": exc.message}
    except Exception as exc:
        logger.exception("Unexpected extraction error for %s", document_id)
        extraction_error = {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred during extraction.",
        }

    return ExtractResponse(
        document_id=document_id,
        filename=sanitized_filename,
        mime_type=mime_type,
        page_count=len(pages),
        pages=pages,
        extraction=extraction,
        extraction_meta=extraction_meta,
        extraction_error=extraction_error,
        flags={},
        needs_review=True,
        message="Extraction complete." if extraction else "Preprocessing complete. Extraction failed.",
    )
