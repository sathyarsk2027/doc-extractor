# AI Document Extractor — Evaluation Report

## 1. Setup & Environment
- **Evaluation Date**: `2026-11-16T14:53:39.964982+00:00`
- **Model**: `qwen/qwen3.8-27b` (Seed: `42`)
- **Git Commit**: `349c3d4c9ef4577aaf58e2252808302c65a2d599`
- **Prompt SHA-256**: `1d06ec7147f6489dd80ac79f877fa0a9892ac98e743b848be54c761a2e1dd31f`
- **Python Version**: `3.14.6`
- **Default Extraction Mode**: `auto`
- **Document Inventory**: 8 documents (digital_pdf: 6, photo: 2)
- **Total Cases Evaluated**: 38 cases

---

## 2. Header-Field Accuracy

All rates reported as `k/n (accuracy %, Wilson 95% CI [lower %, upper %])`:

| Field | Text Path | Clean Image | Lowres (50%) | JPEG Q35 | Rot3 + Blur | Overall |
|---|---|---|---|---|---|---|
| `vendor` | 4/6 (66.7%, [30.0%, 90.3%]) | 5/8 (62.5%, [30.6%, 86.3%]) | 6/8 (75.0%, [40.9%, 92.9%]) | 5/8 (62.5%, [30.6%, 86.3%]) | 5/8 (62.5%, [30.6%, 86.3%]) | 25/38 (65.8%, [49.9%, 78.8%]) |
| `invoice_number` | 5/6 (83.3%, [43.6%, 97.0%]) | 4/8 (50.0%, [21.5%, 78.5%]) | 4/8 (50.0%, [21.5%, 78.5%]) | 4/8 (50.0%, [21.5%, 78.5%]) | 6/8 (75.0%, [40.9%, 92.9%]) | 23/38 (60.5%, [44.7%, 74.4%]) |
| `date` | 6/6 (100.0%, [61.0%, 100.0%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 6/8 (75.0%, [40.9%, 92.9%]) | 33/38 (86.8%, [72.7%, 94.2%]) |
| `currency` | 6/6 (100.0%, [61.0%, 100.0%]) | 8/8 (100.0%, [67.6%, 100.0%]) | 8/8 (100.0%, [67.6%, 100.0%]) | 8/8 (100.0%, [67.6%, 100.0%]) | 8/8 (100.0%, [67.6%, 100.0%]) | 38/38 (100.0%, [90.8%, 100.0%]) |
| `subtotal` | 5/6 (83.3%, [43.6%, 97.0%]) | 5/8 (62.5%, [30.6%, 86.3%]) | 5/8 (62.5%, [30.6%, 86.3%]) | 5/8 (62.5%, [30.6%, 86.3%]) | 5/8 (62.5%, [30.6%, 86.3%]) | 25/38 (65.8%, [49.9%, 78.8%]) |
| `taxable_amount` | 5/6 (83.3%, [43.6%, 97.0%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 33/38 (86.8%, [72.7%, 94.2%]) |
| `cgst` | 5/6 (83.3%, [43.6%, 97.0%]) | 6/8 (75.0%, [40.9%, 92.9%]) | 6/8 (75.0%, [40.9%, 92.9%]) | 6/8 (75.0%, [40.9%, 92.9%]) | 6/8 (75.0%, [40.9%, 92.9%]) | 29/38 (76.3%, [60.8%, 87.0%]) |
| `sgst` | 5/6 (83.3%, [43.6%, 97.0%]) | 6/8 (75.0%, [40.9%, 92.9%]) | 6/8 (75.0%, [40.9%, 92.9%]) | 6/8 (75.0%, [40.9%, 92.9%]) | 6/8 (75.0%, [40.9%, 92.9%]) | 29/38 (76.3%, [60.8%, 87.0%]) |
| `igst` | 5/6 (83.3%, [43.6%, 97.0%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 33/38 (86.8%, [72.7%, 94.2%]) |
| `cess` | 6/6 (100.0%, [61.0%, 100.0%]) | 8/8 (100.0%, [67.6%, 100.0%]) | 8/8 (100.0%, [67.6%, 100.0%]) | 8/8 (100.0%, [67.6%, 100.0%]) | 8/8 (100.0%, [67.6%, 100.0%]) | 38/38 (100.0%, [90.8%, 100.0%]) |
| `tax` | 5/6 (83.3%, [43.6%, 97.0%]) | 6/8 (75.0%, [40.9%, 92.9%]) | 6/8 (75.0%, [40.9%, 92.9%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 31/38 (81.6%, [66.6%, 90.8%]) |
| `total` | 5/6 (83.3%, [43.6%, 97.0%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 33/38 (86.8%, [72.7%, 94.2%]) |
| `prices_include_tax` | 5/6 (83.3%, [43.6%, 97.0%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 7/8 (87.5%, [52.9%, 97.8%]) | 33/38 (86.8%, [72.7%, 94.2%]) |
| `vendor_exact` | 4/6 (66.7%, [30.0%, 90.3%]) | 5/8 (62.5%, [30.6%, 86.3%]) | 6/8 (75.0%, [40.9%, 92.9%]) | 4/8 (50.0%, [21.5%, 78.5%]) | 5/8 (62.5%, [30.6%, 86.3%]) | 24/38 (63.2%, [47.3%, 76.6%]) |
| `critical_correct` | 4/6 (66.7%, [30.0%, 90.3%]) | 4/8 (50.0%, [21.5%, 78.5%]) | 5/8 (62.5%, [30.6%, 86.3%]) | 4/8 (50.0%, [21.5%, 78.5%]) | 4/8 (50.0%, [21.5%, 78.5%]) | 21/38 (55.3%, [39.7%, 69.9%]) |
| `all_header_correct` | 4/6 (66.7%, [30.0%, 90.3%]) | 1/8 (12.5%, [2.2%, 47.1%]) | 2/8 (25.0%, [7.1%, 59.1%]) | 0/8 (0.0%, [0.0%, 32.4%]) | 2/8 (25.0%, [7.1%, 59.1%]) | 9/38 (23.7%, [13.0%, 39.2%]) |
| `fully_correct` | 1/6 (16.7%, [3.0%, 56.4%]) | 0/8 (0.0%, [0.0%, 32.4%]) | 2/8 (25.0%, [7.1%, 59.1%]) | 0/8 (0.0%, [0.0%, 32.4%]) | 1/8 (12.5%, [2.2%, 47.1%]) | 4/38 (10.5%, [4.2%, 24.1%]) |

---

## 3. Line-Item Extraction Metrics

| Metric | Text Path | Clean Image | Lowres (50%) | JPEG Q35 | Rot3 + Blur | Overall |
|---|---|---|---|---|---|---|
| Item Recall (matched/expected) | 50.0% (n=6) | 81.2% (n=8) | 87.5% (n=8) | 68.8% (n=8) | 71.9% (n=8) | 73.0% (n=38) |
| Item Precision (matched/predicted) | 50.0% (n=6) | 81.2% (n=8) | 87.5% (n=8) | 68.8% (n=8) | 71.9% (n=8) | 73.0% (n=38) |
| Description Accuracy (ratio >= 0.80) | 100.0% (n=6) | 93.8% (n=8) | 96.9% (n=8) | 96.9% (n=8) | 92.2% (n=8) | 95.7% (n=38) |
| Quantity Accuracy (diff <= 0.001) | 100.0% (n=6) | 100.0% (n=8) | 100.0% (n=8) | 100.0% (n=8) | 100.0% (n=8) | 100.0% (n=38) |
| Unit Price Accuracy (diff <= 0.01) | 100.0% (n=6) | 100.0% (n=8) | 100.0% (n=8) | 100.0% (n=8) | 93.8% (n=8) | 98.7% (n=38) |

---

## 4. Review Flag & Validator Effectiveness

| Metric | Count | Description |
|---|---|---|
| **True Positives (TP)** | 12 | Extraction had errors and was correctly flagged (`needs_review=true`) |
| **False Negatives (FN)** | 22 | **Silent Errors**: Extraction had errors but was NOT flagged (`needs_review=false`) |
| **False Positives (FP)** | 3 | False Alarms: Clean extraction was flagged for review |
| **True Negatives (TN)** | 1 | Clean extraction and was not flagged |
| **Validator Recall** | 35.3% | Caught errors / Total defective extractions (`TP / (TP + FN)`) |
| **Validator Precision** | 80.0% | Genuine errors / Total flagged extractions (`TP / (TP + FP)`) |

### Fired Review Flags Distribution
| Flag Code | Frequency |
|---|---|
| `ITEM_MATH_MISMATCH` | 13 |
| `TOTAL_MISMATCH` | 2 |
| `NO_LINE_ITEMS` | 1 |
| `LINE_SUM_MISMATCH` | 1 |

---

## 5. Latency, Token Usage & Capacity

| Modality / Path | Cases | Mean Latency (ms) | P95 Latency (ms) | Mean Tokens (In) | Mean Tokens (Out) | Mean Total Tokens | Free-Plan Docs/Day |
|---|---|---|---|---|---|---|---|
| Text | 6 | 1680 | 2146 | 2036 | 388 | 2424 | ~82 |
| Image | 8 | 11720 | 39789 | 3456 | 398 | 3854 | ~51 |
| Lowres | 8 | 4253 | 7010 | 3456 | 399 | 3855 | ~51 |
| Jpeg35 | 8 | 5693 | 10042 | 3456 | 399 | 3855 | ~51 |
| Rot3blur | 8 | 11330 | 34475 | 3584 | 400 | 3984 | ~50 |
| **Overall** | 38 | 7212 | 19245 | 3259 | 397 | 3656 | ~54 |

> [!NOTE]
> Free tier capacity estimate is based on the 200,000 tokens/day Groq free quota ceiling and 8,000 tokens/minute rate limit.

---

## 6. Limitations
- **Small Sample Size ($n$)**: The evaluation set represents a targeted sample of documents and may not reflect all invoice variations.
- **Simulated Perturbations**: Degraded variants (`lowres`, `jpeg35`, `rot3blur`) are synthetically produced from the same source pages, meaning errors between variants of the same document are not independent.
- **Single Human Annotator**: Ground truth values and ambiguous field rules were prepared and verified by a single human reviewer.
- **Provider Rate & Quota Variability**: Results are tied to the Groq free tier multimodal model (`qwen/qwen3.8-27b`) at the specified seed; upstream model revisions, API latency spikes, or quota adjustments can impact reproduction.
- **Scope of Results**: Performance statistics apply exclusively to the tested document types and layout styles.
