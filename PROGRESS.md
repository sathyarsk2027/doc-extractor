# Progress Log

## Step 0.1: Project Directory Structure
- **What changed**: Scaffolded the complete folder tree for `doc-extractor/` including `backend/app/`, `backend/app/routes/`, `backend/app/services/`, `backend/tests/`, `samples/`, and `eval/`. Added initial placeholder files, package inits, `samples/README.md`, and `eval/.gitkeep`.
- **Verification result**: Directory structure verified via filesystem traversal. All paths exist as specified.

## Step 0.2: Gitignore Setup
- **What changed**: Created `doc-extractor/.gitignore` covering `.env`, `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `node_modules/`, `dist/`, `backend/storage/`, `.pytest_cache/`, `.DS_Store`, and all files in `samples/` except `samples/README.md`. Initialized git repository.
- **Verification result**: Tested `git check-ignore` against `.env`, `.venv/`, `.pytest_cache/`, `samples/test.pdf`, and confirmed `samples/README.md` is retained.

## Step 0.3: Backend Virtual Environment and Dependencies
- **What changed**: Created `backend/.venv`, installed all pinned tech stack packages (FastAPI, uvicorn[standard], python-multipart, Pydantic v2, PyMuPDF, Pillow, python-dotenv, google-genai, pytest, httpx), exported pinned dependencies to `backend/requirements.txt`, created `backend/.env.example` with specified configuration keys, and created local untracked `backend/.env`.
- **Verification result**: Packages verified via `pip freeze` and pinned. `git status -u` confirms `backend/.env` and `.venv/` are strictly ignored while `backend/.env.example` is present.

## Step 0.4: Frontend Setup (Vite React)
- **What changed**: Scaffolded React frontend with Vite in `frontend/`, installed npm dependencies, configured dev proxy in `vite.config.js` to forward `/api` requests to `http://localhost:8000`.
- **Verification result**: Verified with `npm run build` which succeeded cleanly without errors (34 modules transformed, output in `dist/`).

## Step 0.5: Hello-World Checks & Verification for Phase 0
- **What changed**: Implemented `backend/app/main.py` with `GET /api/health` returning `{"status": "ok"}`, implemented `backend/app/config.py` loading typed environment settings with defaults, added `README.md` with Windows PowerShell run instructions.
- **Verification result**:
  - `uvicorn app.main:app` verified: `GET http://127.0.0.1:8000/api/health` returned `{"status":"ok"}` with HTTP 200.
  - `npm run dev` verified: `http://localhost:5173` returned HTTP 200 with HTML title match.
  - `git status --ignored` verified: `backend/.env`, `.venv/`, `node_modules/`, `dist/` are strictly ignored and not tracked.

## Step 1.1: Custom Exception and Standard Error Envelope
- **What changed**: Defined `AppError(code, message, status_code)` and `ErrorResponse` schema in `app/errors.py`. Registered exception handlers in `app/main.py` for `AppError`, `RequestValidationError`, `StarletteHTTPException`, and generic `Exception` to guarantee all error responses adhere to `{"error": {"code": "...", "message": "..."}}` with server-side logging and no client stack traces.
- **Verification result**: Tested custom `AppError` (HTTP 413, code `FILE_TOO_LARGE`), unhandled exceptions (HTTP 500, code `INTERNAL_ERROR`), and missing routes (HTTP 404, code `NOT_FOUND`). All returned valid structured JSON error envelopes with zero stack leaks.

## Step 1.2: File Validation Service
- **What changed**: Implemented `app/services/validation.py` featuring magic byte identification (`%PDF-`, `\x89PNG\r\n\x1a\n`, `\xff\xd8\xff`), chunk-based streamed size enforcement (`MAX_FILE_MB`), empty file rejection (`EMPTY_FILE`, 400), and filename sanitization stripping path traversal and control characters with length capped at 100 characters.
- **Verification result**: Verified via automated checks for PDF, PNG, JPEG magic headers, unsupported format rejection (HTTP 415), empty file rejection (HTTP 400), and directory traversal sanitization. All checks passed.

