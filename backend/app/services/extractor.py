"""Document extraction service interface and orchestration."""

import base64
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pymupdf

from app.config import settings, features_for
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
        version: str | None = None,
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


INVOICE_LABEL_PATTERNS = [
    re.compile(
        r"(?i)(?:tax\s+invoice\s*#?|invoice\s*(?:no\.?|number|#)|bill\s*(?:no\.?|number|#))\s*[:\-#]?\s*([A-Za-z0-9\/\-_]+)"
    ),
]


def find_invoice_candidate_on_page(page_text: str) -> str | None:
    """Find invoice number candidate on a single page near typical labels."""
    for pat in INVOICE_LABEL_PATTERNS:
        match = pat.search(page_text)
        if match:
            cand = match.group(1).strip()
            if len(cand) >= 2:
                return cand.upper()
    return None


def detect_multi_invoices(
    pages_text: list[str],
) -> tuple[list[int] | None, dict[str, Any] | None]:
    """Detect if distinct invoice numbers appear on different pages of a text-layer PDF.

    If 2 or more distinct normalized values occur on different pages:
    - Group consecutive pages by invoice number.
    - Select the group with the most pages (ties broken by choosing the first group).
    - Return (selected_pages_1_indexed, warning_flag_dict).

    Otherwise returns (None, None).
    """
    if len(pages_text) < 2:
        return None, None

    page_candidates = [
        (idx + 1, find_invoice_candidate_on_page(txt))
        for idx, txt in enumerate(pages_text)
    ]

    distinct_invoices = set(cand for _, cand in page_candidates if cand is not None)
    if len(distinct_invoices) < 2:
        return None, None

    # Group consecutive pages by invoice number
    groups: list[dict[str, Any]] = []
    current_group: dict[str, Any] | None = None

    for page_num, cand in page_candidates:
        if current_group is None:
            current_group = {"invoice": cand, "pages": [page_num]}
        else:
            if cand is not None and current_group["invoice"] is not None and cand != current_group["invoice"]:
                groups.append(current_group)
                current_group = {"invoice": cand, "pages": [page_num]}
            else:
                if current_group["invoice"] is None and cand is not None:
                    current_group["invoice"] = cand
                current_group["pages"].append(page_num)

    if current_group:
        groups.append(current_group)

    # Pick group with most pages; ties break to first group
    best_group = max(groups, key=lambda g: len(g["pages"]))
    selected_pages: list[int] = best_group["pages"]

    ranges_desc_list = []
    for g in groups:
        p_list = g["pages"]
        r_str = f"pages {p_list[0]}-{p_list[-1]}" if len(p_list) > 1 else f"page {p_list[0]}"
        inv_str = f" ({g['invoice']})" if g["invoice"] else ""
        ranges_desc_list.append(f"{r_str}{inv_str}")
    ranges_desc = ", ".join(ranges_desc_list)

    flag = {
        "code": "MULTIPLE_INVOICES_SUSPECTED",
        "message": f"Multiple invoices suspected across pages: {ranges_desc}. Extracted pages: {selected_pages}.",
        "severity": "warning",
    }
    return selected_pages, flag


def extract_page_text_with_tables(page: pymupdf.Page) -> str:
    """Extract page text using sort=True, rendering detected tables as pipe-separated rows in reading order."""
    if not hasattr(page, "find_tables"):
        return page.get_text("text", sort=True).strip()

    try:
        tabs = page.find_tables()
        if not tabs or not tabs.tables:
            return page.get_text("text", sort=True).strip()
    except Exception as exc:
        logger.debug("find_tables failed on page: %s", exc)
        return page.get_text("text", sort=True).strip()

    items: list[tuple[float, float, str]] = []
    tab_rects: list[pymupdf.Rect] = []

    for t in tabs.tables:
        t_rect = pymupdf.Rect(t.bbox)
        tab_rects.append(t_rect)
        try:
            rows = t.extract()
            lines = []
            for r in rows:
                cells = [(c or "").strip() for c in r]
                if any(cells):
                    lines.append(" | ".join(cells))
            if lines:
                items.append((t_rect.y0, t_rect.x0, "\n".join(lines)))
        except Exception as exc:
            logger.debug("Failed to extract table: %s", exc)

    # Extract non-table text blocks in reading order
    try:
        blocks = page.get_text("blocks", sort=True)
        for b in blocks:
            b_rect = pymupdf.Rect(b[:4])
            b_text = b[4].strip()
            if not b_text:
                continue
            inside = False
            b_area = b_rect.get_area()
            for tr in tab_rects:
                if b_rect.intersects(tr):
                    inter_area = (b_rect & tr).get_area()
                    if b_area > 0 and (inter_area / b_area) > 0.3:
                        inside = True
                        break
            if not inside:
                items.append((b_rect.y0, b_rect.x0, b_text))
    except Exception as exc:
        logger.debug("Failed to get blocks with sort=True: %s", exc)
        return page.get_text("text", sort=True).strip()

    items.sort(key=lambda x: (x[0], x[1]))
    return "\n\n".join(it[2] for it in items).strip()


