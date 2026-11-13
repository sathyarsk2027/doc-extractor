"""Tests for Phase 5 persistence and document API."""

import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.errors import AppError
from app.schemas import InvoiceData, ExtractionMeta, LineItem
from app.services.db import get_db, init_db
from app.services.documents import purge_retention, get_document_by_id
from app.services.storage import cleanup_expired, get_document_dir


def _make_pdf() -> bytes:
    """Create a minimal synthetic PDF."""
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=400)
    page.insert_text((30, 30), "Synthetic Invoice")
    data = doc.tobytes()
    doc.close()
    return data


def _synthetic_invoice(vendor="Alpha Labs", total=100.0, subtotal=90.0, tax=10.0) -> InvoiceData:
    """Return a consistent synthetic InvoiceData."""
    return InvoiceData(
        vendor=vendor,
        invoice_number="INV-2025-001",
        date="2025-06-15",
        currency="USD",
        subtotal=subtotal,
        tax=tax,
        total=total,
        line_items=[
            LineItem(description="Service Fee", quantity=1.0, unit_price=subtotal, amount=subtotal)
        ],
    )


def test_persistence_across_restart(client: TestClient):
    """Uploaded document creates rows in SQLite, which survive DB reconnect/restart."""
    inv = _synthetic_invoice()
    meta = ExtractionMeta(
        model="mock-model",
        latency_ms=120,
        input_tokens=100,
        output_tokens=50,
        pages_sent=[1],
        source="image",
    )

    with patch("app.routes.extract.extract_document", return_value=(inv, meta)):
        res = client.post(
            "/api/extract",
            files={"file": ("invoice.pdf", _make_pdf(), "application/pdf")},
        )

    assert res.status_code == 200
    data = res.json()
    doc_id = data["id"]
    assert data["status"] == "extracted"
    assert data["needs_review"] is False
    assert data["original"]["vendor"] == "Alpha Labs"
    assert len(data["pages"]) == 1

    # Simulate server restart by opening fresh connection to the DB file
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, status, filename FROM documents WHERE id = ?", (doc_id,))
        doc_row = cursor.fetchone()
        assert doc_row is not None
        assert doc_row["id"] == doc_id
        assert doc_row["status"] == "extracted"
        assert doc_row["filename"] == "invoice.pdf"

        cursor.execute("SELECT original_json, flags_json FROM extractions WHERE document_id = ?", (doc_id,))
        ext_row = cursor.fetchone()
        assert ext_row is not None
        saved_orig = json.loads(ext_row["original_json"])
        assert saved_orig["vendor"] == "Alpha Labs"

    # GET /api/documents/{id} should return full detail
    get_res = client.get(f"/api/documents/{doc_id}")
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["id"] == doc_id
    assert detail["original"]["vendor"] == "Alpha Labs"
    assert detail["original"]["total"] == 100.0