## Step 1.3: CORS Configuration
- **What changed**: Configured `CORSMiddleware` in `app/main.py` explicitly binding `allow_origins=[settings.frontend_origin]` (`http://localhost:5173`) with credentials, methods, and headers permitted.
- **Verification result**: Tested GET requests with origin headers. Confirmed `access-control-allow-origin: http://localhost:5173` is returned for the configured frontend origin, while arbitrary origins are rejected without CORS headers.

## Step 1.4 & 1.5: Extraction Route and Extractor Interface Stub
- **What changed**: Defined `ExtractResponse` and `PagePreview` schemas in `app/schemas.py`. Defined the stub interface in `app/services/extractor.py` returning `None` for LLM extraction. Implemented `POST /api/extract` in `app/routes/extract.py` and mounted it on the FastAPI application.
- **Verification result**: Verified route registration and schema compatibility.

## Step 1.6: Phase 1 Test Suite & Verification
- **What changed**: Implemented pytest fixtures in `backend/tests/conftest.py` generating in-memory test files (PyMuPDF PDF, Pillow PNG/JPEG, empty buffer, plain text, oversized payload). Implemented test suite in `backend/tests/test_upload.py` covering valid uploads, missing files (`NO_FILE`), empty files (`EMPTY_FILE`), non-supported files (`UNSUPPORTED_TYPE`), oversized payloads (`FILE_TOO_LARGE`), and strict JSON error envelopes.
- **Verification result**:
  - `pytest -q` passed 7/7 tests in 0.38s.
  - Live uvicorn server tested via `curl`:
    - Real PDF upload returned HTTP 200 with `ExtractResponse` JSON (`mime_type: "application/pdf"`, `extraction: null`).
    - Bad file upload returned HTTP 415 with standard error shape `{"error": {"code": "UNSUPPORTED_TYPE", "message": "..."}}`.

## Step 2.1: Temporary Document Storage and TTL Cleanup
- **What changed**: Implemented `backend/app/services/storage.py` providing UUID-isolated document directories (`{STORAGE_DIR}/{document_id}/`), `save_original` preserving untouched raw file bytes with MIME-derived extensions, `get_page_path` preventing directory traversal, `delete_document`, and `cleanup_expired` enforcing folder deletion for uploads older than `FILE_TTL_MINUTES`. Integrated TTL cleanup into app startup lifespan and before every upload.
- **Verification result**: Verified via unit tests: expired folders older than TTL are purged, active folders are retained, and non-UUID traversal requests return 404.

## Step 2.2: Document Preprocessing Service
- **What changed**: Implemented `backend/app/services/preprocessing.py`. PDFs are opened via PyMuPDF with checks for encryption (`PDF_ENCRYPTED`, 422), corruption or 0 pages (`CORRUPT_FILE`, 422), and page limits (`PDF_TOO_MANY_PAGES`, 422); each page is rendered to PNG at `PDF_RENDER_DPI`. Images are processed via Pillow with corruption checks, EXIF orientation correction (`ImageOps.exif_transpose`), mode conversion to RGB, proportional downscaling to `MAX_IMAGE_WIDTH` (never upscaling), and EXIF metadata stripping for privacy.
- **Verification result**: Verified via unit tests covering multi-page rendering, encryption rejection, corruption rejection, page limit enforcement, EXIF orientation transpositions, and downscaling limits.

## Step 2.3: File Preview Serving Endpoint
- **What changed**: Implemented `GET /api/files/{document_id}/pages/{page_number}.png` in `backend/app/routes/files.py`. Serves rendered PNG previews with `Cache-Control: private, max-age=300`. Strictly validates UUIDs and path safety, returning HTTP 404 with standard error JSON if missing or expired.
- **Verification result**: Verified via automated tests: valid previews return 200 with PNG bytes; non-UUID traversal attempts like `../../etc/passwd` return 404 `NOT_FOUND`.

## Step 2.4: Updated Extraction Endpoint Payload
- **What changed**: Updated `POST /api/extract` to save original file bytes, execute preprocessing, generate preview URLs, and return complete `ExtractResponse` with document ID, page previews, and message. Deletes partial directories if preprocessing fails midway.
- **Verification result**: Tested on live uvicorn server with real PDF, JPEG, and PNG files. Returned HTTP 200 with complete JSON metadata and preview URLs.

