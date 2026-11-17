"""Evaluation scoring functions, field-level matching, and Wilson interval metrics."""
import json
import difflib
import math
import re
import string
from dataclasses import dataclass, field
from typing import Any, Optional

from app.schemas import InvoiceData, LineItem

HEADER_FIELDS = [
    "vendor",
    "invoice_number",
    "date",
    "currency",
    "subtotal",
    "tax",
    "total",
    "taxable_amount",
    "cgst",
    "sgst",
    "igst",
    "cess",
    "prices_include_tax",
]


def normalize_text(text: Optional[str]) -> str:
    """Normalize text: casefold, strip punctuation, collapse whitespace."""
    if not text:
        return ""
    # Casefold
    folded = text.casefold()
    # Strip punctuation
    stripped = folded.translate(str.maketrans("", "", string.punctuation))
    # Collapse whitespace
    collapsed = re.sub(r"\s+", " ", stripped).strip()
    return collapsed


def wilson_interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float, float]:
    """Calculate the Wilson score confidence interval for a binomial proportion.

    Args:
        k: Number of successes.
        n: Total number of trials.
        confidence: Confidence level (default 0.95).

    Returns:
        Tuple of (p, lower_bound, upper_bound), bounded in [0.0, 1.0].
    """
    if n <= 0:
        return 0.0, 0.0, 0.0

    p = k / n
    # z for two-tailed normal distribution
    if abs(confidence - 0.95) < 1e-4:
        z = 1.959963984540054
    elif abs(confidence - 0.99) < 1e-4:
        z = 2.5758293035489004
    elif abs(confidence - 0.90) < 1e-4:
        z = 1.6448536269514722
    else:
        # Standard approximation using erfc-inverse could be used, but 95% is default
        z = 1.959963984540054

    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    spread = (z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)) / denom

    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    if k == n:
        upper = 1.0
    if k == 0:
        lower = 0.0
    return p, lower, upper


@dataclass
class LineItemMatchResult:
    """Detailed matching metrics for invoice line items."""

    expected_count: int
    predicted_count: int
    matched_count: int
    recall: float
    precision: float
    description_correct: int
    quantity_correct: int
    unit_price_correct: int
    has_discrepancy: bool
    wrong_item_notes: list[str] = field(default_factory=list)
    unmatched_expected: list[dict[str, Any]] = field(default_factory=list)
    unmatched_predicted: list[LineItem] = field(default_factory=list)


@dataclass
class CaseScoreResult:
    """Evaluation score result for a single test case."""

    doc_id: str
    case_id: str
    header_scores: dict[str, dict[str, Any]]
    vendor_exact: bool
    vendor_near: bool
    critical_correct: bool
    all_header_correct: bool
    line_item_result: LineItemMatchResult
    fully_correct: bool
    wrong_fields: list[str]
    has_error: bool
    flagged: bool
    classification: str  # "TP", "FN", "FP", "TN"
    flag_codes: list[str]


