"""Phase 5 verification script: test persistence across server restart."""

import json
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

import pymupdf


def make_synthetic_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=400)
    page.insert_text((40, 40), "Synthetic Invoice 2026")
    page.insert_text((40, 70), "Vendor: Acme Global")
    page.insert_text((40, 100), "Total: 150.00 USD")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def post_multipart(url: str, filename: str, file_bytes: bytes, mime_type: str) -> dict:
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str) -> any:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_bytes(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.read()


def main():
    backend_dir = Path(__file__).resolve().parent.parent
    python_exe = sys.executable

    print("[1/5] Starting backend server...")
    proc = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8008"],
        cwd=str(backend_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be responsive
    for _ in range(30):
        try:
            get_json("http://127.0.0.1:8008/api/health")
            break
        except Exception:
            time.sleep(0.3)
    else:
        proc.kill()
        print("ERROR: Failed to start backend server.")
        sys.exit(1)

    print("[2/5] Uploading synthetic document...")
    pdf_bytes = make_synthetic_pdf()
    upload_res = post_multipart(
        "http://127.0.0.1:8008/api/extract",
        "synthetic_invoice.pdf",
        pdf_bytes,
        "application/pdf",
    )
    doc_id = upload_res["id"]
    page_preview_url = upload_res["pages"][0]["preview_url"]
    print(f"Uploaded successfully! ID: {doc_id}, status: {upload_res['status']}")

    print("[3/5] Stopping backend server (simulating shutdown)...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

    print("[4/5] Restarting backend server...")
    proc2 = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8008"],
        cwd=str(backend_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    for _ in range(30):
        try:
            get_json("http://127.0.0.1:8008/api/health")
            break
        except Exception:
            time.sleep(0.3)
    else:
        proc2.kill()
        print("ERROR: Failed to restart backend server.")
        sys.exit(1)

    try:
        print("[5/5] Verifying persistence across restart...")
        doc_list = get_json("http://127.0.0.1:8008/api/documents")
        matching = [d for d in doc_list if d["id"] == doc_id]
        if not matching:
            print(f"FAILED: Document {doc_id} not found in /api/documents list!")
            sys.exit(1)
        print(f"Found document in GET /api/documents: filename={matching[0]['filename']}, status={matching[0]['status']}")

        preview_full_url = f"http://127.0.0.1:8008{page_preview_url}"
        status_code, img_bytes = get_bytes(preview_full_url)
        if status_code == 200 and img_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            print(f"Preview successfully loaded from {page_preview_url} ({len(img_bytes)} bytes PNG)")
        else:
            print(f"FAILED: Preview failed to load with status {status_code}")
            sys.exit(1)

        print("\nSUCCESS: Phase 5 persistence and preview verification complete!")
    finally:
        proc2.terminate()
        try:
            proc2.wait(timeout=5)
        except Exception:
            proc2.kill()


if __name__ == "__main__":
    main()

