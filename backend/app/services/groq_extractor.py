"""Groq-based document extraction implementation."""

import json
import logging
import re
import threading
import time

from groq import Groq, RateLimitError, AuthenticationError, APITimeoutError, APIConnectionError, InternalServerError

from app.config import settings, features_for
from app.errors import AppError
from app.schemas import InvoiceData, ExtractionMeta, derive_invoice_fields
from app.services.extractor import Extractor, images_to_base64_urls

logger = logging.getLogger("doc_extractor")

# Serialize all Groq calls (one at a time) for rate-limit safety
_groq_lock = threading.Lock()

PROMPT_V1 = """\
You are a precise data-extraction assistant for invoices and receipts.

Examine the provided document carefully and extract all visible information into a single JSON object with exactly this structure:

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
  "taxable_amount": number or null,
  "cgst": number or null,
  "sgst": number or null,
  "igst": number or null,
  "cess": number or null,
  "subtotal": number or null,
  "tax": number or null,
  "total": number or null,
  "prices_include_tax": boolean or null
}

Strict Rules:
1. Output ONLY one valid JSON object. No markdown fences, no commentary, no explanation.
2. Use null for any field whose value is not clearly visible in the document.
3. NEVER calculate, add, or sum numbers yourself. Extract numbers exactly as printed on the document. If a total tax amount is not printed as a single pre-calculated number, extract cgst, sgst, igst, and cess individually and leave "tax" as null (application code will derive the sum).
4. Date format: "date" must be in YYYY-MM-DD format (ISO 8601). If the printed date is e.g. "05-11-2026", convert it to "2026-11-05".
5. Numbers: Plain numbers only without currency symbols or thousands separators. Example: 1582.00 not "Rs. 1,582.00".
6. Currency: 3-letter ISO 4217 code (e.g. INR, USD, EUR, GBP).
7. Copy text (vendor name, item descriptions, invoice number) exactly as printed on the document. "Bill No.", "Invoice No." and "Tax Invoice#" all mean invoice_number; copy the digits exactly.
8. GST / Tax Summary Table Rule:
   - When a GST or tax breakdown table is present (e.g. columns for Taxable, CGST, SGST, IGST, CESS), extract amounts from the TOTAL row (often labelled with "T:", "Total", or at the bottom line).
   - "taxable_amount": total taxable value from the summary total row.
   - "cgst": total CGST amount from the summary total row.
   - "sgst": total SGST amount from the summary total row.
   - "igst": total IGST amount from the summary total row.
   - "cess": total CESS amount from the summary total row.
   - Do NOT extract individual tax rate sub-rows (e.g. 2.5%, 9%) as invoice-level totals.
9. Prices-Include-Tax Rule:
   - If the document states that item prices include taxes (e.g. "inclusive of GST", "prices include tax", "AMT INCL. OF APPLICABLE TAXES", "MRP incl."), or if line item amounts sum to the invoice total rather than the taxable amount, set "prices_include_tax": true.
10. Fused-Digit / Column Separation Rule:
    - Watch out for fused column digits or touch-aligned text (e.g. "1 590.00" where "1" is a rate/serial number and "590.00" is the monetary amount; or "Item: 8 QTY : 9 1582.00" where "1582.00" is the total sales value). Separate line item numbers, quantities, and rates from actual monetary amounts.
11. Multi-page: Combine all pages into one single complete JSON object.
"""

