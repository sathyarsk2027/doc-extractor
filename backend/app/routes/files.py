"""File preview image route definitions."""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.errors import AppError
from app.services.storage import get_page_path, validate_document_id

router = APIRouter(prefix="/api/files", tags=["Files"])


@router.get(
    "/{document_id}/pages/{page_number}.png",
    summary="Get rendered document page preview",
    response_class=FileResponse,
)
def get_page_preview(document_id: str, page_number: int) -> FileResponse:
    """Serve rendered preview PNG image with caching header.

    Raises:
        AppError: NOT_FOUND (404) if document_id is invalid or page preview does not exist.
    """
    validate_document_id(document_id)
    page_path = get_page_path(document_id, page_number)

    if not page_path or not page_path.is_file():
        raise AppError(
            code="NOT_FOUND",
            message="Preview page image not found or has expired.",
            status_code=404,
        )

    return FileResponse(
        path=page_path,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=300"},
    )