def score_header_field(field_name: str, expected_val: Any, pred_val: Any) -> tuple[bool, str]:
    """Score a single header field.

    Returns:
        (is_correct, status_type) where status_type in ('correct', 'hallucination', 'miss', 'value_mismatch')
    """
    if expected_val is None:
        if pred_val is None:
            return True, "correct"
        return False, "hallucination"

    if pred_val is None:
        return False, "miss"

    # Numeric fields
    if field_name in ("subtotal", "tax", "total", "taxable_amount", "cgst", "sgst", "igst", "cess"):
        try:
            diff = abs(float(pred_val) - float(expected_val))
            if diff <= 0.01 + 1e-6:
                return True, "correct"
            return False, "value_mismatch"
        except (ValueError, TypeError):
            return False, "value_mismatch"

    # Vendor field (near match ratio >= 0.90)
    if field_name == "vendor":
        norm_pred = normalize_text(str(pred_val))
        norm_exp = normalize_text(str(expected_val))
        if norm_pred == norm_exp:
            return True, "correct"
        ratio = difflib.SequenceMatcher(None, norm_pred, norm_exp).ratio()
        if ratio >= 0.90:
            return True, "correct"
        return False, "value_mismatch"

    # Invoice number (equal after stripping spaces)
    if field_name == "invoice_number":
        clean_pred = str(pred_val).replace(" ", "").casefold()
        clean_exp = str(expected_val).replace(" ", "").casefold()
        if clean_pred == clean_exp:
            return True, "correct"
        return False, "value_mismatch"

    # Date (exact ISO string)
    if field_name == "date":
        if str(pred_val).strip() == str(expected_val).strip():
            return True, "correct"
        return False, "value_mismatch"

    # Currency
    if field_name == "currency":
        if str(pred_val).strip().upper() == str(expected_val).strip().upper():
            return True, "correct"
        return False, "value_mismatch"

    # prices_include_tax
    if field_name == "prices_include_tax":
        if bool(pred_val) == bool(expected_val):
            return True, "correct"
        return False, "value_mismatch"

    # Fallback exact string comparison
    if str(pred_val).strip() == str(expected_val).strip():
        return True, "correct"
    return False, "value_mismatch"


def match_line_items(
    expected_items: list[dict[str, Any]],
    predicted_items: list[LineItem],
) -> LineItemMatchResult:
    """Greedily match expected line items to predicted items with tie-breaking."""
    exp_count = len(expected_items)
    pred_count = len(predicted_items)

    if exp_count == 0 and pred_count == 0:
        return LineItemMatchResult(
            expected_count=0,
            predicted_count=0,
            matched_count=0,
            recall=1.0,
            precision=1.0,
            description_correct=0,
            quantity_correct=0,
            unit_price_correct=0,
            has_discrepancy=False,
            wrong_item_notes=[],
        )

    matched_pred_indices: set[int] = set()
    matched_pairs: list[tuple[dict[str, Any], LineItem]] = []
    wrong_notes: list[str] = []
    unmatched_exp: list[dict[str, Any]] = []
    unmatched_pred: list[LineItem] = []

    # Greedily match each expected item
    for e_idx, e_item in enumerate(expected_items):
        e_amount = e_item.get("amount")
        e_desc = normalize_text(e_item.get("description"))

        best_p_idx = -1
        best_sim = -1.0

        for p_idx, p_item in enumerate(predicted_items):
            if p_idx in matched_pred_indices:
                continue

            # Amount check: if expected is not IGNORE, must match within 0.01
            amount_matches = True
            if e_amount not in (None, "IGNORE"):
                if p_item.amount is None or abs(float(p_item.amount) - float(e_amount)) > 0.01 + 1e-6:
                    amount_matches = False

            if not amount_matches:
                continue

            # Calculate description similarity for tie-breaking
            p_desc = normalize_text(p_item.description)
            sim = difflib.SequenceMatcher(None, e_desc, p_desc).ratio()
            if sim > best_sim:
                best_sim = sim
                best_p_idx = p_idx

        if best_p_idx >= 0:
            matched_pred_indices.add(best_p_idx)
            matched_pairs.append((e_item, predicted_items[best_p_idx]))
        else:
            wrong_notes.append(f"Expected item #{e_idx+1} unmatched (amount={e_amount})")
            unmatched_exp.append(e_item)

    # Unmatched predicted items (extras)
    for p_idx, p_item in enumerate(predicted_items):
        if p_idx not in matched_pred_indices:
            wrong_notes.append(f"Extra predicted item #{p_idx+1} (amount={p_item.amount})")
            unmatched_pred.append(p_item)

    matched_count = len(matched_pairs)
    recall = (matched_count / exp_count) if exp_count > 0 else 1.0
    precision = (matched_count / pred_count) if pred_count > 0 else (1.0 if exp_count == 0 else 0.0)

    # Detailed field verification for matched pairs
    desc_correct = 0
    qty_correct = 0
    unit_price_correct = 0
    pair_discrepancy = False

    for e_item, p_item in matched_pairs:
        # Description: ratio >= 0.80
        e_desc = e_item.get("description")
        if e_desc == "IGNORE":
            desc_correct += 1
        elif e_desc is not None:
            norm_e = normalize_text(e_desc)
            norm_p = normalize_text(p_item.description)
            if difflib.SequenceMatcher(None, norm_e, norm_p).ratio() >= 0.80:
                desc_correct += 1
            else:
                pair_discrepancy = True
                wrong_notes.append(f"Description mismatch: expected '{e_desc}' vs '{p_item.description}'")

        # Quantity: diff <= 0.001
        e_qty = e_item.get("quantity")
        if e_qty == "IGNORE":
            qty_correct += 1
        elif e_qty is not None:
            if p_item.quantity is not None and abs(float(p_item.quantity) - float(e_qty)) <= 0.001 + 1e-6:
                qty_correct += 1
            else:
                pair_discrepancy = True
                wrong_notes.append(f"Quantity mismatch: expected {e_qty} vs {p_item.quantity}")

        # Unit price: diff <= 0.01
        e_up = e_item.get("unit_price")
        if e_up == "IGNORE":
            unit_price_correct += 1
        elif e_up is not None:
            if p_item.unit_price is not None and abs(float(p_item.unit_price) - float(e_up)) <= 0.01 + 1e-6:
                unit_price_correct += 1
            else:
                pair_discrepancy = True
                wrong_notes.append(f"Unit price mismatch: expected {e_up} vs {p_item.unit_price}")

    has_discrepancy = (
        (matched_count < exp_count)
        or (matched_count < pred_count)
        or pair_discrepancy
    )

    return LineItemMatchResult(
        expected_count=exp_count,
        predicted_count=pred_count,
        matched_count=matched_count,
        recall=recall,
        precision=precision,
        description_correct=desc_correct,
        quantity_correct=qty_correct,
        unit_price_correct=unit_price_correct,
        has_discrepancy=has_discrepancy,
        wrong_item_notes=wrong_notes,
        unmatched_expected=unmatched_exp,
        unmatched_predicted=unmatched_pred,
    )