def test_cleanup_expired_keeps_saved_documents_and_removes_orphans():
    """cleanup_expired() never removes folders present in documents table, but removes orphans."""
    storage_root = settings.storage_path
    storage_root.mkdir(parents=True, exist_ok=True)

    saved_id = str(uuid.uuid4())
    orphan_id = str(uuid.uuid4())

    saved_dir = storage_root / saved_id
    saved_dir.mkdir(parents=True, exist_ok=True)
    (saved_dir / "page_1.png").write_bytes(b"dummy")

    orphan_dir = storage_root / orphan_id
    orphan_dir.mkdir(parents=True, exist_ok=True)
    (orphan_dir / "page_1.png").write_bytes(b"dummy")

    # Insert saved_id into documents table
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO documents (
                id, filename, mime_type, page_count, pages_json, status, source,
                created_at, updated_at
            ) VALUES (?, 'doc.pdf', 'application/pdf', 1, '[]', 'extracted', 'image', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')
            """,
            (saved_id,),
        )
        cursor.execute(
            """
            INSERT INTO extractions (document_id, flags_json) VALUES (?, '{}')
            """,
            (saved_id,),
        )

    # Set mtimes to 2 hours ago
    past_time = time.time() - 7200
    os.utime(saved_dir, (past_time, past_time))
    os.utime(orphan_dir, (past_time, past_time))

    # Run cleanup with 60 min TTL
    deleted = cleanup_expired(ttl_minutes=60)
    assert deleted >= 1
    assert not orphan_dir.exists()
    assert saved_dir.exists()


def test_list_documents_filtering_pagination_ordering(client: TestClient):
    """List endpoint supports status filtering, pagination, and newest-first ordering."""
    inv = _synthetic_invoice()
    meta = ExtractionMeta(
        model="mock", latency_ms=10, input_tokens=10, output_tokens=10, pages_sent=[1], source="image"
    )

    ids = []
    # Create 3 documents
    for i in range(3):
        with patch("app.routes.extract.extract_document", return_value=(inv, meta)):
            res = client.post(
                "/api/extract",
                files={"file": (f"invoice_{i}.pdf", _make_pdf(), "application/pdf")},
            )
            assert res.status_code == 200
            ids.append(res.json()["id"])
            time.sleep(0.01)

    # Mark the second document as reviewed
    client.put(
        f"/api/documents/{ids[1]}",
        json={"data": inv.model_dump(), "mark_reviewed": True},
    )

    # List all
    all_res = client.get("/api/documents")
    assert all_res.status_code == 200
    summaries = all_res.json()
    assert len(summaries) >= 3
    # Check newest first
    returned_ids = [s["id"] for s in summaries[:3]]
    assert returned_ids == list(reversed(ids))

    # Filter by status=reviewed
    reviewed_res = client.get("/api/documents?status=reviewed")
    assert reviewed_res.status_code == 200
    reviewed_list = reviewed_res.json()
    assert any(s["id"] == ids[1] for s in reviewed_list)
    for s in reviewed_list:
        assert s["status"] == "reviewed"

    # Filter by status=extracted
    extracted_res = client.get("/api/documents?status=extracted")
    assert extracted_res.status_code == 200
    extracted_list = extracted_res.json()
    for s in extracted_list:
        assert s["status"] == "extracted"

    # Pagination: limit=2
    p1 = client.get("/api/documents?limit=2&offset=0").json()
    assert len(p1) == 2
    p2 = client.get("/api/documents?limit=2&offset=2").json()
    assert len(p2) >= 1
    assert p1[0]["id"] != p2[0]["id"]


def test_put_recomputes_flags_and_mark_reviewed(client: TestClient):
    """PUT updates reviewed_json, re-runs checks, updates flags, and sets reviewed_at when requested."""
    # Invoice with broken total: subtotal 90 + tax 10 != total 200 -> TOTAL_MISMATCH flag
    broken_inv = _synthetic_invoice(total=200.0, subtotal=90.0, tax=10.0)
    meta = ExtractionMeta(
        model="mock", latency_ms=10, input_tokens=10, output_tokens=10, pages_sent=[1], source="image"
    )

    with patch("app.routes.extract.extract_document", return_value=(broken_inv, meta)):
        res = client.post(
            "/api/extract",
            files={"file": ("invoice.pdf", _make_pdf(), "application/pdf")},
        )
    assert res.status_code == 200
    doc_id = res.json()["id"]
    assert res.json()["status"] == "needs_review"
    assert "total" in res.json()["flags"]

    # 1. PUT corrected data without mark_reviewed: flags disappear, status remains
    corrected_inv = _synthetic_invoice(total=100.0, subtotal=90.0, tax=10.0)
    put_res = client.put(
        f"/api/documents/{doc_id}",
        json={"data": corrected_inv.model_dump(), "mark_reviewed": False},
    )
    assert put_res.status_code == 200
    put_data = put_res.json()
    assert put_data["flags"] == {}
    assert put_data["status"] == "needs_review"  # kept current status
    assert put_data["reviewed"]["total"] == 100.0
    assert put_data["reviewed_at"] is None

    # 2. PUT with mark_reviewed=True
    mark_res = client.put(
        f"/api/documents/{doc_id}",
        json={"data": corrected_inv.model_dump(), "mark_reviewed": True},
    )
    assert mark_res.status_code == 200
    mark_data = mark_res.json()
    assert mark_data["status"] == "reviewed"
    assert mark_data["needs_review"] is False
    assert mark_data["reviewed_at"] is not None


def test_failed_extraction_saved_with_error_and_can_be_retried(client: TestClient):
    """Failed extraction saves record with error and previews; reextract retries and updates."""
    # Upload fails due to rate limit
    with patch("app.routes.extract.extract_document") as mock_extract:
        mock_extract.side_effect = AppError(
            code="RATE_LIMITED",
            message="The free AI quota is temporarily used up.",
            status_code=429,
        )
        res = client.post(
            "/api/extract",
            files={"file": ("failed.pdf", _make_pdf(), "application/pdf")},
        )

    assert res.status_code == 200
    data = res.json()
    doc_id = data["id"]
    assert data["status"] == "needs_review"
    assert data["error"]["code"] == "RATE_LIMITED"
    assert data["original"] is None
    assert len(data["pages"]) == 1

    # Re-extract with successful extraction
    successful_inv = _synthetic_invoice()
    meta = ExtractionMeta(
        model="mock", latency_ms=10, input_tokens=10, output_tokens=10, pages_sent=[1], source="image"
    )

    with patch("app.routes.documents.extract_document", return_value=(successful_inv, meta)):
        re_res = client.post(f"/api/documents/{doc_id}/reextract")

    assert re_res.status_code == 200
    re_data = re_res.json()
    assert re_data["id"] == doc_id
    assert re_data["error"] is None
    assert re_data["status"] == "extracted"
    assert re_data["original"]["vendor"] == "Alpha Labs"


def test_delete_removes_rows_and_files_cascade(client: TestClient):
    """Single delete removes documents row, extractions row via ON DELETE CASCADE, and storage folder."""
    inv = _synthetic_invoice()
    meta = ExtractionMeta(
        model="mock", latency_ms=10, input_tokens=10, output_tokens=10, pages_sent=[1], source="image"
    )

    with patch("app.routes.extract.extract_document", return_value=(inv, meta)):
        res = client.post("/api/extract", files={"file": ("doc_cascade.pdf", _make_pdf(), "application/pdf")})

    doc_id = res.json()["id"]
    doc_dir = get_document_dir(doc_id)
    assert doc_dir.exists()

    # Verify rows exist in both documents and extractions before deletion
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents WHERE id = ?", (doc_id,))
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM extractions WHERE document_id = ?", (doc_id,))
        assert cursor.fetchone()[0] == 1

    # Delete via endpoint
    del_res = client.delete(f"/api/documents/{doc_id}")
    assert del_res.status_code == 200

    # Verify disk folder is removed
    assert not doc_dir.exists()

    # Verify both documents row and extractions row (CASCADE) are gone from DB
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents WHERE id = ?", (doc_id,))
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT COUNT(*) FROM extractions WHERE document_id = ?", (doc_id,))
        assert cursor.fetchone()[0] == 0

    # Verify 404 on subsequent GET
    assert client.get(f"/api/documents/{doc_id}").status_code == 404


def test_delete_all_requires_confirm(client: TestClient):
    """DELETE /api/documents requires confirm=true; purges all documents and files when confirmed."""
    inv = _synthetic_invoice()
    meta = ExtractionMeta(
        model="mock", latency_ms=10, input_tokens=10, output_tokens=10, pages_sent=[1], source="image"
    )

    with patch("app.routes.extract.extract_document", return_value=(inv, meta)):
        res1 = client.post("/api/extract", files={"file": ("doc1.pdf", _make_pdf(), "application/pdf")})
        res2 = client.post("/api/extract", files={"file": ("doc2.pdf", _make_pdf(), "application/pdf")})

    id1 = res1.json()["id"]
    id2 = res2.json()["id"]
    dir1 = get_document_dir(id1)
    dir2 = get_document_dir(id2)
    assert dir1.exists()
    assert dir2.exists()

    # Delete all without confirm -> 400 CONFIRM_REQUIRED
    bad_res = client.delete("/api/documents")
    assert bad_res.status_code == 400
    assert bad_res.json()["error"]["code"] == "CONFIRM_REQUIRED"
    assert dir1.exists()

    # Delete all with confirm=false -> 400
    bad_res2 = client.delete("/api/documents?confirm=false")
    assert bad_res2.status_code == 400
    assert bad_res2.json()["error"]["code"] == "CONFIRM_REQUIRED"

    # Delete all with confirm=true -> 200
    good_res = client.delete("/api/documents?confirm=true")
    assert good_res.status_code == 200
    assert good_res.json()["deleted"] >= 2

    # Verify directories and database records are completely wiped
    assert not dir1.exists()
    assert not dir2.exists()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents")
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT COUNT(*) FROM extractions")
        assert cursor.fetchone()[0] == 0


def test_invalid_uuid_and_path_traversal_returns_404(client: TestClient):
    """Invalid UUIDs and traversal attempts return 404 error without server errors."""
    assert client.get("/api/documents/invalid-uuid-123").status_code == 404
    assert client.get("/api/documents/../../etc/passwd").status_code == 404
    assert client.put("/api/documents/invalid-uuid", json={"data": _synthetic_invoice().model_dump()}).status_code == 404
    assert client.delete("/api/documents/invalid-uuid").status_code == 404
    assert client.post("/api/documents/invalid-uuid/reextract").status_code == 404


def test_sql_injection_in_status_is_harmless(client: TestClient):
    """SQL injection patterns in the status parameter are parameterized and harmless."""
    inj_res = client.get("/api/documents?status=' OR '1'='1")
    assert inj_res.status_code == 200
    assert inj_res.json() == []


def test_retention_purge_removes_old_keeps_new_and_zero_disables():
    """Documents older than RETENTION_DAYS are purged (rows and files), newer kept, and 0 disables."""
    storage_root = settings.storage_path
    storage_root.mkdir(parents=True, exist_ok=True)

    old_id = str(uuid.uuid4())
    new_id = str(uuid.uuid4())

    old_dir = storage_root / old_id
    old_dir.mkdir(parents=True, exist_ok=True)
    (old_dir / "page_1.png").write_bytes(b"old")

    new_dir = storage_root / new_id
    new_dir.mkdir(parents=True, exist_ok=True)
    (new_dir / "page_1.png").write_bytes(b"new")

    # Timestamps
    old_date = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    new_date = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO documents (
                id, filename, mime_type, page_count, pages_json, status, source,
                created_at, updated_at
            ) VALUES
            (?, 'old.pdf', 'application/pdf', 1, '[]', 'extracted', 'image', ?, ?),
            (?, 'new.pdf', 'application/pdf', 1, '[]', 'extracted', 'image', ?, ?)
            """,
            (old_id, old_date, old_date, new_id, new_date, new_date),
        )
        cursor.execute(
            """
            INSERT INTO extractions (document_id, flags_json) VALUES (?, '{}'), (?, '{}')
            """,
            (old_id, new_id),
        )

    # 1. RETENTION_DAYS=0 disables purge
    purged_zero = purge_retention(retention_days=0)
    assert purged_zero == 0
    assert old_dir.exists()
    assert new_dir.exists()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents WHERE id = ?", (old_id,))
        assert cursor.fetchone()[0] == 1

    # 2. RETENTION_DAYS=30 purges 45-day-old document, keeps 2-day-old document
    purged = purge_retention(retention_days=30)
    assert purged == 1

    # Old document rows and folder removed
    assert not old_dir.exists()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents WHERE id = ?", (old_id,))
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT COUNT(*) FROM extractions WHERE document_id = ?", (old_id,))
        assert cursor.fetchone()[0] == 0

        # New document rows and folder intact
        cursor.execute("SELECT COUNT(*) FROM documents WHERE id = ?", (new_id,))
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM extractions WHERE document_id = ?", (new_id,))
        assert cursor.fetchone()[0] == 1
    assert new_dir.exists()
