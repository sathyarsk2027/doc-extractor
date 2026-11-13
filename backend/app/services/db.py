"""Database service using standard library sqlite3."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from app.config import settings

CURRENT_SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    pages_json TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reviewed_at TEXT NULL
);

CREATE TABLE IF NOT EXISTS extractions (
    document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    original_json TEXT NULL,
    reviewed_json TEXT NULL,
    flags_json TEXT NOT NULL,
    meta_json TEXT NULL,
    error_json TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
"""


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format with microsecond precision."""
    return datetime.now(timezone.utc).isoformat()


def get_db_path() -> Path:
    """Return resolved database file path, ensuring parent directory exists."""
    db_path = settings.db_file_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_db_connection(db_file: Path | str | None = None) -> sqlite3.Connection:
    """Create and configure a new SQLite connection."""
    target_path = Path(db_file) if db_file else get_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


@contextmanager
def get_db(db_file: Path | str | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for acquiring a database connection per request."""
    conn = get_db_connection(db_file)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_file: Path | str | None = None) -> None:
    """Initialize database tables and schema versioning if missing."""
    with get_db(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        version = cursor.fetchone()[0]

        if version < CURRENT_SCHEMA_VERSION:
            cursor.executescript(SCHEMA_SQL)
            cursor.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION};")
