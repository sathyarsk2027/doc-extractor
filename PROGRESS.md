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
