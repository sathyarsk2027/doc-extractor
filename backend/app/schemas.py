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

    # GST & Tax Breakdown Additions
    taxable_amount: float | None = None
    cgst: float | None = None
    sgst: float | None = None
    igst: float | None = None
    cess: float | None = None
    prices_include_tax: bool | None = None


def derive_invoice_fields(invoice: InvoiceData) -> InvoiceData:
    """Derive tax and subtotal in code when explicit breakdown is available."""
    # 1. Derive total tax from component breakdown if tax is missing
    gst_parts = [invoice.cgst, invoice.sgst, invoice.igst, invoice.cess]
    if any(p is not None for p in gst_parts):
        total_gst = round(sum(p for p in gst_parts if p is not None), 2)
        if invoice.tax is None or invoice.tax == 0:
            invoice.tax = total_gst

    # 2. Derive subtotal from taxable_amount
    if invoice.taxable_amount is not None:
        if invoice.subtotal is None or (invoice.prices_include_tax and invoice.subtotal == invoice.total):
            invoice.subtotal = invoice.taxable_amount

    return invoice


class ExtractionMeta(BaseModel):
    """Metadata about the LLM extraction call."""

    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    pages_sent: list[int]
    repaired: bool = False
    source: str = "image"  # "text" or "image"


class PagePreview(BaseModel):
    """Metadata and URL for a rendered document page preview."""

    page: int = Field(..., description="1-indexed page number")
    preview_url: str = Field(..., description="URL to retrieve the page preview PNG")
    width: int = Field(..., description="Preview image width in pixels")
    height: int = Field(..., description="Preview image height in pixels")


class ErrorPayload(BaseModel):
    """Error code and message payload."""

    code: str
    message: str


class DocumentSummary(BaseModel):
    """Summary of a document for history list display."""

    id: str
    filename: str
    created_at: str
    status: str
    page_count: int
    vendor: str | None = None
    total: float | None = None
    currency: str | None = None
    needs_review: bool


class DocumentDetail(BaseModel):
    """Full detail of a document, its pages, extractions, and flags."""

    id: str
    filename: str
    mime_type: str
    page_count: int
    status: str
    created_at: str
    updated_at: str
    reviewed_at: str | None = None
    pages: list[PagePreview] = Field(default_factory=list)
    original: InvoiceData | None = None
    reviewed: InvoiceData | None = None
    flags: dict[str, Any] = Field(default_factory=dict)
    needs_review: bool
    meta: ExtractionMeta | None = None
    error: ErrorPayload | None = None


class DocumentUpdateRequest(BaseModel):
    """Payload for updating document extracted data and review status."""

    data: InvoiceData
    mark_reviewed: bool = False


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