## Step 2.5: Minimal Smoke-Test Frontend Page
- **What changed**: Replaced Vite starter in `frontend/src/App.jsx` with a lean (<100 lines) smoke-test interface featuring file selection, upload button, loading indicator, error alert box (`error.message`), and responsive grid displaying rendered preview images. Added clean plain CSS in `frontend/src/App.css`.
- **Verification result**: `npm run build` completed successfully without warnings, transforming 32 modules into production assets.

## Step 2.6: Phase 2 Test Suite & End-to-End Verification
- **What changed**: Implemented comprehensive test suite in `backend/tests/test_preprocessing.py`.
- **Verification result**:
  - `pytest -v` passed all 16 tests across upload and preprocessing suites in 1.61s.
  - Uploaded 3 real files (`invoice.pdf`, `phone_photo.jpg`, `store_receipt.png`) against live backend server. Previews fetched with HTTP 200 and verified image headers.
  - Confirmed `.env` and `storage/` are completely untracked and excluded in `.gitignore`.

## Step 3.1: Config and Dependencies
- **What changed**: Installed `groq==1.7.0`, uninstalled `google-genai`, re-froze `requirements.txt`. Updated `.env.example` and `.env` with Groq config keys (`GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_TIMEOUT_SECONDS`, `GROQ_MAX_RETRIES`, `GROQ_MAX_OUTPUT_TOKENS`, `EXTRACTION_MAX_PAGES`). Updated `config.py` to load all new settings with defaults and added `groq_api_key_valid` property that rejects missing/placeholder keys.
- **Verification result**: `pip freeze` confirms `groq==1.7.0` present and `google-genai` absent. Config loads cleanly: `groq_api_key_valid=False` with placeholder, model/timeout/max_pages defaults correct.

## Step 3.2: Schemas
- **What changed**: Added `LineItem`, `InvoiceData`, `ExtractionMeta` models to `app/schemas.py`. Added `extraction_meta`, `extraction_error`, `flags`, and `needs_review` fields to `ExtractResponse`.
- **Verification result**: All models import and serialize correctly. `InvoiceData` with nested `LineItem` round-trips through `model_dump_json()`.

## Steps 3.3–3.6: Extractor Interface, Page Selection, Prompt/Call, Error Handling
- **What changed**: Created abstract `Extractor` base class and `extract_document()` orchestrator in `app/services/extractor.py`. Implemented `GroqExtractor` in `app/services/groq_extractor.py` with: extraction prompt constant, `reasoning_effort="none"` + `response_format={"type":"json_object"}` + `temperature=0`, JSON parse with code-fence stripping, one repair retry on parse failure, module-level `threading.Lock` for serialization, 429 retry with `retry-after` header (cap 65s, default 20s), and mapped error types (`AuthenticationError`→LLM_AUTH_ERROR, `RateLimitError`→RATE_LIMITED, timeout/5xx→LLM_UNAVAILABLE). Page selection: all if ≤max_pages, else first+last, never >3.
- **Verification result**: All modules import cleanly. `get_extractor()` correctly raises `LLM_AUTH_ERROR` when key is placeholder.

## Step 3.7: Wire into API Route
- **What changed**: Rewrote `POST /api/extract` route as sync `def` (not `async def`) so blocking Groq SDK call runs in FastAPI's thread pool. Route now: reads file bytes synchronously, validates, preprocesses, then attempts LLM extraction. If extraction fails with `AppError`, returns HTTP 200 with `extraction: null` and `extraction_error: {code, message}` alongside previews. If extraction succeeds, returns `extraction` dict and `extraction_meta`.
- **Verification result**: All 16 existing tests pass (8 upload + 8 preprocessing). Manual test with placeholder key shows `extraction_error: {code: "LLM_AUTH_ERROR", ...}` with HTTP 200 and previews intact.

## Step 3.8: Manual Try Script
- **What changed**: Created `backend/scripts/try_extract.py` that takes a file path, runs the full pipeline (detect MIME → save → preprocess → extract), and prints extracted JSON, token counts, latency, and pages sent. Cleans up temp files afterward.
- **Verification result**: Script imports and runs correctly (with placeholder key it shows the expected `LLM_AUTH_ERROR`).

