"""Pytest fixtures generated entirely in code without committed binaries."""

import io
import pymupdf
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings


@pytest.fixture(scope="session")
def client() -> TestClient:
    """FastAPI TestClient fixture."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="session")
def valid_pdf_bytes() -> bytes:
    """Create a minimal valid 1-page PDF using PyMuPDF."""
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=400)
    page.insert_text((50, 50), "Test Invoice")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture(scope="session")
def valid_png_bytes() -> bytes:
    """Create a minimal valid PNG image using Pillow."""
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="session")
def valid_jpeg_bytes() -> bytes:
    """Create a minimal valid JPEG image using Pillow."""
    img = Image.new("RGB", (100, 100), color=(0, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture(scope="session")
def empty_file_bytes() -> bytes:
    """An empty file buffer."""
    return b""


@pytest.fixture(scope="session")
def fake_pdf_bytes() -> bytes:
    """Plain text masquerading as a PDF."""
    return b"Not a real PDF header at all, just plain text."


@pytest.fixture(scope="session")
def oversized_bytes() -> bytes:
    """Payload exceeding MAX_FILE_MB."""
    # 10 MB + 64 KB of valid PDF prefix followed by padding
    size = (settings.max_file_mb * 1024 * 1024) + (64 * 1024)
    return b"%PDF-1.4 " + (b"0" * (size - 9))
