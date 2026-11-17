# AI Document Extractor — Evaluation Report

## 1. Setup & Environment
- **Evaluation Date**: `2026-11-16T14:53:39.964982+00:00`
- **Model**: `qwen/qwen3.8-27b` (Seed: `42`)
- **Git Commit**: `349c3d4c9ef4577aaf58e2252808302c65a2d599`
- **Git HEAD**: `132c495` (tag: `eval-v1`, working tree: dirty)
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
| Description Accuracy (among matched items, ratio >= 0.80) | 100.0% (n=6) | 93.8% (n=8) | 96.9% (n=8) | 96.9% (n=8) | 92.2% (n=8) | 95.7% (n=38) |
| Quantity Accuracy (among matched items, diff <= 0.001) | 100.0% (n=6) | 100.0% (n=8) | 100.0% (n=8) | 100.0% (n=8) | 100.0% (n=8) | 100.0% (n=38) |
| Unit Price Accuracy (among matched items, diff <= 0.01) | 100.0% (n=6) | 100.0% (n=8) | 100.0% (n=8) | 100.0% (n=8) | 93.8% (n=8) | 98.7% (n=38) |

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
> Recorded latency represents overall wall-clock request duration; API-only latency cannot be separated from retry waits.

---

## 6. Limitations
- **Small Sample Size ($n$)**: The evaluation set represents a targeted sample of documents and may not reflect all invoice variations.
- **Simulated Perturbations**: Degraded variants (`lowres`, `jpeg35`, `rot3blur`) are synthetically produced from the same source pages, meaning errors between variants of the same document are not independent.
- **Single Human Annotator**: Ground truth values and ambiguous field rules were prepared and verified by a single human reviewer.
- **Provider Rate & Quota Variability**: Results are tied to the Groq free tier multimodal model (`qwen/qwen3.8-27b`) at the specified seed; upstream model revisions, API latency spikes, or quota adjustments can impact reproduction.
- **Scope of Results**: Performance statistics apply exclusively to the tested document types and layout styles.

---

## 7. Paired Text vs Image Comparison (Digital PDFs Only, n=6)

Direct pairwise comparison of the **Text Path** (`mode=text`) versus the **Clean Image Path** (`mode=image`) across the 6 digital PDF documents evaluated on the exact same files:

| Metric / Field | Text Path | Clean Image | Comparison / Delta |
|---|---|---|---|
| **Critical Fields Correct (`critical_correct`)** | 4/6 (66.7%) | 3/6 (50.0%) | Text +16.7% |
| **All Header Fields Correct (`all_header_correct`)** | 4/6 (66.7%) | 1/6 (16.7%) | Text +50.0% |
| **Line-Item Recall** | 50.0% | 75.0% | Text -25.0% |
| **Mean Total Tokens** | 2424 | 4270 | Text saves 43.2% tokens |
| **Mean Latency** | 1680 ms | 13033 ms | Text is 7.8x faster |

### Per-Document Outcome (by Number of Wrong Header Fields)
| Outcome | Document Count | Share |
|---|---|---|
| **Text Better** (fewer wrong header fields) | 3 / 6 | 50.0% |
| **Equal** (identical number of wrong header fields) | 3 / 6 | 50.0% |
| **Text Worse** (more wrong header fields) | 0 / 6 | 0.0% |

### Paired Per-Field Accuracy (k/6)
| Field | Text Path | Clean Image | Difference |
|---|---|---|---|
| `vendor` | 4/6 (66.7%) | 3/6 (50.0%) | +16.7% |
| `invoice_number` | 5/6 (83.3%) | 3/6 (50.0%) | +33.3% |
| `date` | 6/6 (100.0%) | 6/6 (100.0%) | 0.0% |
| `currency` | 6/6 (100.0%) | 6/6 (100.0%) | 0.0% |
| `subtotal` | 5/6 (83.3%) | 5/6 (83.3%) | 0.0% |
| `taxable_amount` | 5/6 (83.3%) | 5/6 (83.3%) | 0.0% |
| `cgst` | 5/6 (83.3%) | 4/6 (66.7%) | +16.7% |
| `sgst` | 5/6 (83.3%) | 4/6 (66.7%) | +16.7% |
| `igst` | 5/6 (83.3%) | 5/6 (83.3%) | 0.0% |
| `cess` | 6/6 (100.0%) | 6/6 (100.0%) | 0.0% |
| `tax` | 5/6 (83.3%) | 4/6 (66.7%) | +16.7% |
| `total` | 5/6 (83.3%) | 5/6 (83.3%) | 0.0% |
| `prices_include_tax` | 5/6 (83.3%) | 5/6 (83.3%) | 0.0% |
| `vendor_exact` | 4/6 (66.7%) | 3/6 (50.0%) | +16.7% |
| `critical_correct` | 4/6 (66.7%) | 3/6 (50.0%) | +16.7% |
| `all_header_correct` | 4/6 (66.7%) | 1/6 (16.7%) | +50.0% |
| `fully_correct` | 1/6 (16.7%) | 0/6 (0.0%) | +16.7% |