## Step 3.9: Tests (all mocked)
- **What changed**: Created `tests/test_extraction.py` with 20 tests covering: JSON parsing helpers (valid, fenced, invalid, extra fields), page selection (1/2/5 pages), GroqExtractor with mocked client (valid response, fenced response, repair on first failure, double failure → LLM_BAD_OUTPUT, 429→retry→success, 429 exhausted→RATE_LIMITED, auth error→LLM_AUTH_ERROR), placeholder API key check, and route integration (returns 200 with extraction_error while preserving previews).
- **Verification result**: `pytest tests/ -q` → **36 passed in 0.82s** (8 upload + 8 preprocessing + 20 extraction). Zero real API calls used.

## Step 3.10: Frontend Smoke Update
- **What changed**: Updated `App.jsx` to show extracted JSON in a `<pre>` block, extraction_meta (model, latency, tokens, pages, repaired), extraction_error in error style, validation flags with severity colors, and a needs_review badge. Updated `App.css` with dark-mode-safe colors (explicit light text for h1/h2/h3/p), styled JSON block, flag error/warning colors, and light mode overrides.
- **Verification result**: `npm run build` → 32 modules transformed, built in 780ms, zero warnings.

## Phase 3 Verification: Real Groq API Extraction
- **What changed**: Added `guard_against_real_api_calls` autouse fixture to `conftest.py` so automated tests strictly mock LLM extraction and cannot consume live quota. Ran live extraction via `try_extract.py` and via web frontend dev proxy.
- **Verification result**:
  - `pytest -q`: 36 passed in 2.17s (all mocked, zero real API calls used).
  - Real call 1: `invoice.pdf` (text PDF, 2 pages) extracted vendor `ACME SUPPLIES CORP`, invoice `INV-2026-9041`, date `2026-11-12`, currency `USD`, 5 line items, subtotal $650.00, tax $52.00, total $702.00. Input tokens: 3956, output tokens: 337, latency: 5245ms.
  - Real call 2: `phone_photo.jpg` (plain sample photo) extracted all fields as null and empty line items per prompt rules. Input tokens: 2162, output tokens: 60, latency: 3884ms.
  - Real call 3: Web proxy upload of `sample_invoice.pdf` via Vite proxy (`http://127.0.0.1:5173/api/extract`) returned HTTP 200 with previews, extracted vendor `ACME Supplies Inc.`, invoice `1024`, total $142.50. Input tokens: 2162, output tokens: 75, latency: 1709ms.
  - Total real API calls used: 3 of 5.
  - Git status: strictly clean, no secrets leaked or committed.

## Step 4.1: Validation Checks and Review Flags Module
- **What changed**: Implemented `app/services/checks.py` containing pure validation logic for `InvoiceData`:
  - `REQUIRED_MISSING` (error): missing vendor, date, or total.
  - `TOTAL_MISMATCH` (error): subtotal + tax differs from total by more than tolerance.
  - `LINE_SUM_MISMATCH` (warning): sum of line item amounts differs from subtotal/total by more than tolerance.
  - `ITEM_MATH_MISMATCH` (warning): quantity * unit_price differs from line item amount.
  - `DATE_INVALID` (error): date is not a valid YYYY-MM-DD calendar date.
  - `DATE_SUSPICIOUS` (warning): date earlier than 2000-01-01 or > 1 day in future.
  - `NEGATIVE_VALUE` (warning): negative values on total, subtotal, tax, or line amounts.
  - `CURRENCY_INVALID` (warning): currency not a 3-letter uppercase ISO code.
  - `NO_LINE_ITEMS` (warning): empty line items array.
  - Tolerance handling: 0.02 (2 cents) for standard amounts <= 100.00 (allowing 0.01 to pass and 0.05 to fail on 100.00 total) scaling to 0.5% for larger totals.
- **Verification result**: Tested edge cases: 0.01 discrepancy passes, 0.05 fails on 100.00 total; 99.99 rounding discrepancy passes.

## Step 4.2: Integration into Extract Route
- **What changed**: Connected `run_checks(invoice_data)` in `app/routes/extract.py`. Populates `flags` dict and calculates `needs_review` (`bool(flags)` if extraction succeeded; `{}` and `True` if extraction failed). Also updated `scripts/try_extract.py` to display flags and review status.
- **Verification result**: Route tests verify flags and needs_review returned in response payload.