def score_case(
    doc_id: str,
    case_id: str,
    ground_truth: dict[str, Any],
    prediction: Optional[InvoiceData],
    flags: dict[str, Any],
    needs_review: bool,
) -> CaseScoreResult:
    """Score a single extraction output against ground truth annotation."""
    expected = ground_truth.get("expected", {})
    wrong_fields: list[str] = []
    header_scores: dict[str, dict[str, Any]] = {}

    vendor_exact = False
    vendor_near = False

    # Check vendor exact vs near
    exp_vendor = expected.get("vendor")
    pred_vendor = prediction.vendor if prediction else None
    if exp_vendor not in ("IGNORE", None) and pred_vendor is not None:
        norm_exp = normalize_text(exp_vendor)
        norm_pred = normalize_text(pred_vendor)
        vendor_exact = (norm_exp == norm_pred)
        vendor_near = vendor_exact or (difflib.SequenceMatcher(None, norm_exp, norm_pred).ratio() >= 0.90)

    # Score each header field
    for fld in HEADER_FIELDS:
        if fld not in expected:
            continue
        exp_val = expected[fld]
        if exp_val == "IGNORE":
            continue

        pred_val = getattr(prediction, fld, None) if prediction else None
        is_corr, status_type = score_header_field(fld, exp_val, pred_val)
        header_scores[fld] = {
            "correct": is_corr,
            "status": status_type,
            "expected": exp_val,
            "predicted": pred_val,
        }
        if not is_corr:
            wrong_fields.append(fld)

    # Critical correctness: vendor near + date + total
    crit_vendor = header_scores.get("vendor", {}).get("correct", False) if "vendor" in expected and expected["vendor"] != "IGNORE" else True
    crit_date = header_scores.get("date", {}).get("correct", False) if "date" in expected and expected["date"] != "IGNORE" else True
    crit_total = header_scores.get("total", {}).get("correct", False) if "total" in expected and expected["total"] != "IGNORE" else True
    critical_correct = crit_vendor and crit_date and crit_total

    all_header_correct = (len(wrong_fields) == 0)

    # Line item matching
    exp_items = expected.get("line_items", [])
    pred_items = prediction.line_items if prediction else []
    li_result = match_line_items(exp_items, pred_items)
    for note in li_result.wrong_item_notes:
        wrong_fields.append(f"item:{note}")

    fully_correct = all_header_correct and not li_result.has_discrepancy
    has_error = (len(wrong_fields) > 0)
    flagged = bool(needs_review)

    # Confusion matrix
    if has_error and flagged:
        classification = "TP"
    elif has_error and not flagged:
        classification = "FN"  # Silent error
    elif not has_error and flagged:
        classification = "FP"  # False alarm
    else:
        classification = "TN"

    # Flag codes
    flag_codes = [f_data.get("code", "UNKNOWN") for f_data in flags.values()]

    return CaseScoreResult(
        doc_id=doc_id,
        case_id=case_id,
        header_scores=header_scores,
        vendor_exact=vendor_exact,
        vendor_near=vendor_near,
        critical_correct=critical_correct,
        all_header_correct=all_header_correct,
        line_item_result=li_result,
        fully_correct=fully_correct,
        wrong_fields=wrong_fields,
        has_error=has_error,
        flagged=flagged,
        classification=classification,
        flag_codes=flag_codes,
    )


