"""Ground truth management, schema validation, and template generation."""

import json
import logging
import os
import re
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("evaluation.ground_truth")

HEADER_FIELDS = [
    "vendor",
    "invoice_number",
    "date",
    "currency",
    "subtotal",
    "taxable_amount",
    "cgst",
    "sgst",
    "igst",
    "cess",
    "tax",
    "total",
    "prices_include_tax",
]

NUMERIC_FIELDS = [
    "subtotal",
    "taxable_amount",
    "cgst",
    "sgst",
    "igst",
    "cess",
    "tax",
    "total",
]

LINE_ITEM_FIELDS = ["description", "quantity", "unit_price", "amount"]
DOCUMENT_KINDS = {"digital_pdf", "scan", "photo"}


def get_eval_dir() -> Path:
    """Return the absolute path to the eval/ root directory."""
    env_eval = os.getenv("EVAL_DIR")
    if env_eval:
        return Path(env_eval).resolve()
    # evaluation/ -> backend/ -> doc-extractor/ -> eval/
    return Path(__file__).resolve().parent.parent.parent / "eval"


def get_data_dir(dataset: str = "dev") -> Path:
    if dataset == "holdout":
        return get_eval_dir() / "holdout" / "data"
    return get_eval_dir() / "data"


def get_gt_dir(dataset: str = "dev") -> Path:
    if dataset == "holdout":
        return get_eval_dir() / "holdout" / "ground_truth"
    return get_eval_dir() / "ground_truth"


def get_variants_dir() -> Path:
    return get_eval_dir() / "variants"


def get_results_dir(label: str = "v1") -> Path:
    if label == "v1":
        return get_eval_dir() / "results"
    return get_eval_dir() / "results" / label


def get_report_dir() -> Path:
    return get_eval_dir() / "report"


def validate_ground_truth_dict(data: dict[str, Any]) -> tuple[bool, bool, list[str]]:
    """Validate ground truth structure, types, and readiness.

    Returns:
        (is_valid, is_verified, errors)
    """
    errors: list[str] = []

    # Required top-level keys
    for req in ("doc_id", "source_file", "document_kind", "_status", "expected"):
        if req not in data:
            errors.append(f"Missing required top-level key: '{req}'")

    if errors:
        return False, False, errors

    # document_kind
    kind = data.get("document_kind")
    if kind not in DOCUMENT_KINDS:
        errors.append(f"Invalid document_kind '{kind}'. Must be one of: {sorted(DOCUMENT_KINDS)}")

    # _status
    status = data.get("_status")
    if status not in ("TODO", "verified"):
        errors.append(f"Invalid _status '{status}'. Must be 'TODO' or 'verified'")

    expected = data.get("expected")
    if not isinstance(expected, dict):
        errors.append("'expected' must be an object")
        return False, False, errors

    # Date validation
    date_val = expected.get("date")
    if date_val not in (None, "IGNORE"):
        if not isinstance(date_val, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_val):
            errors.append(f"Invalid ISO date '{date_val}'. Must be 'YYYY-MM-DD', null, or 'IGNORE'")
        else:
            try:
                datetime.strptime(date_val, "%Y-%m-%d")
            except ValueError:
                errors.append(f"Calendar date '{date_val}' does not exist")

    # Numeric fields validation
    for num_field in NUMERIC_FIELDS:
        val = expected.get(num_field)
        if val not in (None, "IGNORE"):
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                errors.append(f"Field '{num_field}' must be a number, null, or 'IGNORE' (got {type(val).__name__})")

    # Line items validation
    items = expected.get("line_items", [])
    if not isinstance(items, list):
        errors.append("'line_items' must be a list")
    else:
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"line_items[{idx}] must be an object")
                continue
            for li_field in LINE_ITEM_FIELDS:
                if li_field not in item:
                    errors.append(f"line_items[{idx}] missing '{li_field}'")
            # Quantity, unit_price, amount type checks
            for li_num in ("quantity", "unit_price", "amount"):
                val = item.get(li_num)
                if val not in (None, "IGNORE"):
                    if not isinstance(val, (int, float)) or isinstance(val, bool):
                        errors.append(f"line_items[{idx}].{li_num} must be a number, null, or 'IGNORE'")

    is_valid = len(errors) == 0
    is_verified = is_valid and (status == "verified")
    return is_valid, is_verified, errors


