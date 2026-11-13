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

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "your-key-here")
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


settings = Settings()
