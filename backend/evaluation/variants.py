"""Deterministic degraded variant generation (lowres, jpeg35, rot3blur)."""

import io
import json
import logging
from pathlib import Path
from typing import Optional

import pymupdf
from PIL import Image, ImageFilter

from evaluation.ground_truth import get_data_dir, get_gt_dir, get_variants_dir

logger = logging.getLogger("evaluation.variants")

VARIANT_TYPES = ("lowres", "jpeg35", "rot3blur")


def apply_degradation(img: Image.Image, variant: str) -> Image.Image:
    """Apply a deterministic visual degradation to a Pillow RGB image.

    - lowres: scale to 50% width and height.
    - jpeg35: re-encode at JPEG quality 35.
    - rot3blur: rotate 3 degrees (white fill, expand canvas) then GaussianBlur radius 1.2.
    """
    if variant == "lowres":
        new_w = max(1, int(img.width * 0.5))
        new_h = max(1, int(img.height * 0.5))
        return img.resize((new_w, new_h), Image.Resampling.BILINEAR)

    elif variant == "jpeg35":
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=35)
        buf.seek(0)
        return Image.open(buf).convert("RGB")

    elif variant == "rot3blur":
        # Rotate 3 degrees counter-clockwise with white fill and expanded canvas
        rotated = img.rotate(3, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255))
        # Apply GaussianBlur radius 1.2
        return rotated.filter(ImageFilter.GaussianBlur(radius=1.2))

    else:
        raise ValueError(f"Unknown variant type: '{variant}'")


def resolve_doc_id_for_file(file_path: Path) -> str:
    """Find the doc_id from ground truth if available, otherwise use filename stem."""
    gt_dir = get_gt_dir()
    if gt_dir.exists():
        for gt_file in gt_dir.glob("*.json"):
            if gt_file.name == ".gitkeep":
                continue
            try:
                data = json.loads(gt_file.read_text(encoding="utf-8"))
                if data.get("source_file") == file_path.name:
                    return str(data.get("doc_id", file_path.stem))
            except Exception:
                pass
    return file_path.stem


def generate_variants_for_pdf(doc_path: Path, doc_id: str, out_dir: Path) -> list[Path]:
    """Generate image-only PDF variants with no text layer for a PDF document."""
    doc = pymupdf.open(str(doc_path))
    # Render all pages at 150 DPI
    rendered_pages: list[Image.Image] = []
    for page in doc:
        pix = page.get_pixmap(dpi=150)
        page_img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        rendered_pages.append(page_img)
    doc.close()

    created_paths: list[Path] = []
    for variant in VARIANT_TYPES:
        out_path = out_dir / f"{doc_id}__{variant}.pdf"
        var_pdf = pymupdf.open()

        for page_img in rendered_pages:
            deg_img = apply_degradation(page_img, variant)
            buf = io.BytesIO()
            deg_img.save(buf, format="PNG")
            img_bytes = buf.getvalue()

            w, h = deg_img.size
            new_page = var_pdf.new_page(width=w, height=h)
            new_page.insert_image(pymupdf.Rect(0, 0, w, h), stream=img_bytes)

        var_pdf.save(str(out_path), no_new_id=True, deflate=True)
        var_pdf.close()
        created_paths.append(out_path)

    return created_paths


def generate_variants_for_image(doc_path: Path, doc_id: str, out_dir: Path) -> list[Path]:
    """Generate degraded image variants for a PNG/JPG document."""
    img = Image.open(doc_path).convert("RGB")
    created_paths: list[Path] = []

    for variant in VARIANT_TYPES:
        out_path = out_dir / f"{doc_id}__{variant}.jpg"
        deg_img = apply_degradation(img, variant)
        deg_img.save(out_path, format="JPEG", quality=90)
        created_paths.append(out_path)

    return created_paths


def generate_variants_for_document(doc_path: Path, out_dir: Optional[Path] = None) -> list[Path]:
    """Generate all three variants for a single document file."""
    target_dir = out_dir or get_variants_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    doc_id = resolve_doc_id_for_file(doc_path)
    suffix = doc_path.suffix.lower()

    if suffix == ".pdf":
        return generate_variants_for_pdf(doc_path, doc_id, target_dir)
    elif suffix in (".png", ".jpg", ".jpeg"):
        return generate_variants_for_image(doc_path, doc_id, target_dir)
    else:
        logger.warning("Unsupported file format for variant generation: %s", doc_path.name)
        return []


def cmd_variants() -> int:
    """Generate degraded image variants for all documents in eval/data/."""
    data_dir = get_data_dir()
    variants_dir = get_variants_dir()
    variants_dir.mkdir(parents=True, exist_ok=True)

    data_files = [p for p in data_dir.iterdir() if p.is_file() and p.name != ".gitkeep"]
    if not data_files:
        print(f"No documents found in {data_dir}. Place your document files there first.")
        return 0

    total_created = 0
    print(f"Generating variants for {len(data_files)} document(s) in {data_dir}...")
    for doc_path in sorted(data_files):
        created = generate_variants_for_document(doc_path, variants_dir)
        total_created += len(created)
        print(f"  ✓ {doc_path.name} -> {len(created)} variants created:")
        for cp in created:
            print(f"      - {cp.name}")

    print(f"\nDone: {total_created} total variant file(s) generated under {variants_dir}.")
    return 0