def cmd_score(label: str = "v1", dataset: str = "dev") -> int:
    """Score raw extraction results against verified ground truth."""
    from evaluation.ground_truth import get_results_dir, get_gt_dir, load_ground_truth

    results_dir = get_results_dir(label)
    raw_dir = results_dir / "raw"
    gt_dir = get_gt_dir(dataset)

    if not raw_dir.exists():
        print(f"No results found in {raw_dir}. Run evaluation cases first via 'cli run'.")
        return 1

    case_files = sorted(raw_dir.glob("*.json"))
    if not case_files:
        print(f"No case JSON files found in {raw_dir}.")
        return 1

    print(f"Scoring {len(case_files)} case(s)...")
    scored_cases: list[dict[str, Any]] = []

    for c_path in case_files:
        case_id = c_path.stem
        # case_id format: <doc_id>__<mode/variant>
        parts = case_id.split("__")
        doc_id = parts[0]

        gt_file = gt_dir / f"{doc_id}.json"
        if not gt_file.exists():
            print(f"  [WARN] Ground truth file not found for doc '{doc_id}': {gt_file}")
            continue

        gt = load_ground_truth(gt_file)
        with c_path.open("r", encoding="utf-8") as f:
            raw_data = json.load(f)

        pred_dict = raw_data.get("extraction")
        pred_inv = InvoiceData.model_validate(pred_dict) if pred_dict else None
        flags = raw_data.get("flags", {})
        needs_review = raw_data.get("needs_review", False)

        res = score_case(
            doc_id=doc_id,
            case_id=case_id,
            ground_truth=gt,
            prediction=pred_inv,
            flags=flags,
            needs_review=needs_review,
        )

        scored_cases.append({
            "doc_id": res.doc_id,
            "case_id": res.case_id,
            "classification": res.classification,
            "critical_correct": res.critical_correct,
            "fully_correct": res.fully_correct,
            "wrong_fields_count": len(res.wrong_fields),
        })

    # Save summary of scores
    scores_file = results_dir / "scores.json"
    with scores_file.open("w", encoding="utf-8") as f:
        json.dump(scored_cases, f, indent=2)

    print(f"Scoring complete. Scored {len(scored_cases)} cases. Saved to {scores_file.name}.")
    return 0