def sanity_check_ground_truth(data: dict[str, Any], today: Optional[date] = None) -> list[str]:
    """Run sanity checks on ground truth data and return warning messages.

    Warnings only — does not alter validation status or modify any file.

    Checks:
      (a) sum of line-item amounts differs from both subtotal and total by > 0.02
      (b) subtotal + tax differs from total by > 0.02 when all 3 present and prices_include_tax is not true
      (c) cgst + sgst + igst + cess differs from tax by > 0.02 when those fields are present
      (d) date is not a valid ISO date or lies in the future
      (e) invoice_number contains spaces
      (f) zero line items
      (g) _draft_notes still exists
    """
    warnings: list[str] = []
    expected = data.get("expected")
    if not isinstance(expected, dict):
        return warnings

    # (a) sum of line-item amounts differs from both subtotal and total by more than 0.02
    items = expected.get("line_items")
    if isinstance(items, list) and items:
        numeric_amounts = [
            it.get("amount") for it in items
            if isinstance(it, dict) and isinstance(it.get("amount"), (int, float)) and not isinstance(it.get("amount"), bool)
        ]
        if numeric_amounts:
            item_sum = sum(numeric_amounts)
            subtotal = expected.get("subtotal")
            total = expected.get("total")

            has_sub = isinstance(subtotal, (int, float)) and not isinstance(subtotal, bool)
            has_tot = isinstance(total, (int, float)) and not isinstance(total, bool)

            diff_sub = (abs(item_sum - subtotal) > 0.02) if has_sub else True
            diff_tot = (abs(item_sum - total) > 0.02) if has_tot else True

            if (has_sub or has_tot) and diff_sub and diff_tot:
                sub_str = f"{subtotal:.2f}" if has_sub else "null"
                tot_str = f"{total:.2f}" if has_tot else "null"
                warnings.append(
                    f"line_items.amount: sum of line-item amounts ({item_sum:.2f}) differs from both "
                    f"subtotal ({sub_str}) and total ({tot_str}) by > 0.02"
                )

    # (b) subtotal + tax differs from total by more than 0.02 when all three are present and prices_include_tax is not true
    subtotal = expected.get("subtotal")
    tax = expected.get("tax")
    total = expected.get("total")
    prices_include_tax = expected.get("prices_include_tax")

    has_sub = isinstance(subtotal, (int, float)) and not isinstance(subtotal, bool)
    has_tax = isinstance(tax, (int, float)) and not isinstance(tax, bool)
    has_tot = isinstance(total, (int, float)) and not isinstance(total, bool)

    if has_sub and has_tax and has_tot and prices_include_tax is not True:
        calc_total = subtotal + tax
        if abs(calc_total - total) > 0.02:
            warnings.append(
                f"total: subtotal ({subtotal:.2f}) + tax ({tax:.2f}) = {calc_total:.2f} differs from total ({total:.2f}) by > 0.02 (prices_include_tax is not true)"
            )

    # (c) cgst + sgst + igst + cess differs from tax by more than 0.02 when those fields are present
    gst_components = {}
    for comp in ("cgst", "sgst", "igst", "cess"):
        val = expected.get(comp)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            gst_components[comp] = val

    if has_tax and gst_components:
        comp_sum = sum(gst_components.values())
        if abs(comp_sum - tax) > 0.02:
            comp_str = " + ".join(f"{k} ({v:.2f})" for k, v in gst_components.items())
            warnings.append(
                f"tax: {comp_str} = {comp_sum:.2f} differs from tax ({tax:.2f}) by > 0.02"
            )

    # (d) the date is not a valid ISO date or lies in the future
    date_val = expected.get("date")
    ref_today = today or date.today()
    if not isinstance(date_val, str):
        warnings.append(f"date: '{date_val}' is not a valid ISO date (expected YYYY-MM-DD)")
    else:
        try:
            parsed_d = datetime.strptime(date_val, "%Y-%m-%d").date()
            if parsed_d > ref_today:
                warnings.append(f"date: '{date_val}' lies in the future (today is {ref_today.isoformat()})")
        except ValueError:
            warnings.append(f"date: '{date_val}' is not a valid ISO date (expected YYYY-MM-DD)")

    # (e) invoice_number contains spaces
    inv_num = expected.get("invoice_number")
    if isinstance(inv_num, str) and " " in inv_num:
        warnings.append(f"invoice_number: '{inv_num}' contains spaces")

    # (f) there are zero line items
    if not isinstance(items, list) or len(items) == 0:
        warnings.append("line_items: contains zero line items")

    # (g) _draft_notes still exists
    if "_draft_notes" in data:
        warnings.append("_draft_notes: draft notes field still exists")

    return warnings