---

## 8. As-Deployed (mode=auto) View (n=8)

Extraction accuracy for the operational configuration (`mode=auto`): routes digital PDFs with embedded text to the Text Path (6 docs), and scanned or photographic documents to the Clean Image Path (2 docs).

| Field / Metric | Accuracy (k/n) | Rate (%) | Wilson 95% CI |
|---|---|---|---|
| `vendor` | 6/8 | 75.0% | [40.9%, 92.9%] |
| `invoice_number` | 6/8 | 75.0% | [40.9%, 92.9%] |
| `date` | 7/8 | 87.5% | [52.9%, 97.8%] |
| `currency` | 8/8 | 100.0% | [67.6%, 100.0%] |
| `subtotal` | 5/8 | 62.5% | [30.6%, 86.3%] |
| `taxable_amount` | 7/8 | 87.5% | [52.9%, 97.8%] |
| `cgst` | 7/8 | 87.5% | [52.9%, 97.8%] |
| `sgst` | 7/8 | 87.5% | [52.9%, 97.8%] |
| `igst` | 7/8 | 87.5% | [52.9%, 97.8%] |
| `cess` | 8/8 | 100.0% | [67.6%, 100.0%] |
| `tax` | 7/8 | 87.5% | [52.9%, 97.8%] |
| `total` | 7/8 | 87.5% | [52.9%, 97.8%] |
| `prices_include_tax` | 7/8 | 87.5% | [52.9%, 97.8%] |
| `vendor_exact` | 6/8 | 75.0% | [40.9%, 92.9%] |
| **`critical_correct`** | **5/8** | **62.5%** | [30.6%, 86.3%] |
| **`all_header_correct`** | **4/8** | **50.0%** | [21.5%, 78.5%] |
| **`fully_correct`** | **1/8** | **12.5%** | [2.2%, 47.1%] |

---

## 9. Per-Document Performance Summary (Anonymized A–H)

Summary across all evaluated documents (documents ordered alphabetically by ID and assigned labels A–H; mapping preserved privately in `eval/results/doc_label_map.json`):

| Document | Kind | Cases | Critical Fields Correct | Mean Wrong Header Fields | Line Items Matched / Expected | Flagged Cases |
|---|---|---|---|---|---|---|
| Doc A | `digital_pdf` | 5 | 5/5 (100.0%) | 2.60 | 6/10 (60.0%) | 3/5 |
| Doc B | `digital_pdf` | 5 | 5/5 (100.0%) | 0.20 | 7/10 (70.0%) | 2/5 |
| Doc C | `digital_pdf` | 5 | 0/5 (0.0%) | 9.00 | 0/10 (0.0%) | 0/5 |
| Doc D | `digital_pdf` | 5 | 5/5 (100.0%) | 0.60 | 7/10 (70.0%) | 4/5 |
| Doc E | `digital_pdf` | 5 | 0/5 (0.0%) | 2.00 | 19/20 (95.0%) | 5/5 |
| Doc F | `photo` | 4 | 0/4 (0.0%) | 2.00 | 32/32 (100.0%) | 0/4 |
| Doc G | `photo` | 4 | 4/4 (100.0%) | 1.75 | 8/8 (100.0%) | 0/4 |
| Doc H | `digital_pdf` | 5 | 2/5 (40.0%) | 0.80 | 40/40 (100.0%) | 1/5 |
| **Overall** | — | **38** | **21/38 (55.3%)** | **2.39** | **119/140 (85.0%)** | **15/38 (39.5%)** |

---

## 10. Document-Level Bootstrap Confidence Intervals

Empirical 95% confidence intervals derived by resampling documents with replacement (stdlib `random`, seed 42, 2,000 resamples), clustering perturbation variants of each document together:

| Metric | Point Estimate | Wilson 95% CI (n=38) | Document Bootstrap 95% CI |
|---|---|---|---|
| `critical_correct` Rate | 21/38 (55.3%) | [39.7%, 69.9%] | [23.7%, 87.2%] (mean 55.1%) |
| `all_header_correct` Rate | 9/38 (23.7%) | [13.0%, 39.2%] | [5.4%, 43.6%] (mean 23.3%) |
| Mean Wrong Header Fields / Case | 2.39 | — *(N/A)* | [0.97, 4.58] (mean 2.41) |
| Validator Recall | 12/34 (35.3%) | [21.5%, 52.1%] | [9.1%, 63.9%] (mean 34.3%) |

