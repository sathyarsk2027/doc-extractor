# AI Document-to-Data Extractor

An application to extract structured data (vendor, invoice number, date, line items, totals) from invoices and receipts (PDF, JPG, PNG) using vision-capable LLMs on Groq, backed by validation checks and review flags.

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, Uvicorn, PyMuPDF, Pillow, Pydantic v2, python-dotenv, groq SDK (Qwen 3.8 27B vision model)
- **Frontend**: React + Vite (JavaScript), plain CSS
- **Testing**: pytest, httpx (100% mocked automated tests, 0 live API tokens consumed during test runs)

---

## Configuration & Environment Variables

Environment variables are loaded from `backend/.env`. Copy from `backend/.env.example`:

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | *(required)* | Your Groq API key (`gsk_...`). Never committed or printed. |
| `GROQ_MODEL` | `qwen/qwen3.8-27b` | Multimodal vision model used for extraction. |
| `GROQ_TIMEOUT_SECONDS` | `60` | HTTP client timeout for Groq API calls. |
| `GROQ_MAX_RETRIES` | `2` | Number of retries on HTTP 429 rate limits respecting `retry-after`. |
| `GROQ_MAX_OUTPUT_TOKENS` | `1500` | Maximum completion tokens allowed for extraction JSON. |
| `EXTRACTION_MAX_PAGES` | `2` | Maximum pages sent to LLM (all pages if <= 2, else first & last page). |
| `EXTRACTION_MODE` | `auto` | Text-first extraction mode for PDFs: `auto`, `text`, or `image`. |
| `GROQ_SEED` | `42` | Seed for best-effort LLM reproducibility. |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS allowed origin. |
| `MAX_FILE_MB` | `10` | Maximum uploaded file size in megabytes. |
| `MAX_PDF_PAGES` | `5` | Maximum PDF page count allowed for processing. |
| `MAX_IMAGE_WIDTH` | `2000` | Proportional downscaling ceiling for uploaded images. |
| `PDF_RENDER_DPI` | `150` | DPI used to render PDF pages into preview PNGs. |
| `STORAGE_DIR` | `storage` | Local directory for ephemeral page previews. |
| `FILE_TTL_MINUTES` | `60` | Ephemeral document cleanup TTL. |
| `DB_PATH` | `data/app.db` | SQLite database file path (relative to `backend/` or absolute). |
| `RETENTION_DAYS` | `30` | Auto-purging retention threshold in days at startup (0 disables purge). |

### Quota Notes (Groq Free Tier)
- **Limits**: 30 RPM, 1,000 RPD, 8,000 tokens/min, 200,000 tokens/day.
- **Token Accounting**: Each rendered page image consumes ~1,800 to 2,048 input vision tokens.
- **Daily Capacity**: At ~4,000 tokens per 2-page invoice, the free tier comfortably handles approximately **40–50 documents per day**.
- **Rate-limit Throttling**: The backend serializes Groq calls with a thread lock and automatically waits on HTTP 429 using the `retry-after` header (capped at 65 seconds).

---

## Provider Architecture & Swapping Note

All LLM provider interaction is cleanly decoupled:
1. **Abstract Interface**: `app.services.extractor.Extractor` defines `extract(page_images: list[bytes]) -> tuple[InvoiceData, ExtractionMeta]`.
2. **Provider Implementation**: All Groq-specific client code, prompts, vision formatting, and retry logic live exclusively in `app.services.groq_extractor.GroqExtractor`.
3. **Swapping Providers**: To swap to another LLM provider (e.g. Google Gemini, Anthropic, or OpenAI), implement a new subclass of `Extractor` (e.g., `GeminiExtractor`) and return it in `get_extractor()`. The REST routes, Pydantic schemas, validation checks, preprocessing, and UI code require zero modifications.

---

## Run Locally (Windows / PowerShell)

### 1. Backend Setup
From the repository root (`doc-extractor`):
```powershell
cd backend

# Create virtual environment (if not already created)
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install pinned dependencies
pip install -r requirements.txt

# Copy environment configuration and configure your key
Copy-Item .env.example .env
# Edit .env and set: GROQ_API_KEY=gsk_...

# Run backend development server
uvicorn app.main:app --reload --port 8000
```
- Health Check: `http://localhost:8000/api/health`
- OpenAPI Docs: `http://localhost:8000/docs`

### 2. Frontend Setup
From the repository root (`doc-extractor`):
```powershell
cd frontend

# Install npm dependencies
npm install

# Run frontend development server (proxies /api to http://localhost:8000)
npm run dev
```
- Frontend application: `http://localhost:5173`

### 3. Run Backend Test Suite
From the `backend` directory:
```powershell
.\.venv\Scripts\pytest -v
```
All automated tests strictly mock LLM extraction via `conftest.py` autouse guards; zero API tokens are consumed during test execution.

### 4. Manual Try Script
Extract a document directly from the terminal and inspect JSON, latency, token usage, and review flags:
```powershell
cd backend
.\.venv\Scripts\python scripts/try_extract.py ..\samples\invoice.pdf
```

