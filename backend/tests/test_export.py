"""Tests for Phase 7 CSV export endpoints."""

import csv
import io
from unittest.mock import patch

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.schemas import InvoiceData, ExtractionMeta, LineItem


def _make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=400)
    page.insert_text((30, 30), "Export Test Invoice")
    data = doc.tobytes()
    doc.close()
    return data


def _mock_meta():
    return ExtractionMeta(
        model="mock", latency_ms=10, input_tokens=10, output_tokens=10, pages_sent=[1], source="image"
    )


EXPECTED_COLUMNS = [
    "document_id",
    "filename",
    "vendor",
    "invoice_number",
    "date",
    "currency",
    "subtotal",
    "tax",
    "total",
    "item_description",
    "item_quantity",
    "item_unit_price",
    "item_amount",
    "status",
    "needs_review",
    "flag_codes",
]


def test_single_document_export_csv(client: TestClient):
    """Single-document export generates valid CSV with BOM, exact column order, and repeated header fields."""
    inv = InvoiceData(
        vendor="Global Supplies Ltd",
        invoice_number="INV-2026-99",
        date="2026-06-15",
        currency="USD",
        subtotal=150.0,
        tax=15.0,
        total=165.0,
        line_items=[
            LineItem(description="Widget Alpha", quantity=2.0, unit_price=50.0, amount=100.0),
            LineItem(description="Widget Beta", quantity=1.0, unit_price=50.0, amount=50.0),
        ],
    )

    with patch("app.routes.extract.extract_document", return_value=(inv, _mock_meta())):
        res = client.post("/api/extract", files={"file": ("invoice.pdf", _make_pdf(), "application/pdf")})
    assert res.status_code == 200
    doc_id = res.json()["id"]

    export_res = client.get(f"/api/documents/{doc_id}/export.csv")
    assert export_res.status_code == 200
    assert "text/csv" in export_res.headers["content-type"]
    assert 'attachment; filename="invoice.csv"' in export_res.headers["content-disposition"]

    # Verify UTF-8 BOM: first 3 bytes must be \xef\xbb\xbf
    raw_content = export_res.content
    assert raw_content[:3] == b"\xef\xbb\xbf"

    # Parse CSV with standard csv.reader
    text = raw_content.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))
    assert len(reader) == 3  # Header + 2 line item rows

    header = reader[0]
    assert header == EXPECTED_COLUMNS

    # Both line item rows repeat header fields
    row1, row2 = reader[1], reader[2]
    assert row1[0] == doc_id
    assert row1[1] == "invoice.pdf"
    assert row1[2] == "Global Supplies Ltd"
    assert row1[3] == "INV-2026-99"
    assert row1[4] == "2026-06-15"
    assert row1[5] == "USD"
    assert row1[6] == "150.00"
    assert row1[7] == "15.00"
    assert row1[8] == "165.00"
    assert row1[9] == "Widget Alpha"
    assert row1[10] == "2"
    assert row1[11] == "50.00"
    assert row1[12] == "100.00"

    assert row2[9] == "Widget Beta"
    assert row2[10] == "1"
    assert row2[12] == "50.00"


def test_empty_items_yields_one_row(client: TestClient):
    """An invoice with no line items yields exactly one row with empty item columns."""
    inv = InvoiceData(
        vendor="No Items Cafe",
        invoice_number="RECEIPT-001",
        date="2026-05-01",
        currency="USD",
        total=25.00,
        line_items=[],
    )

    with patch("app.routes.extract.extract_document", return_value=(inv, _mock_meta())):
        res = client.post("/api/extract", files={"file": ("receipt.pdf", _make_pdf(), "application/pdf")})
    doc_id = res.json()["id"]

    export_res = client.get(f"/api/documents/{doc_id}/export.csv")
    assert export_res.status_code == 200

    text = export_res.content.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))
    assert len(reader) == 2  # Header + 1 row
    data_row = reader[1]
    assert data_row[2] == "No Items Cafe"
    assert data_row[8] == "25.00"
    # item columns empty
    assert data_row[9] == ""   # description
    assert data_row[10] == ""  # quantity
    assert data_row[11] == ""  # unit price
    assert data_row[12] == ""  # amount


def test_reviewed_data_preferred_over_original(client: TestClient):
    """CSV export prefers reviewed data when present over original extraction data."""
    orig_inv = InvoiceData(
        vendor="Original Vendor",
        invoice_number="INV-OLD",
        total=100.0,
        subtotal=100.0,
        date="2026-01-01",
        currency="USD",
    )
    with patch("app.routes.extract.extract_document", return_value=(orig_inv, _mock_meta())):
        res = client.post("/api/extract", files={"file": ("doc.pdf", _make_pdf(), "application/pdf")})
    doc_id = res.json()["id"]

    # Update with reviewed data
    rev_inv = InvoiceData(
        vendor="Reviewed Vendor Inc",
        invoice_number="INV-NEW",
        total=120.0,
        subtotal=120.0,
        date="2026-01-02",
        currency="EUR",
    )
    client.put(f"/api/documents/{doc_id}", json={"data": rev_inv.model_dump(), "mark_reviewed": True})

    export_res = client.get(f"/api/documents/{doc_id}/export.csv")
    assert export_res.status_code == 200

    text = export_res.content.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))
    row = reader[1]
    assert row[2] == "Reviewed Vendor Inc"
    assert row[3] == "INV-NEW"
    assert row[4] == "2026-01-02"
    assert row[5] == "EUR"
    assert row[8] == "120.00"
    assert row[13] == "reviewed"
    assert row[14] == "false"  # needs_review is false


