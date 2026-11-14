"""Pipeline runner, case matrix planning, pacing, and execution."""

import hashlib
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pymupdf

from app.config import settings
from app.errors import AppError
from app.schemas import InvoiceData, ExtractionMeta
from app.services.checks import run_checks
from app.services.extractor import extract_document
from app.services.preprocessing import preprocess_document
from app.services.storage import delete_document, get_document_dir, save_original
from app.services.validation import detect_mime_type
from evaluation.ground_truth import (
    get_data_dir,
    get_gt_dir,
    get_results_dir,
    get_variants_dir,
    load_ground_truth,
)

logger = logging.getLogger("evaluation.pipeline_runner")


@dataclass
class PipelineResult:
    """Standardized result of running extraction pipeline on a document file."""

    extraction: Optional[InvoiceData]
    flags: dict[str, Any]
    needs_review: bool
    meta: Optional[ExtractionMeta]
    error: Optional[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        """Convert result to JSON-serializable dictionary."""
        return {
            "extraction": self.extraction.model_dump() if self.extraction else None,
            "flags": self.flags,
            "needs_review": self.needs_review,
            "meta": self.meta.model_dump() if self.meta else None,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineResult":
        """Reconstruct PipelineResult from serialized dictionary."""
        raw_extraction = data.get("extraction")
        extraction = InvoiceData.model_validate(raw_extraction) if raw_extraction else None
        raw_meta = data.get("meta")
        meta = ExtractionMeta.model_validate(raw_meta) if raw_meta else None
        return cls(
            extraction=extraction,
            flags=data.get("flags", {}),
            needs_review=data.get("needs_review", False),
            meta=meta,
            error=data.get("error"),
        )


@dataclass
class EvalCase:
    """A single evaluation execution unit."""

    case_id: str
    doc_id: str
    source_file: str
    target_path: Path
    mode: str
    case_type: str  # text, image, lowres, jpeg35, rot3blur
    estimated_tokens: int


def has_usable_text_layer(path: Path | str, min_chars: int = 50) -> bool:
    """Check if a file is a PDF with at least min_chars of embedded text."""
    p = Path(path)
    if not p.is_file():
        return False
    try:
        content = p.read_bytes()
        mime = detect_mime_type(content[:32])
        if mime != "application/pdf":
            return False
        doc = pymupdf.open(stream=content, filetype="pdf")
        total_text = "".join(page.get_text() for page in doc)
        doc.close()
        return len(total_text.strip()) >= min_chars
    except Exception as exc:
        logger.debug("Error checking text layer for %s: %s", path, exc)
        return False


def run_pipeline_on_file(path: Path | str, mode: Optional[str] = None) -> PipelineResult:
    """Execute preprocessing, extraction, and validation on a single document file.

    Does not write to SQLite DB; isolates working files in a temporary storage
    directory and removes all temporary files after completion.
    """
    file_path = Path(path)
    if not file_path.is_file():
        return PipelineResult(
            extraction=None,
            flags={},
            needs_review=True,
            meta=None,
            error={"code": "FILE_NOT_FOUND", "message": f"File not found: {file_path}"},
        )

    document_id = str(uuid.uuid4())
    try:
        content = file_path.read_bytes()
        mime_type = detect_mime_type(content[:32])

        # Preprocess pages into storage/{document_id}/
        save_original(document_id, content, mime_type)
        doc_dir = get_document_dir(document_id)
        preprocess_document(doc_dir, content, mime_type)

        # Run extraction with mode override (does NOT touch DB)
        invoice_data, meta = extract_document(document_id, mode_override=mode)

        # Run validation checks
        flags = run_checks(invoice_data)
        needs_review = bool(flags)

        return PipelineResult(
            extraction=invoice_data,
            flags=flags,
            needs_review=needs_review,
            meta=meta,
            error=None,
        )

    except AppError as exc:
        logger.warning("Pipeline AppError on %s: [%s] %s", file_path.name, exc.code, exc.message)
        return PipelineResult(
            extraction=None,
            flags={},
            needs_review=True,
            meta=None,
            error={"code": exc.code, "message": exc.message},
        )
    except Exception as exc:
        logger.exception("Unexpected error in run_pipeline_on_file for %s", file_path.name)
        return PipelineResult(
            extraction=None,
            flags={},
            needs_review=True,
            meta=None,
            error={"code": type(exc).__name__, "message": str(exc)},
        )
    finally:
        # Guarantee cleanup of all temporary preview images and original files
        try:
            delete_document(document_id)
        except Exception as exc:
            logger.debug("Failed to clean up doc dir %s: %s", document_id, exc)


def get_git_commit() -> str:
    """Retrieve current git commit hash."""
    try:
        res = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent.parent.parent), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def get_prompt_sha256() -> str:
    """Retrieve SHA-256 hash of EXTRACTION_PROMPT."""
    try:
        from app.services.groq_extractor import EXTRACTION_PROMPT
        return hashlib.sha256(EXTRACTION_PROMPT.encode("utf-8")).hexdigest()
    except Exception:
        return "unknown"


def build_case_matrix(only_doc: Optional[str] = None) -> list[EvalCase]:
    """Build the case matrix for all documents in eval/data/."""
    data_dir = get_data_dir()
    gt_dir = get_gt_dir()
    variants_dir = get_variants_dir()

    data_files = sorted([p for p in data_dir.iterdir() if p.is_file() and p.name != ".gitkeep"])
    cases: list[EvalCase] = []

    for doc_path in data_files:
        # Resolve doc_id
        doc_id = doc_path.stem
        # Check ground truth for explicit doc_id
        for gt_path in gt_dir.glob("*.json"):
            if gt_path.name == ".gitkeep":
                continue
            try:
                gt_data = load_ground_truth(gt_path)
                if gt_data.get("source_file") == doc_path.name:
                    doc_id = gt_data.get("doc_id", doc_id)
                    break
            except Exception:
                pass

        if only_doc and (only_doc not in (doc_id, doc_path.name, doc_path.stem)):
            continue

        # 1. Text-path case (only if usable text layer exists)
        if has_usable_text_layer(doc_path):
            cases.append(
                EvalCase(
                    case_id=f"{doc_id}__text",
                    doc_id=doc_id,
                    source_file=doc_path.name,
                    target_path=doc_path,
                    mode="text",
                    case_type="text",
                    estimated_tokens=2200,
                )
            )

        # 2. Clean image-path case
        cases.append(
            EvalCase(
                case_id=f"{doc_id}__image",
                doc_id=doc_id,
                source_file=doc_path.name,
                target_path=doc_path,
                mode="image",
                case_type="image",
                estimated_tokens=4000,
            )
        )

        # 3. Degraded variants (lowres, jpeg35, rot3blur)
        ext = ".pdf" if doc_path.suffix.lower() == ".pdf" else ".jpg"
        for v in ("lowres", "jpeg35", "rot3blur"):
            var_path = variants_dir / f"{doc_id}__{v}{ext}"
            cases.append(
                EvalCase(
                    case_id=f"{doc_id}__{v}",
                    doc_id=doc_id,
                    source_file=doc_path.name,
                    target_path=var_path,
                    mode="auto",
                    case_type=v,
                    estimated_tokens=4000,
                )
            )

    return cases


def cmd_plan(only_doc: Optional[str] = None) -> int:
    """Print evaluation case matrix, token estimates, and runtime without API calls."""
    cases = build_case_matrix(only_doc=only_doc)
    if not cases:
        print("No cases found in case matrix. Ensure documents are in eval/data/.")
        return 0

    total_tokens = sum(c.estimated_tokens for c in cases)
    # Estimate time: 8000 tokens/min limit + ~15s per-call pacing
    total_minutes = (total_tokens / 8000.0) + (len(cases) * 15.0 / 60.0)
    daily_cap = int(os.getenv("EVAL_DAILY_TOKEN_CAP", 150000))

    print(f"=== Evaluation Plan & Case Matrix (Dry Run) ===")
    print(f"Total Cases: {len(cases)} across {len(set(c.doc_id for c in cases))} document(s)\n")

    for idx, c in enumerate(cases, 1):
        status_note = ""
        if not c.target_path.exists():
            status_note = " (file not yet generated: run 'cli variants')"
        print(f"  {idx:2d}. {c.case_id:<26} [mode={c.mode:<5}] ~{c.estimated_tokens:,} tokens{status_note}")

    print("\n--- Summary Estimates (Zero Real API Calls) ---")
    print(f"  Total API Calls:     {len(cases)} calls (authorized budget: at most 45 calls)")
    print(f"  Estimated Tokens:    {total_tokens:,} tokens")
    print(f"  Estimated Runtime:   ~{total_minutes:.1f} minutes (respecting 8K tokens/min rate & pacing)")
    print(f"  Daily Token Cap:     {daily_cap:,} tokens (env: EVAL_DAILY_TOKEN_CAP)")

    return 0


def load_daily_usage(date_str: str) -> dict[str, Any]:
    """Load or initialize usage data for a specific date."""
    usage_file = get_results_dir() / "usage.json"
    if usage_file.is_file():
        try:
            all_usage = json.loads(usage_file.read_text(encoding="utf-8"))
            return all_usage.get(date_str, {"date": date_str, "total_tokens": 0, "total_calls": 0})
        except Exception:
            pass
    return {"date": date_str, "total_tokens": 0, "total_calls": 0}


def update_daily_usage(date_str: str, tokens: int, calls: int = 1) -> None:
    """Record token and call count to eval/results/usage.json."""
    results_dir = get_results_dir()
    results_dir.mkdir(parents=True, exist_ok=True)
    usage_file = results_dir / "usage.json"

    all_usage: dict[str, Any] = {}
    if usage_file.is_file():
        try:
            all_usage = json.loads(usage_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    current = all_usage.get(date_str, {"date": date_str, "total_tokens": 0, "total_calls": 0})
    current["total_tokens"] += tokens
    current["total_calls"] += calls
    all_usage[date_str] = current

    with usage_file.open("w", encoding="utf-8") as f:
        json.dump(all_usage, f, indent=2)


def write_manifest(case_ids: list[str]) -> Path:
    """Generate and write eval/results/manifest.json."""
    results_dir = get_results_dir()
    results_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = results_dir / "manifest.json"

    manifest_data = {
        "date": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit(),
        "model": settings.groq_model,
        "seed": settings.groq_seed,
        "default_extraction_mode": settings.extraction_mode,
        "prompt_sha256": get_prompt_sha256(),
        "python_version": sys.version.split()[0],
        "cases": case_ids,
    }

    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    return manifest_path


def cmd_run(
    limit: Optional[int] = None,
    only: Optional[str] = None,
    force: bool = False,
    repeats: int = 1,
) -> int:
    """Execute evaluation run with rate-limit pacing and automatic resume."""
    results_dir = get_results_dir()
    raw_dir = results_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    cases = build_case_matrix(only_doc=only)
    if not cases:
        print("No cases to run.")
        return 0

    write_manifest([c.case_id for c in cases])

    daily_cap = int(os.getenv("EVAL_DAILY_TOKEN_CAP", 150000))
    today_str = datetime.now().strftime("%Y-%m-%d")
    usage = load_daily_usage(today_str)

    executed = 0
    consecutive_errors = 0

    print(f"=== Starting Evaluation Run ===")
    print(f"Cases to evaluate: {len(cases)} (limit={limit}, force={force})")
    print(f"Today's usage so far: {usage['total_tokens']:,} tokens across {usage['total_calls']} calls\n")

    for case in cases:
        if limit is not None and executed >= limit:
            print(f"\n[LIMIT] Reached limit of {limit} cases for this run.")
            print(f"Resume remaining cases with: python -m evaluation.cli run")
            return 0

        case_out_file = raw_dir / f"{case.case_id}.json"
        if case_out_file.exists() and not force:
            print(f"  [CACHED] {case.case_id}")
            continue

        # Check budget before executing
        if usage["total_tokens"] + case.estimated_tokens > daily_cap:
            print(f"\n[STOP] Reached or approaching daily token cap ({usage['total_tokens']:,}/{daily_cap:,}).")
            print("Run stopped cleanly to protect quota. Resume tomorrow with: python -m evaluation.cli run")
            return 0

        if not case.target_path.is_file():
            print(f"  [ERROR] File missing for case {case.case_id}: {case.target_path}")
            consecutive_errors += 1
            if consecutive_errors >= 3:
                print("\n[STOP] 3 consecutive errors encountered. Stopping cleanly.")
                return 1
            continue

        print(f"  [RUN] {case.case_id} (mode={case.mode})...", end="", flush=True)

        res = run_pipeline_on_file(case.target_path, mode=case.mode)

        # Save result JSON
        with case_out_file.open("w", encoding="utf-8") as f:
            json.dump(res.to_dict(), f, indent=2)

        executed += 1

        if res.error:
            consecutive_errors += 1
            print(f" FAILED [{res.error.get('code')}]: {res.error.get('message')}")
            # Stop if 429 indicates long wait
            if res.error.get("code") == "RATE_LIMITED" and "wait" in res.error.get("message", "").lower():
                print("[STOP] Rate limit exceeded threshold. Run stopped cleanly.")
                return 0
            if consecutive_errors >= 3:
                print("\n[STOP] 3 consecutive errors encountered. Stopping cleanly.")
                return 1
        else:
            consecutive_errors = 0
            tokens_used = (res.meta.input_tokens + res.meta.output_tokens) if res.meta else case.estimated_tokens
            update_daily_usage(today_str, tokens_used, calls=1)
            usage["total_tokens"] += tokens_used
            usage["total_calls"] += 1
            print(f" OK ({tokens_used:,} tokens, {res.meta.latency_ms if res.meta else 0}ms)")

            # Pacing sleep: max(10, total_tokens / 8000 * 60 + 5)
            pacing_seconds = max(10, int((tokens_used / 8000.0) * 60.0 + 5.0))
            if executed < len(cases) and (limit is None or executed < limit):
                print(f"    (Pacing: sleeping {pacing_seconds}s to respect Groq rate limits...)")
                time.sleep(pacing_seconds)

    print(f"\nRun complete: {executed} case(s) executed.")
    return 0
