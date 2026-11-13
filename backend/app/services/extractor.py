"""Document extraction service interface and orchestration."""

import base64
import logging
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import settings
from app.errors import AppError
from app.schemas import InvoiceData, ExtractionMeta
from app.services.storage import get_document_dir

logger = logging.getLogger("doc_extractor")


class Extractor(ABC):
    """Abstract base class for LLM-based document extraction."""

    @abstractmethod
    def extract(self, page_images: list[bytes]) -> tuple[InvoiceData, ExtractionMeta]:
        """Extract structured invoice data from page images.

        Args:
            page_images: List of PNG image bytes for selected pages.

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


def images_to_base64_urls(images: list[bytes]) -> list[str]:
    """Convert PNG image bytes to base64 data URLs."""
    urls = []
    for img_bytes in images:
        b64 = base64.b64encode(img_bytes).decode("ascii")
        urls.append(f"data:image/png;base64,{b64}")
    return urls


def extract_document(document_id: str) -> tuple[InvoiceData, ExtractionMeta]:
    """Run the full extraction pipeline for a preprocessed document.

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

    logger.info(
        "Extracting document %s: %d of %d pages selected (pages %s)",
        document_id,
        len(images),
        page_count,
        page_numbers,
    )

    invoice_data, meta = extractor.extract(images)
    meta.pages_sent = page_numbers

    return invoice_data, meta
