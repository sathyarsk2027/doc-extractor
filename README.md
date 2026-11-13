# AI Document-to-Data Extractor

An application to extract structured data (vendor, date, line items, totals) from invoices and receipts (PDF, JPG, PNG).

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, Uvicorn, PyMuPDF, Pillow, Pydantic v2, python-dotenv, google-genai (Phase 3)
- **Frontend**: React + Vite (JavaScript), plain CSS
- **Testing**: pytest, httpx

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

# Copy environment configuration
Copy-Item .env.example .env

# Run backend development server
uvicorn app.main:app --reload --port 8000
```
- Health Check: `http://localhost:8000/api/health`
- Swagger UI / OpenAPI Docs: `http://localhost:8000/docs`

### 2. Frontend Setup
From the repository root (`doc-extractor`):
```powershell
cd frontend

# Install npm dependencies
npm install

# Run frontend development server (proxies /api to http://localhost:8000)
npm run dev
```
- Frontend smoke-test page: `http://localhost:5173`

### 3. Run Backend Test Suite
From the `backend` directory:
```powershell
.\.venv\Scripts\pytest -v
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
Uploads a document (PDF, PNG, JPG), validates it by magic bytes and size, preproposes pages to PNG previews, and executes the extraction pipeline (stubbed in Phase 1/2; LLM extraction in Phase 3).

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
    "document_id": "877af164-a1e3-4c8c-8a22-6cf60ecd88db",
    "filename": "invoice.pdf",
    "mime_type": "application/pdf",
    "page_count": 2,
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
    "extraction": null,
    "message": "Preprocessing complete. LLM extraction arrives in Phase 3."
  }
  ```
- **Error Responses**:
  - `400 Bad Request`:
    - `NO_FILE`: `"No file was uploaded."`
    - `EMPTY_FILE`: `"Uploaded file is empty."`
  - `413 Content Too Large`:
    - `FILE_TOO_LARGE`: `"File exceeds 10 MB limit."` (stream read aborts early)
  - `415 Unsupported Media Type`:
    - `UNSUPPORTED_TYPE`: `"Unsupported file type. Only PDF, PNG, and JPEG files are supported."`
  - `422 Unprocessable Entity`:
    - `PDF_TOO_MANY_PAGES`: `"PDF page count (6) exceeds maximum allowed limit of 5 pages."`
    - `PDF_ENCRYPTED`: `"Password-protected PDFs are not supported."`
    - `CORRUPT_FILE`: `"The PDF file is corrupt or cannot be read."` / `"The image file is corrupt or cannot be decoded."`
  - `500 Internal Server Error`:
    - `INTERNAL_ERROR`: `"An unexpected internal server error occurred."`

---

### 2. `GET /api/files/{document_id}/pages/{page_number}.png`
Retrieves the rendered PNG preview of a specific document page.

- **URL Parameters**:
  - `document_id` (string, UUIDv4): Unique identifier assigned during upload. Non-UUID parameters are rejected immediately.
  - `page_number` (integer, >= 1): 1-indexed page number.
- **Success Response (`200 OK`)**:
  - `Content-Type: image/png`
  - `Cache-Control: private, max-age=300`
  - Body: Binary PNG data (EXIF metadata stripped for privacy).
- **Error Response (`404 Not Found`)**:
  - Returned if `document_id` is invalid/unknown, expired, or if the page number does not exist:
  ```json
  {
    "error": {
      "code": "NOT_FOUND",
      "message": "Preview page image not found or has expired."
    }
  }
  ```

---

### 3. `GET /api/health`
Health check endpoint returning system status.

- **Success Response (`200 OK`)**:
  ```json
  {
    "status": "ok"
  }
  ```
