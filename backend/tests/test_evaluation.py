"""Tests for Phase 8 evaluation framework (all mocked, zero real API calls)."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pymupdf
import pytest

from app.config import settings
from app.errors import AppError
from app.schemas import InvoiceData, ExtractionMeta, LineItem
from app.services.db import get_db
from evaluation.ground_truth import (
    cmd_templates,
    cmd_check_gt,
    get_gt_dir,
    load_ground_truth,
    validate_ground_truth_dict,
    sanity_check_ground_truth,
)
from evaluation.pipeline_runner import (
    PipelineResult,
    has_usable_text_layer,
    run_pipeline_on_file,
)


def _make_dummy_pdf(text: str = "Test Invoice") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=400)
    page.insert_text((30, 30), text)
    data = doc.tobytes()
    doc.close()
    return data


def _synthetic_clean_invoice() -> InvoiceData:
    return InvoiceData(
        vendor="Acme Supplies Ltd",
        invoice_number="INV-9999",
        date="2026-11-05",
        currency="USD",
        subtotal=100.0,
        tax=10.0,
        total=110.0,
        line_items=[
            LineItem(description="Item A", quantity=1.0, unit_price=100.0, amount=100.0)
        ],
    )


def test_pipeline_result_serialization():
    """PipelineResult round-trips via to_dict and from_dict."""
    inv = _synthetic_clean_invoice()
    meta = ExtractionMeta(
        model="mock-model",
        latency_ms=150,
        input_tokens=200,
        output_tokens=80,
        pages_sent=[1],
        repaired=False,
        source="text",
    )
    result = PipelineResult(
        extraction=inv,
        flags={},
        needs_review=False,
        meta=meta,
        error=None,
    )
    data = result.to_dict()
    assert data["extraction"]["vendor"] == "Acme Supplies Ltd"
    assert data["meta"]["model"] == "mock-model"
    assert data["error"] is None

    restored = PipelineResult.from_dict(data)
    assert restored.extraction.vendor == "Acme Supplies Ltd"
    assert restored.meta.model == "mock-model"
    assert restored.needs_review is False
    assert restored.error is None


def test_has_usable_text_layer(tmp_path):
    """Detects embedded text in PDF and rejects image or short text."""
    rich_text = "This is a digital invoice document with enough text to exceed the fifty character threshold easily."
    rich_pdf = tmp_path / "rich.pdf"
    rich_pdf.write_bytes(_make_dummy_pdf(rich_text))
    assert has_usable_text_layer(rich_pdf) is True

    sparse_pdf = tmp_path / "sparse.pdf"
    sparse_pdf.write_bytes(_make_dummy_pdf("Short"))
    assert has_usable_text_layer(sparse_pdf) is False

    assert has_usable_text_layer(tmp_path / "nonexistent.pdf") is False


def test_run_pipeline_on_file_missing_file(tmp_path):
    """Missing file returns clean PipelineResult with FILE_NOT_FOUND error."""
    missing = tmp_path / "missing.pdf"
    res = run_pipeline_on_file(missing)
    assert res.extraction is None
    assert res.needs_review is True
    assert res.error["code"] == "FILE_NOT_FOUND"


def test_run_pipeline_on_file_success(tmp_path):
    """Successful pipeline run produces InvoiceData, flags, meta, and cleans up temp files."""
    test_pdf = tmp_path / "sample.pdf"
    test_pdf.write_bytes(_make_dummy_pdf("Invoice #123 Acme Supplies"))

    inv = _synthetic_clean_invoice()
    meta = ExtractionMeta(
        model="mock-model",
        latency_ms=210,
        input_tokens=1500,
        output_tokens=320,
        pages_sent=[1],
        repaired=False,
        source="image",
    )

    test_doc_id = "11111111-2222-3333-4444-555555555555"
    with patch("uuid.uuid4", return_value=test_doc_id), \
         patch("evaluation.pipeline_runner.extract_document", return_value=(inv, meta)) as mock_ext:
        res = run_pipeline_on_file(test_pdf, mode="image")

        assert mock_ext.called
        assert mock_ext.call_args[1].get("mode_override") == "image"

    assert res.extraction is not None
    assert res.extraction.vendor == "Acme Supplies Ltd"
    assert res.meta.model == "mock-model"
    assert res.meta.latency_ms == 210
    assert res.needs_review is False
    assert res.flags == {}
    assert res.error is None

    # Verify no documents row written to SQLite
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents")
        count = cursor.fetchone()[0]
        assert count == 0

    # Verify document storage directory was deleted
    assert not (settings.storage_path / test_doc_id).exists()


def test_run_pipeline_on_file_app_error_cleanup(tmp_path):
    """When extraction raises AppError, error is captured and temp files are deleted."""
    test_pdf = tmp_path / "rate_limited.pdf"
    test_pdf.write_bytes(_make_dummy_pdf("Invoice Content"))

    test_doc_id = "22222222-3333-4444-5555-666666666666"
    with patch("uuid.uuid4", return_value=test_doc_id), \
         patch("evaluation.pipeline_runner.extract_document") as mock_ext:
        mock_ext.side_effect = AppError("RATE_LIMITED", "AI quota exhausted", status_code=429)
        res = run_pipeline_on_file(test_pdf)

    assert res.extraction is None
    assert res.needs_review is True
    assert res.error["code"] == "RATE_LIMITED"
    assert res.error["message"] == "AI quota exhausted"

    # Verify document storage directory was deleted
    assert not (settings.storage_path / test_doc_id).exists()


# ---------------------------------------------------------------------------
# Ground Truth Tests (Step A3 & A8)
# ---------------------------------------------------------------------------

def test_ground_truth_validation_rejects_todo():
    """Ground truth with _status: 'TODO' is valid schema but not verified/ready."""
    data = {
        "doc_id": "test01",
        "source_file": "test01.pdf",
        "document_kind": "digital_pdf",
        "_status": "TODO",
        "expected": {
            "vendor": "Acme",
            "invoice_number": "123",
            "date": "2026-11-05",
            "currency": "USD",
            "subtotal": 100.0,
            "total": 100.0,
            "line_items": [],
        },
    }
    is_valid, is_verified, errors = validate_ground_truth_dict(data)
    assert is_valid is True
    assert is_verified is False


def test_ground_truth_validation_rejects_bad_date():
    """Ground truth rejects non-ISO or non-existent calendar dates."""
    base = {
        "doc_id": "test01",
        "source_file": "test01.pdf",
        "document_kind": "digital_pdf",
        "_status": "verified",
        "expected": {"vendor": "Acme", "line_items": []},
    }

    # Slash-separated date
    base["expected"]["date"] = "2026/11/05"
    is_valid, _, errors = validate_ground_truth_dict(base)
    assert is_valid is False
    assert any("Invalid ISO date" in e for e in errors)

    # Impossible date (Feb 30)
    base["expected"]["date"] = "2026-02-30"
    is_valid, _, errors = validate_ground_truth_dict(base)
    assert is_valid is False
    assert any("does not exist" in e for e in errors)

    # Valid ISO date
    base["expected"]["date"] = "2026-11-05"
    is_valid, is_verified, errors = validate_ground_truth_dict(base)
    assert is_valid is True
    assert is_verified is True


def test_ground_truth_validation_rejects_bad_number_types():
    """Ground truth rejects string or boolean values for numeric fields."""
    base = {
        "doc_id": "test01",
        "source_file": "test01.pdf",
        "document_kind": "digital_pdf",
        "_status": "verified",
        "expected": {
            "vendor": "Acme",
            "date": "2026-11-05",
            "total": "one hundred",
            "line_items": [],
        },
    }
    is_valid, _, errors = validate_ground_truth_dict(base)
    assert is_valid is False
    assert any("total" in e for e in errors)

    # Boolean is rejected as number
    base["expected"]["total"] = True
    is_valid, _, errors = validate_ground_truth_dict(base)
    assert is_valid is False


def test_templates_never_overwrites(tmp_path, monkeypatch):
    """cmd_templates generates template for new doc but NEVER overwrites existing ground truth."""
    eval_mock = tmp_path / "eval"
    data_mock = eval_mock / "data"
    gt_mock = eval_mock / "ground_truth"
    data_mock.mkdir(parents=True)
    gt_mock.mkdir(parents=True)

    monkeypatch.setenv("EVAL_DIR", str(eval_mock))

    # Existing document with custom ground truth
    (data_mock / "existing.pdf").write_bytes(b"%PDF-1.4 dummy")
    existing_gt_content = {
        "doc_id": "existing",
        "source_file": "existing.pdf",
        "document_kind": "digital_pdf",
        "_status": "verified",
        "expected": {"vendor": "PRESERVED VENDOR", "line_items": []},
    }
    (gt_mock / "existing.json").write_text(json.dumps(existing_gt_content), encoding="utf-8")

    # New unannotated document
    (data_mock / "newdoc.pdf").write_bytes(b"%PDF-1.4 dummy")

    ret = cmd_templates()
    assert ret == 0

    # Verify existing ground truth was NOT overwritten
    preserved = json.loads((gt_mock / "existing.json").read_text(encoding="utf-8"))
    assert preserved["expected"]["vendor"] == "PRESERVED VENDOR"
    assert preserved["_status"] == "verified"

    # Verify new template was created with TODO status
    new_gt = json.loads((gt_mock / "newdoc.json").read_text(encoding="utf-8"))
    assert new_gt["_status"] == "TODO"
    assert new_gt["source_file"] == "newdoc.pdf"
    assert "_instructions" in new_gt


def test_verified_reliance_7474_ground_truth():
    """Verify reliance_7474.json is valid, verified, and matches expected specification."""
    gt_dir = get_gt_dir()
    rel_path = gt_dir / "reliance_7474.json"
    assert rel_path.is_file()

    data = load_ground_truth(rel_path)
    is_valid, is_verified, errors = validate_ground_truth_dict(data)
    assert is_valid is True, f"Validation errors: {errors}"
    assert is_verified is True
    assert data["expected"]["vendor"] == "Reliance Retail Limited"
    assert data["expected"]["invoice_number"] == "621418926514866"
    assert len(data["expected"]["line_items"]) == 8


# ---------------------------------------------------------------------------
# Variant Tests (Step A4 & A8)
# ---------------------------------------------------------------------------

from evaluation.variants import generate_variants_for_document, apply_degradation


def test_variants_pdf_no_text_layer_and_same_page_count(tmp_path):
    """Output PDF variants have NO text layer (get_text is empty) and same page count."""
    # Create 2-page source PDF with text
    src_pdf = tmp_path / "source.pdf"
    doc = pymupdf.open()
    doc.new_page(width=300, height=400).insert_text((30, 30), "Page 1 Content with digital text")
    doc.new_page(width=300, height=400).insert_text((30, 30), "Page 2 Content with digital text")
    doc.save(str(src_pdf))
    doc.close()

    variants = generate_variants_for_document(src_pdf, out_dir=tmp_path / "vars")
    assert len(variants) == 3

    for var_path in variants:
        assert var_path.is_file()
        assert var_path.suffix == ".pdf"
        var_doc = pymupdf.open(str(var_path))
        # Same page count
        assert len(var_doc) == 2
        # Zero text layer on all pages
        for page in var_doc:
            assert page.get_text().strip() == ""
        var_doc.close()


def test_variants_deterministic_output(tmp_path):
    """Running variant generation twice produces byte-identical files."""
    src_pdf = tmp_path / "source.pdf"
    doc = pymupdf.open()
    doc.new_page(width=300, height=400).insert_text((30, 30), "Deterministic Test")
    doc.save(str(src_pdf))
    doc.close()

    run1_dir = tmp_path / "run1"
    run2_dir = tmp_path / "run2"

    vars1 = generate_variants_for_document(src_pdf, out_dir=run1_dir)
    vars2 = generate_variants_for_document(src_pdf, out_dir=run2_dir)

    for p1, p2 in zip(sorted(vars1), sorted(vars2)):
        assert p1.name == p2.name
        b1 = p1.read_bytes()
        b2 = p2.read_bytes()
        assert b1 == b2, f"Non-deterministic output for {p1.name}"


# ---------------------------------------------------------------------------
# Scoring Tests (Step A5 & A8)
# ---------------------------------------------------------------------------

from evaluation.scoring import (
    normalize_text,
    wilson_interval,
    score_header_field,
    match_line_items,
    score_case,
)


def test_text_normalization():
    """Text normalization correctly handles casefolding, punctuation, and whitespace."""
    raw = "  Acme, Supplies & Co. -- (LLC) \n\t "
    normalized = normalize_text(raw)
    assert normalized == "acme supplies co llc"


def test_wilson_interval_sanity_values():
    """Wilson interval calculations match mathematical bounds and expected values."""
    # 0 successes out of 10
    p, lower, upper = wilson_interval(0, 10)
    assert p == 0.0
    assert lower == 0.0
    assert 0.25 < upper < 0.32

    # 10 successes out of 10
    p, lower, upper = wilson_interval(10, 10)
    assert p == 1.0
    assert 0.68 < lower < 0.75
    assert upper == 1.0

    # 5 successes out of 10 (symmetric interval around 0.5)
    p, lower, upper = wilson_interval(5, 10)
    assert p == 0.5
    assert 0.20 < lower < 0.28
    assert 0.72 < upper < 0.80

    # Empty n returns zeros
    assert wilson_interval(0, 0) == (0.0, 0.0, 0.0)


def test_header_scoring_rules():
    """Verify null-vs-null, hallucination, miss, tolerance edges, and vendor exact vs near."""
    # Null vs Null -> Correct
    corr, status = score_header_field("subtotal", None, None)
    assert corr is True
    assert status == "correct"

    # Expected Null, Pred non-null -> Hallucination
    corr, status = score_header_field("subtotal", None, 10.0)
    assert corr is False
    assert status == "hallucination"

    # Expected non-null, Pred Null -> Miss
    corr, status = score_header_field("subtotal", 10.0, None)
    assert corr is False
    assert status == "miss"

    # Numeric tolerance edges: 0.01 passes, 0.02 fails
    corr, _ = score_header_field("total", 100.00, 100.01)
    assert corr is True
    corr, _ = score_header_field("total", 100.00, 100.02)
    assert corr is False

    # Vendor exact vs near
    corr, _ = score_header_field("vendor", "Reliance Retail Limited", "reliance retail limited")
    assert corr is True
    # Slight typo with > 90% difflib ratio
    corr, _ = score_header_field("vendor", "Reliance Retail Limited", "Reliance Retail Limite")
    assert corr is True
    # Mismatch with low similarity
    corr, _ = score_header_field("vendor", "Reliance Retail Limited", "Walmart Store Corp")
    assert corr is False


def test_line_item_matching_duplicates_and_tolerances():
    """Greedy line item matching handles duplicate amounts, description tie-breaking, and extras."""
    expected_items = [
        {"description": "Item Alpha", "quantity": 1.0, "unit_price": 50.0, "amount": 50.0},
        {"description": "Item Beta", "quantity": 2.0, "unit_price": 25.0, "amount": 50.0},
    ]

    # Predictions swapped in order
    predicted_items = [
        LineItem(description="Item Beta", quantity=2.0, unit_price=25.0, amount=50.0),
        LineItem(description="Item Alpha", quantity=1.0, unit_price=50.0, amount=50.0),
        LineItem(description="Extra Item", quantity=1.0, unit_price=10.0, amount=10.0),
    ]

    res = match_line_items(expected_items, predicted_items)
    assert res.expected_count == 2
    assert res.predicted_count == 3
    assert res.matched_count == 2
    assert res.recall == 1.0
    assert abs(res.precision - (2 / 3)) < 1e-4
    assert res.description_correct == 2
    assert res.quantity_correct == 2
    assert res.unit_price_correct == 2
    assert res.has_discrepancy is True  # Because of extra item


def test_validator_effectiveness_confusion_matrix():
    """Verify TP, FN (silent error), FP (false alarm), TN classification."""
    gt = {
        "expected": {
            "vendor": "Acme",
            "invoice_number": "123",
            "total": 100.0,
            "line_items": [],
        }
    }

    correct_inv = InvoiceData(
        vendor="Acme",
        invoice_number="123",
        date="2026-11-05",
        currency="USD",
        total=100.0,
    )
    wrong_inv = InvoiceData(
        vendor="Acme",
        invoice_number="999",  # Wrong
        date="2026-11-05",
        currency="USD",
        total=100.0,
    )

    # 1. TP: Has error and flagged
    res_tp = score_case("doc1", "case1", gt, wrong_inv, {"ERR": {"code": "ERR"}}, needs_review=True)
    assert res_tp.classification == "TP"

    # 2. FN (Silent error): Has error and NOT flagged
    res_fn = score_case("doc1", "case2", gt, wrong_inv, {}, needs_review=False)
    assert res_fn.classification == "FN"

    # 3. FP (False alarm): Clean extraction but flagged
    res_fp = score_case("doc1", "case3", gt, correct_inv, {"WARN": {"code": "WARN"}}, needs_review=True)
    assert res_fp.classification == "FP"

    # 4. TN: Clean extraction and NOT flagged
    res_tn = score_case("doc1", "case4", gt, correct_inv, {}, needs_review=False)
    assert res_tn.classification == "TN"


# ---------------------------------------------------------------------------
# Runner Tests (Step A6 & A8)
# ---------------------------------------------------------------------------

from evaluation.pipeline_runner import (
    write_manifest,
    cmd_run,
    build_case_matrix,
    cmd_plan,
)


def test_runner_writes_manifest(tmp_path, monkeypatch):
    """write_manifest generates complete manifest.json with model, seed, prompt hash, commit."""
    mock_eval = tmp_path / "eval"
    monkeypatch.setenv("EVAL_DIR", str(mock_eval))

    manifest_path = write_manifest(["case_1", "case_2"])
    assert manifest_path.is_file()

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "date" in data
    assert "git_commit" in data
    assert "model" in data
    assert "seed" in data
    assert "prompt_sha256" in data
    assert len(data["prompt_sha256"]) == 64  # Valid SHA-256
    assert data["cases"] == ["case_1", "case_2"]


def test_runner_resumes_without_recalling_cached_cases(tmp_path, monkeypatch):
    """cmd_run skips cases that already have cached raw outputs unless force=True."""
    mock_eval = tmp_path / "eval"
    raw_dir = mock_eval / "results" / "raw"
    data_dir = mock_eval / "data"
    raw_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)

    monkeypatch.setenv("EVAL_DIR", str(mock_eval))
    monkeypatch.setattr("time.sleep", lambda s: None)

    # Put a mock document in data
    (data_dir / "doc1.pdf").write_bytes(b"%PDF-1.4 dummy")

    # Put an existing result in raw
    existing_result = {
        "extraction": {"vendor": "Cached Inc", "line_items": []},
        "flags": {},
        "needs_review": False,
        "meta": {"model": "m", "latency_ms": 1, "input_tokens": 10, "output_tokens": 10, "pages_sent": [1], "repaired": False, "source": "image"},
        "error": None,
    }
    (raw_dir / "doc1__image.json").write_text(json.dumps(existing_result), encoding="utf-8")

    # Run without force: pipeline should NOT be called for doc1__image
    with patch("evaluation.pipeline_runner.run_pipeline_on_file") as mock_pipeline:
        mock_pipeline.return_value = PipelineResult(
            extraction=None, flags={}, needs_review=True, meta=None, error={"code": "MOCK", "message": "m"}
        )
        cmd_run(only="doc1")

        # The image case was cached, so it wasn't called
        called_args = [call.args for call in mock_pipeline.call_args_list]
        called_modes = [call.kwargs.get("mode") for call in mock_pipeline.call_args_list]
        assert "image" not in called_modes


def test_runner_stops_at_token_cap(tmp_path, monkeypatch):
    """cmd_run stops cleanly before exceeding EVAL_DAILY_TOKEN_CAP."""
    mock_eval = tmp_path / "eval"
    data_dir = mock_eval / "data"
    data_dir.mkdir(parents=True)

    monkeypatch.setenv("EVAL_DIR", str(mock_eval))
    monkeypatch.setenv("EVAL_DAILY_TOKEN_CAP", "100")  # Very low cap
    monkeypatch.setattr("time.sleep", lambda s: None)

    (data_dir / "doc1.pdf").write_bytes(b"%PDF-1.4 dummy")

    with patch("evaluation.pipeline_runner.run_pipeline_on_file") as mock_pipeline:
        ret = cmd_run()
        assert ret == 0  # Clean stop
        assert mock_pipeline.call_count == 0  # 0 calls because estimated tokens (4000) > 100


# ---------------------------------------------------------------------------
# Report & Privacy Tests (Step A7 & A8)
# ---------------------------------------------------------------------------

from evaluation.report import cmd_report, cmd_timing


def test_report_contains_no_private_strings(tmp_path, monkeypatch):
    """Report contains ONLY aggregate numbers, never vendor names, invoice numbers, or amounts."""
    mock_eval = tmp_path / "eval"
    gt_dir = mock_eval / "ground_truth"
    raw_dir = mock_eval / "results" / "raw"
    report_dir = mock_eval / "report"

    gt_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)

    monkeypatch.setenv("EVAL_DIR", str(mock_eval))

    secret_vendor = "SuperSecretVendorCorporation"
    secret_invoice_num = "INV-CONFIDENTIAL-9999"
    secret_amount = 765432.19

    # Write ground truth
    gt_data = {
        "doc_id": "secret_doc",
        "source_file": "secret.pdf",
        "document_kind": "digital_pdf",
        "_status": "verified",
        "expected": {
            "vendor": secret_vendor,
            "invoice_number": secret_invoice_num,
            "date": "2026-11-05",
            "currency": "USD",
            "total": secret_amount,
            "line_items": [
                {
                    "description": "Secret Item",
                    "quantity": 1.0,
                    "unit_price": secret_amount,
                    "amount": secret_amount,
                }
            ],
        },
    }
    (gt_dir / "secret_doc.json").write_text(json.dumps(gt_data), encoding="utf-8")

    # Write raw output
    raw_data = {
        "extraction": {
            "vendor": secret_vendor,
            "invoice_number": secret_invoice_num,
            "date": "2026-11-05",
            "currency": "USD",
            "total": secret_amount,
            "line_items": [
                {
                    "description": "Secret Item",
                    "quantity": 1.0,
                    "unit_price": secret_amount,
                    "amount": secret_amount,
                }
            ],
        },
        "flags": {},
        "needs_review": False,
        "meta": {
            "model": "test-model",
            "latency_ms": 120,
            "input_tokens": 500,
            "output_tokens": 100,
            "pages_sent": [1],
            "repaired": False,
            "source": "image",
        },
        "error": None,
    }
    (raw_dir / "secret_doc__image.json").write_text(json.dumps(raw_data), encoding="utf-8")

    # Generate report
    ret = cmd_report()
    assert ret == 0

    summary_file = report_dir / "summary.md"
    assert summary_file.is_file()
    summary_text = summary_file.read_text(encoding="utf-8")

    # PRIVACY ASSERTIONS: zero private values in markdown report
    assert secret_vendor not in summary_text
    assert secret_invoice_num not in summary_text
    assert str(secret_amount) not in summary_text
    assert "secret.pdf" not in summary_text

    # Structure assertions
    assert "## 1. Setup & Environment" in summary_text
    assert "## 2. Header-Field Accuracy" in summary_text
    assert "## 4. Review Flag & Validator Effectiveness" in summary_text
    assert "## 5. Latency, Token Usage & Capacity" in summary_text
    assert "## 6. Limitations" in summary_text


def test_timing_command(tmp_path):
    """cmd_timing computes mean seconds and percentage reduction."""
    timing_csv = tmp_path / "timing.csv"
    timing_csv.write_text(
        "doc_id,method,seconds,errors_left,notes\n"
        "doc1,manual,100,0,\n"
        "doc1,tool,25,0,\n"
        "doc2,manual,200,0,\n"
        "doc2,tool,75,0,\n",
        encoding="utf-8",
    )
    ret = cmd_timing(csv_path=str(timing_csv))
    assert ret == 0


def test_timing_command_empty_prints_no_timing_data_yet(tmp_path, capsys):
    """cmd_timing prints 'No timing data yet' when CSV has only header and no data rows."""
    empty_csv = tmp_path / "timing_empty.csv"
    empty_csv.write_text("doc_id,method,seconds,errors_left,notes\n", encoding="utf-8")
    ret = cmd_timing(csv_path=str(empty_csv))
    assert ret == 0
    captured = capsys.readouterr()
    assert "No timing data yet" in captured.out


# ---------------------------------------------------------------------------
# Tests: Ground Truth Sanity Checks (Warnings Only)
# ---------------------------------------------------------------------------

def test_sanity_check_line_item_sum_differs():
    """(a) Warn when sum of line-item amounts differs from both subtotal and total by > 0.02."""
    data_match_sub = {
        "expected": {
            "subtotal": 100.0,
            "total": 118.0,
            "date": "2026-11-01",
            "invoice_number": "INV123",
            "line_items": [{"amount": 100.0}],
        }
    }
    assert not any("line_items.amount" in w for w in sanity_check_ground_truth(data_match_sub))

    data_match_tot = {
        "expected": {
            "subtotal": 100.0,
            "total": 118.0,
            "date": "2026-11-01",
            "invoice_number": "INV123",
            "line_items": [{"amount": 118.0}],
        }
    }
    assert not any("line_items.amount" in w for w in sanity_check_ground_truth(data_match_tot))

    data_mismatch = {
        "expected": {
            "subtotal": 100.0,
            "total": 118.0,
            "date": "2026-11-01",
            "invoice_number": "INV123",
            "line_items": [{"amount": 50.0}],
        }
    }
    warns = sanity_check_ground_truth(data_mismatch)
    assert any("line_items.amount" in w for w in warns)
    assert any("50.00" in w and "subtotal" in w and "total" in w for w in warns)


def test_sanity_check_subtotal_tax_total_mismatch():
    """(b) Warn when subtotal + tax differs from total by > 0.02 when prices_include_tax is not true."""
    data_valid = {
        "expected": {
            "subtotal": 100.0,
            "tax": 18.0,
            "total": 118.0,
            "prices_include_tax": False,
            "date": "2026-11-01",
            "invoice_number": "INV123",
            "line_items": [{"amount": 100.0}],
        }
    }
    assert not any("total: subtotal" in w for w in sanity_check_ground_truth(data_valid))

    data_mismatch = {
        "expected": {
            "subtotal": 100.0,
            "tax": 18.0,
            "total": 125.0,
            "prices_include_tax": False,
            "date": "2026-11-01",
            "invoice_number": "INV123",
            "line_items": [{"amount": 100.0}],
        }
    }
    warns = sanity_check_ground_truth(data_mismatch)
    assert any("total: subtotal" in w for w in warns)

    data_tax_incl = {
        "expected": {
            "subtotal": 100.0,
            "tax": 18.0,
            "total": 100.0,
            "prices_include_tax": True,
            "date": "2026-11-01",
            "invoice_number": "INV123",
            "line_items": [{"amount": 100.0}],
        }
    }
    assert not any("total: subtotal" in w for w in sanity_check_ground_truth(data_tax_incl))


def test_sanity_check_gst_components_mismatch():
    """(c) Warn when cgst + sgst + igst + cess differs from tax by > 0.02."""
    data_valid = {
        "expected": {
            "tax": 18.0,
            "cgst": 9.0,
            "sgst": 9.0,
            "date": "2026-11-01",
            "invoice_number": "INV123",
            "line_items": [{"amount": 18.0}],
        }
    }
    assert not any("tax:" in w and "cgst" in w for w in sanity_check_ground_truth(data_valid))

    data_mismatch = {
        "expected": {
            "tax": 18.0,
            "cgst": 9.0,
            "sgst": 8.0,
            "date": "2026-11-01",
            "invoice_number": "INV123",
            "line_items": [{"amount": 18.0}],
        }
    }
    warns = sanity_check_ground_truth(data_mismatch)
    assert any("tax:" in w and "cgst" in w for w in warns)


def test_sanity_check_date_invalid_or_future():
    """(d) Warn when date is invalid ISO format or lies in the future."""
    from datetime import date as d_class
    ref_today = d_class(2026, 11, 14)

    data_past = {"expected": {"date": "2026-11-01", "line_items": [{"amount": 10}]}}
    assert not any("date:" in w for w in sanity_check_ground_truth(data_past, today=ref_today))

    data_future = {"expected": {"date": "2026-11-20", "line_items": [{"amount": 10}]}}
    warns = sanity_check_ground_truth(data_future, today=ref_today)
    assert any("date: '2026-11-20' lies in the future" in w for w in warns)

    data_invalid = {"expected": {"date": "14/11/2026", "line_items": [{"amount": 10}]}}
    warns_inv = sanity_check_ground_truth(data_invalid, today=ref_today)
    assert any("date: '14/11/2026' is not a valid ISO date" in w for w in warns_inv)

    data_none = {"expected": {"date": None, "line_items": [{"amount": 10}]}}
    warns_none = sanity_check_ground_truth(data_none, today=ref_today)
    assert any("date: 'None' is not a valid ISO date" in w for w in warns_none)


def test_sanity_check_invoice_number_contains_spaces():
    """(e) Warn when invoice_number contains spaces."""
    data_spaces = {"expected": {"invoice_number": "INV 001 2026", "line_items": [{"amount": 10}], "date": "2026-11-01"}}
    warns = sanity_check_ground_truth(data_spaces)
    assert any("invoice_number: 'INV 001 2026' contains spaces" in w for w in warns)

    data_no_spaces = {"expected": {"invoice_number": "INV-001-2026", "line_items": [{"amount": 10}], "date": "2026-11-01"}}
    assert not any("invoice_number:" in w for w in sanity_check_ground_truth(data_no_spaces))


def test_sanity_check_zero_line_items():
    """(f) Warn when there are zero line items."""
    data_zero = {"expected": {"line_items": [], "date": "2026-11-01", "invoice_number": "123"}}
    warns = sanity_check_ground_truth(data_zero)
    assert any("line_items: contains zero line items" in w for w in warns)

    data_missing = {"expected": {"date": "2026-11-01", "invoice_number": "123"}}
    warns_missing = sanity_check_ground_truth(data_missing)
    assert any("line_items: contains zero line items" in w for w in warns_missing)


def test_sanity_check_draft_notes_exists():
    """(g) Warn when _draft_notes still exists."""
    data_with_notes = {
        "_draft_notes": "Needs review on shipping discount",
        "expected": {"line_items": [{"amount": 10}], "date": "2026-11-01", "invoice_number": "123"},
    }
    warns = sanity_check_ground_truth(data_with_notes)
    assert any("_draft_notes: draft notes field still exists" in w for w in warns)

    data_without = {
        "expected": {"line_items": [{"amount": 10}], "date": "2026-11-01", "invoice_number": "123"},
    }
    assert not any("_draft_notes:" in w for w in sanity_check_ground_truth(data_without))


def test_cmd_check_gt_prints_sanity_warnings_without_changing_status(tmp_path, capsys, monkeypatch):
    """cmd_check_gt prints warnings with field names and does not alter validation status."""
    gt_dir = tmp_path / "ground_truth"
    data_dir = tmp_path / "data"
    gt_dir.mkdir()
    data_dir.mkdir()

    (data_dir / "inv.pdf").write_text("dummy", encoding="utf-8")

    gt_content = {
        "doc_id": "inv",
        "source_file": "inv.pdf",
        "document_kind": "digital_pdf",
        "_status": "verified",
        "_draft_notes": "Unverified vendor",
        "expected": {
            "vendor": "Acme",
            "invoice_number": "INV 100",
            "date": "2026-11-01",
            "currency": "USD",
            "subtotal": 100.0,
            "taxable_amount": 100.0,
            "cgst": None,
            "sgst": None,
            "igst": None,
            "cess": None,
            "tax": None,
            "total": 100.0,
            "prices_include_tax": False,
            "line_items": [{"description": "Item", "quantity": 1, "unit_price": 100.0, "amount": 100.0}],
        },
    }
    (gt_dir / "inv.json").write_text(json.dumps(gt_content), encoding="utf-8")

    monkeypatch.setenv("EVAL_DIR", str(tmp_path))

    ret = cmd_check_gt()
    assert ret == 0

    captured = capsys.readouterr().out
    assert "✓ inv.json" in captured
    assert "Sanity Check Warnings (1 file(s)):" in captured
    assert "_draft_notes: draft notes field still exists" in captured
    assert "invoice_number: 'INV 100' contains spaces" in captured


def test_cmd_diff_prints_field_diff_and_unmatched_items(tmp_path, capsys, monkeypatch):
    """cmd_diff prints field-by-field expected/predicted diff and line-item matching details."""
    from evaluation.scoring import cmd_diff

    gt_dir = tmp_path / "ground_truth"
    raw_dir = tmp_path / "results" / "raw"
    gt_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)

    gt_data = {
        "doc_id": "docX",
        "expected": {
            "vendor": "Acme Tools",
            "invoice_number": "INV-100",
            "total": 100.0,
            "line_items": [
                {"description": "Item 1", "quantity": 1, "unit_price": 50.0, "amount": 50.0},
                {"description": "Item 2", "quantity": 1, "unit_price": 50.0, "amount": 50.0},
            ],
        },
    }
    (gt_dir / "docX.json").write_text(json.dumps(gt_data), encoding="utf-8")

    raw_data = {
        "extraction": {
            "vendor": "Acme Tools",  # Correct
            "invoice_number": "INV-100",  # Correct
            "total": 90.0,  # Wrong
            "line_items": [
                {"description": "Item 1", "quantity": 1, "unit_price": 50.0, "amount": 50.0},  # Matches Item 1
                {"description": "Item Extra", "quantity": 1, "unit_price": 40.0, "amount": 40.0},  # Extra
            ],
        },
        "flags": {},
        "needs_review": False,
    }
    (raw_dir / "docX__text.json").write_text(json.dumps(raw_data), encoding="utf-8")

    monkeypatch.setenv("EVAL_DIR", str(tmp_path))

    # Missing case returns 1
    assert cmd_diff("nonexistent__text") == 1
    err_out = capsys.readouterr().out
    assert "Result file not found" in err_out

    # Valid case returns 0 and prints full diff
    ret = cmd_diff("docX__text")
    assert ret == 0

    out = capsys.readouterr().out
    assert "Case Diff: docX__text (Document: docX)" in out
    assert "vendor" in out and "✓ CORRECT" in out
    assert "total" in out and "✗ WRONG" in out
    assert "Expected count:   2" in out
    assert "Predicted count:  2" in out
    assert "Matched count:    1" in out
    assert "Item Recall:      50.0%" in out
    assert "Item Precision:   50.0%" in out
    assert "Unmatched Expected Items (1):" in out
    assert "Item 2" in out
    assert "Unmatched Predicted Items (1):" in out
    assert "Item Extra" in out


# ---------------------------------------------------------------------------
# Extended Report Views Tests (Task 10)
# ---------------------------------------------------------------------------

from evaluation.report import (
    compute_document_bootstrap,
    is_flag_only_on_ignore,
    generate_report_markdown,
    cmd_causes_template,
)


def test_bootstrap_is_deterministic():
    """Bootstrap confidence intervals are deterministic for a given random seed."""
    cases_by_doc = {
        "doc1": [
            {"critical_correct": True, "all_header_correct": True, "wrong_header_count": 0, "classification": "TN"},
            {"critical_correct": True, "all_header_correct": False, "wrong_header_count": 1, "classification": "TP"},
        ],
        "doc2": [
            {"critical_correct": False, "all_header_correct": False, "wrong_header_count": 3, "classification": "FN"},
        ],
        "doc3": [
            {"critical_correct": True, "all_header_correct": True, "wrong_header_count": 0, "classification": "TN"},
        ],
    }

    res1 = compute_document_bootstrap(cases_by_doc, seed=42, n_resamples=500)
    res2 = compute_document_bootstrap(cases_by_doc, seed=42, n_resamples=500)

    assert res1 == res2
    assert res1["critical_correct"]["mean"] == res2["critical_correct"]["mean"]
    assert res1["critical_correct"]["lower"] == res2["critical_correct"]["lower"]
    assert res1["critical_correct"]["upper"] == res2["critical_correct"]["upper"]
    assert res1["validator_recall"]["lower"] == res2["validator_recall"]["lower"]


def test_paired_comparison_counts():
    """Paired comparison accurately tallies text better / equal / worse based on wrong headers."""
    manifest = {
        "git_commit": "abc1234",
        "git_version": {"short_hash": "abc1234", "dirty": False, "nearest_tag": "v1.0"},
    }
    scored_cases = [
        # doc1: text has 0 wrong, image has 2 wrong -> text better
        {"doc_id": "doc1", "case_id": "doc1__text", "case_type": "text", "document_kind": "digital_pdf", "wrong_header_count": 0, "field_results": {"critical_correct": True, "all_header_correct": True}, "classification": "TN", "li_metrics": {"li_recall": 1.0}},
        {"doc_id": "doc1", "case_id": "doc1__image", "case_type": "image", "document_kind": "digital_pdf", "wrong_header_count": 2, "field_results": {"critical_correct": False, "all_header_correct": False}, "classification": "FN", "li_metrics": {"li_recall": 0.8}},
        # doc2: text has 1 wrong, image has 1 wrong -> equal
        {"doc_id": "doc2", "case_id": "doc2__text", "case_type": "text", "document_kind": "digital_pdf", "wrong_header_count": 1, "field_results": {"critical_correct": True, "all_header_correct": False}, "classification": "TN", "li_metrics": {"li_recall": 1.0}},
        {"doc_id": "doc2", "case_id": "doc2__image", "case_type": "image", "document_kind": "digital_pdf", "wrong_header_count": 1, "field_results": {"critical_correct": True, "all_header_correct": False}, "classification": "TN", "li_metrics": {"li_recall": 1.0}},
        # doc3: text has 3 wrong, image has 1 wrong -> text worse
        {"doc_id": "doc3", "case_id": "doc3__text", "case_type": "text", "document_kind": "digital_pdf", "wrong_header_count": 3, "field_results": {"critical_correct": False, "all_header_correct": False}, "classification": "FN", "li_metrics": {"li_recall": 0.5}},
        {"doc_id": "doc3", "case_id": "doc3__image", "case_type": "image", "document_kind": "digital_pdf", "wrong_header_count": 1, "field_results": {"critical_correct": True, "all_header_correct": False}, "classification": "TN", "li_metrics": {"li_recall": 1.0}},
    ]
    doc_kinds = {"digital_pdf": 3}

    md = generate_report_markdown(manifest, scored_cases, doc_kinds)

    assert "## 7. Paired Text vs Image Comparison (Digital PDFs Only, n=3)" in md
    assert "| **Text Better** (fewer wrong header fields) | 1 / 3 | 33.3% |" in md
    assert "| **Equal** (identical number of wrong header fields) | 1 / 3 | 33.3% |" in md
    assert "| **Text Worse** (more wrong header fields) | 1 / 3 | 33.3% |" in md


def test_auto_mode_case_selection():
    """mode=auto selection routes digital PDFs to text and photos/scans to image."""
    manifest = {
        "git_commit": "abc1234",
        "git_version": {"short_hash": "abc1234", "dirty": False, "nearest_tag": "v1.0"},
    }
    scored_cases = [
        # doc1 (digital_pdf) has both text and image; auto should pick text
        {"doc_id": "doc1", "case_id": "doc1__text", "case_type": "text", "document_kind": "digital_pdf", "field_results": {"critical_correct": True}, "classification": "TN", "wrong_header_count": 0},
        {"doc_id": "doc1", "case_id": "doc1__image", "case_type": "image", "document_kind": "digital_pdf", "field_results": {"critical_correct": False}, "classification": "FN", "wrong_header_count": 2},
        # doc2 (photo) has only image; auto should pick image
        {"doc_id": "doc2", "case_id": "doc2__image", "case_type": "image", "document_kind": "photo", "field_results": {"critical_correct": True}, "classification": "TN", "wrong_header_count": 0},
    ]
    doc_kinds = {"digital_pdf": 1, "photo": 1}

    md = generate_report_markdown(manifest, scored_cases, doc_kinds)

    assert "## 8. As-Deployed (mode=auto) View (n=2)" in md
    # Both selected cases have critical_correct=True, so 2/2
    assert "| **`critical_correct`** | **2/2** | **100.0%** |" in md


def test_ignore_only_flag_exclusion():
    """Flags firing exclusively on IGNORE fields are identified and excluded."""
    expected = {
        "vendor": "Acme Tools",
        "date": "2026-11-01",
        "total": "IGNORE",
        "line_items": [
            {"description": "Item 1", "quantity": "IGNORE", "unit_price": "IGNORE", "amount": 100.0},
            {"description": "Item 2", "quantity": 1.0, "unit_price": 50.0, "amount": 50.0},
        ],
    }

    # Header flag on IGNORE field -> True
    assert is_flag_only_on_ignore("total", {"code": "TOTAL_MISMATCH"}, expected) is True

    # Header flag on non-IGNORE field -> False
    assert is_flag_only_on_ignore("vendor", {"code": "REQUIRED_MISSING"}, expected) is False

    # Line item flag on item 0 where quantity/unit_price is IGNORE -> True
    assert is_flag_only_on_ignore("line_items[0].amount", {"code": "ITEM_MATH_MISMATCH"}, expected) is True

    # Line item flag on item 1 where quantity/unit_price are NOT IGNORE -> False
    assert is_flag_only_on_ignore("line_items[1].amount", {"code": "ITEM_MATH_MISMATCH"}, expected) is False


def test_causes_template_and_cause_counting(tmp_path, monkeypatch):
    """causes-template writes private error_causes.json and report tallies causes with unlabelled nulls."""
    eval_dir = tmp_path / "eval"
    results_dir = eval_dir / "results"
    raw_dir = results_dir / "raw"
    gt_dir = eval_dir / "ground_truth"
    report_dir = eval_dir / "report"

    results_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    gt_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)

    monkeypatch.setenv("EVAL_DIR", str(eval_dir))

    # Create synthetic doc with an error
    gt_data = {
        "doc_id": "testdoc",
        "source_file": "testdoc.pdf",
        "document_kind": "digital_pdf",
        "_status": "verified",
        "expected": {"vendor": "ExpectedVendor", "line_items": []},
    }
    (gt_dir / "testdoc.json").write_text(json.dumps(gt_data), encoding="utf-8")

    # Raw result with wrong vendor and needs_review=False -> FN (silent error)
    raw_data = {
        "extraction": {"vendor": "WrongVendor", "line_items": []},
        "flags": {},
        "needs_review": False,
        "meta": {"model": "m", "latency_ms": 100, "input_tokens": 10, "output_tokens": 10, "pages_sent": [1], "repaired": False, "source": "text"},
        "error": None,
    }
    (raw_dir / "testdoc__text.json").write_text(json.dumps(raw_data), encoding="utf-8")

    # Run causes-template
    ret = cmd_causes_template()
    assert ret == 0

    causes_file = results_dir / "error_causes.json"
    assert causes_file.is_file()
    causes_content = json.loads(causes_file.read_text(encoding="utf-8"))
    assert "testdoc__text" in causes_content
    assert causes_content["testdoc__text"] is None

    # Now label the cause and run report
    causes_content["testdoc__text"] = "vendor_naming"
    causes_file.write_text(json.dumps(causes_content), encoding="utf-8")

    (results_dir / "manifest.json").write_text(json.dumps({"cases": ["testdoc__text"]}), encoding="utf-8")
    ret_rep = cmd_report()
    assert ret_rep == 0

    summary_text = (report_dir / "summary.md").read_text(encoding="utf-8")
    assert "## 12. Validator Analysis (Extended)" in summary_text
    assert "| `vendor_naming` | 1 | 100.0% |" in summary_text
    assert "| `unlabelled` | 0 | 0.0% |" in summary_text


def test_report_contains_no_fixture_private_strings(tmp_path, monkeypatch):
    """Extended report contains zero vendor names, invoice numbers, amounts, or filenames from fixtures."""
    eval_dir = tmp_path / "eval"
    results_dir = eval_dir / "results"
    raw_dir = results_dir / "raw"
    gt_dir = eval_dir / "ground_truth"
    report_dir = eval_dir / "report"

    results_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    gt_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)

    monkeypatch.setenv("EVAL_DIR", str(eval_dir))

    private_vendor = "TopSecretCorporationXYZ"
    private_invoice_num = "INV-CONFIDENTIAL-8888"
    private_amount = 998877.66
    private_filename = "classified_invoice.pdf"

    gt_data = {
        "doc_id": "secret_doc",
        "source_file": private_filename,
        "document_kind": "digital_pdf",
        "_status": "verified",
        "expected": {
            "vendor": private_vendor,
            "invoice_number": private_invoice_num,
            "date": "2026-11-05",
            "currency": "USD",
            "total": private_amount,
            "line_items": [
                {"description": "Item", "quantity": 1.0, "unit_price": private_amount, "amount": private_amount}
            ],
        },
    }
    (gt_dir / "secret_doc.json").write_text(json.dumps(gt_data), encoding="utf-8")

    raw_data = {
        "extraction": {
            "vendor": private_vendor,
            "invoice_number": private_invoice_num,
            "date": "2026-11-05",
            "currency": "USD",
            "total": private_amount,
            "line_items": [
                {"description": "Item", "quantity": 1.0, "unit_price": private_amount, "amount": private_amount}
            ],
        },
        "flags": {},
        "needs_review": False,
        "meta": {"model": "m", "latency_ms": 100, "input_tokens": 10, "output_tokens": 10, "pages_sent": [1], "repaired": False, "source": "text"},
        "error": None,
    }
    (raw_dir / "secret_doc__text.json").write_text(json.dumps(raw_data), encoding="utf-8")

    (results_dir / "manifest.json").write_text(json.dumps({"cases": ["secret_doc__text"]}), encoding="utf-8")

    ret = cmd_report()
    assert ret == 0

    summary_text = (report_dir / "summary.md").read_text(encoding="utf-8")

    # Assert ZERO privacy leaks across the entire markdown report
    assert private_vendor not in summary_text
    assert private_invoice_num not in summary_text
    assert str(private_amount) not in summary_text
    assert private_filename not in summary_text
    assert "secret_doc" not in summary_text  # doc_id is also anonymized to Doc A






