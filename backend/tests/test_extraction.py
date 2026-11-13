"""Tests for Phase 3 extraction — all Groq API calls are mocked."""

import io
import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pymupdf
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app.config import settings
from app.errors import AppError
from app.schemas import InvoiceData, ExtractionMeta
from app.services.groq_extractor import (
    GroqExtractor,
    _strip_code_fences,
    _parse_invoice_json,
)
from app.services.extractor import select_pages, extract_document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_JSON = json.dumps({
    "vendor": "Acme Corp",
    "invoice_number": "INV-001",
    "date": "2025-03-15",
    "currency": "USD",
    "line_items": [
        {"description": "Widget A", "quantity": 2, "unit_price": 50.0, "amount": 100.0},
        {"description": "Widget B", "quantity": 1, "unit_price": 25.0, "amount": 25.0},
    ],
    "subtotal": 125.0,
    "tax": 12.5,
    "total": 137.5,
})

FENCED_JSON = f"```json\n{VALID_JSON}\n```"

INVALID_JSON = "{ this is not json at all }"

VALID_BUT_WRONG_SCHEMA = json.dumps({"unexpected_field": "value"})


def _make_mock_response(content: str, input_tokens: int = 100, output_tokens: int = 50):
    """Build a mock Groq chat completion response."""
    mock = MagicMock()
    mock.choices = [MagicMock()]
    mock.choices[0].message.content = content
    mock.usage = MagicMock()
    mock.usage.prompt_tokens = input_tokens
    mock.usage.completion_tokens = output_tokens
    return mock


