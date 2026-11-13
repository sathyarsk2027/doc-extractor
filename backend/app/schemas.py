"""Pydantic schemas for API requests and responses."""

from typing import Any
from pydantic import BaseModel, Field


class PagePreview(BaseModel):
    """Metadata and URL for a rendered document page preview."""

    page: int = Field(..., description="1-indexed page number")
    preview_url: str = Field(..., description="URL to retrieve the page preview PNG")
    width: int = Field(..., description="Preview image width in pixels")
    height: int = Field(..., description="Preview image height in pixels")


class ExtractResponse(BaseModel):
    """Response schema for POST /api/extract."""

    document_id: str | None = Field(
        default=None, description="Unique identifier for uploaded document"
    )
    filename: str = Field(..., description="Sanitized original document filename")
    mime_type: str = Field(
        ..., description="Validated MIME type (application/pdf, image/png, image/jpeg)"
    )
    page_count: int = Field(default=0, description="Total number of pages processed")
    pages: list[PagePreview] = Field(
        default_factory=list, description="List of page preview descriptors"
    )
    extraction: dict[str, Any] | None = Field(
        default=None, description="Extracted structured data (stub for Phase 3)"
    )
    message: str = Field(..., description="Status or informational message")
