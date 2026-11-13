"""Groq-based document extraction implementation."""

import json
import logging
import re
import threading
import time

from groq import Groq, RateLimitError, AuthenticationError, APITimeoutError, APIConnectionError, InternalServerError

from app.config import settings
from app.errors import AppError
from app.schemas import InvoiceData, ExtractionMeta
from app.services.extractor import Extractor, images_to_base64_urls

logger = logging.getLogger("doc_extractor")

# Serialize all Groq calls (one at a time) for rate-limit safety
_groq_lock = threading.Lock()

EXTRACTION_PROMPT = """\
You are a precise data-extraction assistant for invoices and receipts.

Examine the provided document image(s) carefully and extract all visible information into a single JSON object with exactly this structure:

{
  "vendor": string or null,
  "invoice_number": string or null,
  "date": string or null,
  "currency": string or null,
  "line_items": [
    {
      "description": string,
      "quantity": number or null,
      "unit_price": number or null,
      "amount": number or null
    }
  ],
  "subtotal": number or null,
  "tax": number or null,
  "total": number or null
}

Rules:
- Output ONLY one JSON object. No markdown, no commentary, no explanation.
- Use null for any field whose value is not clearly visible in the document. Never guess or calculate missing values.
- "date" must be in YYYY-MM-DD format (ISO 8601).
- Numbers must be plain numbers without currency symbols, thousands separators, or formatting. Example: 1234.56 not "$1,234.56".
- "currency" must be a 3-letter ISO 4217 code (e.g. INR, USD, EUR, GBP).
- Copy text exactly as printed on the document (vendor name, descriptions, invoice number).
- If multiple pages are provided, they belong to the same document — combine all information into one JSON object.
- "line_items" should list every individual item/service line visible. Use an empty array [] if none are visible.
"""

REPAIR_PROMPT_TEMPLATE = """\
The previous JSON output had a validation error:
{error}

Please output ONLY the corrected JSON object with the same schema. No explanation, no markdown fences.
"""


def _strip_code_fences(text: str) -> str:
    """Remove accidental markdown code fences from LLM output."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _parse_invoice_json(raw_text: str) -> InvoiceData:
    """Parse and validate raw JSON text into InvoiceData.

    Raises:
        ValueError: If parsing or validation fails, with a descriptive message.
    """
    cleaned = _strip_code_fences(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    return InvoiceData.model_validate(data)


def _build_user_content(base64_urls: list[str]) -> list[dict]:
    """Build the multimodal user message content with text + images."""
    content: list[dict] = [{"type": "text", "text": EXTRACTION_PROMPT}]
    for url in base64_urls:
        content.append({
            "type": "image_url",
            "image_url": {"url": url},
        })
    return content


class GroqExtractor(Extractor):
    """Extractor using the Groq API with vision-capable models."""

    def __init__(self) -> None:
        self._client = Groq(
            api_key=settings.groq_api_key,
            timeout=settings.groq_timeout_seconds,
        )

    def _call_groq(self, messages: list[dict]) -> tuple[str, int, int]:
        """Make a single Groq API call with rate-limit retry logic.

        Returns:
            Tuple of (response text, input tokens, output tokens).

        Raises:
            AppError: On auth, rate-limit, timeout, or server errors.
        """
        retries_left = settings.groq_max_retries

        while True:
            try:
                with _groq_lock:
                    response = self._client.chat.completions.create(
                        model=settings.groq_model,
                        messages=messages,
                        temperature=0,
                        max_completion_tokens=settings.groq_max_output_tokens,
                        response_format={"type": "json_object"},
                        reasoning_effort="none",
                    )

                text = response.choices[0].message.content or ""
                usage = response.usage
                input_tokens = usage.prompt_tokens if usage else 0
                output_tokens = usage.completion_tokens if usage else 0

                return text, input_tokens, output_tokens

            except AuthenticationError:
                raise AppError(
                    code="LLM_AUTH_ERROR",
                    message="AI service credentials are invalid.",
                    status_code=500,
                )

            except RateLimitError as exc:
                if retries_left <= 0:
                    raise AppError(
                        code="RATE_LIMITED",
                        message="The free AI quota is temporarily used up. Please try again in a minute.",
                        status_code=429,
                    )

                # Read retry-after from the response headers
                retry_after = 20  # default
                if hasattr(exc, "response") and exc.response is not None:
                    header_val = exc.response.headers.get("retry-after")
                    if header_val:
                        try:
                            retry_after = min(int(float(header_val)), 65)
                        except (ValueError, TypeError):
                            retry_after = 20

                logger.warning(
                    "Groq rate limited. Waiting %ds before retry (%d retries left).",
                    retry_after,
                    retries_left,
                )
                time.sleep(retry_after)
                retries_left -= 1

            except (APITimeoutError, APIConnectionError):
                raise AppError(
                    code="LLM_UNAVAILABLE",
                    message="AI service is temporarily unavailable. Please try again.",
                    status_code=502,
                )

            except InternalServerError:
                raise AppError(
                    code="LLM_UNAVAILABLE",
                    message="AI service encountered an internal error. Please try again.",
                    status_code=502,
                )

            except Exception as exc:
                logger.exception("Unexpected Groq API error: %s", type(exc).__name__)
                raise AppError(
                    code="LLM_UNAVAILABLE",
                    message="AI service encountered an unexpected error.",
                    status_code=502,
                )

    def extract(self, page_images: list[bytes]) -> tuple[InvoiceData, ExtractionMeta]:
        """Extract structured invoice data from page images using Groq vision.

        Args:
            page_images: List of PNG image bytes.

        Returns:
            Tuple of (extracted invoice data, extraction metadata).
        """
        base64_urls = images_to_base64_urls(page_images)

        user_content = _build_user_content(base64_urls)
        messages = [{"role": "user", "content": user_content}]

        start_ms = time.monotonic_ns() // 1_000_000

        raw_text, input_tokens, output_tokens = self._call_groq(messages)

        elapsed_ms = (time.monotonic_ns() // 1_000_000) - start_ms

        logger.info(
            "Groq extraction: model=%s latency=%dms input_tokens=%d output_tokens=%d",
            settings.groq_model,
            elapsed_ms,
            input_tokens,
            output_tokens,
        )

        repaired = False

        # First parse attempt
        try:
            invoice_data = _parse_invoice_json(raw_text)
        except ValueError as first_err:
            logger.warning("First parse failed: %s — attempting repair call", first_err)

            # Repair attempt: send the error back and ask for corrected JSON
            repair_messages = messages + [
                {"role": "assistant", "content": raw_text},
                {
                    "role": "user",
                    "content": REPAIR_PROMPT_TEMPLATE.format(error=str(first_err)),
                },
            ]

            repair_text, repair_input, repair_output = self._call_groq(repair_messages)
            input_tokens += repair_input
            output_tokens += repair_output
            elapsed_ms = (time.monotonic_ns() // 1_000_000) - start_ms

            try:
                invoice_data = _parse_invoice_json(repair_text)
                repaired = True
            except ValueError as second_err:
                logger.error("Repair parse also failed: %s", second_err)
                raise AppError(
                    code="LLM_BAD_OUTPUT",
                    message=f"AI produced invalid output that could not be repaired: {second_err}",
                    status_code=502,
                )

        meta = ExtractionMeta(
            model=settings.groq_model,
            latency_ms=elapsed_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            pages_sent=[],  # Will be filled by extract_document()
            repaired=repaired,
        )

        return invoice_data, meta

