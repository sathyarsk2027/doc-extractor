"""Phase 7 verification script: export synthetic document, verify BOM and CSV format."""

from app.schemas import DocumentDetail, InvoiceData, LineItem
from app.services.export import generate_documents_csv

inv = InvoiceData(
    vendor="Acme Synthetics Ltd",
    invoice_number="INV-2026-001",
    date="2026-11-13",
    currency="INR",
    subtotal=100.0,
    tax=18.0,
    total=118.0,
    line_items=[
        LineItem(description="Consulting Service (INR)", quantity=1.0, unit_price=100.0, amount=100.0)
    ]
)

doc = DocumentDetail(
    id="11111111-2222-3333-4444-555555555555",
    filename="synthetic_invoice.pdf",
    mime_type="application/pdf",
    page_count=1,
    status="reviewed",
    created_at="2026-11-13T10:00:00Z",
    updated_at="2026-11-13T10:00:00Z",
    reviewed_at="2026-11-13T10:05:00Z",
    pages=[],
    reviewed=inv,
    original=inv,
    flags={},
    needs_review=False,
)

csv_bytes = generate_documents_csv([doc])

# 1. Print first 3 bytes (BOM proof)
print(f"BOM Raw Bytes: {csv_bytes[:3]}")
print(f"BOM Hex: {[hex(b) for b in csv_bytes[:3]]} (Expected: ['0xef', '0xbb', '0xbf'])")
assert csv_bytes[:3] == b"\xef\xbb\xbf", "BOM missing!"

# 2. Print CSV lines
print("\nExported CSV Content:")
print(csv_bytes.decode("utf-8-sig"))