## Step 4.3: Table-driven Checks Test Suite
- **What changed**: Created `tests/test_checks.py` containing 29 table-driven tests covering clean invoices, all check codes, tolerance edge cases, rounding cases, and multi-flag scenarios.
- **Verification result**: `pytest tests/test_checks.py -q` passed 29/29 tests in 0.19s. Full test suite: 65 passed in 2.02s.

## Step 4.4: Frontend Smoke Update
- **What changed**: Enhanced flags rendering in `App.jsx` and `App.css` displaying severity color-coded warning/error list (error red, warning amber) with field names and messages, plus review status badge.
- **Verification result**: `npm run build` succeeds cleanly in 2.06s with zero errors or warnings.

## Phase 4 Verification & Documentation
- **What changed**: Updated `README.md` with new env vars, free-tier quota limits (8K tokens/min, 40-50 docs/day), updated API contracts (extraction, extraction_meta, extraction_error, flags, needs_review), and decoupled provider swapping architecture. Ran live extraction on `invoice.pdf` (Real call #4) demonstrating zero flags (`needs_review=False`). Demonstrated `TOTAL_MISMATCH` on broken total via pure script without API calls.
- **Verification result**: Real API calls used: 4 of 5. Full test suite: 65 passed, 0 failed. Git status: clean, no secrets leaked.

## Bug-Fix & Robustness Enhancements (Steps 1–6)
- **Step 1: Text-first extraction for PDFs**: Added `EXTRACTION_MODE=auto|text|image` configuration. When a PDF has an embedded digital text layer (`>= 50` characters), `services/extractor.py` extracts text directly via PyMuPDF and routes text content to Groq, bypassing vision tiling and saving ~1,800 tokens per page while delivering exact character accuracy. Set `source: "text" | "image"` in `ExtractionMeta`.
- **Step 2: Schema additions & code derivation**: Added `taxable_amount`, `cgst`, `sgst`, `igst`, `cess`, and `prices_include_tax` to `InvoiceData`. Implemented `derive_invoice_fields()` in `schemas.py` to derive `tax` (sum of GST components) and `subtotal` (from `taxable_amount` when `prices_include_tax` is true) automatically in code without LLM arithmetic.
- **Step 3: Prompt rules**: Added strict rules to `EXTRACTION_PROMPT` for GST summary table total row extraction (`T:`, `Total`), no arithmetic/adding numbers rule, prices-include-tax detection rule, and fused-digit / column separation rule.
- **Step 4: Checks changes**: Updated `LINE_SUM_MISMATCH` in `services/checks.py` to evaluate against `subtotal` OR `total` (critical for tax-inclusive retail receipts where line items sum to the final total), with explanatory hint when `prices_include_tax` is true. Updated `TOTAL_MISMATCH` to compare `taxable_amount + tax` against total when prices are tax-inclusive.
- **Step 5: Synthetic tests**: Added synthetic test fixtures in `tests/test_checks.py` and `tests/test_extraction.py` covering GST derivation, text-first extraction, tax-inclusive line item sums, and Groq `seed` passing (zero customer PII).
- **Step 6: Groq seed parameter**: Verified Groq API supports `seed: int` for best-effort determinism. Added `GROQ_SEED=42` to config and passed `seed=settings.groq_seed` with `temperature=0` to `client.chat.completions.create`.
- **Verification result**: `pytest -q` passed 70/70 tests in 0.82s (100% mocked, zero API calls).

## Live Verification on samples/7474.pdf (3 Runs, 60+ seconds apart)
- Ran 3 independent live extractions using `try_extract.py` spaced 65+ seconds apart to strictly observe the 8K tokens/min rate limit.
- Real API calls used: Calls 5, 6, 7 (total session calls: 7 of 14).
- Determinism confirmed: Runs 2 and 3 produced 100% identical JSON outputs and token counts with `seed=42`.
- Exact match on: vendor (`Reliance Retail Limited`), invoice number (`621418926514866`), date (`2026-11-05`), currency (`INR`), taxable amount (`1521.94`), CGST (`30.03`), SGST (`30.03`), total tax (`60.06`), total (`1582.00`), all 8 line item amounts (`308.00`, `123.00`, `99.00`, `60.00`, `97.00`, `54.00`, `719.00`, `122.00`), and `prices_include_tax: true`.

## Phase 4 Close-Out Verification
- **Run comparison on 7474.pdf**: Confirmed that the model's raw extracted JSON for Runs 1, 2, and 3 was 100% identical (vendor, invoice_number, date, currency, GST components, all 8 line item descriptions and amounts, prices_include_tax).
- **Regression test on samples/invoice.pdf (Call #8)**: Extracted ACME SUPPLIES CORP cleanly via text mode (`source="text"`), reducing input tokens to 1,105 (from 3,956). Subtotal $650.00, Tax $52.00, Total $702.00, 5 line items. 0 flags raised (`needs_review=False`). Confirms no regressions introduced.
- **Image path test on samples/store_receipt.png (Call #9)**: Tested vision path with a real receipt scan (`source="image"`, 2,664 input tokens). Correctly extracted ACME Supplies Inc., #1024, USD, total 142.50. Accurately flagged missing date and no line items.
- **Total real API calls**: 9 of 14 used.

## Phase 5: Persistence and Document API
- **Step 5.1 Database setup (`services/db.py`)**: Added SQLite database connection service with WAL mode, foreign keys enabled (`PRAGMA foreign_keys=ON`), schema versioning (`PRAGMA user_version`), and tables `documents` and `extractions` with cascade deletion. Added `DB_PATH` (`data/app.db`) and `RETENTION_DAYS` (default 30) settings. Gitignored `data/`, `*.db`, and WAL files.
- **Step 5.2 Keep saved files & retention purge (`services/storage.py`)**: Updated `cleanup_expired()` to protect any folder whose ID exists in the `documents` table while removing orphan folders older than TTL. Added `purge_retention()` to delete documents older than `RETENTION_DAYS` at startup lifespan.
- **Step 5.3 Repository and schemas (`services/documents.py`, `schemas.py`)**: Implemented `DocumentSummary`, `DocumentDetail`, `ErrorPayload`, and `DocumentUpdateRequest` schemas. Built repository functions: `save_extracted_document`, `get_document_by_id`, `list_documents`, `update_document_data`, `delete_document_record`, `delete_all_documents`, `purge_retention`.
- **Step 5.4 Document API endpoints (`routes/documents.py`, `routes/extract.py`)**:
  - `POST /api/extract`: Saves extracted document and returns `DocumentDetail`. On extraction error, saves record with error envelope and status `needs_review` while returning 200 with previews.
  - `GET /api/documents`: Returns list of `DocumentSummary`, newest first, with status filter, limit (capped at 200), and offset.
  - `GET /api/documents/{id}`: Returns full `DocumentDetail` (404 on missing or invalid UUID).
  - `PUT /api/documents/{id}`: Updates `reviewed_json`, recomputes checks/flags; marks `reviewed` with timestamp if `mark_reviewed=True`.
  - `POST /api/documents/{id}/reextract`: Retries extraction on preprocessed files for failed/rate-limited documents.
  - `DELETE /api/documents/{id}`: Deletes DB rows and disk directory.
  - `DELETE /api/documents?confirm=true`: Purges all documents and storage folders (400 if confirm missing).
- **Step 5.5 Tests (`tests/test_documents.py`)**: Added 7 comprehensive integration tests covering persistence across DB reconnection, TTL protection of saved folders, status filtering and pagination, flag recomputation and review marking, failed extraction saving and re-extraction, deletion and confirm safety, and UUID/injection safety. Updated existing tests to match `DocumentDetail` response schema.
- **Verification result**:
  - `pytest -q`: 77 passed in 2.43s (all tests mocked, 0 real API calls).
  - Persistence verified via `scripts/verify_phase5.py`: uploaded synthetic document on live backend, restarted server, verified listing in `GET /api/documents` and preview fetch from `/api/files/{id}/pages/1.png` (HTTP 200 PNG).
  - Git status verified: `data/` and `storage/` are untracked and gitignored.

