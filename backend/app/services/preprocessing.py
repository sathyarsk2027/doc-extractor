"""Document preprocessing service for PDFs and images."""

import io
from pathlib import Path
from PIL import Image, ImageOps
import pymupdf

from app.config import settings
from app.errors import AppError


def preprocess_pdf(doc_dir: Path, content: bytes) -> list[dict]:
    """Process PDF bytes: validate encryption/corruption/page limit and render pages to PNG.

    Raises:
        AppError: PDF_ENCRYPTED (422) if document is password-protected.
        AppError: CORRUPT_FILE (422) if document cannot be opened or contains 0 pages.
        AppError: PDF_TOO_MANY_PAGES (422) if page count exceeds MAX_PDF_PAGES.
    """
    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise AppError(
            code="CORRUPT_FILE",
            message="The PDF file is corrupt or cannot be read.",
            status_code=422,
        ) from exc

    try:
        if doc.needs_pass or doc.is_encrypted:
            raise AppError(
                code="PDF_ENCRYPTED",
                message="Password-protected PDFs are not supported.",
                status_code=422,
            )

        page_count = len(doc)
        if page_count == 0:
            raise AppError(
                code="CORRUPT_FILE",
                message="The PDF document contains 0 pages.",
                status_code=422,
            )

        if page_count > settings.max_pdf_pages:
            raise AppError(
                code="PDF_TOO_MANY_PAGES",
                message=f"PDF page count ({page_count}) exceeds maximum allowed limit of {settings.max_pdf_pages} pages.",
                status_code=422,
            )

        zoom = settings.pdf_render_dpi / 72.0
        matrix = pymupdf.Matrix(zoom, zoom)
        pages_meta = []

        for idx, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            page_png_path = doc_dir / f"page_{idx}.png"
            pix.save(str(page_png_path))
            pages_meta.append({
                "page": idx,
                "width": pix.width,
                "height": pix.height,
            })

        return pages_meta
    finally:
        doc.close()


def preprocess_image(doc_dir: Path, content: bytes) -> list[dict]:
    """Process image bytes: validate corruption, apply EXIF rotation, downscale, strip metadata, and save page_1.png.

    Raises:
        AppError: CORRUPT_FILE (422) if image cannot be parsed or loaded.
    """
    try:
        img = Image.open(io.BytesIO(content))
        img.load()
    except Exception as exc:
        raise AppError(
            code="CORRUPT_FILE",
            message="The image file is corrupt or cannot be decoded.",
            status_code=422,
        ) from exc

    try:
        # Apply EXIF orientation transposition if present
        img = ImageOps.exif_transpose(img)

        # Convert palette/alpha/greyscale modes to RGB
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Downscale proportionally if width exceeds MAX_IMAGE_WIDTH (never upscale)
        if img.width > settings.max_image_width:
            ratio = settings.max_image_width / float(img.width)
            new_height = max(1, int(float(img.height) * ratio))
            img = img.resize((settings.max_image_width, new_height), Image.Resampling.LANCZOS)

        # Save preview as page_1.png without EXIF metadata (privacy protection)
        page_png_path = doc_dir / "page_1.png"
        img.save(page_png_path, format="PNG")

        return [{
            "page": 1,
            "width": img.width,
            "height": img.height,
        }]
    finally:
        img.close()


def preprocess_document(doc_dir: Path, content: bytes, mime_type: str) -> list[dict]:
    """Dispatch preprocessing according to validated MIME type."""
    if mime_type == "application/pdf":
        return preprocess_pdf(doc_dir, content)
    if mime_type in ("image/png", "image/jpeg"):
        return preprocess_image(doc_dir, content)

    raise AppError(
        code="UNSUPPORTED_TYPE",
        message=f"Unsupported file MIME type: {mime_type}",
        status_code=415,
    )
