"""Validation checks and review flags for extracted invoice data."""

import re
from datetime import date, datetime, timedelta
from typing import Any

from app.schemas import InvoiceData


def get_tolerance(base: float | None) -> float:
    """Calculate tolerance for rounding discrepancies.

    Per spec: max(0.02, 0.5% of base).
    For standard amounts up to 100.00, tolerance is 0.02 (2 cents),
    allowing 0.01 discrepancy to pass (e.g. 99.99 vs 100.00) while 0.05 fails.
    For larger amounts (> 100.00), scales up to 0.5% (0.005 * base).
    """
    if base is None or base == 0:
        return 0.02
    abs_base = abs(base)
    if abs_base <= 100.0:
        return 0.02
    return max(0.02, 0.005 * abs_base)


def exceeds_tolerance(diff: float, base: float | None) -> bool:
    """Return True if diff exceeds the allowed tolerance."""
    return round(abs(diff), 4) > get_tolerance(base)


def run_checks(invoice: InvoiceData) -> dict[str, dict[str, str]]:
    """Run pure validation checks on extracted InvoiceData.

    Returns:
        Dictionary mapping field names to flag descriptors:
        {"total": {"code": "TOTAL_MISMATCH", "message": "...", "severity": "error"}, ...}
    """
    flags: dict[str, dict[str, str]] = {}

    def _set_flag(field: str, code: str, message: str, severity: str) -> None:
        """Set flag on field, preserving error severity over warning if field already flagged."""
        if field in flags and flags[field]["severity"] == "error" and severity == "warning":
            return
        flags[field] = {
            "code": code,
            "message": message,
            "severity": severity,
        }

    # 1. REQUIRED_MISSING (error): vendor, date or total is null or empty
    if not invoice.vendor or not invoice.vendor.strip():
        _set_flag("vendor", "REQUIRED_MISSING", "Vendor name is missing.", "error")

    if not invoice.date or not invoice.date.strip():
        _set_flag("date", "REQUIRED_MISSING", "Invoice date is missing.", "error")

    if invoice.total is None:
        _set_flag("total", "REQUIRED_MISSING", "Total amount is missing.", "error")

    # 2. DATE_INVALID (error) & DATE_SUSPICIOUS (warning)
    if invoice.date and invoice.date.strip():
        parsed_date: date | None = None
        # Strict YYYY-MM-DD regex check first
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", invoice.date.strip()):
            _set_flag("date", "DATE_INVALID", f"Date '{invoice.date}' is not in YYYY-MM-DD format.", "error")
        else:
            try:
                parsed_date = datetime.strptime(invoice.date.strip(), "%Y-%m-%d").date()
            except ValueError:
                _set_flag("date", "DATE_INVALID", f"Date '{invoice.date}' is not a valid calendar date.", "error")

        if parsed_date is not None:
            # Check suspicious: earlier than 2000-01-01 or more than 1 day in the future
            tomorrow = date.today() + timedelta(days=1)
            if parsed_date < date(2000, 1, 1) or parsed_date > tomorrow:
                _set_flag(
                    "date",
                    "DATE_SUSPICIOUS",
                    f"Date '{invoice.date}' is unusually far in the past or future.",
                    "warning",
                )

    # 3. CURRENCY_INVALID (warning): not a 3-letter uppercase code
    if invoice.currency is not None:
        if not re.match(r"^[A-Z]{3}$", invoice.currency.strip()):
            _set_flag(
                "currency",
                "CURRENCY_INVALID",
                f"Currency '{invoice.currency}' is not a valid 3-letter uppercase ISO code.",
                "warning",
            )

    # 4. NO_LINE_ITEMS (warning): empty line_items
    if not invoice.line_items:
        _set_flag("line_items", "NO_LINE_ITEMS", "No line items were detected.", "warning")

    # 5. LINE_SUM_MISMATCH (warning):
    # Sum of line items should match subtotal OR total (for tax-inclusive invoices)
    if invoice.line_items:
        amounts = [item.amount for item in invoice.line_items if item.amount is not None]
        if amounts:
            line_sum = sum(amounts)
            matches_subtotal = False
            matches_total = False

            if invoice.subtotal is not None:
                matches_subtotal = not exceeds_tolerance(line_sum - invoice.subtotal, invoice.subtotal)

            if invoice.total is not None:
                matches_total = not exceeds_tolerance(line_sum - invoice.total, invoice.total)

            # If it matches EITHER subtotal OR total, line sum is consistent
            if not matches_subtotal and not matches_total:
                hint = ""
                if invoice.prices_include_tax:
                    hint = " (prices marked tax-inclusive; compared against total)"
                target_str = f"subtotal ({invoice.subtotal:.2f})" if invoice.subtotal is not None else ""
                if invoice.total is not None:
                    target_str += f" or total ({invoice.total:.2f})" if target_str else f"total ({invoice.total:.2f})"

                _set_flag(
                    "line_items",
                    "LINE_SUM_MISMATCH",
                    f"Sum of line items ({line_sum:.2f}) does not match {target_str}{hint}.",
                    "warning",
                )

    # 6. TOTAL_MISMATCH (error):
    # subtotal + tax differs from total by more than tolerance (only when all three exist)
    if (
        invoice.subtotal is not None
        and invoice.tax is not None
        and invoice.total is not None
    ):
        base_subtotal = (
            invoice.taxable_amount
            if (invoice.prices_include_tax and invoice.taxable_amount is not None)
            else invoice.subtotal
        )
        expected_total = base_subtotal + invoice.tax
        diff = expected_total - invoice.total
        if exceeds_tolerance(diff, invoice.total):
            _set_flag(
                "total",
                "TOTAL_MISMATCH",
                f"Subtotal ({base_subtotal:.2f}) + tax ({invoice.tax:.2f}) = {expected_total:.2f}, differs from total ({invoice.total:.2f}) by {abs(diff):.2f}.",
                "error",
            )

    # 7. ITEM_MATH_MISMATCH (warning):
    # for a line with quantity, unit_price and amount, quantity x unit_price differs from amount
    for idx, item in enumerate(invoice.line_items):
        if (
            item.quantity is not None
            and item.unit_price is not None
            and item.amount is not None
        ):
            calc_amount = item.quantity * item.unit_price
            diff = calc_amount - item.amount
            if exceeds_tolerance(diff, item.amount):
                _set_flag(
                    f"line_items[{idx}].amount",
                    "ITEM_MATH_MISMATCH",
                    f"Quantity ({item.quantity}) x unit price ({item.unit_price:.2f}) = {calc_amount:.2f}, differs from amount ({item.amount:.2f}).",
                    "warning",
                )

    # 8. NEGATIVE_VALUE (warning):
    # negative total/subtotal/tax or line amount (credit notes are possible, so warning only)
    if invoice.total is not None and invoice.total < 0:
        _set_flag("total", "NEGATIVE_VALUE", f"Total amount is negative ({invoice.total:.2f}).", "warning")

    if invoice.subtotal is not None and invoice.subtotal < 0:
        _set_flag("subtotal", "NEGATIVE_VALUE", f"Subtotal is negative ({invoice.subtotal:.2f}).", "warning")

    if invoice.tax is not None and invoice.tax < 0:
        _set_flag("tax", "NEGATIVE_VALUE", f"Tax amount is negative ({invoice.tax:.2f}).", "warning")

    for idx, item in enumerate(invoice.line_items):
        if item.amount is not None and item.amount < 0:
            _set_flag(
                f"line_items[{idx}].amount",
                "NEGATIVE_VALUE",
                f"Line item amount is negative ({item.amount:.2f}).",
                "warning",
            )

    return flags
