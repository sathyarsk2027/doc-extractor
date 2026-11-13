"""Document extraction route definitions."""

import uuid
from fastapi import APIRouter, File, UploadFile

from app.schemas import ExtractResponse, PagePreview
from app.services.validation import validate_upload
from app.services.extractor import extract
from app.services.storage import (
    create_document_dir,
    save_original,
    delete_document,
    cleanup_expired,
    get_document_dir,
)
from app.services.preprocessing import preprocess_document

router = APIRouter(prefix="/api", tags=["Extraction"])


@router.post("/extract", response_model=ExtractResponse, summary="Upload document for extraction")
async def extract_document(file: UploadFile = File(...)) -> ExtractResponse:
    """Validate uploaded document, preprocess pages, and execute extraction pipeline."""
    # Run cleanup of expired document folders on each upload request
    cleanup_expired()

    # Generate unique UUID4 identifier for this upload
    document_id = str(uuid.uuid4())

    # Stream & validate uploaded file
    validation = await validate_upload(file)

    try:
        # Save original untouched bytes
        save_original(document_id, validation.content, validation.mime_type)

        # Preprocess document (renders previews: page_1.png, page_2.png, ...)
        doc_dir = get_document_dir(document_id)
        pages_meta = preprocess_document(doc_dir, validation.content, validation.mime_type)

        pages = [
            PagePreview(
                page=p["page"],
                preview_url=f"/api/files/{document_id}/pages/{p['page']}.png",
                width=p["width"],
                height=p["height"],
            )
            for p in pages_meta
        ]

        extracted_data = extract(validation.content, validation.mime_type)

        return ExtractResponse(
            document_id=document_id,
            filename=validation.sanitized_filename,
            mime_type=validation.mime_type,
            page_count=len(pages),
            pages=pages,
            extraction=extracted_data,
            message="Preprocessing complete. LLM extraction arrives in Phase 3.",
        )
    except Exception:
        # If preprocessing fails midway, delete partially created folder
        delete_document(document_id)
        raise
