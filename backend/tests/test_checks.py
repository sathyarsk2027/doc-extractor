"""Table-driven unit tests for validation checks and review flags."""

import pytest
from app.schemas import InvoiceData, LineItem
from app.services.checks import run_checks, exceeds_tolerance, get_tolerance


def _base_valid_invoice(**kwargs) -> InvoiceData:
    """Return a completely consistent, valid invoice with zero flags, allowing overrides."""
    base = {
        "vendor": "Acme Corp",
        "invoice_number": "INV-001",
        "date": "2025-06-15",
        "currency": "USD",
        "line_items": [
            LineItem(description="Item 1", quantity=2.0, unit_price=40.0, amount=80.0),
            LineItem(description="Item 2", quantity=1.0, unit_price=20.0, amount=20.0),
        ],
        "subtotal": 100.0,
        "tax": 10.0,
        "total": 110.0,
    }
    base.update(kwargs)
    return InvoiceData(**base)


# ---------------------------------------------------------------------------
# Test 1: Fully consistent invoice -> no flags
# ---------------------------------------------------------------------------

def test_consistent_invoice_has_no_flags():
    invoice = _base_valid_invoice()
    flags = run_checks(invoice)
    assert flags == {}, f"Expected no flags, got: {flags}"


# ---------------------------------------------------------------------------
# Test 2: REQUIRED_MISSING (error) on vendor, date, and total
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "field,kwargs,expected_field,expected_code",
    [
        ("vendor", {"vendor": None}, "vendor", "REQUIRED_MISSING"),
        ("vendor_empty", {"vendor": "   "}, "vendor", "REQUIRED_MISSING"),
        ("date", {"date": None}, "date", "REQUIRED_MISSING"),
        ("date_empty", {"date": ""}, "date", "REQUIRED_MISSING"),
        ("total", {"total": None}, "total", "REQUIRED_MISSING"),
    ],
)
def test_required_missing_flags(field, kwargs, expected_field, expected_code):
    base_dict = _base_valid_invoice().model_dump()
    base_dict.update(kwargs)
    invoice = InvoiceData.model_validate(base_dict)
    flags = run_checks(invoice)

    assert expected_field in flags
    assert flags[expected_field]["code"] == expected_code
    assert flags[expected_field]["severity"] == "error"


# ---------------------------------------------------------------------------
# Test 3: TOTAL_MISMATCH (error)
# ---------------------------------------------------------------------------

def test_total_mismatch():
    invoice = _base_valid_invoice()
    # subtotal (100) + tax (10) = 110 != total (120)
    invoice.total = 120.0
    flags = run_checks(invoice)

    assert "total" in flags
    assert flags["total"]["code"] == "TOTAL_MISMATCH"
    assert flags["total"]["severity"] == "error"


# ---------------------------------------------------------------------------
# Test 4: LINE_SUM_MISMATCH (warning)
# ---------------------------------------------------------------------------

def test_line_sum_mismatch_with_subtotal():
    invoice = _base_valid_invoice()
    # Line items sum to 100.0, but subtotal is 105.0
    invoice.subtotal = 105.0
    invoice.total = 115.0  # Keep subtotal + tax = total consistent so only LINE_SUM triggers
    flags = run_checks(invoice)

    assert "line_items" in flags
    assert flags["line_items"]["code"] == "LINE_SUM_MISMATCH"
    assert flags["line_items"]["severity"] == "warning"


def test_line_sum_mismatch_with_total_when_no_subtotal():
    invoice = InvoiceData(
        vendor="Acme Corp",
        date="2025-06-15",
        currency="USD",
        line_items=[
            LineItem(description="Item 1", amount=50.0),
        ],
        subtotal=None,
        tax=None,
        total=100.0,  # 50.0 != 100.0
    )
    flags = run_checks(invoice)

    assert "line_items" in flags
    assert flags["line_items"]["code"] == "LINE_SUM_MISMATCH"
    assert flags["line_items"]["severity"] == "warning"


# ---------------------------------------------------------------------------
# Test 5: ITEM_MATH_MISMATCH (warning)
# ---------------------------------------------------------------------------

