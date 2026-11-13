"""Pydantic schemas for API requests and responses."""

from typing import Any
from pydantic import BaseModel, Field


class LineItem(BaseModel):
    """A single line item from an invoice or receipt."""

    description: str
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = None


class InvoiceData(BaseModel):
    """Structured data extracted from an invoice or receipt."""

    vendor: str | None = None
    invoice_number: str | None = None
    date: str | None = None  # ISO 8601 YYYY-MM-DD
    currency: str | None = None  # 3-letter code e.g. INR, USD
    line_items: list[LineItem] = []
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None


class ExtractionMeta(BaseModel):
    """Metadata about the LLM extraction call."""

    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    pages_sent: list[int]
    repaired: bool = False


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
        default=None, description="Extracted structured data from the document"
    )
    extraction_meta: dict[str, Any] | None = Field(
        default=None, description="Metadata about the extraction call"
    )
    extraction_error: dict[str, str] | None = Field(
        default=None, description="Error details if extraction failed"
    )
    flags: dict[str, Any] = Field(
        default_factory=dict, description="Validation flags on extracted data"
    )
    needs_review: bool = Field(
        default=True, description="Whether the document needs human review"
    )
    message: str = Field(..., description="Status or informational message")