def cmd_diff(case_id: str) -> int:
    """Print field-by-field diff between expected and predicted values for a single case."""
    from evaluation.ground_truth import get_results_dir, get_gt_dir, load_ground_truth

    raw_path = get_results_dir() / "raw" / f"{case_id}.json"
    if not raw_path.is_file():
        print(f"Error: Result file not found for case '{case_id}' at {raw_path}")
        return 1

    doc_id = case_id.split("__")[0]
    gt_path = get_gt_dir() / f"{doc_id}.json"
    if not gt_path.is_file():
        # Fallback search
        found_gt = None
        for p in get_gt_dir().glob("*.json"):
            if p.name != ".gitkeep":
                try:
                    data = load_ground_truth(p)
                    if data.get("doc_id") == doc_id:
                        found_gt = p
                        break
                except Exception:
                    pass
        if found_gt:
            gt_path = found_gt
        else:
            print(f"Error: Ground truth file not found for doc '{doc_id}' in {get_gt_dir()}")
            return 1

    try:
        raw_data = json.loads(raw_path.read_text(encoding="utf-8"))
        gt_data = load_ground_truth(gt_path)
    except Exception as exc:
        print(f"Error reading JSON files: {exc}")
        return 1

    pred_data = raw_data.get("extraction")
    prediction = InvoiceData.model_validate(pred_data) if pred_data else None
    flags = raw_data.get("flags") or {}
    needs_review = raw_data.get("needs_review") or False

    case_res = score_case(doc_id, case_id, gt_data, prediction, flags, needs_review)

    print("=" * 80)
    print(f"Case Diff: {case_id} (Document: {doc_id})")
    print("=" * 80)
    print(f"Classification:   {case_res.classification}")
    print(f"Needs Review:     {needs_review}")
    flag_list = [f"{k} ({v.get('code', 'UNKNOWN')})" for k, v in flags.items()] if isinstance(flags, dict) else []
    print(f"Fired Flags:      {', '.join(flag_list) if flag_list else 'None'}")
    print(f"Critical Correct: {case_res.critical_correct}")
    print(f"Fully Correct:    {case_res.fully_correct}")

    print("\n--- Header Fields ---")
    print(f"{'FIELD':<20} {'EXPECTED':<30} {'PREDICTED':<30} {'RESULT'}")
    print("-" * 90)
    for fld in HEADER_FIELDS:
        if fld in case_res.header_scores:
            s = case_res.header_scores[fld]
            status_str = "✓ CORRECT" if s["correct"] else f"✗ WRONG ({s['status']})"
            exp_str = str(s["expected"]) if s["expected"] is not None else "null"
            pred_str = str(s["predicted"]) if s["predicted"] is not None else "null"
            print(f"{fld:<20} {exp_str:<30} {pred_str:<30} {status_str}")

    li = case_res.line_item_result
    print("\n--- Line-Item Matching ---")
    print(f"Expected count:   {li.expected_count}")
    print(f"Predicted count:  {li.predicted_count}")
    print(f"Matched count:    {li.matched_count}")
    print(f"Item Recall:      {li.recall * 100:.1f}%")
    print(f"Item Precision:   {li.precision * 100:.1f}%")

    if li.unmatched_expected:
        print(f"\nUnmatched Expected Items ({len(li.unmatched_expected)}):")
        for idx, it in enumerate(li.unmatched_expected, 1):
            desc = it.get("description", "N/A")
            amt = it.get("amount", "N/A")
            qty = it.get("quantity", "N/A")
            up = it.get("unit_price", "N/A")
            print(f"  {idx}. desc={desc!r}, amount={amt}, qty={qty}, unit_price={up}")
    else:
        print("\nUnmatched Expected Items: None")

    if li.unmatched_predicted:
        print(f"\nUnmatched Predicted Items ({len(li.unmatched_predicted)}):")
        for idx, it in enumerate(li.unmatched_predicted, 1):
            desc = it.description or "N/A"
            amt = it.amount if it.amount is not None else "N/A"
            qty = it.quantity if it.quantity is not None else "N/A"
            up = it.unit_price if it.unit_price is not None else "N/A"
            print(f"  {idx}. desc={desc!r}, amount={amt}, qty={qty}, unit_price={up}")
    else:
        print("\nUnmatched Predicted Items: None")

    print("=" * 80)
    return 0
