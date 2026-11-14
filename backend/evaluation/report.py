"""Aggregate report generation and manual timing comparison."""

import csv
import json
import logging
import math
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

logger = logging.getLogger("evaluation.report")

CASE_TYPES = ["text", "image", "lowres", "jpeg35", "rot3blur"]


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


def generate_report_markdown(
    manifest: dict[str, Any],
    scored_cases: list[dict[str, Any]],
    doc_kinds: dict[str, int],
) -> str:
    """Generate aggregate markdown summary without personal data."""
    # Partition cases by type
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sc in scored_cases:
        by_type[sc["case_type"]].append(sc)

    all_cases = scored_cases
    n_total = len(all_cases)

    # 1. Setup Section
    doc_kind_str = ", ".join(f"{k}: {v}" for k, v in sorted(doc_kinds.items()))
    lines = [
        "# AI Document Extractor — Evaluation Report",
        "",
        "## 1. Setup & Environment",
        f"- **Evaluation Date**: `{manifest.get('date', 'N/A')}`",
        f"- **Model**: `{manifest.get('model', 'N/A')}` (Seed: `{manifest.get('seed', 'N/A')}`)",
        f"- **Git Commit**: `{manifest.get('git_commit', 'N/A')}`",
        f"- **Prompt SHA-256**: `{manifest.get('prompt_sha256', 'N/A')}`",
        f"- **Python Version**: `{manifest.get('python_version', 'N/A')}`",
        f"- **Default Extraction Mode**: `{manifest.get('default_extraction_mode', 'auto')}`",
        f"- **Document Inventory**: {sum(doc_kinds.values())} documents ({doc_kind_str})",
        f"- **Total Cases Evaluated**: {n_total} cases",
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
        ("Item Recall (matched/expected)", "li_recall"),
        ("Item Precision (matched/predicted)", "li_precision"),
        ("Description Accuracy (ratio >= 0.80)", "li_desc_acc"),
        ("Quantity Accuracy (diff <= 0.001)", "li_qty_acc"),
        ("Unit Price Accuracy (diff <= 0.01)", "li_price_acc"),
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
    # Counts across all cases
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
        "",
        "---",
        "",
        "## 6. Limitations",
        "- **Small Sample Size ($n$)**: The evaluation set represents a targeted sample of documents and may not reflect all invoice variations.",
        "- **Simulated Perturbations**: Degraded variants (`lowres`, `jpeg35`, `rot3blur`) are synthetically produced from the same source pages, meaning errors between variants of the same document are not independent.",
        "- **Single Human Annotator**: Ground truth values and ambiguous field rules were prepared and verified by a single human reviewer.",
        "- **Provider Rate & Quota Variability**: Results are tied to the Groq free tier multimodal model (`qwen/qwen3.8-27b`) at the specified seed; upstream model revisions, API latency spikes, or quota adjustments can impact reproduction.",
        "- **Scope of Results**: Performance statistics apply exclusively to the tested document types and layout styles.",
        "",
    ])

    return "\n".join(lines)


def cmd_report() -> int:
    """Generate aggregate summary markdown report from scored results."""
    results_dir = get_results_dir()
    raw_dir = results_dir / "raw"
    gt_dir = get_gt_dir()
    report_dir = get_report_dir()
    report_dir.mkdir(parents=True, exist_ok=True)

    manifest_file = results_dir / "manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_file.is_file():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Read all ground truth documents to aggregate document kinds
    doc_kinds: dict[str, int] = defaultdict(int)
    for gt_path in gt_dir.glob("*.json"):
        if gt_path.name == ".gitkeep":
            continue
        try:
            gt_data = load_ground_truth(gt_path)
            doc_kinds[gt_data.get("document_kind", "unknown")] += 1
        except Exception:
            pass

    # Read and score raw cases
    raw_files = sorted(raw_dir.glob("*.json")) if raw_dir.exists() else []
    scored_cases: list[dict[str, Any]] = []

    for rf in raw_files:
        case_id = rf.stem
        # parse case_id: <doc_id>__<case_type>
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

        scored_cases.append({
            "case_id": case_id,
            "doc_id": doc_id,
            "case_type": case_type,
            "field_results": field_results,
            "li_metrics": li_metrics,
            "classification": score_res.classification,
            "flag_codes": score_res.flag_codes,
            "latency_ms": meta_dict.get("latency_ms", 0),
            "input_tokens": meta_dict.get("input_tokens", 0),
            "output_tokens": meta_dict.get("output_tokens", 0),
        })

    markdown = generate_report_markdown(manifest, scored_cases, doc_kinds)

    out_file = report_dir / "summary.md"
    out_file.write_text(markdown, encoding="utf-8")
    print(f"Report generated successfully: {out_file} ({len(scored_cases)} cases analyzed).")
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
