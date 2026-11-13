"""Configuration settings for AI Document-to-Data Extractor."""

import os
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

    # General app settings
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    max_file_mb: int = int(os.getenv("MAX_FILE_MB", "10"))
    max_pdf_pages: int = int(os.getenv("MAX_PDF_PAGES", "5"))
    max_image_width: int = int(os.getenv("MAX_IMAGE_WIDTH", "2000"))
    pdf_render_dpi: int = int(os.getenv("PDF_RENDER_DPI", "150"))
    storage_dir: str = os.getenv("STORAGE_DIR", "storage")
    file_ttl_minutes: int = int(os.getenv("FILE_TTL_MINUTES", "60"))

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