def _make_png_bytes(width: int = 100, height: int = 100) -> bytes:
    """Create minimal PNG image bytes."""
    img = Image.new("RGB", (width, height), color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Unit tests: JSON parsing helpers
# ---------------------------------------------------------------------------

class TestStripCodeFences:
    def test_clean_json(self):
        assert _strip_code_fences('{"a": 1}') == '{"a": 1}'

    def test_json_fences(self):
        assert _strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_plain_fences(self):
        assert _strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_whitespace(self):
        assert _strip_code_fences('  ```json\n  {"a": 1}  \n  ```  ') == '{"a": 1}'


class TestParseInvoiceJson:
    def test_valid(self):
        result = _parse_invoice_json(VALID_JSON)
        assert isinstance(result, InvoiceData)
        assert result.vendor == "Acme Corp"
        assert result.total == 137.5
        assert len(result.line_items) == 2

    def test_fenced(self):
        result = _parse_invoice_json(FENCED_JSON)
        assert result.vendor == "Acme Corp"

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            _parse_invoice_json(INVALID_JSON)

    def test_extra_fields_accepted(self):
        """InvoiceData should accept unknown fields gracefully (Pydantic default)."""
        data = json.dumps({"vendor": "Test", "total": 10.0, "extra_field": "ignored"})
        result = _parse_invoice_json(data)
        assert result.vendor == "Test"


# ---------------------------------------------------------------------------
# Unit tests: Page selection
# ---------------------------------------------------------------------------

class TestPageSelection:
    def _setup_pages(self, tmp_path: Path, count: int) -> Path:
        """Create dummy page PNGs in a temp directory."""
        for i in range(1, count + 1):
            (tmp_path / f"page_{i}.png").write_bytes(_make_png_bytes())
        return tmp_path

    def test_single_page(self, tmp_path):
        doc_dir = self._setup_pages(tmp_path, 1)
        images, pages = select_pages(doc_dir, 1)
        assert len(images) == 1
        assert pages == [1]

    def test_two_pages(self, tmp_path):
        doc_dir = self._setup_pages(tmp_path, 2)
        images, pages = select_pages(doc_dir, 2)
        assert len(images) == 2
        assert pages == [1, 2]

    def test_five_pages_selects_first_and_last(self, tmp_path):
        doc_dir = self._setup_pages(tmp_path, 5)
        images, pages = select_pages(doc_dir, 5)
        assert len(images) == 2
        assert pages == [1, 5]


# ---------------------------------------------------------------------------
# Unit tests: GroqExtractor with mocked client
# ---------------------------------------------------------------------------

class TestGroqExtractor:
    @patch("app.services.groq_extractor.Groq")
    def test_valid_json_response(self, MockGroq):
        """Valid JSON response -> correct InvoiceData."""
        mock_client = MagicMock()
        MockGroq.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_mock_response(VALID_JSON)

        extractor = GroqExtractor()
        images = [_make_png_bytes()]
        invoice, meta = extractor.extract(images)

        assert invoice.vendor == "Acme Corp"
        assert invoice.total == 137.5
        assert len(invoice.line_items) == 2
        assert meta.repaired is False
        assert meta.input_tokens == 100
        assert meta.output_tokens == 50

    @patch("app.services.groq_extractor.Groq")
    def test_fenced_json_parsed(self, MockGroq):
        """Response wrapped in ```json fences -> parsed correctly."""
        mock_client = MagicMock()
        MockGroq.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_mock_response(FENCED_JSON)

        extractor = GroqExtractor()
        invoice, meta = extractor.extract([_make_png_bytes()])

        assert invoice.vendor == "Acme Corp"
        assert meta.repaired is False

    @patch("app.services.groq_extractor.Groq")
    def test_invalid_then_valid_repair(self, MockGroq):
        """Invalid JSON first, valid on repair -> repaired=True."""
        mock_client = MagicMock()
        MockGroq.return_value = mock_client
        mock_client.chat.completions.create.side_effect = [
            _make_mock_response(INVALID_JSON, 100, 10),
            _make_mock_response(VALID_JSON, 200, 50),
        ]

        extractor = GroqExtractor()
        invoice, meta = extractor.extract([_make_png_bytes()])

        assert invoice.vendor == "Acme Corp"
        assert meta.repaired is True
        assert meta.input_tokens == 300  # 100 + 200
        assert meta.output_tokens == 60  # 10 + 50

    @patch("app.services.groq_extractor.Groq")
    def test_invalid_twice_raises(self, MockGroq):
        """Invalid JSON both times -> LLM_BAD_OUTPUT."""
        mock_client = MagicMock()
        MockGroq.return_value = mock_client
        mock_client.chat.completions.create.side_effect = [
            _make_mock_response(INVALID_JSON),
            _make_mock_response("still not valid json {{{"),
        ]

        extractor = GroqExtractor()
        with pytest.raises(AppError) as exc_info:
            extractor.extract([_make_png_bytes()])
        assert exc_info.value.code == "LLM_BAD_OUTPUT"
        assert exc_info.value.status_code == 502

    @patch("app.services.groq_extractor.Groq")
    def test_rate_limit_then_success(self, MockGroq):
        """429 then success -> retried after the (mocked) wait."""
        from groq import RateLimitError

        mock_client = MagicMock()
        MockGroq.return_value = mock_client

        # Create a rate limit error with a mock response
        mock_response = MagicMock()
        mock_response.headers = {"retry-after": "1"}
        mock_response.status_code = 429
        rate_err = RateLimitError(
            message="rate limit", response=mock_response, body=None
        )

        mock_client.chat.completions.create.side_effect = [
            rate_err,
            _make_mock_response(VALID_JSON),
        ]

        extractor = GroqExtractor()
        with patch("app.services.groq_extractor.time.sleep") as mock_sleep:
            invoice, meta = extractor.extract([_make_png_bytes()])

        assert invoice.vendor == "Acme Corp"
        mock_sleep.assert_called_once_with(1)

    @patch("app.services.groq_extractor.Groq")
    def test_rate_limit_exhausted(self, MockGroq):
        """429 every time -> RATE_LIMITED error."""
        from groq import RateLimitError

        mock_client = MagicMock()
        MockGroq.return_value = mock_client

        mock_response = MagicMock()
        mock_response.headers = {"retry-after": "1"}
        mock_response.status_code = 429
        rate_err = RateLimitError(
            message="rate limit", response=mock_response, body=None
        )

        # Will be called 1 initial + GROQ_MAX_RETRIES times
        mock_client.chat.completions.create.side_effect = rate_err

        extractor = GroqExtractor()
        with patch("app.services.groq_extractor.time.sleep"):
            with pytest.raises(AppError) as exc_info:
                extractor.extract([_make_png_bytes()])
        assert exc_info.value.code == "RATE_LIMITED"
        assert exc_info.value.status_code == 429

    @patch("app.services.groq_extractor.Groq")
    def test_auth_error(self, MockGroq):
        """Authentication error -> LLM_AUTH_ERROR."""
        from groq import AuthenticationError

        mock_client = MagicMock()
        MockGroq.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 401
        auth_err = AuthenticationError(
            message="invalid key", response=mock_response, body=None
        )
        mock_client.chat.completions.create.side_effect = auth_err

        extractor = GroqExtractor()
        with pytest.raises(AppError) as exc_info:
            extractor.extract([_make_png_bytes()])
        assert exc_info.value.code == "LLM_AUTH_ERROR"
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Tests: Missing/placeholder API key
# ---------------------------------------------------------------------------

class TestMissingApiKey:
    def test_placeholder_key_fails_clearly(self):
        """Missing/placeholder API key -> clear error, no crash."""
        from app.services.extractor import get_extractor

        with patch.object(type(settings), "groq_api_key_valid", new_callable=PropertyMock, return_value=False):
            with pytest.raises(AppError) as exc_info:
                get_extractor()
            assert exc_info.value.code == "LLM_AUTH_ERROR"
            assert "GROQ_API_KEY" in exc_info.value.message


# ---------------------------------------------------------------------------
# Integration tests: Route returns extraction_error with previews
# ---------------------------------------------------------------------------

class TestRouteExtractionError:
    def test_route_returns_200_with_extraction_error(self):
        """Route returns 200 with extraction_error when extractor raises, previews still included."""
        client = TestClient(__import__("app.main", fromlist=["app"]).app, raise_server_exceptions=False)

        # Create a valid 1-page PDF
        doc = pymupdf.open()
        page = doc.new_page(width=200, height=300)
        page.insert_text((20, 20), "Test Invoice")
        pdf_bytes = doc.tobytes()
        doc.close()

        # Mock get_extractor to fail — but after preprocessing succeeds
        with patch("app.routes.extract.extract_document") as mock_extract:
            mock_extract.side_effect = AppError(
                code="RATE_LIMITED",
                message="The free AI quota is temporarily used up. Please try again in a minute.",
                status_code=429,
            )

            response = client.post(
                "/api/extract",
                files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["extraction"] is None
        assert data["extraction_error"]["code"] == "RATE_LIMITED"
        assert data["extraction_error"]["message"].startswith("The free AI quota")
        assert data["document_id"] is not None
        assert len(data["pages"]) == 1
        assert data["pages"][0]["preview_url"].endswith("1.png")



# ---------------------------------------------------------------------------
# Tests: GST derivation and text-first extraction
# ---------------------------------------------------------------------------

class TestGstDerivationAndTextMode:
    def test_derive_invoice_fields_from_gst(self):
        """Derive total tax from cgst + sgst and subtotal from taxable_amount."""
        from app.schemas import derive_invoice_fields

        invoice = InvoiceData(
            vendor="Retail Supermarket Ltd",
            date="2026-11-05",
            currency="INR",
            total=1582.0,
            taxable_amount=1521.94,
            cgst=30.03,
            sgst=30.03,
            tax=None,       # Missing, should be derived
            subtotal=None,  # Missing, should be derived
            prices_include_tax=True,
        )
        derived = derive_invoice_fields(invoice)
        assert derived.tax == 60.06
        assert derived.subtotal == 1521.94
        assert derived.total == 1582.0

    @patch("app.services.groq_extractor.Groq")
    def test_text_first_extraction_mode(self, MockGroq):
        """When source='text', text prompt is constructed and meta.source='text'."""
        mock_client = MagicMock()
        MockGroq.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_mock_response(VALID_JSON)

        extractor = GroqExtractor()
        doc_text = "Sample Digital PDF Text Content Invoice #123"
        invoice, meta = extractor.extract(
            page_images=[_make_png_bytes()],
            text_content=doc_text,
            source="text",
        )

        assert meta.source == "text"
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["seed"] == settings.groq_seed
        messages = call_kwargs["messages"]
        user_content = messages[0]["content"]
        # Verify no image_url block was sent
        for block in user_content:
            assert block["type"] != "image_url"
            if block["type"] == "text":
                assert "DOCUMENT TEXT" in block["text"]
                assert doc_text in block["text"]

    @patch("app.services.groq_extractor.Groq")
    def test_image_extraction_mode(self, MockGroq):
        """When source='image', images are converted to data URLs and meta.source='image'."""
        mock_client = MagicMock()
        MockGroq.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_mock_response(VALID_JSON)

        extractor = GroqExtractor()
        invoice, meta = extractor.extract(
            page_images=[_make_png_bytes()],
            source="image",
        )

        assert meta.source == "image"
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["seed"] == settings.groq_seed
        messages = call_kwargs["messages"]
        user_content = messages[0]["content"]
        has_image = any(b["type"] == "image_url" for b in user_content)
        assert has_image is True