def test_float_rounding_and_bom_cleaning(client: TestClient):
    """0.1 + 0.2 floating point math is rounded cleanly to 2 decimal places."""
    float_sum = 0.1 + 0.2  # 0.30000000000000004 in Python
    inv = InvoiceData(
        vendor="Math Tech",
        invoice_number="M-101",
        date="2026-01-01",
        currency="USD",
        subtotal=float_sum,
        tax=0.03,
        total=0.33,
    )

    with patch("app.routes.extract.extract_document", return_value=(inv, _mock_meta())):
        res = client.post("/api/extract", files={"file": ("math.pdf", _make_pdf(), "application/pdf")})
    doc_id = res.json()["id"]

    export_res = client.get(f"/api/documents/{doc_id}/export.csv")
    assert export_res.content[:3] == b"\xef\xbb\xbf"

    text = export_res.content.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))
    row = reader[1]
    assert row[6] == "0.30"  # subtotal rounded cleanly, not 0.30000000000000004
    assert row[8] == "0.33"


def test_formula_injection_protection(client: TestClient):
    """Text cells starting with =, +, -, @ are prefixed with a quote; negative numeric amounts are not."""
    inv = InvoiceData(
        vendor='=HYPERLINK("http://evil.com")',
        invoice_number="-INV-EVIL",
        date="2026-01-01",
        currency="USD",
        subtotal=-100.0,
        tax=-5.0,
        total=-105.0,
        line_items=[
            LineItem(description="+cmd|' /C calc'!A0", quantity=1.0, unit_price=-100.0, amount=-100.0)
        ],
    )

    with patch("app.routes.extract.extract_document", return_value=(inv, _mock_meta())):
        res = client.post("/api/extract", files={"file": ("@formula_test.pdf", _make_pdf(), "application/pdf")})
    doc_id = res.json()["id"]

    export_res = client.get(f"/api/documents/{doc_id}/export.csv")
    text = export_res.content.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))
    row = reader[1]

    # Text columns: prefixed with '
    assert row[1] == "'@formula_test.pdf"
    assert row[2] == '\'=HYPERLINK("http://evil.com")'
    assert row[3] == "'-INV-EVIL"
    assert row[9] == "'+cmd|' /C calc'!A0"

    # Numeric columns: negative numbers are NOT prefixed with a quote
    assert row[6] == "-100.00"
    assert row[7] == "-5.00"
    assert row[8] == "-105.00"
    assert row[11] == "-100.00"
    assert row[12] == "-100.00"


def test_bulk_export_and_filtering(client: TestClient):
    """Bulk export exports matching documents, supports status=all and status=reviewed."""
    inv1 = InvoiceData(vendor="Vendor 1", total=10.0, date="2026-01-01")
    inv2 = InvoiceData(vendor="Vendor 2", total=20.0, date="2026-01-02")

    with patch("app.routes.extract.extract_document", return_value=(inv1, _mock_meta())):
        res1 = client.post("/api/extract", files={"file": ("doc1.pdf", _make_pdf(), "application/pdf")})
    with patch("app.routes.extract.extract_document", return_value=(inv2, _mock_meta())):
        res2 = client.post("/api/extract", files={"file": ("doc2.pdf", _make_pdf(), "application/pdf")})

    id1 = res1.json()["id"]
    id2 = res2.json()["id"]

    # Mark id1 as reviewed
    client.put(f"/api/documents/{id1}", json={"data": inv1.model_dump(), "mark_reviewed": True})

    # 1. status=reviewed (default)
    bulk_rev = client.get("/api/documents/export.csv")
    assert bulk_rev.status_code == 200
    assert bulk_rev.content[:3] == b"\xef\xbb\xbf"
    reader_rev = list(csv.reader(io.StringIO(bulk_rev.content.decode("utf-8-sig"))))
    assert len(reader_rev) == 2  # Header + doc1 only
    assert reader_rev[1][0] == id1

    # 2. status=all
    bulk_all = client.get("/api/documents/export.csv?status=all")
    assert bulk_all.status_code == 200
    reader_all = list(csv.reader(io.StringIO(bulk_all.content.decode("utf-8-sig"))))
    assert len(reader_all) >= 3
    doc_ids = [r[0] for r in reader_all[1:]]
    assert id1 in doc_ids
    assert id2 in doc_ids

    # 3. No match returns header only, not an error
    empty_export = client.get("/api/documents/export.csv?status=nonexistent_status")
    assert empty_export.status_code == 200
    reader_empty = list(csv.reader(io.StringIO(empty_export.content.decode("utf-8-sig"))))
    assert len(reader_empty) == 1
    assert reader_empty[0] == EXPECTED_COLUMNS


def test_export_error_handling_and_validation(client: TestClient):
    """Unknown document IDs and invalid UUID formats return 404."""
    assert client.get("/api/documents/00000000-0000-0000-0000-000000000000/export.csv").status_code == 404
    assert client.get("/api/documents/not-a-uuid/export.csv").status_code == 404
    assert client.get("/api/documents/../../etc/passwd/export.csv").status_code == 404

