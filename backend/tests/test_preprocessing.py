"""Tests for Phase 2 document preprocessing and preview storage."""

import io
import os
import time
import uuid
from pathlib import Path
from PIL import Image
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.services.storage import cleanup_expired, get_document_dir


def assert_standard_error(data: dict, expected_code: str):
    """Verify that response matches {"error": {"code", "message"}} envelope."""
    assert "error" in data, f"Missing 'error' key: {data}"
    assert data["error"]["code"] == expected_code
    assert "message" in data["error"]


def test_multipage_pdf_preprocessing(client: TestClient):
    """Multi-page PDF produces the right number of PNG previews accessible via GET."""
    doc = pymupdf.open()
    for i in range(3):
        p = doc.new_page(width=200, height=300)
        p.insert_text((20, 20), f"Page {i + 1}")
    pdf_bytes = doc.tobytes()
    doc.close()

    res = client.post("/api/extract", files={"file": ("multipage.pdf", pdf_bytes, "application/pdf")})
    assert res.status_code == 200
    data = res.json()
    assert data["document_id"] is not None
    assert data["page_count"] == 3
    assert len(data["pages"]) == 3

    for p in data["pages"]:
        assert p["preview_url"].startswith(f"/api/files/{data['document_id']}/pages/")
        assert p["width"] > 0
        assert p["height"] > 0

        # Fetch preview image
        img_res = client.get(p["preview_url"])
        assert img_res.status_code == 200
        assert img_res.headers["content-type"] == "image/png"
        assert "private, max-age=300" in img_res.headers.get("cache-control", "")
        assert img_res.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_pdf_too_many_pages(client: TestClient):
    """PDF exceeding MAX_PDF_PAGES returns PDF_TOO_MANY_PAGES (422) and cleans up folder."""
    doc = pymupdf.open()
    for _ in range(settings.max_pdf_pages + 1):
        doc.new_page(width=200, height=200)
    pdf_bytes = doc.tobytes()
    doc.close()

    res = client.post("/api/extract", files={"file": ("toomany.pdf", pdf_bytes, "application/pdf")})
    assert res.status_code == 422
    assert_standard_error(res.json(), "PDF_TOO_MANY_PAGES")


def test_pdf_encrypted(client: TestClient):
    """Encrypted/password-protected PDF returns PDF_ENCRYPTED (422)."""
    doc = pymupdf.open()
    p = doc.new_page(width=200, height=200)
    p.insert_text((20, 20), "Protected content")
    pdf_bytes = doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="password123",
        owner_pw="owner123",
    )
    doc.close()

    res = client.post("/api/extract", files={"file": ("locked.pdf", pdf_bytes, "application/pdf")})
    assert res.status_code == 422
    assert_standard_error(res.json(), "PDF_ENCRYPTED")


def test_pdf_corrupt(client: TestClient):
    """Corrupt PDF with valid magic header but corrupted body returns CORRUPT_FILE (422)."""
    corrupt_bytes = b"%PDF-1.4\n" + b"CorruptGarbageBodyNotAPdf" * 10
    res = client.post("/api/extract", files={"file": ("corrupt.pdf", corrupt_bytes, "application/pdf")})
    assert res.status_code == 422
    assert_standard_error(res.json(), "CORRUPT_FILE")


def test_jpeg_exif_rotation(client: TestClient):
    """A JPEG with EXIF orientation metadata is transposed correctly."""
    # Create image 100 wide x 200 high
    img = Image.new("RGB", (100, 200), color=(10, 20, 30))
    exif = img.getexif()
    # Orientation 6 = Rotate 90 CW (transposes dimensions to 200 x 100)
    exif[274] = 6
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    jpeg_bytes = buf.getvalue()

    res = client.post("/api/extract", files={"file": ("oriented.jpg", jpeg_bytes, "image/jpeg")})
    assert res.status_code == 200
    data = res.json()
    assert data["page_count"] == 1
    page = data["pages"][0]
    # Width and height should be transposed to 200 and 100
    assert page["width"] == 200
    assert page["height"] == 100