def test_item_math_mismatch():
    invoice = _base_valid_invoice()
    # Item 1: quantity=2, unit_price=40 -> expected 80, but amount is 70
    invoice.line_items[0].amount = 70.0
    invoice.subtotal = 90.0
    invoice.total = 100.0
    flags = run_checks(invoice)

    assert "line_items[0].amount" in flags
    assert flags["line_items[0].amount"]["code"] == "ITEM_MATH_MISMATCH"
    assert flags["line_items[0].amount"]["severity"] == "warning"


# ---------------------------------------------------------------------------
# Test 6: DATE_INVALID (error) and DATE_SUSPICIOUS (warning)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "invalid_date",
    [
        "2025/06/15",
        "June 15, 2025",
        "15-06-2025",
        "2025-02-30",  # invalid calendar day
        "not-a-date",
    ],
)
def test_date_invalid(invalid_date):
    invoice = _base_valid_invoice()
    invoice.date = invalid_date
    flags = run_checks(invoice)

    assert "date" in flags
    assert flags["date"]["code"] == "DATE_INVALID"
    assert flags["date"]["severity"] == "error"


@pytest.mark.parametrize(
    "suspicious_date",
    [
        "1999-12-31",  # Before 2000-01-01
        "1990-05-12",
        "2099-01-01",  # More than 1 day in the future
    ],
)
def test_date_suspicious(suspicious_date):
    invoice = _base_valid_invoice()
    invoice.date = suspicious_date
    flags = run_checks(invoice)

    assert "date" in flags
    assert flags["date"]["code"] == "DATE_SUSPICIOUS"
    assert flags["date"]["severity"] == "warning"


# ---------------------------------------------------------------------------
# Test 7: NEGATIVE_VALUE (warning)
# ---------------------------------------------------------------------------

def test_negative_values():
    invoice = _base_valid_invoice()
    invoice.subtotal = -50.0
    invoice.tax = -5.0
    invoice.total = -55.0  # -50 + -5 = -55 so math is consistent
    invoice.line_items = [
        LineItem(description="Refund Item", quantity=1.0, unit_price=-50.0, amount=-50.0),
    ]
    flags = run_checks(invoice)

    assert flags["total"]["code"] == "NEGATIVE_VALUE"
    assert flags["total"]["severity"] == "warning"
    assert flags["subtotal"]["code"] == "NEGATIVE_VALUE"
    assert flags["tax"]["code"] == "NEGATIVE_VALUE"
    assert flags["line_items[0].amount"]["code"] == "NEGATIVE_VALUE"


# ---------------------------------------------------------------------------
# Test 8: CURRENCY_INVALID (warning)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_currency",
    [
        "$",
        "usd",    # lowercase
        "US",     # 2 letters
        "USDT",   # 4 letters
        "123",
    ],
)
def test_currency_invalid(bad_currency):
    invoice = _base_valid_invoice()
    invoice.currency = bad_currency
    flags = run_checks(invoice)

    assert "currency" in flags
    assert flags["currency"]["code"] == "CURRENCY_INVALID"
    assert flags["currency"]["severity"] == "warning"


# ---------------------------------------------------------------------------
# Test 9: NO_LINE_ITEMS (warning)
# ---------------------------------------------------------------------------

def test_no_line_items():
    invoice = _base_valid_invoice()
    invoice.line_items = []
    flags = run_checks(invoice)

    assert "line_items" in flags
    assert flags["line_items"]["code"] == "NO_LINE_ITEMS"
    assert flags["line_items"]["severity"] == "warning"


# ---------------------------------------------------------------------------
# Test 10: Tolerance edge cases (0.01 passes, 0.05 fails on 100.00 total)
# ---------------------------------------------------------------------------

def test_tolerance_edge_case_passes_0_01_on_100_total():
    """Difference of 0.01 on 100.00 total is within tolerance -> passes (no TOTAL_MISMATCH)."""
    invoice = InvoiceData(
        vendor="Acme Corp",
        date="2025-06-15",
        currency="USD",
        line_items=[LineItem(description="Item", amount=100.0)],
        subtotal=90.0,
        tax=9.99,   # 90.0 + 9.99 = 99.99, diff from 100.00 is 0.01
        total=100.0,
    )
    flags = run_checks(invoice)
    assert "total" not in flags, f"Expected 0.01 diff to pass, but got flag: {flags.get('total')}"


