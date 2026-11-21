# Pipeline Evaluation Comparison: v1 vs v2

Comparison evaluated over **14 common cases** across **8 documents** on the `dev` dataset.

> [!NOTE]
> The development dataset was used to identify weaknesses and design fixes in pipeline v2; therefore, observed gains on this dataset are optimistic. An independent evaluation on an unseen holdout dataset is required to confirm generalizability.

## 1. Run Metadata

| Setting | v1 | v2 |
|---|---|---|
| **Pipeline Version** | v1 | v2 |
| **Model** | qwen/qwen3.8-27b | qwen/qwen3.8-27b |
| **Prompt SHA-256** | `1d06ec7147f6...` | `9d8f8a562030...` |
| **Common Evaluated Cases** | 14 | 14 |

## 2. Overall Performance Comparison (Pooled Across Common Cases)

| Metric | v1 | v2 | Delta (v2 - v1) |
|---|---|---|---|
| **Critical Correct Rate** | 8/14 (57.1%) | 7/14 (50.0%) | -7.1% |
| **All Headers Correct Rate** | 5/14 (35.7%) | 1/14 (7.1%) | -28.6% |
| **Mean Wrong Headers / Case** | 3.71 | 5.50 | +1.79 |
| **Line-Item Recall (macro)** | 67.9% | 61.6% | -6.2% |
| **Line-Item Recall (micro)** | 82.0% | 76.0% | -6.0% |
| **Silent Errors (FN)** | 9 | 8 | -1 |
| **Validator Recall** | 30.8% | 38.5% | +7.7% |
| **False Alarms (FP)** | 1 | 0 | -1 |
| **Mean Tokens / Case** | 3,241 | 3,235 | -7 |

## 3. Performance by Case Type

### Case Type: `image` (8 cases)

| Metric | v1 | v2 | Delta (v2 - v1) |
|---|---|---|---|
| **Critical Correct Rate** | 4/8 (50.0%) | 5/8 (62.5%) | +12.5% |
| **All Headers Correct Rate** | 1/8 (12.5%) | 1/8 (12.5%) | +0.0% |
| **Mean Wrong Headers / Case** | 3.75 | 3.62 | -0.12 |
| **Line-Item Recall (macro)** | 81.2% | 85.9% | +4.7% |
| **Line-Item Recall (micro)** | 90.0% | 90.0% | +0.0% |
| **Silent Errors (FN)** | 5 | 5 | +0 |
| **Validator Recall** | 37.5% | 28.6% | -8.9% |
| **False Alarms (FP)** | 0 | 0 | +0 |
| **Mean Tokens / Case** | 3,854 | 3,746 | -109 |

### Case Type: `text` (6 cases)

| Metric | v1 | v2 | Delta (v2 - v1) |
|---|---|---|---|
| **Critical Correct Rate** | 4/6 (66.7%) | 2/6 (33.3%) | -33.3% |
| **All Headers Correct Rate** | 4/6 (66.7%) | 0/6 (0.0%) | -66.7% |
| **Mean Wrong Headers / Case** | 3.67 | 8.00 | +4.33 |
| **Line-Item Recall (macro)** | 50.0% | 29.2% | -20.8% |
| **Line-Item Recall (micro)** | 70.0% | 55.0% | -15.0% |
| **Silent Errors (FN)** | 4 | 3 | -1 |
| **Validator Recall** | 20.0% | 50.0% | +30.0% |
| **False Alarms (FP)** | 1 | 0 | -1 |
| **Mean Tokens / Case** | 2,424 | 2,554 | +130 |

## 4. Per-Document Comparison & Sign Test

Document-level comparison based on total wrong header fields across all shared cases:

| Document | v1 Wrong Headers | v2 Wrong Headers | Outcome |
|---|---|---|---|
| Document A | 8 | 11 | v2 Worse (+3) |
| Document B | 4 | 7 | v2 Worse (+3) |
| Document C | 24 | 24 | Equal (Tie) |
| Document D | 3 | 7 | v2 Worse (+4) |
| Document E | 4 | 6 | v2 Worse (+2) |
| Document F | 6 | 4 | v2 Better (-2) |
| Document G | 2 | 2 | Equal (Tie) |
| Document H | 1 | 16 | v2 Worse (+15) |

- **v2 Better**: 1 documents
- **Equal (Tie)**: 2 documents
- **v2 Worse**: 5 documents
- **Exact Sign Test**: p = 0.9844 (one-sided testing v2 better, N=6 non-tied documents)
