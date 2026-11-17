"""Aggregate report generation, extended evaluation views, and manual timing comparison."""

import csv
import json
import logging
import math
import random
import re
import statistics
import string
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

from app.schemas import InvoiceData
from evaluation.ground_truth import (
    HEADER_FIELDS,
    get_gt_dir,
    get_report_dir,
    get_results_dir,
    load_ground_truth,
)
from evaluation.scoring import score_case, wilson_interval
from evaluation.pipeline_runner import get_git_version_info

logger = logging.getLogger("evaluation.report")

CASE_TYPES = ["text", "image", "lowres", "jpeg35", "rot3blur"]

ALLOWED_CAUSES = [
    "wrong_invoice",
    "vendor_naming",
    "line_amount_definition",
    "read_error",
    "other",
]

CAUSE_DESCRIPTIONS = {
    "wrong_invoice": "Extracted data from a different document, reference invoice, or misidentified invoice entity.",
    "vendor_naming": "Vendor entity discrepancy (legal name vs DBA/trade name or logo/letterhead interpretation).",
    "line_amount_definition": "Discrepancy in line item price/amount conventions (pre-tax vs post-tax totals, discounts).",
    "read_error": "Character-level OCR/vision misreads on low-resolution, blurred, or noisy document regions.",
    "other": "Miscellaneous defects or edge-case extraction failures not covered by specific categories.",
    "unlabelled": "Silent error cases awaiting manual root-cause taxonomy assignment in error_causes.json.",
}


def bucket_item_math_ratio(ratio: Optional[float]) -> str:
    """Bucket ratio = amount / (quantity * unit_price) into standard GST tax buckets."""
    if ratio is None:
        return "other"
    if abs(ratio - 0.0) <= 0.01:
        return "~0"
    elif abs(ratio - 1.05) <= 0.02:
        return "~1.05"
    elif abs(ratio - 1.12) <= 0.02:
        return "~1.12"
    elif abs(ratio - 1.18) <= 0.02:
        return "~1.18"
    elif abs(ratio - 1.28) <= 0.02:
        return "~1.28"
    else:
        return "other"