def test_tolerance_edge_case_fails_0_05_on_100_total():
    """Difference of 0.05 on 100.00 total exceeds tolerance -> fails (TOTAL_MISMATCH error)."""
    invoice = InvoiceData(
        vendor="Acme Corp",
        date="2025-06-15",
        currency="USD",
        line_items=[LineItem(description="Item", amount=100.0)],
        subtotal=90.0,
        tax=9.95,   # 90.0 + 9.95 = 99.95, diff from 100.00 is 0.05
        total=100.0,
    )
    flags = run_checks(invoice)
    assert "total" in flags
    assert flags["total"]["code"] == "TOTAL_MISMATCH"
    assert flags["total"]["severity"] == "error"


# ---------------------------------------------------------------------------
# Test 11: Rounded-total case (line items sum to 99.99, total 100.00 -> no flag)
# ---------------------------------------------------------------------------

def test_rounded_total_case():
    """Line items sum to 99.99, total 100.00 -> no flag (within tolerance)."""
    invoice = InvoiceData(
        vendor="Acme Corp",
        invoice_number="INV-001",
        date="2025-06-15",
        currency="USD",
        line_items=[
            LineItem(description="Item 1", amount=33.33),
            LineItem(description="Item 2", amount=33.33),
            LineItem(description="Item 3", amount=33.33),
        ],  # sum is 99.99
        subtotal=99.99,
        tax=0.01,
        total=100.0,
    )
    flags = run_checks(invoice)
    assert flags == {}, f"Expected no flags for 99.99 rounding discrepancy, got: {flags}"


# ---------------------------------------------------------------------------
# Test 12: Multiple flags at once
# ---------------------------------------------------------------------------

def test_multiple_flags_at_once():
    """Document with multiple simultaneous defects generates all corresponding flags."""
    invoice = InvoiceData(
        vendor=None,              # REQUIRED_MISSING (vendor)
        date="not-a-date",        # DATE_INVALID (date)
        currency="dollars",       # CURRENCY_INVALID (currency)
        line_items=[],            # NO_LINE_ITEMS (line_items)
        subtotal=100.0,
        tax=10.0,
        total=200.0,              # TOTAL_MISMATCH (total)
    )
    flags = run_checks(invoice)

    assert "vendor" in flags
    assert flags["vendor"]["code"] == "REQUIRED_MISSING"

    assert "date" in flags
    assert flags["date"]["code"] == "DATE_INVALID"

    assert "currency" in flags
    assert flags["currency"]["code"] == "CURRENCY_INVALID"

    assert "line_items" in flags
    assert flags["line_items"]["code"] == "NO_LINE_ITEMS"

    assert "total" in flags
    assert flags["total"]["code"] == "TOTAL_MISMATCH"


# ---------------------------------------------------------------------------
# Test 13: Tax-inclusive invoices & GST breakdown (synthetic fixture, no PII)
# ---------------------------------------------------------------------------

def test_tax_inclusive_invoice_matches_total_no_flag():
    """In tax-inclusive retail invoices, line items sum to total (not subtotal) -> no LINE_SUM_MISMATCH."""
    invoice = InvoiceData(
        vendor="Retail Supermarket Ltd",
        invoice_number="INV-998877",
        date="2026-11-05",
        currency="INR",
        line_items=[
            LineItem(description="Item A", amount=590.0),
            LineItem(description="Item B", amount=870.0),
            LineItem(description="Item C", amount=122.0),
        ],  # sum is 1582.00
        taxable_amount=1521.94,
        cgst=30.03,
        sgst=30.03,
        subtotal=1521.94,
        tax=60.06,
        total=1582.00,
        prices_include_tax=True,
    )
    flags = run_checks(invoice)
    assert flags == {}, f"Expected 0 flags for tax-inclusive retail invoice, got: {flags}"


