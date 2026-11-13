"""CSV export service supporting single and bulk exports with UTF-8 BOM and injection protection."""

import csv
import io
import re
from pathlib import Path
from typing import Any

from app.schemas import DocumentDetail

CSV_COLUMNS = [
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

INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_text(val: Any) -> str:
    """Prefix text starting with formula trigger chars with a single quote."""
    if val is None:
        return ""
    text = str(val)
    if text and text[0] in INJECTION_PREFIXES:
        return f"'{text}"
    return text


def format_csv_number(val: Any, decimals: int = 2) -> str:
    """Format numeric values with dot decimal separator, rounded to decimals. Never formula-prefixed."""
    if val is None or val == "":
        return ""
    try:
        f = float(val)
        rounded = round(f, decimals)
        return f"{rounded:.{decimals}f}"
    except (ValueError, TypeError):
        return ""


def format_csv_quantity(val: Any) -> str:
    """Format quantity without unnecessary trailing zeros if whole."""
    if val is None or val == "":
        return ""
    try:
        f = float(val)
        rounded = round(f, 2)
        if rounded.is_integer():
            return str(int(rounded))
        return f"{rounded:.2f}"
    except (ValueError, TypeError):
        return ""


def sanitize_download_filename(filename: str) -> str:
    """Derive safe ASCII-safe attachment filename ending in .csv."""
    name = Path(filename).name
    # Strip extension
    stem = Path(name).stem if Path(name).suffix else name
    safe_stem = re.sub(r"[^a-zA-Z0-9_\-]", "_", stem).strip("_") or "document"
    return f"{safe_stem}.csv"


def _build_document_rows(doc: DocumentDetail) -> list[dict[str, Any]]:
    """Build CSV row dicts for a single document."""
    # Use reviewed data when present, otherwise original
    data = doc.reviewed if doc.reviewed is not None else doc.original

    # Extract flag codes joined with semicolon
    flags = doc.flags or {}
    flag_codes_set = set()
    for f in flags.values():
        if isinstance(f, dict) and "code" in f:
            flag_codes_set.add(f["code"])
    flag_codes = ";".join(sorted(flag_codes_set))

    # Base document header fields
    base_info = {
        "document_id": doc.id,
        "filename": sanitize_csv_text(doc.filename),
        "vendor": sanitize_csv_text(data.vendor if data else ""),
        "invoice_number": sanitize_csv_text(data.invoice_number if data else ""),
        "date": data.date if (data and data.date) else "",
        "currency": data.currency if (data and data.currency) else "",
        "subtotal": format_csv_number(data.subtotal) if data else "",
        "tax": format_csv_number(data.tax) if data else "",
        "total": format_csv_number(data.total) if data else "",
        "status": doc.status,
        "needs_review": "true" if doc.needs_review else "false",
        "flag_codes": flag_codes,
    }

    line_items = data.line_items if (data and data.line_items) else []
    if not line_items:
        # Document with no line items outputs one row with empty item columns
        row = dict(base_info)
        row["item_description"] = ""
        row["item_quantity"] = ""
        row["item_unit_price"] = ""
        row["item_amount"] = ""
        return [row]

    rows = []
    for item in line_items:
        row = dict(base_info)
        row["item_description"] = sanitize_csv_text(item.description)
        row["item_quantity"] = format_csv_quantity(item.quantity)
        row["item_unit_price"] = format_csv_number(item.unit_price)
        row["item_amount"] = format_csv_number(item.amount)
        rows.append(row)
    return rows


def generate_documents_csv(docs: list[DocumentDetail]) -> bytes:
    """Generate CSV bytes encoded in UTF-8 with BOM (utf-8-sig) using standard library csv."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\r\n")
    writer.writeheader()

    for doc in docs:
        rows = _build_document_rows(doc)
        for r in rows:
            writer.writerow(r)

    # Encode to UTF-8 with BOM
    return output.getvalue().encode("utf-8-sig")

