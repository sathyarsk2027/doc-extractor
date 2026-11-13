"""Document extraction service interface and orchestration."""

import base64
import logging
from abc import ABC, abstractmethod
from pathlib import Path

import pymupdf

from app.config import settings
from app.errors import AppError
from app.schemas import InvoiceData, ExtractionMeta
from app.services.storage import get_document_dir

logger = logging.getLogger("doc_extractor")


class Extractor(ABC):
    """Abstract base class for LLM-based document extraction."""

    @abstractmethod
    def extract(
        self,
        page_images: list[bytes],
        text_content: str | None = None,
        source: str = "image",
    ) -> tuple[InvoiceData, ExtractionMeta]:
        """Extract structured invoice data from page images or extracted text.

        Args:
            page_images: List of PNG image bytes for selected pages.
            text_content: Optional extracted text layer from digital PDF.
            source: Source modality ("text" or "image").

        Returns:
            Tuple of (extracted data, extraction metadata).
        """
        ...


def get_extractor() -> Extractor:
    """Return the configured extractor implementation.

    Raises:
        AppError: LLM_AUTH_ERROR if the API key is missing or placeholder.
    """
    if not settings.groq_api_key_valid:
        raise AppError(
            code="LLM_AUTH_ERROR",
            message="AI service credentials are not configured. Set GROQ_API_KEY in the .env file.",
            status_code=500,
        )

    from app.services.groq_extractor import GroqExtractor

    return GroqExtractor()


def select_pages(doc_dir: Path, page_count: int) -> tuple[list[bytes], list[int]]:
    """Select and load page images for extraction.

    Rules:
    - If page_count <= EXTRACTION_MAX_PAGES: send all pages.
    - If more: send the FIRST page and the LAST page only.
    - Never send more than 3 images.

    Returns:
        Tuple of (list of PNG bytes, list of 1-indexed page numbers sent).
    """
    max_pages = min(settings.extraction_max_pages, 3)

    if page_count <= max_pages:
        page_numbers = list(range(1, page_count + 1))
    else:
        # First and last page
        page_numbers = [1, page_count]

    images: list[bytes] = []
    for pn in page_numbers:
        page_path = doc_dir / f"page_{pn}.png"
        if not page_path.is_file():
            logger.warning("Page file not found: %s", page_path)
            continue
        images.append(page_path.read_bytes())

    return images, page_numbers


def extract_pdf_text_for_pages(doc_dir: Path, page_numbers: list[int]) -> str | None:
    """Extract embedded digital text from original.pdf for selected pages."""
    pdf_path = doc_dir / "original.pdf"
    if not pdf_path.is_file():
        return None

    try:
        doc = pymupdf.open(str(pdf_path))
        text_parts = []
        for pn in page_numbers:
            if pn <= len(doc):
                page_text = doc[pn - 1].get_text("text").strip()
                if page_text:
                    text_parts.append(f"--- PAGE {pn} ---\n{page_text}")
        doc.close()
        return "\n\n".join(text_parts).strip() if text_parts else None
    except Exception as exc:
        logger.warning("Failed to extract digital text from PDF: %s", exc)
        return None


def images_to_base64_urls(images: list[bytes]) -> list[str]:
    """Convert PNG image bytes to base64 data URLs."""
    urls = []
    for img_bytes in images:
        b64 = base64.b64encode(img_bytes).decode("ascii")
        urls.append(f"data:image/png;base64,{b64}")
    return urls


def extract_document(document_id: str) -> tuple[InvoiceData, ExtractionMeta]:
    """Run the full extraction pipeline for a preprocessed document.

    Orchestrates page selection, text-first mode determination, LLM extraction,
    and metadata recording.

    Args:
        document_id: UUID of the already-preprocessed document.

    Returns:
        Tuple of (extracted invoice data, extraction metadata).

    Raises:
        AppError: Various codes depending on the failure mode.
    """
    extractor = get_extractor()

    doc_dir = get_document_dir(document_id)
    if not doc_dir.exists():
        raise AppError(
            code="NOT_FOUND",
            message="Document not found.",
            status_code=404,
        )

    # Count available page PNGs
    page_files = sorted(doc_dir.glob("page_*.png"))
    page_count = len(page_files)

    if page_count == 0:
        raise AppError(
            code="INTERNAL_ERROR",
            message="No preprocessed page images found for this document.",
            status_code=500,
        )

    images, page_numbers = select_pages(doc_dir, page_count)

    if not images:
        raise AppError(
            code="INTERNAL_ERROR",
            message="Failed to load page images for extraction.",
            status_code=500,
        )

    # Determine extraction mode: text-first vs image
    pdf_text = extract_pdf_text_for_pages(doc_dir, page_numbers)
    text_char_count = len(pdf_text) if pdf_text else 0

    mode = settings.extraction_mode.lower()
    if mode == "text" and text_char_count > 0:
        source = "text"
    elif mode == "image":
        source = "image"
    else:  # "auto"
        # If PDF has significant text layer (>= 50 chars), prefer text mode
        source = "text" if text_char_count >= 50 else "image"

    logger.info(
        "Extracting document %s: %d of %d pages selected (pages %s, source=%s, text_chars=%d)",
        document_id,
        len(images),
        page_count,
        page_numbers,
        source,
        text_char_count,
    )

    invoice_data, meta = extractor.extract(
        page_images=images,
        text_content=pdf_text if source == "text" else None,
        source=source,
    )
    meta.pages_sent = page_numbers
    meta.source = source

    return invoice_data, meta