---

## API Contract

All error responses strictly follow the envelope:
```json
{
  "error": {
    "code": "STRING_ERROR_CODE",
    "message": "Human-readable explanation of the error."
  }
}
```

### 1. `POST /api/extract`
Uploads a document (PDF, PNG, JPG), validates it by magic bytes and size, preproposes pages to PNG previews, saves records to SQLite, and executes the extraction pipeline with automated validation checks. Returns the canonical `DocumentDetail` envelope.

- **Request**:
  - `Content-Type: multipart/form-data`
  - Form Fields:
    - `file`: Binary file upload (required)
- **Limits**:
  - Maximum size: `10 MB` (`MAX_FILE_MB`)
  - Maximum PDF pages: `5 pages` (`MAX_PDF_PAGES`)
  - Supported types: PDF (`%PDF-`), PNG (`\x89PNG\r\n\x1a\n`), JPEG (`\xff\xd8\xff`)
- **Success Response (`200 OK`)**:
  ```json
  {
    "id": "877af164-a1e3-4c8c-8a22-6cf60ecd88db",
    "filename": "invoice.pdf",
    "mime_type": "application/pdf",
    "page_count": 2,
    "status": "extracted",
    "created_at": "2026-11-13T10:00:00.123456Z",
    "updated_at": "2026-11-13T10:00:00.123456Z",
    "reviewed_at": null,
    "pages": [
      {
        "page": 1,
        "preview_url": "/api/files/877af164-a1e3-4c8c-8a22-6cf60ecd88db/pages/1.png",
        "width": 1240,
        "height": 1755
      },
      {
        "page": 2,
        "preview_url": "/api/files/877af164-a1e3-4c8c-8a22-6cf60ecd88db/pages/2.png",
        "width": 1240,
        "height": 1755
      }
    ],
    "original": {
      "vendor": "ACME SUPPLIES CORP",
      "invoice_number": "INV-2026-9041",
      "date": "2026-11-12",
      "currency": "USD",
      "line_items": [
        {
          "description": "Server Rack Mount",
          "quantity": 1.0,
          "unit_price": 450.0,
          "amount": 450.0
        }
      ],
      "subtotal": 650.0,
      "tax": 52.0,
      "total": 702.0,
      "taxable_amount": null,
      "cgst": null,
      "sgst": null,
      "igst": null,
      "cess": null,
      "prices_include_tax": false
    },
    "reviewed": null,
    "flags": {},
    "needs_review": false,
    "meta": {
      "model": "qwen/qwen3.8-27b",
      "latency_ms": 2838,
      "input_tokens": 1105,
      "output_tokens": 337,
      "pages_sent": [1, 2],
      "repaired": false,
      "source": "text"
    },
    "error": null
  }
  ```

- **Extraction Failure Graceful Degradation (`200 OK`)**:
  If extraction fails (e.g. rate limit, auth issue, or invalid LLM output), the document is saved in SQLite with `status: "needs_review"` and `error` set. The endpoint **still returns HTTP 200** with page previews intact so the user can see their uploaded document and retry extraction:
  ```json
  {
    "id": "877af164-a1e3-4c8c-8a22-6cf60ecd88db",
    "filename": "invoice.pdf",
    "mime_type": "application/pdf",
    "page_count": 2,
    "status": "needs_review",
    "created_at": "2026-11-13T10:00:00.123456Z",
    "updated_at": "2026-11-13T10:00:00.123456Z",
    "reviewed_at": null,
    "pages": [...],
    "original": null,
    "reviewed": null,
    "flags": {},
    "needs_review": true,
    "meta": null,
    "error": {
      "code": "RATE_LIMITED",
      "message": "The free AI quota is temporarily used up. Please try again in a minute."
    }
  }
  ```

- **Validation Check Codes (`flags`)**:
  - `REQUIRED_MISSING` (error): `vendor`, `date`, or `total` is missing/null.
  - `TOTAL_MISMATCH` (error): `subtotal + tax` differs from `total` beyond tolerance.
  - `LINE_SUM_MISMATCH` (warning): Sum of line items differs from subtotal (or total) beyond tolerance.
  - `ITEM_MATH_MISMATCH` (warning): Line item `quantity * unit_price` differs from `amount`.
  - `DATE_INVALID` (error): Date is not a valid `YYYY-MM-DD` calendar date.
  - `DATE_SUSPICIOUS` (warning): Date is earlier than 2000-01-01 or more than 1 day in the future.
  - `NEGATIVE_VALUE` (warning): Negative total, subtotal, tax, or line item amount.
  - `CURRENCY_INVALID` (warning): Currency is not a 3-letter uppercase ISO code.
  - `NO_LINE_ITEMS` (warning): Document has zero detected line items.
  - `INVOICE_NUMBER_MISSING` (warning): Invoice number is missing or empty.

