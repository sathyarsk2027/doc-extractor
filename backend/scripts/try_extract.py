"""Manual extraction try script - runs the full pipeline on a file.

Usage:
    cd backend
    .venv\\Scripts\\python scripts/try_extract.py ..\\samples\\invoice.pdf
"""

import json
import sys
import time
from pathlib import Path

# Add parent dir to path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.services.validation import detect_mime_type, sanitize_filename
from app.services.storage import create_document_dir, delete_document
from app.services.preprocessing import preprocess_document
from app.services.extractor import extract_document

import uuid


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/try_extract.py <file_path>")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.is_file():
        print(f"File not found: {file_path}")
        sys.exit(1)

    print(f"File: {file_path.name} ({file_path.stat().st_size:,} bytes)")

    content = file_path.read_bytes()
    mime_type = detect_mime_type(content[:32])
    print(f"MIME type: {mime_type}")

    document_id = str(uuid.uuid4())
    print(f"Document ID: {document_id}")

    try:
        # Save and preprocess
        from app.services.storage import save_original, get_document_dir

        save_original(document_id, content, mime_type)
        doc_dir = get_document_dir(document_id)
        pages_meta = preprocess_document(doc_dir, content, mime_type)
        print(f"Preprocessed: {len(pages_meta)} page(s)")

        # Extract
        print("\nCalling Groq API...")
        start = time.monotonic()
        invoice_data, meta = extract_document(document_id)
        elapsed = time.monotonic() - start

        print(f"\n{'='*60}")
        print("EXTRACTED DATA:")
        print('='*60)
        print(json.dumps(invoice_data.model_dump(), indent=2, default=str))

        print(f"\n{'='*60}")
        print("EXTRACTION META:")
        print('='*60)
        print(f"  Model:         {meta.model}")
        print(f"  Latency:       {meta.latency_ms} ms")
        print(f"  Input tokens:  {meta.input_tokens}")
        print(f"  Output tokens: {meta.output_tokens}")
        print(f"  Pages sent:    {meta.pages_sent}")
        print(f"  Repaired:      {meta.repaired}")
        print(f"  Wall time:     {elapsed:.2f}s")

    except Exception as exc:
        print(f"\nERROR: [{type(exc).__name__}] {exc}")
        sys.exit(1)
    finally:
        delete_document(document_id)
        print("\nCleaned up temporary files.")


if __name__ == "__main__":
    main()