def load_ground_truth(file_path: Path | str) -> dict[str, Any]:
    """Load and parse ground truth JSON file."""
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def cmd_templates(dataset: str = "dev") -> int:
    """Generate ground truth templates for unannotated documents in data dir."""
    data_dir = get_data_dir(dataset)
    gt_dir = get_gt_dir(dataset)

    data_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    data_files = [p for p in data_dir.iterdir() if p.is_file() and p.name != ".gitkeep"]
    if not data_files:
        print(f"No documents found in {data_dir}. Place your document files there first.")
        return 0

    # Collect source_files already claimed by existing ground truth files
    claimed_sources: set[str] = set()
    for existing_gt in gt_dir.glob("*.json"):
        if existing_gt.name == ".gitkeep":
            continue
        try:
            content = json.loads(existing_gt.read_text(encoding="utf-8"))
            if "source_file" in content:
                claimed_sources.add(content["source_file"])
        except Exception:
            pass

    created = 0
    skipped = 0
    for doc_path in sorted(data_files):
        doc_id = doc_path.stem
        gt_path = gt_dir / f"{doc_id}.json"

        if doc_path.name in claimed_sources or gt_path.exists():
            skipped += 1
            continue

        template = {
            "doc_id": doc_id,
            "source_file": doc_path.name,
            "document_kind": "digital_pdf" if doc_path.suffix.lower() == ".pdf" else "photo",
            "_status": "TODO",
            "_instructions": (
                "Fill in all expected fields by READING THE DOCUMENT directly (NOT from AI tool output). "
                "Use null for any field the document does not show. "
                "Use 'IGNORE' for any field or row you do not wish to score. "
                "Change _status to 'verified' when complete."
            ),
            "expected": {
                "vendor": None,
                "invoice_number": None,
                "date": None,
                "currency": None,
                "subtotal": None,
                "taxable_amount": None,
                "cgst": None,
                "sgst": None,
                "igst": None,
                "cess": None,
                "tax": None,
                "total": None,
                "prices_include_tax": None,
                "line_items": [
                    {
                        "description": None,
                        "quantity": None,
                        "unit_price": None,
                        "amount": None,
                    }
                ],
            },
            "notes": "",
        }

        with gt_path.open("w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)
        created += 1
        print(f"Created template: {gt_path.name}")

    print(f"\nTemplates summary: {created} created, {skipped} already existed.")
    return 0


def cmd_check_gt(dataset: str = "dev") -> int:
    """Validate ground truth files for syntax, schema, and verified status."""
    gt_dir = get_gt_dir(dataset)
    data_dir = get_data_dir(dataset)

    if not gt_dir.exists():
        print(f"Ground truth directory does not exist: {gt_dir}")
        return 1

    gt_files = [p for p in gt_dir.glob("*.json") if p.name != ".gitkeep"]
    if not gt_files:
        print(f"No ground truth JSON files found in {gt_dir}")
        return 1

    ready: list[str] = []
    unready: list[tuple[str, list[str]]] = []
    file_warnings: list[tuple[str, list[str]]] = []

    for gt_path in sorted(gt_files):
        try:
            data = load_ground_truth(gt_path)
        except Exception as exc:
            unready.append((gt_path.name, [f"JSON parse error: {exc}"]))
            continue

        is_valid, is_verified, errors = validate_ground_truth_dict(data)
        warnings = sanity_check_ground_truth(data)
        if warnings:
            file_warnings.append((gt_path.name, warnings))

        # Check corresponding source file
        source_file = data.get("source_file")
        if source_file:
            src_path = data_dir / source_file
            if not src_path.is_file():
                errors.append(f"Source file '{source_file}' not found in {data_dir}")
                is_verified = False

        if is_verified:
            ready.append(gt_path.name)
        else:
            if data.get("_status") == "TODO":
                errors.append("Status is still 'TODO' (must be 'verified')")
            unready.append((gt_path.name, errors))

    print(f"=== Ground Truth Validation Report ({len(gt_files)} file(s)) ===")
    if ready:
        print(f"\nReady ({len(ready)}):")
        for name in ready:
            print(f"  ✓ {name}")

    if unready:
        print(f"\nNot Ready / Errors ({len(unready)}):")
        for name, errs in unready:
            print(f"  ✗ {name}:")
            for err in errs:
                print(f"      - {err}")

    if file_warnings:
        print(f"\nSanity Check Warnings ({len(file_warnings)} file(s)):")
        for name, warns in file_warnings:
            print(f"  ⚠ {name}:")
            for warn in warns:
                print(f"      - {warn}")

    if unready:
        print(f"\nResult: NOT READY ({len(unready)} unverified or invalid file(s)).")
        return 1
    else:
        print(f"\nResult: ALL {len(ready)} GROUND TRUTH FILE(S) VERIFIED AND READY.")
        return 0