def select_pages(
    doc_dir: Path,
    page_count: int,
    allowed_pages: list[int] | None = None,
) -> tuple[list[bytes], list[int]]:
    """Select and load page images for extraction.

    Rules:
    - If allowed_pages is provided, select pages from that group.
    - If total candidate pages <= EXTRACTION_MAX_PAGES (max 3): send all candidate pages.
    - If more: send the FIRST and LAST candidate page only.
    - Never send more than 3 images.

    Returns:
        Tuple of (list of PNG bytes, list of 1-indexed page numbers sent).
    """
    candidate_pages = allowed_pages if allowed_pages is not None else list(range(1, page_count + 1))
    max_pages = min(settings.extraction_max_pages, 3)

    if len(candidate_pages) <= max_pages:
        page_numbers = candidate_pages
    else:
        page_numbers = [candidate_pages[0], candidate_pages[-1]]

    images: list[bytes] = []
    for pn in page_numbers:
        page_path = doc_dir / f"page_{pn}.png"
        if not page_path.is_file():
            logger.warning("Page file not found: %s", page_path)
            continue
        images.append(page_path.read_bytes())

    return images, page_numbers


def extract_pdf_text_for_pages(
    doc_dir: Path,
    page_numbers: list[int],
    version: str | None = None,
) -> str | None:
    """Extract embedded digital text from original.pdf for selected pages."""
    pdf_path = doc_dir / "original.pdf"
    if not pdf_path.is_file():
        return None

    feat = features_for(version)
    try:
        doc = pymupdf.open(str(pdf_path))
        text_parts = []
        for pn in page_numbers:
            if pn <= len(doc):
                if feat.table_aware_text:
                    page_text = extract_page_text_with_tables(doc[pn - 1])
                else:
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


def extract_document(
    document_id: str,
    mode_override: str | None = None,
    version: str | None = None,
) -> tuple[InvoiceData, ExtractionMeta]:
    """Run the full extraction pipeline for a preprocessed document.

    Orchestrates page selection, text-first mode determination, LLM extraction,
    and metadata recording.

    Args:
        document_id: UUID of the already-preprocessed document.
        mode_override: Optional override for EXTRACTION_MODE ('auto', 'text', 'image').
        version: Optional override for PIPELINE_VERSION ('v1', 'v2').

    Returns:
        Tuple of (extracted invoice data, extraction metadata).

    Raises:
        AppError: Various codes depending on the failure mode.
    """
    extractor = get_extractor()
    feat = features_for(version)

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

    # Multi-invoice detection only if enabled in features
    pdf_path = doc_dir / "original.pdf"
    multi_flag: dict[str, Any] | None = None
    allowed_pages: list[int] | None = None

    if feat.multi_invoice_detection and pdf_path.is_file():
        try:
            doc = pymupdf.open(str(pdf_path))
            all_pages_text = [extract_page_text_with_tables(p) for p in doc]
            doc.close()
            detected_pages, flag = detect_multi_invoices(all_pages_text)
            if detected_pages:
                allowed_pages = detected_pages
                multi_flag = flag
        except Exception as exc:
            logger.debug("Failed multi-invoice check: %s", exc)

    images, page_numbers = select_pages(doc_dir, page_count, allowed_pages=allowed_pages)

    if not images:
        raise AppError(
            code="INTERNAL_ERROR",
            message="Failed to load page images for extraction.",
            status_code=500,
        )

    # Determine extraction mode: text-first vs image
    pdf_text = extract_pdf_text_for_pages(doc_dir, page_numbers, version=version)
    text_char_count = len(pdf_text) if pdf_text else 0

    mode = (mode_override or settings.extraction_mode).lower()
    if mode == "text" and text_char_count > 0:
        source = "text"
    elif mode == "image":
        source = "image"
    else:  # "auto"
        # If PDF has significant text layer (>= 50 chars), prefer text mode
        source = "text" if text_char_count >= 50 else "image"

    logger.info(
        "Extracting document %s: %d of %d pages selected (pages %s, source=%s, text_chars=%d, pipeline=%s)",
        document_id,
        len(images),
        page_count,
        page_numbers,
        source,
        text_char_count,
        feat.version,
    )

    invoice_data, meta = extractor.extract(
        page_images=images,
        text_content=pdf_text if source == "text" else None,
        source=source,
        version=version,
    )
    meta.pages_sent = page_numbers
    meta.source = source
    if multi_flag:
        meta.extra_flags["invoice_number"] = multi_flag

    return invoice_data, meta
