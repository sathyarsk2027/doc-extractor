"""Application error definitions and error response models."""

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Structured error payload detail."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Envelope for all API error responses."""

    error: ErrorDetail


class AppError(Exception):
    """Custom application exception with structured code, message, and status code."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