- **Upload & Preprocessing Errors**:
  - `400 Bad Request`: `NO_FILE`, `EMPTY_FILE`
  - `413 Content Too Large`: `FILE_TOO_LARGE`
  - `415 Unsupported Media Type`: `UNSUPPORTED_TYPE`
  - `422 Unprocessable Entity`: `PDF_TOO_MANY_PAGES`, `PDF_ENCRYPTED`, `CORRUPT_FILE`
  - `500 Internal Server Error`: `INTERNAL_ERROR`

---

### 2. `GET /api/documents`
Lists documents with pagination and status filtering, sorted newest first (`created_at DESC, rowid DESC`).
- **Query Parameters**:
  - `status`: Filter by status (`needs_review`, `reviewed`, `extracted`, or empty for all).
  - `limit`: Integer (default 50, maximum 200).
  - `offset`: Integer (default 0).
- **Response (`200 OK`)**: List of `DocumentSummary`:
  ```json
  [
    {
      "id": "877af164-a1e3-4c8c-8a22-6cf60ecd88db",
      "filename": "invoice.pdf",
      "created_at": "2026-11-13T10:00:00.123456Z",
      "status": "extracted",
      "page_count": 2,
      "vendor": "ACME SUPPLIES CORP",
      "total": 702.0,
      "currency": "USD",
      "needs_review": false
    }
  ]
  ```

---

### 3. `GET /api/documents/{id}`
Retrieves full `DocumentDetail` by UUID (including pages, original/reviewed data, flags, and metadata).
- Returns `404 Not Found` if the UUID is missing or invalid.

---

### 4. `PUT /api/documents/{id}`
Updates human-corrected data for a document, re-executing validation checks and flags.
- **Request Body**:
  ```json
  {
    "data": { ...InvoiceData... },
    "mark_reviewed": true
  }
  ```
- If `mark_reviewed` is `true`, updates status to `"reviewed"` and records `reviewed_at` timestamp.
- Returns updated `DocumentDetail`.

---

### 5. `POST /api/documents/{id}/reextract`
Retries extraction on existing preprocessed page previews without re-uploading (useful for failed or rate-limited documents).
- Clears previous error payload and recomputes flags.
- Returns updated `DocumentDetail`.

---

### 6. `DELETE /api/documents/{id}`
Deletes the document row, cascades deletion to `extractions`, and purges storage folder from disk.
- Returns `{"deleted": true, "id": "..."}`.

---

### 7. `DELETE /api/documents?confirm=true`
Bulk-deletes all documents, extractions, and preview files.
- Returns `400 Bad Request` if `confirm=true` is omitted.
- Returns `{"deleted": true, "count": N}`.

---

### 8. `GET /api/documents/{id}/export.csv`
Exports a single document as an RFC 4180 CSV with UTF-8 BOM (`utf-8-sig`).
- Uses `reviewed` data when present, falling back to `original`.
- Returns `Content-Disposition: attachment; filename="export_{id}.csv"`.

---

### 9. `GET /api/documents/export.csv`
Bulk-exports documents as an RFC 4180 CSV with UTF-8 BOM (`utf-8-sig`).
- **Query Parameter**: `status=reviewed` (default) or `status=all`.
- One line per line item (or 1 row with empty item columns if 0 items).
- Returns `Content-Disposition: attachment; filename="invoices_export.csv"`.

---

### 10. `GET /api/files/{document_id}/pages/{page_number}.png`
Retrieves the rendered PNG preview of a specific document page.
- `Cache-Control: private, max-age=300`

---

### 11. `GET /api/health`
Health check endpoint returning `{"status": "ok"}`.

---

## Data Storage, Retention & Privacy

1. **SQLite Database**:
   - Stored at `DB_PATH` (`data/app.db`).
   - SQLite WAL mode (`PRAGMA journal_mode=WAL`) and foreign keys enforced (`PRAGMA foreign_keys=ON`).
   - Schema versioning via `PRAGMA user_version` handles migrations idempotently.
2. **File Storage & Retention**:
   - Original uploads and rendered page images are isolated in `storage/{document_id}/`.
   - `cleanup_expired()` runs periodically and removes orphan directories older than `FILE_TTL_MINUTES`, but **never** deletes directories associated with saved documents in the database.
   - At startup, `purge_retention()` removes documents and file directories older than `RETENTION_DAYS` (default 30 days; setting 0 disables retention purge).
3. **Privacy**:
   - `data/`, `storage/`, and `backend/.env` are strictly gitignored.
   - No customer names, addresses, or document PII in source control, commit history, or logs.
   - All automated test suites use synthetic test data.
4. **CSV Export Security**:
   - Formula injection protection: text values beginning with `=`, `+`, `-`, `@`, `\t`, `\r` are prefixed with `'` (single quote) to prevent formula execution in spreadsheet applications, while leaving negative numbers untouched.
   - UTF-8 BOM (`\xef\xbb\xbf`) header ensures direct Microsoft Excel compatibility without mojibake or manual import wizard steps.