def test_image_downscaling(client: TestClient):
    """An image wider than MAX_IMAGE_WIDTH is downscaled, and smaller image is not upscaled."""
    # Oversized image: 3000 x 1500 (MAX_IMAGE_WIDTH is 2000)
    huge_img = Image.new("RGB", (3000, 1500), color=(50, 50, 50))
    buf = io.BytesIO()
    huge_img.save(buf, format="PNG")
    res_huge = client.post("/api/extract", files={"file": ("huge.png", buf.getvalue(), "image/png")})
    assert res_huge.status_code == 200
    data_huge = res_huge.json()
    assert data_huge["pages"][0]["width"] == settings.max_image_width
    assert data_huge["pages"][0]["height"] == 1000

    # Small image: 500 x 400 (should not be upscaled)
    small_img = Image.new("RGB", (500, 400), color=(100, 100, 100))
    buf2 = io.BytesIO()
    small_img.save(buf2, format="PNG")
    res_small = client.post("/api/extract", files={"file": ("small.png", buf2.getvalue(), "image/png")})
    assert res_small.status_code == 200
    data_small = res_small.json()
    assert data_small["pages"][0]["width"] == 500
    assert data_small["pages"][0]["height"] == 400


def test_preview_endpoint_security_and_404(client: TestClient, valid_png_bytes: bytes):
    """Preview endpoint serves valid IDs, and returns 404 for unknown IDs and path traversal attempts."""
    # Upload valid file to get real ID
    res = client.post("/api/extract", files={"file": ("doc.png", valid_png_bytes, "image/png")})
    assert res.status_code == 200
    doc_id = res.json()["document_id"]

    # 1. Valid preview
    valid_res = client.get(f"/api/files/{doc_id}/pages/1.png")
    assert valid_res.status_code == 200

    # 2. Unknown page number
    p404_res = client.get(f"/api/files/{doc_id}/pages/999.png")
    assert p404_res.status_code == 404
    assert_standard_error(p404_res.json(), "NOT_FOUND")

    # 3. Unknown UUID
    random_uuid = str(uuid.uuid4())
    unknown_res = client.get(f"/api/files/{random_uuid}/pages/1.png")
    assert unknown_res.status_code == 404
    assert_standard_error(unknown_res.json(), "NOT_FOUND")

    # 4. Path traversal attempt (non-UUID)
    traversal_res = client.get("/api/files/../../etc/passwd/pages/1.png")
    assert traversal_res.status_code == 404
    assert_standard_error(traversal_res.json(), "NOT_FOUND")


def test_cleanup_expired_ttl():
    """cleanup_expired() removes folders older than FILE_TTL_MINUTES and keeps fresh ones."""
    storage_root = settings.storage_path
    storage_root.mkdir(parents=True, exist_ok=True)

    old_id = str(uuid.uuid4())
    fresh_id = str(uuid.uuid4())

    old_dir = storage_root / old_id
    fresh_dir = storage_root / fresh_id

    old_dir.mkdir(parents=True, exist_ok=True)
    fresh_dir.mkdir(parents=True, exist_ok=True)

    (old_dir / "test.txt").write_text("old")
    (fresh_dir / "test.txt").write_text("fresh")

    # Set old_dir mtime to 2 hours ago
    two_hours_ago = time.time() - (120 * 60)
    os.utime(old_dir, (two_hours_ago, two_hours_ago))

    # Set fresh_dir mtime to now
    now = time.time()
    os.utime(fresh_dir, (now, now))

    # Run cleanup with 60 minute TTL
    cleaned = cleanup_expired(ttl_minutes=60)
    assert cleaned >= 1
    assert not old_dir.exists(), "Old expired directory was not removed"
    assert fresh_dir.exists(), "Fresh directory was incorrectly removed"

    # Clean up fresh_dir
    cleanup_expired(ttl_minutes=0)