def test_tax_inclusive_invoice_mismatch_both_triggers_flag_with_hint():
    """When line items match neither subtotal nor total, LINE_SUM_MISMATCH is raised with hint."""
    invoice = InvoiceData(
        vendor="Retail Supermarket Ltd",
        invoice_number="INV-998877",
        date="2026-11-05",
        currency="INR",
        line_items=[
            LineItem(description="Item A", amount=500.0),  # sum is 500.0, differs from 1582 and 1521.94
        ],
        taxable_amount=1521.94,
        cgst=30.03,
        sgst=30.03,
        subtotal=1521.94,
        tax=60.06,
        total=1582.00,
        prices_include_tax=True,
    )
    flags = run_checks(invoice)
    assert "line_items" in flags
    assert flags["line_items"]["code"] == "LINE_SUM_MISMATCH"
    assert "tax-inclusive" in flags["line_items"]["message"]


def test_invoice_number_missing_is_warning():
    """Missing or empty invoice_number produces INVOICE_NUMBER_MISSING warning, not error."""
    inv_none = _base_valid_invoice()
    inv_none.invoice_number = None
    flags = run_checks(inv_none)
    assert "invoice_number" in flags
    assert flags["invoice_number"]["code"] == "INVOICE_NUMBER_MISSING"
    assert flags["invoice_number"]["severity"] == "warning"

    inv_empty = _base_valid_invoice()
    inv_empty.invoice_number = "   "
    flags_empty = run_checks(inv_empty)
    assert "invoice_number" in flags_empty
    assert flags_empty["invoice_number"]["code"] == "INVOICE_NUMBER_MISSING"
    assert flags_empty["invoice_number"]["severity"] == "warning"


# ---------------------------------------------------------------------------
# Test 14: Pipeline v2 tax-aware GST slab checks & text grounding
# ---------------------------------------------------------------------------

def test_gst_slab_multipliers_item_math_no_flag():
    """ITEM_MATH_MISMATCH must NOT fire when amount / (qty * unit_price) matches GST slab (1.05, 1.12, 1.18, 1.28 +/- 0.02)."""
    # 1.05 slab: qty=2, unit_price=100.0, amount=210.0 (ratio 210/200 = 1.05)
    inv_105 = _base_valid_invoice(
        line_items=[LineItem(description="Item 5%", quantity=2.0, unit_price=100.0, amount=210.0)],
        subtotal=200.0,
        tax=10.0,
        total=210.0,
    )
    assert "line_items[0].amount" not in run_checks(inv_105)

    # 1.12 slab: qty=1, unit_price=100.0, amount=112.0 (ratio 1.12)
    inv_112 = _base_valid_invoice(
        line_items=[LineItem(description="Item 12%", quantity=1.0, unit_price=100.0, amount=112.0)],
        subtotal=100.0,
        tax=12.0,
        total=112.0,
    )
    assert "line_items[0].amount" not in run_checks(inv_112)

    # 1.18 slab: qty=1, unit_price=50.0, amount=59.0 (ratio 59/50 = 1.18)
    inv_118 = _base_valid_invoice(
        line_items=[LineItem(description="Item 18%", quantity=1.0, unit_price=50.0, amount=59.0)],
        subtotal=50.0,
        tax=9.0,
        total=59.0,
    )
    assert "line_items[0].amount" not in run_checks(inv_118)

    # 1.28 slab: qty=1, unit_price=100.0, amount=128.0 (ratio 1.28)
    inv_128 = _base_valid_invoice(
        line_items=[LineItem(description="Item 28%", quantity=1.0, unit_price=100.0, amount=128.0)],
        subtotal=100.0,
        tax=28.0,
        total=128.0,
    )
    assert "line_items[0].amount" not in run_checks(inv_128)


def test_gst_slab_item_math_still_fires_for_other_ratios():
    """ITEM_MATH_MISMATCH still fires for non-slab ratios, including ratio near 0."""
    # Arbitrary non-slab ratio: qty=1, unit_price=100.0, amount=145.0 (ratio 1.45)
    inv_bad = _base_valid_invoice(
        line_items=[LineItem(description="Item NonSlab", quantity=1.0, unit_price=100.0, amount=145.0)],
        subtotal=100.0,
        total=145.0,
    )
    flags = run_checks(inv_bad)
    assert "line_items[0].amount" in flags
    assert flags["line_items[0].amount"]["code"] == "ITEM_MATH_MISMATCH"

    # Ratio near 0: qty=2, unit_price=50.0, amount=0.0
    inv_zero = _base_valid_invoice(
        line_items=[LineItem(description="Item Free", quantity=2.0, unit_price=50.0, amount=0.0)],
        subtotal=0.0,
        total=0.0,
    )
    flags_zero = run_checks(inv_zero)
    assert "line_items[0].amount" in flags_zero
    assert flags_zero["line_items[0].amount"]["code"] == "ITEM_MATH_MISMATCH"