> [!NOTE]
> Wilson intervals treat all 38 test cases as independent observations. Document-level bootstrap resamples at the document level (clustering all perturbation variants of each document together), properly accounting for intra-document correlation across variants.

---

## 11. Error Metrics & Critical Field Reliability

### Wrong Header Fields Distribution
| Modality / Path | Cases | Mean Wrong Headers | Median Wrong Headers | Max Wrong Headers |
|---|---|---|---|---|
| Text | 6 | 1.83 | 0.0 | 9 |
| Image | 8 | 2.62 | 2.0 | 9 |
| Lowres | 8 | 2.50 | 2.0 | 9 |
| Jpeg35 | 8 | 2.50 | 1.5 | 9 |
| Rot3blur | 8 | 2.38 | 2.0 | 9 |
| **Overall** | 38 | 2.39 | 2.0 | 9 |

### Per-Path Critical Field Accuracy
| Critical Field | Text Path | Clean Image | Lowres (50%) | JPEG Q35 | Rot3 + Blur | Overall |
|---|---|---|---|---|---|---|
| `vendor` | 4/6 (66.7%) | 5/8 (62.5%) | 6/8 (75.0%) | 5/8 (62.5%) | 5/8 (62.5%) | 25/38 (65.8%) |
| `invoice_number` | 5/6 (83.3%) | 4/8 (50.0%) | 4/8 (50.0%) | 4/8 (50.0%) | 6/8 (75.0%) | 23/38 (60.5%) |
| `date` | 6/6 (100.0%) | 7/8 (87.5%) | 7/8 (87.5%) | 7/8 (87.5%) | 6/8 (75.0%) | 33/38 (86.8%) |
| `total` | 5/6 (83.3%) | 7/8 (87.5%) | 7/8 (87.5%) | 7/8 (87.5%) | 7/8 (87.5%) | 33/38 (86.8%) |
| `critical_correct` | 4/6 (66.7%) | 4/8 (50.0%) | 5/8 (62.5%) | 4/8 (50.0%) | 4/8 (50.0%) | 21/38 (55.3%) |

---

## 12. Validator Analysis (Extended)

### (a) & (b) Validator Confusion Matrix Comparison

| View | TP | FN (Silent) | FP (Alarm) | TN | Validator Recall | Validator Precision |
|---|---|---|---|---|---|---|
| **(a) Baseline (All Flags)** | 12 | 22 | 3 | 1 | 35.3% | 80.0% |
| **(b) Excluding IGNORE-Only Flags** | 12 | 22 | 2 | 2 | 35.3% | 85.7% |

> [!NOTE]
> View (b) excludes review flags that fired exclusively on fields marked `IGNORE` in ground truth (e.g. `ITEM_MATH_MISMATCH` firing on fused receipt text where unit price and quantity are marked `IGNORE`). Under this view, false alarms decrease from 3 to 2, improving validator precision from 80.0% to 85.7%.

### (c) Critical-Field Error Catch Rate
- **Cases with Defective Critical Field** (`vendor`, `invoice_number`, `date`, or `total`): 27 cases
- **Defective Cases Flagged for Review**: 11 cases
- **Critical-Field Catch Rate**: **11/27 (40.7%)**

### (d) Silent Errors by Cause
Root cause distribution across all 22 silent-error cases (from `eval/results/error_causes.json`):

| Error Cause Category | Case Count | Share | Description |
|---|---|---|---|
| `wrong_invoice` | 0 | 0.0% | Root cause category: `wrong_invoice` |
| `vendor_naming` | 0 | 0.0% | Root cause category: `vendor_naming` |
| `line_amount_definition` | 0 | 0.0% | Root cause category: `line_amount_definition` |
| `read_error` | 0 | 0.0% | Root cause category: `read_error` |
| `other` | 0 | 0.0% | Root cause category: `other` |
| `unlabelled` | 22 | 100.0% | Root cause category: `unlabelled` |

---

## 13. Latency & Retry Accounting
- **Measurement Scope**: The recorded latency figures reflect total end-to-end wall-clock time for the successful extraction call.
- **Retry Isolation**: Raw evaluation outputs do not separately log retry attempts or rate-limit backoff sleeps. Therefore, API-only latency cannot be separated from retry overhead.
