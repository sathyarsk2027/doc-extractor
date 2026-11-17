"""Configuration settings for AI Document-to-Data Extractor."""

import os
from dataclasses import dataclass
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

# Resolve path to backend/.env
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)


class Settings(BaseModel):
    """Application settings loaded from environment with typed defaults."""

    # Groq LLM settings
    groq_api_key: str = os.getenv("GROQ_API_KEY", "your-key-here")
    groq_model: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    groq_timeout_seconds: int = int(os.getenv("GROQ_TIMEOUT_SECONDS", "60"))
    groq_max_retries: int = int(os.getenv("GROQ_MAX_RETRIES", "2"))
    groq_max_output_tokens: int = int(os.getenv("GROQ_MAX_OUTPUT_TOKENS", "1500"))
    groq_seed: int = int(os.getenv("GROQ_SEED", "42"))
    extraction_max_pages: int = int(os.getenv("EXTRACTION_MAX_PAGES", "2"))
    extraction_mode: str = os.getenv("EXTRACTION_MODE", "auto")  # "auto", "text", "image"
    pipeline_version: str = os.getenv("PIPELINE_VERSION", "v2")  # "v1", "v2"
    gst_slab_multipliers: list[float] = [1.05, 1.12, 1.18, 1.28]

    # General app settings
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    max_file_mb: int = int(os.getenv("MAX_FILE_MB", "10"))
    max_pdf_pages: int = int(os.getenv("MAX_PDF_PAGES", "5"))
    max_image_width: int = int(os.getenv("MAX_IMAGE_WIDTH", "2000"))
    pdf_render_dpi: int = int(os.getenv("PDF_RENDER_DPI", "150"))
    storage_dir: str = os.getenv("STORAGE_DIR", "storage")
    file_ttl_minutes: int = int(os.getenv("FILE_TTL_MINUTES", "60"))
    db_path: str = os.getenv("DB_PATH", "data/app.db")
    retention_days: int = int(os.getenv("RETENTION_DAYS", "30"))

    @property
    def db_file_path(self) -> Path:
        """Return the resolved database file Path."""
        p = Path(self.db_path)
        if not p.is_absolute():
            p = BACKEND_DIR / p
        return p

    @property
    def storage_path(self) -> Path:
        """Return the resolved storage directory Path."""
        p = Path(self.storage_dir)
        if not p.is_absolute():
            p = BACKEND_DIR / p
        return p

    @property
    def groq_api_key_valid(self) -> bool:
        """Check that the Groq API key is set and not a placeholder."""
        return bool(
            self.groq_api_key
            and self.groq_api_key not in ("your-key-here", "")
        )


settings = Settings()


@dataclass(frozen=True)
class PipelineFeatures:
    """Feature flags and configuration for a given pipeline version."""

    version: str
    table_aware_text: bool        # v1: False (page.get_text("text")), v2: True (sort=True + find_tables)
    multi_invoice_detection: bool # v1: False (standard select_pages), v2: True (detect_multi_invoices + page re-selection)
    tax_aware_item_math: bool     # v1: False (strict math check), v2: True (skip GST slab ratios)
    text_grounding_check: bool    # v1: False (no FIELD_NOT_IN_TEXT), v2: True (FIELD_NOT_IN_TEXT check)
    prompt_version: str           # v1: "v1" (PROMPT_V1), v2: "v2" (PROMPT_V2)

    @property
    def short_string(self) -> str:
        """Compact feature summary for manifests and results."""
        if self.version == "v1":
            return "v1:baseline"
        return "v2:table_text,multi_inv,tax_item,text_ground,prompt_v2"


def features_for(version: str | None = None) -> PipelineFeatures:
    """Return the feature flag bundle for a pipeline version ('v1' or 'v2').

    Defaults to settings.pipeline_version (or env var PIPELINE_VERSION, default 'v2').
    """
    v = (version or getattr(settings, "pipeline_version", "v2")).lower().strip()
    if v == "v1":
        return PipelineFeatures(
            version="v1",
            table_aware_text=False,
            multi_invoice_detection=False,
            tax_aware_item_math=False,
            text_grounding_check=False,
            prompt_version="v1",
        )
    return PipelineFeatures(
        version="v2",
        table_aware_text=True,
        multi_invoice_detection=True,
        tax_aware_item_math=True,
        text_grounding_check=True,
        prompt_version="v2",
    )