def test_custom_gst_slab_list():
    """Custom GST slab multipliers passed to run_checks."""
    inv = _base_valid_invoice(
        line_items=[LineItem(description="Custom Item", quantity=1.0, unit_price=100.0, amount=108.0)],
        subtotal=100.0,
        total=108.0,
    )
    # Default slabs: 1.08 is not in [1.05, 1.12, 1.18, 1.28] -> flags
    assert "line_items[0].amount" in run_checks(inv)

    # Custom slabs including 1.08 -> does not flag
    flags_custom = run_checks(inv, gst_slabs=[1.08, 1.18])
    assert "line_items[0].amount" not in flags_custom


def test_text_grounding_checks():
    """Text-grounding check warns FIELD_NOT_IN_TEXT for vendor or invoice_number when source == 'text'."""
    text_layer = "TAX INVOICE\nVendor: Global Tech Solutions Pvt Ltd\nInvoice No: INV-2026-9999\nDate: 2026-11-05\nTotal: 100.00"

    # 1. Perfectly grounded text -> no warning
    inv_grounded = _base_valid_invoice(
        vendor="Global Tech Solutions Pvt Ltd",
        invoice_number="INV-2026-9999",
    )
    flags = run_checks(inv_grounded, text_content=text_layer, source="text")
    assert "vendor" not in flags
    assert "invoice_number" not in flags

    # 2. Casefold & whitespace-insensitive match -> no warning
    inv_case_space = _base_valid_invoice(
        vendor="GLOBAL   TECH   SOLUTIONS   PVT   LTD",
        invoice_number="inv - 2026 - 9999",
    )
    flags_case = run_checks(inv_case_space, text_content=text_layer, source="text")
    assert "vendor" not in flags_case
    assert "invoice_number" not in flags_case

    # 3. Vendor token overlap >= 0.9 -> matches without flag
    # Vendor has 10 tokens, 9 match text
    text_long = "Alpha Beta Gamma Delta Epsilon Zeta Eta Theta Iota Kappa Extra Text"
    inv_overlap = _base_valid_invoice(
        vendor="Alpha Beta Gamma Delta Epsilon Zeta Eta Theta Iota Omega",  # 9 of 10 match = 0.90
        invoice_number="INV-2026-9999",
    )
    flags_overlap = run_checks(inv_overlap, text_content=text_long + "\nINV-2026-9999", source="text")
    assert "vendor" not in flags_overlap

    # 4. Vendor not in text -> warns FIELD_NOT_IN_TEXT
    inv_wrong_vendor = _base_valid_invoice(
        vendor="Completely Different Vendor Inc",
        invoice_number="INV-2026-9999",
    )
    flags_wv = run_checks(inv_wrong_vendor, text_content=text_layer, source="text")
    assert "vendor" in flags_wv
    assert flags_wv["vendor"]["code"] == "FIELD_NOT_IN_TEXT"
    assert flags_wv["vendor"]["severity"] == "warning"

    # 5. Invoice number not in text -> warns FIELD_NOT_IN_TEXT
    inv_wrong_num = _base_valid_invoice(
        vendor="Global Tech Solutions Pvt Ltd",
        invoice_number="WRONG-INV-001",
    )
    flags_wn = run_checks(inv_wrong_num, text_content=text_layer, source="text")
    assert "invoice_number" in flags_wn
    assert flags_wn["invoice_number"]["code"] == "FIELD_NOT_IN_TEXT"
    assert flags_wn["invoice_number"]["severity"] == "warning"

    # 6. When source == 'image', FIELD_NOT_IN_TEXT is NOT raised even if absent from text
    flags_image = run_checks(inv_wrong_vendor, text_content=text_layer, source="image")
    assert "vendor" not in flags_image