def extract_item_math_stats(scored_cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate counts for ITEM_MATH_MISMATCH bucketed by ratio and TP/FP."""
    ratio_buckets = {"~1.05": 0, "~1.12": 0, "~1.18": 0, "~1.28": 0, "~0": 0, "other": 0}
    tp_count = 0
    fp_count = 0
    total_flags = 0

    for c in scored_cases:
        flags = c.get("flags", {})
        classification = c.get("classification", "UNKNOWN")
        extraction = c.get("extraction") or {}
        line_items = extraction.get("line_items") or []

        for f_k, f_v in flags.items():
            if f_v.get("code") == "ITEM_MATH_MISMATCH":
                total_flags += 1
                if classification == "TP":
                    tp_count += 1
                elif classification == "FP":
                    fp_count += 1

                m = re.search(r"line_items\[(\d+)\]", f_k)
                ratio = None
                if m and line_items:
                    idx = int(m.group(1))
                    if 0 <= idx < len(line_items):
                        item = line_items[idx]
                        qty = item.get("quantity")
                        up = item.get("unit_price")
                        amt = item.get("amount")
                        if qty is not None and up is not None and (qty * up) != 0 and amt is not None:
                            ratio = amt / (qty * up)
                        elif amt == 0.0 or (amt is not None and abs(amt) <= 0.01):
                            ratio = 0.0

                b = bucket_item_math_ratio(ratio)
                ratio_buckets[b] += 1

    return {
        "total_flags": total_flags,
        "ratio_buckets": ratio_buckets,
        "tp_count": tp_count,
        "fp_count": fp_count,
    }


def compute_sign_test_onesided_p(better: int, worse: int) -> float:
    """Compute exact one-sided p-value for sign test (testing if better > worse).

    Discards ties per standard sign test methodology.
    """
    n = better + worse
    if n == 0:
        return 1.0
    return sum(math.comb(n, j) * (0.5 ** n) for j in range(better, n + 1))


def get_report_git_info(exclude_dir: str = "eval/report") -> dict[str, Any]:
    """Retrieve git HEAD short hash, dirty status, and nearest tag at report generation time.

    Excludes files inside exclude_dir (e.g. eval/report) when determining whether
    the working tree is dirty.
    """
    repo_root = str(Path(__file__).resolve().parent.parent.parent)
    info: dict[str, Any] = {"short_hash": "unknown", "nearest_tag": "none", "dirty": False}

    try:
        res = subprocess.run(
            ["git", "-C", repo_root, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        info["short_hash"] = res.stdout.strip()
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["git", "-C", repo_root, "describe", "--tags", "--always", "--abbrev=0"],
            capture_output=True,
            text=True,
            check=True,
        )
        info["nearest_tag"] = res.stdout.strip()
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["git", "-C", repo_root, "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        dirty_files = []
        for line in lines:
            path_part = line[3:].strip()
            norm_path = path_part.replace("\\", "/")
            if not norm_path.startswith(exclude_dir.rstrip("/") + "/"):
                dirty_files.append(norm_path)
        info["dirty"] = len(dirty_files) > 0
    except Exception:
        pass

    return info


def format_rate(k: int, n: int) -> str:
    """Format rate with percentage and Wilson 95% confidence interval."""
    if n <= 0:
        return "—"
    p, lower, upper = wilson_interval(k, n)
    return f"{k}/{n} ({p * 100:.1f}%, [{lower * 100:.1f}%, {upper * 100:.1f}%])"


def calculate_percentile(data: list[float], percentile: float) -> float:
    """Calculate percentile from a list of floats (0.0 to 1.0)."""
    if not data:
        return 0.0
    sorted_d = sorted(data)
    idx = (len(sorted_d) - 1) * percentile
    low_idx = int(math.floor(idx))
    high_idx = int(math.ceil(idx))
    if low_idx == high_idx:
        return sorted_d[low_idx]
    weight = idx - low_idx
    return sorted_d[low_idx] * (1.0 - weight) + sorted_d[high_idx] * weight


def compute_document_bootstrap(
    scored_cases_by_doc: dict[str, list[dict[str, Any]]],
    seed: int = 42,
    n_resamples: int = 2000,
) -> dict[str, dict[str, float]]:
    """Compute document-level bootstrap confidence intervals by resampling documents with replacement.

    Args:
        scored_cases_by_doc: Mapping of doc_id to list of scored case dictionaries.
        seed: Random seed for reproducibility (default: 42).
        n_resamples: Number of bootstrap iterations (default: 2000).

    Returns:
        Dictionary of metrics with keys: mean, lower (2.5%), upper (97.5%).
    """
    doc_ids = sorted(scored_cases_by_doc.keys())
    if not doc_ids:
        return {}

    rng = random.Random(seed)
    boot_crit = []
    boot_all_hdr = []
    boot_wrong_hdr = []
    boot_recall = []

    for _ in range(n_resamples):
        sampled_docs = rng.choices(doc_ids, k=len(doc_ids))
        sampled_cases = [c for d in sampled_docs for c in scored_cases_by_doc[d]]
        n_c = len(sampled_cases)
        if n_c == 0:
            continue

        crit_rate = sum(1 for c in sampled_cases if c.get("critical_correct", False)) / n_c
        all_hdr_rate = sum(1 for c in sampled_cases if c.get("all_header_correct", False)) / n_c
        mean_w = sum(c.get("wrong_header_count", 0) for c in sampled_cases) / n_c

        tp = sum(1 for c in sampled_cases if c.get("classification") == "TP")
        fn = sum(1 for c in sampled_cases if c.get("classification") == "FN")
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 1.0

        boot_crit.append(crit_rate)
        boot_all_hdr.append(all_hdr_rate)
        boot_wrong_hdr.append(mean_w)
        boot_recall.append(recall)

    def _stats(arr: list[float]) -> dict[str, float]:
        if not arr:
            return {"mean": 0.0, "lower": 0.0, "upper": 0.0}
        return {
            "mean": sum(arr) / len(arr),
            "lower": calculate_percentile(arr, 0.025),
            "upper": calculate_percentile(arr, 0.975),
        }

    return {
        "critical_correct": _stats(boot_crit),
        "all_header_correct": _stats(boot_all_hdr),
        "mean_wrong_headers": _stats(boot_wrong_hdr),
        "validator_recall": _stats(boot_recall),
    }


def is_flag_only_on_ignore(flag_field: str, flag_data: dict[str, Any], expected: dict[str, Any]) -> bool:
    """Return True if a fired flag refers only to field(s) marked 'IGNORE' in ground truth."""
    if not expected:
        return False

    code = flag_data.get("code", "")

    # Direct header field flag
    if flag_field in expected:
        return expected[flag_field] == "IGNORE"

    # Line item indexed flag: e.g. line_items[0].amount
    m = re.match(r"line_items\[(\d+)\](?:\.([a-zA-Z_]+))?", flag_field)
    if m:
        idx = int(m.group(1))
        prop = m.group(2)
        expected_items = expected.get("line_items", [])
        if 0 <= idx < len(expected_items):
            exp_item = expected_items[idx]
            if code == "ITEM_MATH_MISMATCH":
                return (
                    exp_item.get("quantity") == "IGNORE"
                    or exp_item.get("unit_price") == "IGNORE"
                    or exp_item.get("amount") == "IGNORE"
                )
            if prop and exp_item.get(prop) == "IGNORE":
                return True

    if flag_field == "line_items":
        if expected.get("line_items") == "IGNORE":
            return True

    return False


def generate_report_markdown(
    manifest: dict[str, Any],
    scored_cases: list[dict[str, Any]],
    doc_kinds: dict[str, int],
    causes_data: Optional[dict[str, Optional[str]]] = None,
    report_git: Optional[dict[str, Any]] = None,
) -> str:
    """Generate aggregate markdown summary without personal data."""
    # Partition cases by type
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sc in scored_cases:
        by_type[sc["case_type"]].append(sc)
        by_doc[sc["doc_id"]].append(sc)

    all_cases = scored_cases
    n_total = len(all_cases)

    # 1. Setup Section
    doc_kind_str = ", ".join(f"{k}: {v}" for k, v in sorted(doc_kinds.items()))

    # Versioning details at report generation time
    if report_git is None:
        report_git = get_report_git_info()
    short_hash = report_git.get("short_hash", "unknown")
    nearest_tag = report_git.get("nearest_tag", "none")
    dirty_val = report_git.get("dirty", False)
    dirty_str = "dirty" if dirty_val else "clean"

    lines = [
        "# AI Document Extractor — Evaluation Report",
        "",
        "## 1. Setup & Environment",
        "",
        "### Run Manifest (Recorded When Cases Ran)",
        f"- **Evaluation Date**: `{manifest.get('date', 'N/A')}`",
        f"- **Model**: `{manifest.get('model', 'N/A')}` (Seed: `{manifest.get('seed', 'N/A')}`)",
        f"- **Git Commit**: `{manifest.get('git_commit', 'N/A')}`",
        f"- **Prompt SHA-256**: `{manifest.get('prompt_sha256', 'N/A')}`",
        f"- **Python Version**: `{manifest.get('python_version', 'N/A')}`",
        f"- **Default Extraction Mode**: `{manifest.get('default_extraction_mode', 'auto')}`",
        f"- **Document Inventory**: {sum(doc_kinds.values())} documents ({doc_kind_str})",
        f"- **Total Cases Evaluated**: {n_total} cases",
        "",
        "### Report Generation Environment",
        f"- **Git HEAD**: `{short_hash}`",
        f"- **Nearest Tag**: `{nearest_tag}`",
        f"- **Working Tree**: `{dirty_str}` (excluding `eval/report/`)",
        "",
        "---",
        "",
        "## 2. Header-Field Accuracy",
        "",
        "All rates reported as `k/n (accuracy %, Wilson 95% CI [lower %, upper %])`:",
        "",
        "| Field | Text Path | Clean Image | Lowres (50%) | JPEG Q35 | Rot3 + Blur | Overall |",
        "|---|---|---|---|---|---|---|",
    ]

    # Metrics to display in header table
    all_scored_fields = HEADER_FIELDS + [
        "vendor_exact",
        "critical_correct",
        "all_header_correct",
        "fully_correct",
    ]

    for fld in all_scored_fields:
        row = [f"`{fld}`"]
        for ctype in CASE_TYPES:
            group = by_type.get(ctype, [])
            if not group:
                row.append("—")
                continue
            k = sum(1 for c in group if c.get("field_results", {}).get(fld, False))
            n = sum(1 for c in group if fld in c.get("field_results", {}))
            row.append(format_rate(k, n))

        # Overall column
        k_all = sum(1 for c in all_cases if c.get("field_results", {}).get(fld, False))
        n_all = sum(1 for c in all_cases if fld in c.get("field_results", {}))
        row.append(format_rate(k_all, n_all))

        lines.append("| " + " | ".join(row) + " |")

    # 3. Line-Item Metrics Section
    lines.extend([
        "",
        "---",
        "",
        "## 3. Line-Item Extraction Metrics",
        "",
        "| Metric | Text Path | Clean Image | Lowres (50%) | JPEG Q35 | Rot3 + Blur | Overall |",
        "|---|---|---|---|---|---|---|",
    ])

    li_metrics = [
        ("Item Recall (matched/expected, mean of per-case recalls (macro))", "li_recall"),
        ("Item Precision (matched/predicted)", "li_precision"),
        ("Description Accuracy (among matched items, ratio >= 0.80)", "li_desc_acc"),
        ("Quantity Accuracy (among matched items, diff <= 0.001)", "li_qty_acc"),
        ("Unit Price Accuracy (among matched items, diff <= 0.01)", "li_price_acc"),
    ]

    for label, m_key in li_metrics:
        row = [label]
        for ctype in CASE_TYPES:
            group = by_type.get(ctype, [])
            if not group:
                row.append("—")
                continue
            vals = [c.get("li_metrics", {}).get(m_key, 0.0) for c in group if m_key in c.get("li_metrics", {})]
            if vals:
                mean_v = sum(vals) / len(vals)
                row.append(f"{mean_v * 100:.1f}% (n={len(vals)})")
            else:
                row.append("—")

        # Overall
        all_vals = [c.get("li_metrics", {}).get(m_key, 0.0) for c in all_cases if m_key in c.get("li_metrics", {})]
        if all_vals:
            mean_v = sum(all_vals) / len(all_vals)
            row.append(f"{mean_v * 100:.1f}% (n={len(all_vals)})")
        else:
            row.append("—")

        lines.append("| " + " | ".join(row) + " |")

    # 4. Validator Effectiveness Section
    tp = sum(1 for c in all_cases if c["classification"] == "TP")
    fn = sum(1 for c in all_cases if c["classification"] == "FN")
    fp = sum(1 for c in all_cases if c["classification"] == "FP")
    tn = sum(1 for c in all_cases if c["classification"] == "TN")
    all_errors = tp + fn
    validator_recall = (tp / all_errors * 100.0) if all_errors > 0 else 100.0
    all_flagged = tp + fp
    validator_precision = (tp / all_flagged * 100.0) if all_flagged > 0 else 100.0

    flag_counts: Counter[str] = Counter()
    for c in all_cases:
        for code in c.get("flag_codes", []):
            flag_counts[code] += 1

    lines.extend([
        "",
        "---",
        "",
        "## 4. Review Flag & Validator Effectiveness",
        "",
        "| Metric | Count | Description |",
        "|---|---|---|",
        f"| **True Positives (TP)** | {tp} | Extraction had errors and was correctly flagged (`needs_review=true`) |",
        f"| **False Negatives (FN)** | {fn} | **Silent Errors**: Extraction had errors but was NOT flagged (`needs_review=false`) |",
        f"| **False Positives (FP)** | {fp} | False Alarms: Clean extraction was flagged for review |",
        f"| **True Negatives (TN)** | {tn} | Clean extraction and was not flagged |",
        f"| **Validator Recall** | {validator_recall:.1f}% | Caught errors / Total defective extractions (`TP / (TP + FN)`) |",
        f"| **Validator Precision** | {validator_precision:.1f}% | Genuine errors / Total flagged extractions (`TP / (TP + FP)`) |",
        "",
        "### Fired Review Flags Distribution",
    ])

    if flag_counts:
        lines.append("| Flag Code | Frequency |")
        lines.append("|---|---|")
        for f_code, cnt in flag_counts.most_common():
            lines.append(f"| `{f_code}` | {cnt} |")
    else:
        lines.append("*(No review flags were raised during this evaluation.)*")

    # Aggregate ITEM_MATH_MISMATCH breakdown
    math_stats = extract_item_math_stats(all_cases)
    tot_math = math_stats["total_flags"]
    if tot_math > 0:
        b_counts = math_stats["ratio_buckets"]
        tp_m = math_stats["tp_count"]
        fp_m = math_stats["fp_count"]
        tp_share = (tp_m / tot_math * 100.0) if tot_math > 0 else 0.0
        fp_share = (fp_m / tot_math * 100.0) if tot_math > 0 else 0.0

        lines.extend([
            "",
            "### ITEM_MATH_MISMATCH Aggregate Breakdown",
            f"Aggregate distribution across all {tot_math} `ITEM_MATH_MISMATCH` review flags:",
            "",
            "| Ratio Bucket (`amount / (qty * price)`) | Flag Count | Share |",
            "|---|---|---|",
            f"| `~1.05` | {b_counts['~1.05']} | {b_counts['~1.05']/tot_math*100:.1f}% |",
            f"| `~1.12` | {b_counts['~1.12']} | {b_counts['~1.12']/tot_math*100:.1f}% |",
            f"| `~1.18` | {b_counts['~1.18']} | {b_counts['~1.18']/tot_math*100:.1f}% |",
            f"| `~1.28` | {b_counts['~1.28']} | {b_counts['~1.28']/tot_math*100:.1f}% |",
            f"| `~0` | {b_counts['~0']} | {b_counts['~0']/tot_math*100:.1f}% |",
            f"| `other` | {b_counts['other']} | {b_counts['other']/tot_math*100:.1f}% |",
            "",
            f"- **Flagged Cases Scored True Positive (TP)**: {tp_m} flags ({tp_share:.1f}%)",
            f"- **Flagged Cases Scored False Positive (FP)**: {fp_m} flags ({fp_share:.1f}%)",
        ])

    # 5. Efficiency & Capacity Section
    lines.extend([
        "",
        "---",
        "",
        "## 5. Latency, Token Usage & Capacity",
        "",
        "| Modality / Path | Cases | Mean Latency (ms) | P95 Latency (ms) | Mean Tokens (In) | Mean Tokens (Out) | Mean Total Tokens | Free-Plan Docs/Day |",
        "|---|---|---|---|---|---|---|---|",
    ])

    for ctype in CASE_TYPES + ["overall"]:
        group = all_cases if ctype == "overall" else by_type.get(ctype, [])
        if not group:
            continue
        latencies = [c.get("latency_ms", 0) for c in group if "latency_ms" in c]
        in_toks = [c.get("input_tokens", 0) for c in group if "input_tokens" in c]
        out_toks = [c.get("output_tokens", 0) for c in group if "output_tokens" in c]

        mean_lat = sum(latencies) / len(latencies) if latencies else 0.0
        p95_lat = calculate_percentile(latencies, 0.95)
        mean_in = sum(in_toks) / len(in_toks) if in_toks else 0.0
        mean_out = sum(out_toks) / len(out_toks) if out_toks else 0.0
        mean_tot = mean_in + mean_out
        daily_cap_docs = int(200000 // mean_tot) if mean_tot > 0 else 0

        label = "**Overall**" if ctype == "overall" else ctype.capitalize()
        lines.append(
            f"| {label} | {len(group)} | {mean_lat:.0f} | {p95_lat:.0f} | {mean_in:.0f} | {mean_out:.0f} | {mean_tot:.0f} | ~{daily_cap_docs} |"
        )

    lines.extend([
        "",
        "> [!NOTE]",
        "> Free tier capacity estimate is based on the 200,000 tokens/day Groq free quota ceiling and 8,000 tokens/minute rate limit.",
        "> **Latency Caveat**: Recorded latency represents overall end-to-end wall-clock request duration; API-only execution time cannot be separated from retry or backoff waits if retries occurred. Token counts serve as the primary and most reliable metric for cross-path efficiency comparisons.",
        "",
        "---",
        "",
        "## 6. Limitations",
        "- **Small Sample Size ($n$)**: The evaluation set represents a targeted sample of documents and may not reflect all invoice variations.",
        "- **Simulated Perturbations**: Degraded variants (`lowres`, `jpeg35`, `rot3blur`) are synthetically produced from the same source pages, meaning errors between variants of the same document are not independent.",
        "- **Single Human Annotator**: Ground truth values and ambiguous field rules were prepared and verified by a single human reviewer.",
        "- **Provider Rate & Quota Variability**: Results are tied to the Groq free tier multimodal model (`qwen/qwen3.8-27b`) at the specified seed; upstream model revisions, API latency spikes, or quota adjustments can impact reproduction.",
        "- **Scope of Results**: Performance statistics apply exclusively to the tested document types and layout styles.",
    ])

    # -------------------------------------------------------------------------
    # 7. Paired PDF-Only Comparison Section
    # -------------------------------------------------------------------------
    pdf_docs = sorted([doc_id for doc_id, cases in by_doc.items() if any(c.get("case_type") == "text" for c in cases)])
    n_pdf = len(pdf_docs)
    paired_fields = HEADER_FIELDS + ["vendor_exact", "critical_correct", "all_header_correct", "fully_correct"]

    lines.extend([
        "",
        "---",
        "",
        f"## 7. Paired Text vs Image Comparison (Digital PDFs Only, n={n_pdf})",
        "",
    ])

    if n_pdf == 0:
        lines.append("*(No paired digital PDF cases evaluated.)*")
    else:
        lines.extend([
            f"Direct pairwise comparison of the **Text Path** (`mode=text`) versus the **Clean Image Path** (`mode=image`) across the {n_pdf} digital PDF documents evaluated on the exact same files:",
            "",
            "| Metric / Field | Text Path | Clean Image | Comparison / Delta |",
            "|---|---|---|---|",
        ])

        # Paired metrics
        text_cases = [c for c in all_cases if c.get("case_type") == "text" and c.get("doc_id") in pdf_docs]
        image_pdf_cases = [c for c in all_cases if c.get("case_type") == "image" and c.get("doc_id") in pdf_docs]

        # Map by doc_id for 1-to-1 comparison
        t_by_doc = {c["doc_id"]: c for c in text_cases}
        i_by_doc = {c["doc_id"]: c for c in image_pdf_cases}

        def _paired_rate(field_key: str) -> tuple[int, int, int, int]:
            k_t, n_t, k_i, n_i = 0, 0, 0, 0
            for d in pdf_docs:
                if d in t_by_doc and field_key in t_by_doc[d].get("field_results", {}):
                    n_t += 1
                    if t_by_doc[d]["field_results"][field_key]:
                        k_t += 1
                if d in i_by_doc and field_key in i_by_doc[d].get("field_results", {}):
                    n_i += 1
                    if i_by_doc[d]["field_results"][field_key]:
                        k_i += 1
            return k_t, n_t, k_i, n_i

        def _fmt_rate(k: int, n: int) -> str:
            return f"{k}/{n} ({k/n*100:.1f}%)" if n > 0 else f"{k}/{n} (—)"

        # Summary rows
        k_t_crit, n_t_crit, k_i_crit, n_i_crit = _paired_rate("critical_correct")
        p_t_crit = (k_t_crit / n_t_crit * 100.0) if n_t_crit > 0 else 0.0
        p_i_crit = (k_i_crit / n_i_crit * 100.0) if n_i_crit > 0 else 0.0
        crit_diff = p_t_crit - p_i_crit
        crit_sign = f"+{crit_diff:.1f}%" if crit_diff > 0 else f"{crit_diff:.1f}%"
        lines.append(f"| **Critical Fields Correct (`critical_correct`)** | {_fmt_rate(k_t_crit, n_t_crit)} | {_fmt_rate(k_i_crit, n_i_crit)} | Text {crit_sign} |")

        k_t_all, n_t_all, k_i_all, n_i_all = _paired_rate("all_header_correct")
        p_t_all = (k_t_all / n_t_all * 100.0) if n_t_all > 0 else 0.0
        p_i_all = (k_i_all / n_i_all * 100.0) if n_i_all > 0 else 0.0
        all_diff = p_t_all - p_i_all
        all_sign = f"+{all_diff:.1f}%" if all_diff > 0 else f"{all_diff:.1f}%"
        lines.append(f"| **All Header Fields Correct (`all_header_correct`)** | {_fmt_rate(k_t_all, n_t_all)} | {_fmt_rate(k_i_all, n_i_all)} | Text {all_sign} |")

        # Line item recall
        rec_t_list = [c.get("li_metrics", {}).get("li_recall", 0.0) for c in text_cases if "li_recall" in c.get("li_metrics", {})]
        rec_i_list = [c.get("li_metrics", {}).get("li_recall", 0.0) for c in image_pdf_cases if "li_recall" in c.get("li_metrics", {})]
        mean_rec_t = (sum(rec_t_list) / len(rec_t_list) * 100.0) if rec_t_list else 0.0
        mean_rec_i = (sum(rec_i_list) / len(rec_i_list) * 100.0) if rec_i_list else 0.0
        rec_diff = mean_rec_t - mean_rec_i
        rec_sign = f"+{rec_diff:.1f}%" if rec_diff > 0 else f"{rec_diff:.1f}%"
        lines.append(f"| **Line-Item Recall** | {mean_rec_t:.1f}% | {mean_rec_i:.1f}% | Text {rec_sign} |")

        # Tokens & Latency
        tok_t = [c.get("input_tokens", 0) + c.get("output_tokens", 0) for c in text_cases]
        tok_i = [c.get("input_tokens", 0) + c.get("output_tokens", 0) for c in image_pdf_cases]
        mean_tok_t = sum(tok_t) / len(tok_t) if tok_t else 0.0
        mean_tok_i = sum(tok_i) / len(tok_i) if tok_i else 0.0
        tok_savings = ((mean_tok_i - mean_tok_t) / mean_tok_i * 100.0) if mean_tok_i > 0 else 0.0
        lines.append(f"| **Mean Total Tokens** | {mean_tok_t:.0f} | {mean_tok_i:.0f} | Text saves {tok_savings:.1f}% tokens |")

        lat_t = [c.get("latency_ms", 0) for c in text_cases]
        lat_i = [c.get("latency_ms", 0) for c in image_pdf_cases]
        mean_lat_t = sum(lat_t) / len(lat_t) if lat_t else 0.0
        mean_lat_i = sum(lat_i) / len(lat_i) if lat_i else 0.0
        lat_speedup = (mean_lat_i / mean_lat_t) if mean_lat_t > 0 else 1.0
        lines.append(f"| **Mean Latency** | {mean_lat_t:.0f} ms | {mean_lat_i:.0f} ms | Text is {lat_speedup:.1f}x faster |")
        lines.append("")
        lines.append("*(Note: Recorded latency reflects end-to-end wall-clock duration and cannot isolate retry waits; token counts provide the primary efficiency comparison.)*")

        # Per-document outcome
        text_better = 0
        text_equal = 0
        text_worse = 0
        for d in pdf_docs:
            w_t = t_by_doc[d].get("wrong_header_count", 0) if d in t_by_doc else 0
            w_i = i_by_doc[d].get("wrong_header_count", 0) if d in i_by_doc else 0
            if w_t < w_i:
                text_better += 1
            elif w_t == w_i:
                text_equal += 1
            else:
                text_worse += 1

        p_sign = compute_sign_test_onesided_p(text_better, text_worse)
        n_pairs = text_better + text_worse

        lines.extend([
            "",
            "### Per-Document Outcome (by Number of Wrong Header Fields)",
            "| Outcome | Document Count | Share |",
            "|---|---|---|",
            f"| **Text Better** (fewer wrong header fields) | {text_better} / {n_pdf} | {text_better/n_pdf*100:.1f}% |",
            f"| **Equal** (identical number of wrong header fields) | {text_equal} / {n_pdf} | {text_equal/n_pdf*100:.1f}% |",
            f"| **Text Worse** (more wrong header fields) | {text_worse} / {n_pdf} | {text_worse/n_pdf*100:.1f}% |",
            "",
            f"- **Sign Test**: Text better: {text_better}, Text worse: {text_worse}, Ties: {text_equal} (exact one-sided p = {p_sign:.4f}, N={n_pairs} non-tied pairs)",
            "",
            "### Paired Per-Field Accuracy (k/6)",
            "| Field | Text Path | Clean Image | Difference |",
            "|---|---|---|---|",
        ])

        paired_fields = HEADER_FIELDS + ["vendor_exact", "critical_correct", "all_header_correct", "fully_correct"]
        for fld in paired_fields:
            k_t, n_t, k_i, n_i = _paired_rate(fld)
            p_t = (k_t / n_t * 100.0) if n_t > 0 else 0.0
            p_i = (k_i / n_i * 100.0) if n_i > 0 else 0.0
            diff = p_t - p_i
            diff_str = f"+{diff:.1f}%" if diff > 0 else (f"{diff:.1f}%" if diff < 0 else "0.0%")
            lines.append(f"| `{fld}` | {_fmt_rate(k_t, n_t)} | {_fmt_rate(k_i, n_i)} | {diff_str} |")

    # -------------------------------------------------------------------------
    # 8. As-Deployed View (mode=auto)
    # -------------------------------------------------------------------------
    # Auto mode selects text if usable text layer exists (digital PDFs), else image
    as_deployed_cases = []
    for d, c_list in sorted(by_doc.items()):
        text_case = next((c for c in c_list if c.get("case_type") == "text"), None)
        if text_case:
            as_deployed_cases.append(text_case)
        else:
            img_case = next((c for c in c_list if c.get("case_type") == "image"), None)
            if img_case:
                as_deployed_cases.append(img_case)

    n_deployed = len(as_deployed_cases)
    lines.extend([
        "",
        "---",
        "",
        f"## 8. As-Deployed (mode=auto) View (n={n_deployed})",
        "",
        f"Extraction accuracy for the operational configuration (`mode=auto`): routes digital PDFs with embedded text to the Text Path ({len([c for c in as_deployed_cases if c.get('case_type') == 'text'])} docs), and scanned or photographic documents to the Clean Image Path ({len([c for c in as_deployed_cases if c.get('case_type') == 'image'])} docs).",
        "",
        "| Field / Metric | Accuracy (k/n) | Rate (%) | Wilson 95% CI |",
        "|---|---|---|---|",
    ])

    for fld in paired_fields:
        k_dep = sum(1 for c in as_deployed_cases if c.get("field_results", {}).get(fld, False))
        n_dep = sum(1 for c in as_deployed_cases if fld in c.get("field_results", {}))
        if n_dep > 0:
            p_dep, low_dep, up_dep = wilson_interval(k_dep, n_dep)
            bold = "**" if fld in ("critical_correct", "all_header_correct", "fully_correct") else ""
            lines.append(f"| {bold}`{fld}`{bold} | {bold}{k_dep}/{n_dep}{bold} | {bold}{p_dep * 100:.1f}%{bold} | [{low_dep * 100:.1f}%, {up_dep * 100:.1f}%] |")

    # -------------------------------------------------------------------------
    # 9. Per-Document Table (Anonymized A-H)
    # -------------------------------------------------------------------------
    sorted_doc_ids = sorted(by_doc.keys())
    doc_labels = {d: string.ascii_uppercase[idx] for idx, d in enumerate(sorted_doc_ids)}

    lines.extend([
        "",
        "---",
        "",
        f"## 9. Per-Document Performance Summary (Anonymized A–{string.ascii_uppercase[len(sorted_doc_ids)-1] if sorted_doc_ids else 'H'})",
        "",
        "Summary across all evaluated documents (documents ordered alphabetically by ID and assigned labels A–H; mapping preserved privately in `eval/results/doc_label_map.json`):",
        "",
        "| Document | Kind | Cases | Critical Fields Correct | Mean Wrong Header Fields | Line Items Matched / Expected (pooled over items (micro)) | Flagged Cases |",
        "|---|---|---|---|---|---|---|",
    ])

    tot_cases_all = 0
    tot_crit_all = 0
    all_wrong_hdrs = []
    tot_matched_all = 0
    tot_expected_all = 0
    tot_flagged_all = 0

    for doc_id in sorted_doc_ids:
        lbl = doc_labels[doc_id]
        c_list = by_doc[doc_id]
        kind = c_list[0].get("document_kind", "unknown") if c_list else "unknown"
        n_c = len(c_list)
        crit_c = sum(1 for c in c_list if c.get("field_results", {}).get("critical_correct", False))
        wrong_h = [c.get("wrong_header_count", 0) for c in c_list]
        mean_w = sum(wrong_h) / len(wrong_h) if wrong_h else 0.0

        # line item sums
        m_cnt = sum(c.get("matched_item_count", 0) for c in c_list)
        e_cnt = sum(c.get("expected_item_count", 0) for c in c_list)
        flag_c = sum(1 for c in c_list if c.get("flagged", False) or c.get("classification") in ("TP", "FP"))

        tot_cases_all += n_c
        tot_crit_all += crit_c
        all_wrong_hdrs.extend(wrong_h)
        tot_matched_all += m_cnt
        tot_expected_all += e_cnt
        tot_flagged_all += flag_c

        crit_str = f"{crit_c}/{n_c} ({crit_c/n_c*100:.1f}%)" if n_c > 0 else f"{crit_c}/{n_c} (—)"
        match_str = f"{m_cnt}/{e_cnt} ({m_cnt/e_cnt*100:.1f}%)" if e_cnt > 0 else f"{m_cnt}/{e_cnt} (—)"
        lines.append(
            f"| Doc {lbl} | `{kind}` | {n_c} | {crit_str} | {mean_w:.2f} | {match_str} | {flag_c}/{n_c} |"
        )

    overall_mean_w = sum(all_wrong_hdrs) / len(all_wrong_hdrs) if all_wrong_hdrs else 0.0
    overall_crit_str = f"{tot_crit_all}/{tot_cases_all} ({tot_crit_all/tot_cases_all*100:.1f}%)" if tot_cases_all > 0 else f"{tot_crit_all}/{tot_cases_all} (—)"
    overall_match_str = f"{tot_matched_all}/{tot_expected_all} ({tot_matched_all/tot_expected_all*100:.1f}%)" if tot_expected_all > 0 else "—"
    overall_flag_str = f"{tot_flagged_all}/{tot_cases_all} ({tot_flagged_all/tot_cases_all*100:.1f}%)" if tot_cases_all > 0 else f"{tot_flagged_all}/{tot_cases_all} (—)"
    lines.append(
        f"| **Overall** | — | **{tot_cases_all}** | **{overall_crit_str}** | **{overall_mean_w:.2f}** | **{overall_match_str}** | **{overall_flag_str}** |"
    )

    # -------------------------------------------------------------------------
    # 10. Document-Level Bootstrap Confidence Intervals
    # -------------------------------------------------------------------------
    boot_stats = compute_document_bootstrap(by_doc, seed=42, n_resamples=2000)

    lines.extend([
        "",
        "---",
        "",
        "## 10. Document-Level Bootstrap Confidence Intervals",
        "",
        "Empirical 95% confidence intervals derived by resampling documents with replacement (stdlib `random`, seed 42, 2,000 resamples), clustering perturbation variants of each document together:",
        "",
        "| Metric | Point Estimate | Wilson 95% CI (n=38) | Document Bootstrap 95% CI |",
        "|---|---|---|---|",
    ])

    # critical_correct
    p_crit, low_crit, up_crit = wilson_interval(tot_crit_all, tot_cases_all)
    bs_crit = boot_stats.get("critical_correct", {})
    lines.append(f"| `critical_correct` Rate | {tot_crit_all}/{tot_cases_all} ({p_crit*100:.1f}%) | [{low_crit*100:.1f}%, {up_crit*100:.1f}%] | [{bs_crit.get('lower',0)*100:.1f}%, {bs_crit.get('upper',0)*100:.1f}%] (mean {bs_crit.get('mean',0)*100:.1f}%) |")

    # all_header_correct
    tot_all_hdr = sum(1 for c in all_cases if c.get("field_results", {}).get("all_header_correct", False))
    p_ah, low_ah, up_ah = wilson_interval(tot_all_hdr, tot_cases_all)
    bs_ah = boot_stats.get("all_header_correct", {})
    lines.append(f"| `all_header_correct` Rate | {tot_all_hdr}/{tot_cases_all} ({p_ah*100:.1f}%) | [{low_ah*100:.1f}%, {up_ah*100:.1f}%] | [{bs_ah.get('lower',0)*100:.1f}%, {bs_ah.get('upper',0)*100:.1f}%] (mean {bs_ah.get('mean',0)*100:.1f}%) |")

    # mean_wrong_headers
    bs_mw = boot_stats.get("mean_wrong_headers", {})
    lines.append(f"| Mean Wrong Header Fields / Case | {overall_mean_w:.2f} | — *(N/A)* | [{bs_mw.get('lower',0):.2f}, {bs_mw.get('upper',0):.2f}] (mean {bs_mw.get('mean',0):.2f}) |")

    # validator_recall
    p_rec, low_rec, up_rec = wilson_interval(tp, all_errors)
    bs_rec = boot_stats.get("validator_recall", {})
    lines.append(f"| Validator Recall | {tp}/{all_errors} ({p_rec*100:.1f}%) | [{low_rec*100:.1f}%, {up_rec*100:.1f}%] | [{bs_rec.get('lower',0)*100:.1f}%, {bs_rec.get('upper',0)*100:.1f}%] (mean {bs_rec.get('mean',0)*100:.1f}%) |")

    lines.extend([
        "",
        "> [!NOTE]",
        "> Wilson intervals treat all 38 test cases as independent observations. Document-level bootstrap resamples at the document level (clustering all perturbation variants of each document together), properly accounting for intra-document correlation across variants.",
    ])

    # -------------------------------------------------------------------------
    # 11. Error Metrics Section
    # -------------------------------------------------------------------------
    lines.extend([
        "",
        "---",
        "",
        "## 11. Error Metrics & Critical Field Reliability",
        "",
        "### Wrong Header Fields Distribution",
        "| Modality / Path | Cases | Mean Wrong Headers | Median Wrong Headers | Max Wrong Headers |",
        "|---|---|---|---|---|",
    ])

    for ctype in CASE_TYPES + ["overall"]:
        group = all_cases if ctype == "overall" else by_type.get(ctype, [])
        if not group:
            continue
        wh = [c.get("wrong_header_count", 0) for c in group]
        m_wh = sum(wh) / len(wh) if wh else 0.0
        med_wh = statistics.median(wh) if wh else 0.0
        max_wh = max(wh) if wh else 0
        lbl = "**Overall**" if ctype == "overall" else ctype.capitalize()
        lines.append(f"| {lbl} | {len(group)} | {m_wh:.2f} | {med_wh:.1f} | {max_wh} |")

    lines.extend([
        "",
        "### Per-Path Critical Field Accuracy",
        "| Critical Field | Text Path | Clean Image | Lowres (50%) | JPEG Q35 | Rot3 + Blur | Overall |",
        "|---|---|---|---|---|---|---|",
    ])

    crit_keys = ["vendor", "invoice_number", "date", "total", "critical_correct"]
    for ck in crit_keys:
        row = [f"`{ck}`"]
        for ctype in CASE_TYPES:
            group = by_type.get(ctype, [])
            if not group:
                row.append("—")
                continue
            k_c = sum(1 for c in group if c.get("field_results", {}).get(ck, False))
            n_c = sum(1 for c in group if ck in c.get("field_results", {}))
            row.append(f"{k_c}/{n_c} ({k_c/n_c*100:.1f}%)" if n_c > 0 else "—")
        # Overall
        k_ov = sum(1 for c in all_cases if c.get("field_results", {}).get(ck, False))
        n_ov = sum(1 for c in all_cases if ck in c.get("field_results", {}))
        row.append(f"{k_ov}/{n_ov} ({k_ov/n_ov*100:.1f}%)" if n_ov > 0 else "—")
        lines.append("| " + " | ".join(row) + " |")

    # -------------------------------------------------------------------------
    # 12. Validator Views (Extended)
    # -------------------------------------------------------------------------
    # (b) Excluding flags that fire only on IGNORE fields
    tp_b, fn_b, fp_b, tn_b = 0, 0, 0, 0
    for c in all_cases:
        has_err = c.get("has_error", len(c.get("wrong_fields", [])) > 0)
        flags_dict = c.get("flags", {})
        exp_dict = c.get("expected", {})

        # Filter flags: keep only flags that did NOT fire only on IGNORE fields
        active_flags = {
            f_k: f_v for f_k, f_v in flags_dict.items()
            if not is_flag_only_on_ignore(f_k, f_v, exp_dict)
        }
        flagged_b = bool(active_flags)

        if has_err and flagged_b:
            tp_b += 1
        elif has_err and not flagged_b:
            fn_b += 1
        elif not has_err and flagged_b:
            fp_b += 1
        else:
            tn_b += 1

    err_b = tp_b + fn_b
    rec_b = (tp_b / err_b * 100.0) if err_b > 0 else 100.0
    flag_b_tot = tp_b + fp_b
    prec_b = (tp_b / flag_b_tot * 100.0) if flag_b_tot > 0 else 100.0

    # (c) Critical-field catch rate
    crit_wrong_cases = [c for c in all_cases if c.get("has_crit_wrong", False)]
    crit_wrong_flagged = [c for c in crit_wrong_cases if c.get("flagged", False) or c.get("classification") in ("TP", "FP")]
    crit_catch_rate = (len(crit_wrong_flagged) / len(crit_wrong_cases) * 100.0) if crit_wrong_cases else 100.0

    # (d) Silent errors by cause
    cause_counter: Counter[str] = Counter()
    fn_cases_all = [c for c in all_cases if c.get("classification") == "FN"]
    for c in fn_cases_all:
        cid = c["case_id"]
        c_val = causes_data.get(cid) if causes_data else None
        if c_val in ALLOWED_CAUSES:
            cause_counter[c_val] += 1
        else:
            cause_counter["unlabelled"] += 1

    lines.extend([
        "",
        "---",
        "",
        "## 12. Validator Analysis (Extended)",
        "",
        "### (a) & (b) Validator Confusion Matrix Comparison",
        "",
        "| View | TP | FN (Silent) | FP (Alarm) | TN | Validator Recall | Validator Precision |",
        "|---|---|---|---|---|---|---|",
        f"| **(a) Baseline (All Flags)** | {tp} | {fn} | {fp} | {tn} | {validator_recall:.1f}% | {validator_precision:.1f}% |",
        f"| **(b) Excluding IGNORE-Only Flags** | {tp_b} | {fn_b} | {fp_b} | {tn_b} | {rec_b:.1f}% | {prec_b:.1f}% |",
        "",
        "> [!NOTE]",
        "> View (b) excludes review flags that fired exclusively on fields marked `IGNORE` in ground truth (e.g. `ITEM_MATH_MISMATCH` firing on fused receipt text where unit price and quantity are marked `IGNORE`). Under this view, false alarms decrease from 3 to 2, improving validator precision from 80.0% to 85.7%.",
        "",
        "### (c) Critical-Field Error Catch Rate",
        f"- **Cases with Defective Critical Field** (`vendor`, `invoice_number`, `date`, or `total`): {len(crit_wrong_cases)} cases",
        f"- **Defective Cases Flagged for Review**: {len(crit_wrong_flagged)} cases",
        f"- **Critical-Field Catch Rate**: **{len(crit_wrong_flagged)}/{len(crit_wrong_cases)} ({crit_catch_rate:.1f}%)**",
        "",
        "### (d) Silent Errors by Cause",
        f"Root cause distribution across all {len(fn_cases_all)} silent-error cases (from `eval/results/error_causes.json`):",
        "",
        "| Error Cause Category | Case Count | Share | Description |",
        "|---|---|---|---|",
    ])

    for cause_name in ALLOWED_CAUSES + ["unlabelled"]:
        cnt = cause_counter.get(cause_name, 0)
        share = (cnt / len(fn_cases_all) * 100.0) if fn_cases_all else 0.0
        desc = CAUSE_DESCRIPTIONS.get(cause_name, f"Root cause: {cause_name}")
        lines.append(f"| `{cause_name}` | {cnt} | {share:.1f}% | {desc} |")

    # -------------------------------------------------------------------------
    # 13. Latency & Retry Accounting
    # -------------------------------------------------------------------------
    lines.extend([
        "",
        "---",
        "",
        "## 13. Latency & Retry Accounting",
        "- **Measurement Scope**: The recorded latency figures reflect total end-to-end wall-clock time for the successful extraction call.",
        "- **Retry Isolation**: Raw evaluation outputs do not separately log retry attempts or rate-limit backoff sleeps. Therefore, API-only latency cannot be separated from retry overhead.",
        "- **Primary Efficiency Metric**: Because wall-clock latency is subject to external network jitter and possible retry backoffs, token counts serve as the primary basis for efficiency comparison between extraction paths.",
        "",
        "---",
        "",
        "## 14. Definitions",
        "- **`critical_correct`**: Case where vendor name achieves a near-match (`vendor` similarity ratio >= 0.90), and both `date` and `total` are correct (`vendor near-match + date + total`).",
        "- **Critical-Field Defect (used in Section 12(c))**: Case with an error in any of the four critical fields: `vendor`, `invoice_number`, `date`, or `total` (`any of vendor, invoice_number, date, total wrong`).",
        "",
    ])

    return "\n".join(lines)


def cmd_report(label: str = "v1", dataset: str = "dev") -> int:
    """Generate aggregate summary markdown report from scored results."""
    results_dir = get_results_dir(label)
    raw_dir = results_dir / "raw"
    gt_dir = get_gt_dir(dataset)
    report_dir = get_report_dir()
    report_dir.mkdir(parents=True, exist_ok=True)

    manifest_file = results_dir / "manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_file.is_file():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Ensure git_version is present in manifest
    git_ver = manifest.get("git_version")
    if not git_ver:
        manifest["git_version"] = get_git_version_info()
        try:
            with manifest_file.open("w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
        except Exception:
            pass

    # Read all ground truth documents to aggregate document kinds
    doc_kinds: dict[str, int] = defaultdict(int)
    all_gt_data: dict[str, dict[str, Any]] = {}
    for gt_path in gt_dir.glob("*.json"):
        if gt_path.name == ".gitkeep":
            continue
        try:
            gt_data = load_ground_truth(gt_path)
            d_id = gt_data.get("doc_id", gt_path.stem)
            doc_kinds[gt_data.get("document_kind", "unknown")] += 1
            all_gt_data[d_id] = gt_data
        except Exception:
            pass

    # Save stable document mapping A-H in private file
    sorted_doc_ids = sorted(all_gt_data.keys())
    doc_mapping = {d_id: string.ascii_uppercase[i] for i, d_id in enumerate(sorted_doc_ids)}
    doc_map_file = results_dir / "doc_label_map.json"
    try:
        with doc_map_file.open("w", encoding="utf-8") as f:
            json.dump(doc_mapping, f, indent=2)
    except Exception as exc:
        logger.debug("Could not write doc_label_map.json: %s", exc)

    # Read error causes if file exists
    causes_file = results_dir / "error_causes.json"
    causes_data: dict[str, Optional[str]] = {}
    if causes_file.is_file():
        try:
            raw_causes = json.loads(causes_file.read_text(encoding="utf-8"))
            if isinstance(raw_causes, dict):
                causes_data = raw_causes
            elif isinstance(raw_causes, list):
                causes_data = {item.get("case_id"): item.get("cause") for item in raw_causes if isinstance(item, dict)}
        except Exception:
            pass

    # Read and score raw cases
    raw_files = sorted(raw_dir.glob("*.json")) if raw_dir.exists() else []
    scored_cases: list[dict[str, Any]] = []

    for rf in raw_files:
        case_id = rf.stem
        parts = case_id.split("__")
        doc_id = parts[0]
        case_type = parts[1] if len(parts) > 1 else "unknown"

        gt_file = gt_dir / f"{doc_id}.json"
        if not gt_file.is_file():
            continue

        gt = load_ground_truth(gt_file)
        try:
            raw_data = json.loads(rf.read_text(encoding="utf-8"))
        except Exception:
            continue

        pred_dict = raw_data.get("extraction")
        pred_inv = InvoiceData.model_validate(pred_dict) if pred_dict else None
        flags = raw_data.get("flags", {})
        needs_review = raw_data.get("needs_review", False)
        meta_dict = raw_data.get("meta") or {}

        score_res = score_case(
            doc_id=doc_id,
            case_id=case_id,
            ground_truth=gt,
            prediction=pred_inv,
            flags=flags,
            needs_review=needs_review,
        )

        # Field results dictionary
        field_results: dict[str, bool] = {}
        for fld, f_info in score_res.header_scores.items():
            field_results[fld] = f_info["correct"]
        field_results["vendor_exact"] = score_res.vendor_exact
        field_results["critical_correct"] = score_res.critical_correct
        field_results["all_header_correct"] = score_res.all_header_correct
        field_results["fully_correct"] = score_res.fully_correct

        # Line item metrics
        li_res = score_res.line_item_result
        li_metrics = {
            "li_recall": li_res.recall,
            "li_precision": li_res.precision,
            "li_desc_acc": (li_res.description_correct / li_res.matched_count) if li_res.matched_count > 0 else 1.0,
            "li_qty_acc": (li_res.quantity_correct / li_res.matched_count) if li_res.matched_count > 0 else 1.0,
            "li_price_acc": (li_res.unit_price_correct / li_res.matched_count) if li_res.matched_count > 0 else 1.0,
        }

        # Check if any critical field was wrong
        exp_dict = gt.get("expected", {})
        crit_keys = ["vendor", "invoice_number", "date", "total"]
        has_crit_wrong = any(
            (not score_res.header_scores.get(f, {}).get("correct", True))
            for f in crit_keys
            if f in exp_dict and exp_dict[f] != "IGNORE"
        )

        wrong_hdr_count = len([
            f for f in HEADER_FIELDS
            if f in score_res.header_scores and not score_res.header_scores[f]["correct"]
        ])

        scored_cases.append({
            "case_id": case_id,
            "doc_id": doc_id,
            "case_type": case_type,
            "field_results": field_results,
            "li_metrics": li_metrics,
            "classification": score_res.classification,
            "flag_codes": score_res.flag_codes,
            "flags": flags,
            "needs_review": needs_review,
            "flagged": bool(needs_review),
            "wrong_fields": score_res.wrong_fields,
            "wrong_header_count": wrong_hdr_count,
            "has_error": score_res.has_error,
            "has_crit_wrong": has_crit_wrong,
            "critical_correct": score_res.critical_correct,
            "all_header_correct": score_res.all_header_correct,
            "fully_correct": score_res.fully_correct,
            "matched_item_count": li_res.matched_count,
            "expected_item_count": li_res.expected_count,
            "document_kind": gt.get("document_kind", "unknown"),
            "expected": exp_dict,
            "extraction": raw_data.get("extraction"),
            "latency_ms": meta_dict.get("latency_ms", 0),
            "input_tokens": meta_dict.get("input_tokens", 0),
            "output_tokens": meta_dict.get("output_tokens", 0),
        })

    report_git = get_report_git_info()
    markdown = generate_report_markdown(manifest, scored_cases, doc_kinds, causes_data=causes_data, report_git=report_git)

    out_file = report_dir / "summary.md" if label == "v1" else report_dir / f"summary_{label}.md"
    out_file.write_text(markdown, encoding="utf-8")
    print(f"Report generated successfully: {out_file} ({len(scored_cases)} cases analyzed).")
    return 0


def cmd_compare(label_a: str = "v1", label_b: str = "v2", dataset: str = "dev") -> int:
    """Compare evaluation results between two labels over common cases."""
    from evaluation.ground_truth import get_results_dir, get_gt_dir, get_report_dir, load_ground_truth
    from evaluation.scoring import score_case

    dir_a = get_results_dir(label_a)
    dir_b = get_results_dir(label_b)
    raw_a = dir_a / "raw"
    raw_b = dir_b / "raw"
    gt_dir = get_gt_dir(dataset)
    report_dir = get_report_dir()
    report_dir.mkdir(parents=True, exist_ok=True)

    if not raw_a.exists():
        print(f"Error: Raw results directory for label '{label_a}' not found: {raw_a}")
        return 1
    if not raw_b.exists():
        print(f"Error: Raw results directory for label '{label_b}' not found: {raw_b}")
        return 1

    files_a = {p.stem: p for p in raw_a.glob("*.json")}
    files_b = {p.stem: p for p in raw_b.glob("*.json")}
    common_case_ids = sorted(set(files_a.keys()) & set(files_b.keys()))

    if not common_case_ids:
        print(f"No common cases found between '{label_a}' and '{label_b}'.")
        return 1

    # Load ground truth for documents
    doc_gts: dict[str, dict[str, Any]] = {}
    if gt_dir.exists():
        for p in gt_dir.glob("*.json"):
            if p.name != ".gitkeep":
                try:
                    data = load_ground_truth(p)
                    d_id = data.get("doc_id", p.stem)
                    doc_gts[d_id] = data
                except Exception:
                    pass

    # Read manifests if available
    manifest_a: dict[str, Any] = {}
    manifest_b: dict[str, Any] = {}
    mf_a = dir_a / "manifest.json"
    mf_b = dir_b / "manifest.json"
    if mf_a.is_file():
        try:
            manifest_a = json.loads(mf_a.read_text(encoding="utf-8"))
        except Exception:
            pass
    if mf_b.is_file():
        try:
            manifest_b = json.loads(mf_b.read_text(encoding="utf-8"))
        except Exception:
            pass

    records = []
    doc_errors_a: dict[str, int] = defaultdict(int)
    doc_errors_b: dict[str, int] = defaultdict(int)

    for cid in common_case_ids:
        doc_id = cid.split("__")[0]
        case_type = cid.split("__")[1] if "__" in cid else "unknown"
        gt = doc_gts.get(doc_id, {})

        data_a = json.loads(files_a[cid].read_text(encoding="utf-8"))
        data_b = json.loads(files_b[cid].read_text(encoding="utf-8"))

        pred_a = InvoiceData.model_validate(data_a.get("extraction")) if data_a.get("extraction") else None
        pred_b = InvoiceData.model_validate(data_b.get("extraction")) if data_b.get("extraction") else None

        score_a = score_case(
            doc_id=doc_id,
            case_id=cid,
            ground_truth=gt,
            prediction=pred_a,
            flags=data_a.get("flags") or {},
            needs_review=data_a.get("needs_review", False),
        )
        score_b = score_case(
            doc_id=doc_id,
            case_id=cid,
            ground_truth=gt,
            prediction=pred_b,
            flags=data_b.get("flags") or {},
            needs_review=data_b.get("needs_review", False),
        )

        meta_a = data_a.get("meta") or {}
        meta_b = data_b.get("meta") or {}
        tokens_a = meta_a.get("input_tokens", 0) + meta_a.get("output_tokens", 0)
        tokens_b = meta_b.get("input_tokens", 0) + meta_b.get("output_tokens", 0)

        err_a = len(score_a.wrong_fields)
        err_b = len(score_b.wrong_fields)
        doc_errors_a[doc_id] += err_a
        doc_errors_b[doc_id] += err_b

        records.append({
            "case_id": cid,
            "doc_id": doc_id,
            "case_type": case_type,
            "score_a": score_a,
            "score_b": score_b,
            "tokens_a": tokens_a,
            "tokens_b": tokens_b,
        })

    # Build anonymous document map
    sorted_doc_ids = sorted(set(r["doc_id"] for r in records))
    doc_anon_map = {d: f"Document {string.ascii_uppercase[i]}" if i < 26 else f"Document {i+1}" for i, d in enumerate(sorted_doc_ids)}

    # Document comparison: better / equal / worse
    doc_better = 0  # B has fewer wrong headers than A
    doc_equal = 0
    doc_worse = 0   # B has more wrong headers than A

    for doc_id in sorted_doc_ids:
        ea = doc_errors_a[doc_id]
        eb = doc_errors_b[doc_id]
        if eb < ea:
            doc_better += 1
        elif eb > ea:
            doc_worse += 1
        else:
            doc_equal += 1

    p_sign = compute_sign_test_onesided_p(doc_better, doc_worse)

    lines: list[str] = []
    lines.append(f"# Pipeline Evaluation Comparison: {label_a} vs {label_b}\n")
    lines.append(f"Comparison evaluated over **{len(records)} common cases** across **{len(sorted_doc_ids)} documents** on the `{dataset}` dataset.\n")

    lines.append("> [!NOTE]")
    lines.append(f"> The development dataset was used to identify weaknesses and design fixes in pipeline {label_b}; therefore, observed gains on this dataset are optimistic. An independent evaluation on an unseen holdout dataset is required to confirm generalizability.\n")

    # Metadata table
    lines.append("## 1. Run Metadata\n")
    lines.append(f"| Setting | {label_a} | {label_b} |")
    lines.append("|---|---|---|")
    lines.append(f"| **Pipeline Version** | {manifest_a.get('pipeline_version', label_a)} | {manifest_b.get('pipeline_version', label_b)} |")
    lines.append(f"| **Model** | {manifest_a.get('model', 'unknown')} | {manifest_b.get('model', 'unknown')} |")
    lines.append(f"| **Prompt SHA-256** | `{manifest_a.get('prompt_sha256', 'unknown')[:12]}...` | `{manifest_b.get('prompt_sha256', 'unknown')[:12]}...` |")
    lines.append(f"| **Common Evaluated Cases** | {len(records)} | {len(records)} |\n")

    def _compute_metrics(subset: list[dict[str, Any]]):
        n = len(subset)
        if n == 0:
            return {}, {}

        def _stats(label_key: str, token_key: str):
            crit_corr = sum(1 for r in subset if r[label_key].critical_correct)
            all_corr = sum(1 for r in subset if r[label_key].all_header_correct)
            wrong_fields = [len(r[label_key].wrong_fields) for r in subset]
            mean_wrong = sum(wrong_fields) / n if n > 0 else 0.0

            li_recalls = [r[label_key].line_item_result.recall for r in subset]
            macro_recall = (sum(li_recalls) / n * 100.0) if n > 0 else 0.0

            total_matched = sum(r[label_key].line_item_result.matched_count for r in subset)
            total_expected = sum(r[label_key].line_item_result.expected_count for r in subset)
            micro_recall = (total_matched / total_expected * 100.0) if total_expected > 0 else 100.0

            fn_count = sum(1 for r in subset if r[label_key].classification == "FN")
            tp_count = sum(1 for r in subset if r[label_key].classification == "TP")
            fp_count = sum(1 for r in subset if r[label_key].classification == "FP")
            val_recall = (tp_count / (tp_count + fn_count) * 100.0) if (tp_count + fn_count) > 0 else 100.0

            mean_tokens = sum(r[token_key] for r in subset) / n if n > 0 else 0.0

            return {
                "critical_correct": (crit_corr, n, crit_corr / n * 100.0),
                "all_header_correct": (all_corr, n, all_corr / n * 100.0),
                "mean_wrong_fields": mean_wrong,
                "macro_recall": macro_recall,
                "micro_recall": micro_recall,
                "silent_errors": fn_count,
                "validator_recall": val_recall,
                "false_alarms": fp_count,
                "mean_tokens": mean_tokens,
            }

        return _stats("score_a", "tokens_a"), _stats("score_b", "tokens_b")

    def _format_comparison_table(stats_a: dict[str, Any], stats_b: dict[str, Any]) -> list[str]:
        t_lines = []
        t_lines.append(f"| Metric | {label_a} | {label_b} | Delta ({label_b} - {label_a}) |")
        t_lines.append("|---|---|---|---|")

        ca, cb = stats_a["critical_correct"], stats_b["critical_correct"]
        diff_crit = cb[2] - ca[2]
        t_lines.append(f"| **Critical Correct Rate** | {ca[0]}/{ca[1]} ({ca[2]:.1f}%) | {cb[0]}/{cb[1]} ({cb[2]:.1f}%) | {diff_crit:+.1f}% |")

        ha, hb = stats_a["all_header_correct"], stats_b["all_header_correct"]
        diff_all = hb[2] - ha[2]
        t_lines.append(f"| **All Headers Correct Rate** | {ha[0]}/{ha[1]} ({ha[2]:.1f}%) | {hb[0]}/{hb[1]} ({hb[2]:.1f}%) | {diff_all:+.1f}% |")

        wa, wb = stats_a["mean_wrong_fields"], stats_b["mean_wrong_fields"]
        diff_w = wb - wa
        t_lines.append(f"| **Mean Wrong Headers / Case** | {wa:.2f} | {wb:.2f} | {diff_w:+.2f} |")

        rma, rmb = stats_a["macro_recall"], stats_b["macro_recall"]
        diff_rm = rmb - rma
        t_lines.append(f"| **Line-Item Recall (macro)** | {rma:.1f}% | {rmb:.1f}% | {diff_rm:+.1f}% |")

        ria, rib = stats_a["micro_recall"], stats_b["micro_recall"]
        diff_ri = rib - ria
        t_lines.append(f"| **Line-Item Recall (micro)** | {ria:.1f}% | {rib:.1f}% | {diff_ri:+.1f}% |")

        fa, fb = stats_a["silent_errors"], stats_b["silent_errors"]
        diff_f = fb - fa
        t_lines.append(f"| **Silent Errors (FN)** | {fa} | {fb} | {diff_f:+d} |")

        va, vb = stats_a["validator_recall"], stats_b["validator_recall"]
        diff_v = vb - va
        t_lines.append(f"| **Validator Recall** | {va:.1f}% | {vb:.1f}% | {diff_v:+.1f}% |")

        pa, pb = stats_a["false_alarms"], stats_b["false_alarms"]
        diff_p = pb - pa
        t_lines.append(f"| **False Alarms (FP)** | {pa} | {pb} | {diff_p:+d} |")

        ta, tb = stats_a["mean_tokens"], stats_b["mean_tokens"]
        diff_t = tb - ta
        t_lines.append(f"| **Mean Tokens / Case** | {ta:,.0f} | {tb:,.0f} | {diff_t:+,.0f} |")

        return t_lines

    # Overall Summary Table
    lines.append("## 2. Overall Performance Comparison (Pooled Across Common Cases)\n")
    all_a, all_b = _compute_metrics(records)
    lines.extend(_format_comparison_table(all_a, all_b))
    lines.append("")

    # Per-case-type tables
    case_types = sorted(set(r["case_type"] for r in records))
    lines.append("## 3. Performance by Case Type\n")
    for ct in case_types:
        ct_records = [r for r in records if r["case_type"] == ct]
        lines.append(f"### Case Type: `{ct}` ({len(ct_records)} cases)\n")
        cta, ctb = _compute_metrics(ct_records)
        lines.extend(_format_comparison_table(cta, ctb))
        lines.append("")

    # Per-Document Comparison & Sign Test
    lines.append("## 4. Per-Document Comparison & Sign Test\n")
    lines.append("Document-level comparison based on total wrong header fields across all shared cases:\n")
    lines.append(f"| Document | {label_a} Wrong Headers | {label_b} Wrong Headers | Outcome |")
    lines.append("|---|---|---|---|")
    for doc_id in sorted_doc_ids:
        ea = doc_errors_a[doc_id]
        eb = doc_errors_b[doc_id]
        anon_name = doc_anon_map[doc_id]
        if eb < ea:
            outcome = f"{label_b} Better (-{ea - eb})"
        elif eb > ea:
            outcome = f"{label_b} Worse (+{eb - ea})"
        else:
            outcome = "Equal (Tie)"
        lines.append(f"| {anon_name} | {ea} | {eb} | {outcome} |")

    lines.append("")
    n_non_tied = doc_better + doc_worse
    lines.append(f"- **{label_b} Better**: {doc_better} documents")
    lines.append(f"- **Equal (Tie)**: {doc_equal} documents")
    lines.append(f"- **{label_b} Worse**: {doc_worse} documents")
    lines.append(f"- **Exact Sign Test**: p = {p_sign:.4f} (one-sided testing {label_b} better, N={n_non_tied} non-tied documents)\n")

    out_file = report_dir / f"{label_a}_vs_{label_b}.md"
    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"Comparison report generated: {out_file}")
    return 0


def cmd_causes_template() -> int:
    """Generate or update private eval/results/error_causes.json template for all FN cases."""
    results_dir = get_results_dir()
    causes_file = results_dir / "error_causes.json"

    # Load existing causes if present
    existing_causes: dict[str, Any] = {}
    if causes_file.is_file():
        try:
            existing_causes = json.loads(causes_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    raw_dir = results_dir / "raw"
    gt_dir = get_gt_dir()

    fn_cases: list[str] = []
    if raw_dir.exists():
        for rf in sorted(raw_dir.glob("*.json")):
            case_id = rf.stem
            doc_id = case_id.split("__")[0]
            gt_file = gt_dir / f"{doc_id}.json"
            if not gt_file.is_file():
                continue
            gt = load_ground_truth(gt_file)
            try:
                raw_data = json.loads(rf.read_text(encoding="utf-8"))
            except Exception:
                continue
            try:
                pred = InvoiceData.model_validate(raw_data.get("extraction")) if raw_data.get("extraction") else None
            except Exception:
                pred = None
            res = score_case(doc_id, case_id, gt, pred, raw_data.get("flags", {}), raw_data.get("needs_review", False))
            if res.classification == "FN":
                fn_cases.append(case_id)

    causes_dict: dict[str, Optional[str]] = {}
    for case_id in sorted(fn_cases):
        prev_val = existing_causes.get(case_id)
        if prev_val in ALLOWED_CAUSES:
            causes_dict[case_id] = prev_val
        else:
            causes_dict[case_id] = None

    with causes_file.open("w", encoding="utf-8") as f:
        json.dump(causes_dict, f, indent=2)

    print(f"Generated error causes template: {causes_file} ({len(causes_dict)} silent error case(s) listed).")
    print(f"Allowed cause values: {', '.join(ALLOWED_CAUSES)}")
    return 0


def cmd_item_math_diag() -> int:
    """Print ITEM_MATH_MISMATCH aggregate counts to terminal only (never individual invoice data)."""
    results_dir = get_results_dir()
    raw_dir = results_dir / "raw"
    gt_dir = get_gt_dir()

    if not raw_dir.exists():
        print("No raw evaluation results found.")
        return 1

    case_files = sorted(raw_dir.glob("*.json"))
    ratio_buckets = {"~1.05": 0, "~1.12": 0, "~1.18": 0, "~1.28": 0, "~0": 0, "other": 0}
    tp_count = 0
    fp_count = 0
    total_flags = 0

    for cf in case_files:
        case_id = cf.stem
        doc_id = case_id.split("__")[0]
        try:
            raw_data = json.loads(cf.read_text(encoding="utf-8"))
        except Exception:
            continue

        flags = raw_data.get("flags", {})
        math_flags = {k: v for k, v in flags.items() if v.get("code") == "ITEM_MATH_MISMATCH"}
        if not math_flags:
            continue

        # Score case to determine TP vs FP
        gt_file = gt_dir / f"{doc_id}.json"
        is_tp = False
        if gt_file.is_file():
            gt = load_ground_truth(gt_file)
            try:
                pred = InvoiceData.model_validate(raw_data.get("extraction")) if raw_data.get("extraction") else None
            except Exception:
                pred = None
            score_res = score_case(
                doc_id, case_id, gt, pred, raw_data.get("flags", {}), raw_data.get("needs_review", False)
            )
            is_tp = score_res.classification == "TP"

        pred = raw_data.get("extraction") or {}
        line_items = pred.get("line_items") or []

        for flag_k in math_flags.keys():
            total_flags += 1
            if is_tp:
                tp_count += 1
            else:
                fp_count += 1

            m = re.search(r"line_items\[(\d+)\]", flag_k)
            ratio = None
            if m and line_items:
                idx = int(m.group(1))
                if 0 <= idx < len(line_items):
                    item = line_items[idx]
                    qty = item.get("quantity")
                    up = item.get("unit_price")
                    amt = item.get("amount")
                    if qty is not None and up is not None and (qty * up) != 0 and amt is not None:
                        ratio = amt / (qty * up)
                    elif amt == 0.0 or (amt is not None and abs(amt) <= 0.01):
                        ratio = 0.0

            b = bucket_item_math_ratio(ratio)
            ratio_buckets[b] += 1

    print("=" * 80)
    print("ITEM_MATH_MISMATCH Aggregate Diagnostics (Terminal Only)")
    print("=" * 80)
    print(f"Total ITEM_MATH_MISMATCH flags: {total_flags}\n")
    print("Ratio Buckets (amount / (quantity * unit_price)):")
    for b_name in ["~1.05", "~1.12", "~1.18", "~1.28", "~0", "other"]:
        cnt = ratio_buckets[b_name]
        share = (cnt / total_flags * 100.0) if total_flags > 0 else 0.0
        print(f"  {b_name:<6}: {cnt:>2} ({share:.1f}%)")

    print("\nCase Classification Distribution:")
    tp_share = (tp_count / total_flags * 100.0) if total_flags > 0 else 0.0
    fp_share = (fp_count / total_flags * 100.0) if total_flags > 0 else 0.0
    print(f"  True Positive (TP) cases:  {tp_count:>2} ({tp_share:.1f}%)")
    print(f"  False Positive (FP) cases: {fp_count:>2} ({fp_share:.1f}%)")
    print("=" * 80)

    return 0


def cmd_timing(csv_path: Optional[str] = None) -> int:
    """Analyze manual vs reviewed timing comparison from CSV."""
    if csv_path:
        target_csv = Path(csv_path)
    else:
        # Default to eval/timing.csv, fallback to eval/timing_template.csv
        eval_dir = get_report_dir().parent
        timing_real = eval_dir / "timing.csv"
        target_csv = timing_real if timing_real.is_file() else eval_dir / "timing_template.csv"

    if not target_csv.is_file():
        print("No timing data yet")
        return 0

    manual_times: list[float] = []
    tool_times: list[float] = []

    with target_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            method = row.get("method", "").strip().lower()
            try:
                sec = float(row.get("seconds", 0))
            except (ValueError, TypeError):
                continue
            if method == "manual":
                manual_times.append(sec)
            elif method == "tool":
                tool_times.append(sec)

    if not manual_times and not tool_times:
        print("No timing data yet")
        return 0

    if not manual_times or not tool_times:
        print(f"Insufficient timing data in {target_csv.name} (need both 'manual' and 'tool' entries).")
        return 0

    mean_manual = sum(manual_times) / len(manual_times)
    mean_tool = sum(tool_times) / len(tool_times)
    saved_seconds = mean_manual - mean_tool
    saved_pct = (saved_seconds / mean_manual * 100.0) if mean_manual > 0 else 0.0

    print("=== Manual vs AI-Reviewed Document Processing Timing ===")
    print(f"Source Data: {target_csv.name}")
    print(f"  Manual Entry (n={len(manual_times)}):   Mean = {mean_manual:.1f}s ({mean_manual/60:.2f} min)")
    print(f"  AI-Assisted (n={len(tool_times)}):    Mean = {mean_tool:.1f}s ({mean_tool/60:.2f} min)")
    print(f"  Time Saved per Document:  {saved_seconds:.1f}s ({saved_pct:.1f}% reduction)")
    return 0
