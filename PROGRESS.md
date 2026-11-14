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

## Phase 5 Verification & Test Expansion
- **Expanded persistence tests**: Added separate dedicated tests in `tests/test_documents.py` for cascade row deletion on SQLite foreign keys (`ON DELETE CASCADE`), delete-all confirmation guard, retention purge (`RETENTION_DAYS` removal, retention period = 0 disable), distinct 404 handling on invalid UUID/path-traversal, and SQL injection safety on status filtering. Full test suite: 80 passed.
- **Assertion integrity**: Verified with `git diff 9f6104c..932f2f4` that zero assertions in `test_upload.py`, `test_preprocessing.py`, and `test_extraction.py` were removed or weakened.
- **Path resolution check**: Verified `settings.db_file_path` resolves identically relative to the backend directory whether initiated from repo root or backend folder.
- **Ignore verification**: Verified `.gitignore:18` and `.gitignore:16` match `backend/data/app.db` and `backend/storage`.

## Phase 6 Follow-up Fixes: UI & Extraction Refinements
- **Dot Marker ("Changed from AI")**: Created `frontend/src/utils/diff.js` equating `null`, `undefined`, and `""`. Added numeric comparison (`parseFloat`) and date validity checks to prevent untouched empty fields or invalid dates from falsely displaying the purple dot indicator. Added unit tests in `frontend/src/utils/diff.test.js` (4/4 tests passed). Added tooltip `title="Changed from AI"` on dot indicators.
- **Invoice Number Extraction & Validation**:
  - Updated Rule 7 in `EXTRACTION_PROMPT` (`services/groq_extractor.py`): `"Bill No.", "Invoice No." and "Tax Invoice#" all mean invoice_number; copy the digits exactly.`
  - Added warning-level validation check `INVOICE_NUMBER_MISSING` in `services/checks.py`. Added test in `tests/test_checks.py`.
  - Re-extracted `samples/7474.pdf` live (Real Call #2 of Phase 5-7 budget): successfully extracted `invoice_number: "621418926514866"`, 0 error flags.
- **Line-Item Flag Layout**: Refactored `LineItemsTable.jsx` to render line item validation flags in a dedicated full-width `<tr>` (`<td colSpan={5}>`) directly below the item row. Kept severity styling (amber warning / red error) and eliminated narrow-column input distortion in the Amount column.
- **Verification result**: `npm run lint` and `npm run build` passed with 0 errors/warnings. Node test runner passed `diff.test.js`.

## Phase 7: CSV Export
- **Step 7.1 Backend Export Service (`services/export.py`)**:
  - Implemented `generate_documents_csv(docs)` using Python standard library `csv` module and `io.StringIO`.
  - Encoded with `utf-8-sig` (UTF-8 BOM: `\xef\xbb\xbf`) for automatic native opening in Microsoft Excel without character corruption or wizard dialogs.
  - Implemented formula-injection sanitization (`sanitize_csv_text`): prefixes strings starting with `'`, `+`, `-`, `=`, `@`, `\t`, `\r` with a single quote `'`, while preserving numeric negative numbers (e.g., `-5.00` remains numeric).
  - Clean decimal float formatting (e.g. `0.1 + 0.2` formats as `0.30`).
  - RFC 4180 compliant column structure: `document_id,filename,vendor,invoice_number,date,currency,subtotal,tax,total,item_description,item_quantity,item_unit_price,item_amount,status,needs_review,flag_codes`.
  - One line per line item; documents with 0 line items output exactly 1 row with empty item columns. Prefers `reviewed` data over `original`.
- **Step 7.2 API Endpoints (`routes/documents.py`)**:
  - `GET /api/documents/{id}/export.csv`: Exports single document with `Content-Disposition: attachment; filename="export_{id}.csv"`.
  - `GET /api/documents/export.csv`: Bulk export with query parameter `status=reviewed` (default) or `status=all` and header `Content-Disposition: attachment; filename="invoices_export.csv"`.
- **Step 7.3 Frontend CSV Download Links**:
  - `ReviewView.jsx`: Added "Download CSV" link triggering `GET /api/documents/{id}/export.csv`. Appends `(Contains unreviewed data)` hint if `status !== "reviewed"`.
  - `HistoryView.jsx`: Added "Export reviewed (CSV)" button triggering `GET /api/documents/export.csv?status=reviewed`.
- **Step 7.4 Export Test Suite (`tests/test_export.py`)**:
  - Implemented 7 table-driven tests:
    1. `test_single_document_export_csv_bom_and_headers`: Verifies UTF-8 BOM bytes (`\xef\xbb\xbf`) and exact headers.
    2. `test_csv_formula_injection_sanitization`: Verifies formula injection prevention (`=cmd`, `@SUM`, `+calc`, `-item`) while negative floats (`-5.00`) are not mangled.
    3. `test_document_with_no_line_items_outputs_one_row`: Verifies empty item columns for documents without items.
    4. `test_float_rounding_in_csv`: Verifies `0.1 + 0.2` outputs `0.30`.
    5. `test_reviewed_data_preferred_over_original`: Verifies corrected reviewed fields are exported.
    6. `test_bulk_export_csv_filtering`: Verifies `status=reviewed` vs `status=all`.
    7. `test_export_csv_missing_or_invalid_id`: Verifies 404 response on invalid UUID.
- **Verification result**:
  - `pytest -q`: **88 passed in 6.59s** (all mocked, zero API calls).
  - `npm run lint`: 0 errors, 0 warnings.
  - `npm run build`: built in 2.02s cleanly (all components < 200 lines).
  - `python scripts/verify_phase7.py`:
    - BOM Raw Bytes: `b'\xef\xbb\xbf'`
    - BOM Hex: `['0xef', '0xbb', '0xbf']`
  - Real API budget: **2 of 3 calls used** across Phases 5-7. Git status: clean of `data/` and `storage/`.

## Phase 8: Evaluation & Benchmarking

### Step A1: Evaluation Layout & Tooling Structure
- **Package creation**: Created `backend/evaluation/` package with `__init__.py`, `cli.py`, `pipeline_runner.py`, `ground_truth.py`, `variants.py`, `scoring.py`, and `report.py`.
- **CLI setup**: Implemented unified CLI `python -m evaluation.cli <command>` supporting subcommands `templates`, `check-gt`, `variants`, `plan`, `run` (with `--limit`, `--only`, `--force`, `--repeats`), `score`, `report`, and `timing`.
- **Evaluation data directories**: Created top-level evaluation directories with `.gitkeep` files: `eval/data/`, `eval/ground_truth/`, `eval/variants/`, `eval/results/`, and `eval/report/`.
- **Gitignore configuration**: Updated `.gitignore` to strictly ignore all files under `eval/data/*`, `eval/ground_truth/*`, `eval/variants/*`, `eval/results/*`, and `eval/report/*` while preserving `.gitkeep`, `eval/report/summary.md`, `eval/README.md`, and `eval/ground_truth.example.json`. Anchored `/data/` and `/storage/` root ignores to prevent collisions with `eval/data/`.
- **Verification**:
  - Verified `python -m evaluation.cli --help` outputs all 8 subcommands and options cleanly.
  - Verified with `git check-ignore -v` that private folders (`eval/data/`, `eval/ground_truth/`, `eval/variants/`, `eval/results/`) are ignored while `.gitkeep`, `summary.md`, `README.md`, and `ground_truth.example.json` remain trackable.
  - Verified git status shows zero private data or secret leaks. Baseline test suite verified by user (88 passed in 3.29s).

### Step A2: DB-Free Pipeline Runner & Extraction Mode Override
- **Pipeline Runner Implementation (`evaluation/pipeline_runner.py`)**:
  - Implemented `run_pipeline_on_file(path, mode=None) -> PipelineResult`:
    - Reads input document and determines MIME type (`application/pdf`, `image/png`, `image/jpeg`).
    - Isolates document processing in an ephemeral `storage/{document_id}/` folder without inserting any rows into SQLite.
    - Preprocesses pages to preview PNGs.
    - Invokes extraction with per-call extraction mode override (`mode_override`), allowing explicit `text`, `image`, or `auto` without mutating global settings.
    - Executes validation checks via `run_checks(invoice_data)` to produce `flags` and `needs_review`.
    - Captures extraction metadata (model, latency, tokens in/out, pages sent, source modality, repaired status).
    - Robust error envelope: handles missing files, unhandled exceptions, and `AppError` (e.g. rate limit / auth / parsing error) returning structured error payloads.
    - `finally` block strictly purges `storage/{document_id}/` temporary files via `delete_document(document_id)`.
  - Added `has_usable_text_layer(path, min_chars=50)` utility to inspect whether a PDF has an embedded digital text layer.
  - Added `PipelineResult.to_dict()` and `PipelineResult.from_dict()` for lossless serialization and deserialization.
- **Minimal Core App Modification**:
  - Added optional `mode_override: str | None = None` parameter to `extract_document(document_id, mode_override=None)` in `backend/app/services/extractor.py`.
  - Diff stat: `backend/app/services/extractor.py | 5 +++--` (3 insertions, 2 deletions).
- **Automated Tests (`tests/test_evaluation.py`)**:
  - `test_pipeline_result_serialization`: verified lossless dictionary serialization/deserialization.
  - `test_has_usable_text_layer`: verified text layer detection threshold on synthetic PDFs.
  - `test_run_pipeline_on_file_missing_file`: verified `FILE_NOT_FOUND` error handling.
  - `test_run_pipeline_on_file_success`: verified InvoiceData extraction, review flags, metadata, zero SQLite writes, and disk cleanup.
  - `test_run_pipeline_on_file_app_error_cleanup`: verified error capture and guaranteed temporary storage cleanup on `AppError`.
  - Test result: `5 passed in 0.64s` (all mocked, 0 real API calls).

### Step A3: Ground Truth Management & Schema Validation
- **Ground Truth Implementation (`evaluation/ground_truth.py`)**:
  - Implemented `validate_ground_truth_dict(data)`:
    - Validates mandatory keys (`doc_id`, `source_file`, `document_kind`, `_status`, `expected`).
    - Validates document kind (`digital_pdf`, `scan`, `photo`).
    - Validates status (`TODO`, `verified`).
    - Enforces ISO 8601 calendar date validity (`YYYY-MM-DD`, rejecting invalid dates or calendar impossibilities like Feb 30).
    - Enforces strict numeric types for monetary and tax fields (rejecting strings, objects, booleans).
    - Supports `null` (not shown on doc) and `"IGNORE"` (skip scoring).
    - Enforces line item structure and numeric amount validation.
  - Implemented `cmd_templates()`:
    - Scans `eval/data/` for document files without ground truth annotations.
    - Generates template files with `_status: "TODO"`, all fields `null`, and reader instructions.
    - Preserves existing annotations: never overwrites existing ground truth files.
  - Implemented `cmd_check_gt()`:
    - Scans `eval/ground_truth/*.json`, validates schemas and verified status, verifies existence of corresponding document in `eval/data/`.
    - Returns clean summary of ready vs unready files and returns appropriate exit code.
- **Reference & Example Annotations**:
  - Copied `samples/7474.pdf` to `eval/data/7474.pdf`.
  - Created verified annotation in `eval/ground_truth/reliance_7474.json` with exact values and fused-item IGNORE rules.
  - Created synthetic reference annotation in `eval/ground_truth.example.json`.
- **Automated Tests (`tests/test_evaluation.py`)**:
  - Added unit tests for TODO status rejection, bad ISO date rejection, non-numeric type rejection, template non-overwrite preservation, and verified reliance_7474 validation.
  - Test suite result: `10 passed in 1.12s` (all mocked, 0 real API calls).

### Step A4: Realistic Image Degraded Variants
- **Variant Generation Engine (`evaluation/variants.py`)**:
  - Implemented `apply_degradation(img, variant)`:
    - `lowres`: Proportional downscaling to 50% width and height using Pillow bilinear filtering.
    - `jpeg35`: Controlled JPEG compression artifacts at quality 35.
    - `rot3blur`: 3-degree counter-clockwise rotation with white background fill (`(255, 255, 255)`) and expanded bounding canvas, followed by `ImageFilter.GaussianBlur(radius=1.2)`.
  - Implemented `generate_variants_for_pdf(doc_path, doc_id, out_dir)`:
    - Renders every source page at 150 DPI into RGB image buffer.
    - Builds an **image-only PDF** with PyMuPDF `insert_image` matching page count and dimensions.
    - Guaranteed zero embedded digital text (`page.get_text() == ""` on all pages).
    - Preserves deterministic byte outputs using `no_new_id=True, deflate=True`.
  - Implemented `generate_variants_for_image(doc_path, doc_id, out_dir)`:
    - Degrades and exports standalone image formats (`.jpg`).
  - Implemented `cmd_variants()` CLI subcommand generating `eval/variants/<doc_id>__<variant>.(pdf|jpg)`.
- **Verification on Reference Document**:
  - Ran `python -m evaluation.cli variants` on `7474.pdf`:
    - Generated `reliance_7474__lowres.pdf` (2 pages, 0 text chars).
    - Generated `reliance_7474__jpeg35.pdf` (2 pages, 0 text chars).
    - Generated `reliance_7474__rot3blur.pdf` (2 pages, 0 text chars).
  - Verified `git check-ignore -v` ignores all generated variant files.
- **Automated Tests (`tests/test_evaluation.py`)**:
  - `test_variants_pdf_no_text_layer_and_same_page_count`: verifies output PDFs have 0 text chars and preserve page count.
  - `test_variants_deterministic_output`: verifies two distinct runs on the same document produce byte-identical variant files.
  - Test suite result: `12 passed in 2.29s` (all mocked, 0 real API calls).

### Step A5: Evaluation Scoring Engine & Wilson Confidence Intervals
- **Scoring Engine Implementation (`evaluation/scoring.py`)**:
  - Implemented `normalize_text(text)`: casefolds, strips punctuation, collapses whitespace.
  - Implemented `wilson_interval(k, n, confidence=0.95)`: mathematical Wilson binomial score interval calculation with closed-form bounds `[0.0, 1.0]`.
  - Implemented `score_header_field(field_name, expected, predicted)`:
    - Null-vs-null = correct.
    - Expected null, predicted non-null = hallucination.
    - Expected value, predicted null = miss.
    - Numerical comparison (subtotal, tax, total, CGST, SGST, IGST, cess) with 0.01 tolerance (handles floating point rounding).
    - Vendor exact (normalized exact) and near match (`difflib.SequenceMatcher.ratio >= 0.90`).
    - Invoice number space-stripped equality; exact ISO date matching; uppercase currency matching; boolean tax inclusion matching.
    - Skips fields marked `"IGNORE"`.
  - Implemented `match_line_items(expected_items, predicted_items)`:
    - Greedy matching on amount (tolerance 0.01) with description similarity tie-breaking.
    - Computes item recall (`matched / expected`) and precision (`matched / predicted`, penalizing extras).
    - Verifies matched item description (`ratio >= 0.80`), quantity (`tolerance 0.001`), and unit price (`tolerance 0.01`).
  - Implemented `score_case(...)`:
    - Evaluates critical correctness (`vendor_near + date + total`).
    - Evaluates `all_header_correct` and `fully_correct` (all header fields and every item matched without error or extras).
    - Classifies validator effectiveness: TP (error & flagged), FN (silent error: error & unflagged), FP (clean & flagged), TN (clean & unflagged).
    - Aggregates fired review flag codes.
  - Implemented `cmd_score()` CLI command to score raw extraction JSON files against ground truth annotations and output `eval/results/scores.json`.
- **Automated Tests (`tests/test_evaluation.py`)**:
  - `test_text_normalization`: verifies whitespace, punctuation, and casefolding.
  - `test_wilson_interval_sanity_values`: verifies boundary values for k=0, k=n, k=n/2 against Wilson formula.
  - `test_header_scoring_rules`: verifies null/hallucination/miss, numeric tolerance limits (0.01 passes, 0.02 fails), and vendor exact vs near matching.
  - `test_line_item_matching_duplicates_and_tolerances`: verifies greedy disambiguation of duplicate amounts, recall, precision, and extra items penalty.
  - `test_validator_effectiveness_confusion_matrix`: verifies TP, FN, FP, TN classification.
  - Test suite result: `17 passed in 2.44s` (all mocked, 0 real API calls).

### Step A6: Case Matrix Planning, Rate-Limit Pacing & Resumable Runner
- **Case Matrix & Planning Engine (`evaluation/pipeline_runner.py`)**:
  - Implemented `build_case_matrix(only_doc=None) -> list[EvalCase]`:
    - Discovers all documents in `eval/data/`.
    - Generates `<doc>__text` (only if embedded digital text layer >= 50 characters).
    - Generates `<doc>__image` (clean rendered image path).
    - Generates 3 degraded variant cases (`<doc>__lowres`, `<doc>__jpeg35`, `<doc>__rot3blur`) with mode `auto`.
  - Implemented `cmd_plan(only_doc=None)`:
    - Dry-run listing case matrix with per-case modes and estimated token footprints (~2,200 for text, ~4,000 for image/variants).
    - Estimates overall runtime and total API calls against authorized 45-call budget.
    - Zero real API calls made.
- **Execution Engine, Pacing & Manifest (`evaluation/pipeline_runner.py`)**:
  - Implemented `write_manifest(case_ids)`: exports `eval/results/manifest.json` recording date, git commit hash, model, seed, extraction mode, prompt SHA-256, and case inventory.
  - Implemented `load_daily_usage(date)` and `update_daily_usage(date, tokens, calls)` tracking tokens in `eval/results/usage.json`.
  - Implemented `cmd_run(limit, only, force, repeats)`:
    - Resumable: skips already-completed cases present in `eval/results/raw/{case_id}.json` unless `--force`.
    - Token budget guard: stops cleanly before exceeding `EVAL_DAILY_TOKEN_CAP` (default 150,000 tokens/day).
    - Pacing sleep: enforces `max(10, tokens / 8000 * 60 + 5)` seconds between calls to respect Groq free-tier 8,000 tokens/min limit.
    - Rate limit safety: cleanly halts on 429 rate limit wait > 65s or 3 consecutive errors.
- **Automated Tests (`tests/test_evaluation.py`)**:
  - `test_runner_writes_manifest`: verified manifest metadata, model, seed, and 64-char prompt SHA-256 hash.
  - `test_runner_resumes_without_recalling_cached_cases`: verified cached cases in `raw/` are skipped on subsequent runs.
  - `test_runner_stops_at_token_cap`: verified clean stop before exceeding `EVAL_DAILY_TOKEN_CAP`.
  - Test suite result: `20 passed in 4.06s` (all mocked, 0 real API calls).

### Step A7: Aggregate Reporting & Timing Comparison
- **Aggregate Report Generator (`evaluation/report.py`)**:
  - Implemented `generate_report_markdown(manifest, scored_cases, doc_kinds)`:
    - Guaranteed privacy: strictly outputs aggregate metrics only (no vendor names, invoice numbers, amounts, or document filenames).
    - Section 1: Setup & Environment (model, seed, commit, date, prompt SHA-256, document inventory by kind, case counts).
    - Section 2: Header-field accuracy table across all paths (`text`, `image`, `lowres`, `jpeg35`, `rot3blur`, and `overall`) reported as `k/n (pct, Wilson 95% CI)`.
    - Section 3: Line-item metrics (recall, precision, description accuracy, quantity accuracy, unit price accuracy).
    - Section 4: Validator effectiveness table (TP, FN silent errors, FP false alarms, TN, recall, precision, and fired review flag distribution).
    - Section 5: Efficiency, latency (mean & P95), tokens, and free-plan daily capacity (`200,000 / mean_tokens`).
    - Section 6: Limitations (sample size, synthetic degradation perturbations, single human annotator, provider model/quota factors).
  - Implemented `cmd_report()` CLI command writing directly to `eval/report/summary.md`.
- **Timing Engine (`evaluation/report.py`)**:
  - Created `eval/timing_template.csv` with columns `doc_id,method,seconds,errors_left,notes`.
  - Implemented `cmd_timing(csv_path)` CLI command analyzing manual entry vs tool review times and computing mean seconds and time savings percentage.

### Step A8: Comprehensive Mocked Evaluation Test Suite & Stage A Verification
- **Automated Test Suite (`backend/tests/test_evaluation.py`)**:
  - 22 table-driven, fully mocked unit tests:
    - Pipeline result serialization / deserialization roundtrip.
    - Embedded text layer detection threshold on synthetic PDFs.
    - Pipeline runner missing file error handling.
    - Pipeline runner successful extraction with mode override, review flags, zero DB writes, and storage cleanup.
    - Pipeline runner error cleanup under `AppError`.
    - Ground truth validation rejecting unverified `TODO` status, invalid date strings, calendar impossibilities (e.g. Feb 30), and non-numeric types.
    - Ground truth template non-overwrite preservation.
    - Ground truth validation on reference document `reliance_7474.json`.
    - Variant generation verifying 0 digital text chars and preserved page count.
    - Variant generation determinism verifying byte-identical outputs across runs.
    - Text normalization with punctuation and whitespace collapsing.
    - Wilson 95% confidence interval boundary sanity checks.
    - Header field scoring rules (null-vs-null, hallucination, miss, tolerance edges 0.01 vs 0.02, vendor exact vs near).
    - Greedy line-item matching with duplicate amount disambiguation and extra items penalty.
    - Validator effectiveness confusion matrix (TP, FN silent errors, FP, TN).
    - Manifest generation with valid SHA-256 prompt hash.
    - Runner cached case skipping and resumability.
    - Runner token budget cap enforcement.
    - Report privacy verification (guaranteeing zero private vendor, invoice number, or amount strings).
    - Timing command statistics calculation.
  - Test result: **22 passed in 4.03s** (0 real API tokens consumed, 100% mocked).
- **Verification Evidence**:
  - `python -m evaluation.cli templates`: ran cleanly (0 created, 1 existing).
  - `python -m evaluation.cli check-gt`: validated `reliance_7474.json` as verified and ready.
  - `python -m evaluation.cli variants`: produced deterministic image-only PDFs for `7474.pdf` (lowres, jpeg35, rot3blur).
  - `python -m evaluation.cli plan`: printed complete case matrix (5 cases, 18,200 estimated tokens, 0 API calls).
  - `python -m evaluation.cli timing`: computed 76.4% time reduction on template data.
  - `git check-ignore -v`: confirmed `eval/data/`, `eval/ground_truth/`, `eval/variants/`, and `eval/results/` are ignored.
  - `git status`: clean of all private data or documents.