PROMPT_V2 = """\
You are a precise data-extraction assistant for invoices and receipts.

Examine the provided document carefully and extract all visible information into a single JSON object with exactly this structure:

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
  "taxable_amount": number or null,
  "cgst": number or null,
  "sgst": number or null,
  "igst": number or null,
  "cess": number or null,
  "subtotal": number or null,
  "tax": number or null,
  "total": number or null,
  "prices_include_tax": boolean or null
}

Strict Rules:
1. Output ONLY one valid JSON object. No markdown fences, no commentary, no explanation.
2. Use null for any field whose value is not clearly visible in the document.
3. NEVER calculate, add, or sum numbers yourself. Extract numbers exactly as printed on the document. If a total tax amount is not printed as a single pre-calculated number, extract cgst, sgst, igst, and cess individually and leave "tax" as null (application code will derive the sum).
4. Date format: "date" must be in YYYY-MM-DD format (ISO 8601). If the printed date is e.g. "05-11-2026", convert it to "2026-11-05".
5. Numbers: Plain numbers only without currency symbols or thousands separators. Example: 1582.00 not "Rs. 1,582.00".
6. Currency: 3-letter ISO 4217 code (e.g. INR, USD, EUR, GBP).
7. Copy text (vendor name, item descriptions, invoice number) exactly as printed on the document. "Bill No.", "Invoice No." and "Tax Invoice#" all mean invoice_number; copy the digits exactly.
8. GST / Tax Summary Table Rule:
   - When a GST or tax breakdown table is present (e.g. columns for Taxable, CGST, SGST, IGST, CESS), extract amounts from the TOTAL row (often labelled with "T:", "Total", or at the bottom line).
   - "taxable_amount": total taxable value from the summary total row.
   - "cgst": total CGST amount from the summary total row.
   - "sgst": total SGST amount from the summary total row.
   - "igst": total IGST amount from the summary total row.
   - "cess": total CESS amount from the summary total row.
   - Do NOT extract individual tax rate sub-rows (e.g. 2.5%, 9%) as invoice-level totals.
9. Prices-Include-Tax Rule:
   - If the document states that item prices include taxes (e.g. "inclusive of GST", "prices include tax", "AMT INCL. OF APPLICABLE TAXES", "MRP incl."), or if line item amounts sum to the invoice total rather than the taxable amount, set "prices_include_tax": true.
10. Fused-Digit / Column Separation Rule:
    - Watch out for fused column digits or touch-aligned text (e.g. "1 590.00" where "1" is a rate/serial number and "590.00" is the monetary amount; or "Item: 8 QTY : 9 1582.00" where "1582.00" is the total sales value). Separate line item numbers, quantities, and rates from actual monetary amounts.
11. Multi-page: Combine all pages into one single complete JSON object.
12. Vendor Identification Rule:
    - vendor = the legal name of the company that issues the invoice (the seller), e.g. the name next to "Sold by", "Registered office", GSTIN or CIN lines. Not a store brand banner, logo text or marketplace name unless it is the issuer.
13. Line Items Amount and Unit Price Rule:
    - amount = the line total printed in the right-most amount column of that item's row, copied as printed (it may include tax). unit_price = the per-unit price as printed. Never compute either.
"""


def get_extraction_prompt(version: str | None = None) -> str:
    """Return the extraction prompt for the specified or configured pipeline version."""
    feat = features_for(version)
    if feat.prompt_version == "v1":
        return PROMPT_V1
    return PROMPT_V2


EXTRACTION_PROMPT = get_extraction_prompt()

REPAIR_PROMPT_TEMPLATE = """\
The previous JSON output had a validation error:
{error}

Please output ONLY the corrected JSON object with the same schema. No explanation, no markdown fences.
"""


def _strip_code_fences(text: str) -> str:
    """Remove accidental markdown code fences from LLM output."""
    text = text.strip()
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


def _build_image_user_content(base64_urls: list[str], version: str | None = None) -> list[dict]:
    """Build the multimodal user message content with text instructions + image URLs."""
    prompt = get_extraction_prompt(version)
    content: list[dict] = [{"type": "text", "text": prompt}]
    for url in base64_urls:
        content.append({
            "type": "image_url",
            "image_url": {"url": url},
        })
    return content


def _build_text_user_content(text_content: str, version: str | None = None) -> list[dict]:
    """Build the text-only user message content with text instructions + document text."""
    prompt = get_extraction_prompt(version)
    prompt_with_text = (
        f"{prompt}\n\n"
        f"--- DOCUMENT TEXT ---\n"
        f"{text_content}\n"
        f"--- END OF DOCUMENT TEXT ---"
    )
    return [{"type": "text", "text": prompt_with_text}]


class GroqExtractor(Extractor):
    """Extractor using the Groq API supporting both text-first and vision modes."""

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
                        seed=settings.groq_seed,
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

                retry_after = 20
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

    def extract(
        self,
        page_images: list[bytes],
        text_content: str | None = None,
        source: str = "image",
        version: str | None = None,
    ) -> tuple[InvoiceData, ExtractionMeta]:
        """Extract structured invoice data from page images or text content using Groq.

        Args:
            page_images: List of PNG image bytes.
            text_content: Optional raw text layer from digital PDF.
            source: "text" or "image".
            version: Optional pipeline version override ("v1", "v2").

        Returns:
            Tuple of (extracted invoice data, extraction metadata).
        """
        if source == "text" and text_content:
            user_content = _build_text_user_content(text_content, version=version)
        else:
            base64_urls = images_to_base64_urls(page_images)
            user_content = _build_image_user_content(base64_urls, version=version)
            source = "image"

        messages = [{"role": "user", "content": user_content}]

        start_ms = time.monotonic_ns() // 1_000_000

        raw_text, input_tokens, output_tokens = self._call_groq(messages)

        elapsed_ms = (time.monotonic_ns() // 1_000_000) - start_ms

        logger.info(
            "Groq extraction: model=%s source=%s latency=%dms input_tokens=%d output_tokens=%d",
            settings.groq_model,
            source,
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

        # Derive tax and subtotal if missing based on GST breakdown
        invoice_data = derive_invoice_fields(invoice_data)

        meta = ExtractionMeta(
            model=settings.groq_model,
            latency_ms=elapsed_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            pages_sent=[],
            repaired=repaired,
            source=source,
        )

        return invoice_data, meta
