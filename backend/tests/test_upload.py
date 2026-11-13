"""Tests for document upload endpoint and validation rules."""

import pytest
from fastapi.testclient import TestClient


def assert_standard_error(data: dict, expected_code: str):
    """Verify that the response dictionary strictly adheres to {"error": {"code", "message"}}."""
    assert "error" in data, f"Missing 'error' key in response: {data}"
    assert set(data.keys()) == {"error"}, f"Unexpected top-level keys: {data.keys()}"
    error_obj = data["error"]
    assert "code" in error_obj, f"Missing 'code' key in error: {error_obj}"
    assert "message" in error_obj, f"Missing 'message' key in error: {error_obj}"
    assert set(error_obj.keys()) == {"code", "message"}, f"Unexpected keys in error object: {error_obj.keys()}"
    assert error_obj["code"] == expected_code
    assert isinstance(error_obj["message"], str)
    assert len(error_obj["message"]) > 0


def test_upload_valid_pdf(client: TestClient, valid_pdf_bytes: bytes):
    """A valid PDF upload returns 200 and expected schema."""
    files = {"file": ("invoice.pdf", valid_pdf_bytes, "application/pdf")}
    response = client.post("/api/extract", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["mime_type"] == "application/pdf"
    assert data["filename"] == "invoice.pdf"
    assert data["extraction"] is None


def test_upload_valid_png(client: TestClient, valid_png_bytes: bytes):
    """A valid PNG upload returns 200 and expected schema."""
    files = {"file": ("receipt.png", valid_png_bytes, "image/png")}
    response = client.post("/api/extract", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["mime_type"] == "image/png"
    assert data["filename"] == "receipt.png"


def test_upload_valid_jpeg(client: TestClient, valid_jpeg_bytes: bytes):
    """A valid JPEG upload returns 200 and expected schema."""
    files = {"file": ("receipt.jpg", valid_jpeg_bytes, "image/jpeg")}
    response = client.post("/api/extract", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["mime_type"] == "image/jpeg"
    assert data["filename"] == "receipt.jpg"


def test_upload_missing_file(client: TestClient):
    """Missing file multipart parameter returns NO_FILE with HTTP 400."""
    response = client.post("/api/extract", data={})
    assert response.status_code == 400
    assert_standard_error(response.json(), "NO_FILE")


def test_upload_empty_file(client: TestClient, empty_file_bytes: bytes):
    """An empty file returns EMPTY_FILE with HTTP 400."""
    files = {"file": ("empty.pdf", empty_file_bytes, "application/pdf")}
    response = client.post("/api/extract", files=files)
    assert response.status_code == 400
    assert_standard_error(response.json(), "EMPTY_FILE")


def test_upload_fake_pdf(client: TestClient, fake_pdf_bytes: bytes):
    """A non-PDF file renamed as .pdf returns UNSUPPORTED_TYPE with HTTP 415."""
    files = {"file": ("fake.pdf", fake_pdf_bytes, "application/pdf")}
    response = client.post("/api/extract", files=files)
    assert response.status_code == 415
    assert_standard_error(response.json(), "UNSUPPORTED_TYPE")


def test_upload_oversized_file(client: TestClient, oversized_bytes: bytes):
    """A file exceeding MAX_FILE_MB returns FILE_TOO_LARGE with HTTP 413."""
    files = {"file": ("huge.pdf", oversized_bytes, "application/pdf")}
    response = client.post("/api/extract", files=files)
    assert response.status_code == 413
    assert_standard_error(response.json(), "FILE_TOO_LARGE")


def test_error_envelope_structure(client: TestClient):
    """Every error response strictly matches {"error": {"code": str, "message": str}}."""
    for url, method, payload, expected_status, expected_code in [
        ("/api/extract", "post", {}, 400, "NO_FILE"),
        ("/api/extract", "post", {"file": ("empty.pdf", b"", "application/pdf")}, 400, "EMPTY_FILE"),
        ("/api/extract", "post", {"file": ("fake.pdf", b"text", "application/pdf")}, 415, "UNSUPPORTED_TYPE"),
        ("/api/nonexistent", "get", None, 404, "NOT_FOUND"),
    ]:
        if method == "post":
            if payload and "file" in payload:
                res = client.post(url, files={"file": payload["file"]})
            else:
                res = client.post(url, data={})
        else:
            res = client.get(url)

        assert res.status_code == expected_status
        assert_standard_error(res.json(), expected_code)
