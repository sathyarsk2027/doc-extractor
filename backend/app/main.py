"""AI Document-to-Data Extractor Backend Application."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.errors import AppError, ErrorDetail, ErrorResponse
from app.routes.extract import router as extract_router
from app.routes.files import router as files_router
from app.routes.documents import router as documents_router
from app.services.storage import cleanup_expired
from app.services.db import init_db
from app.services.documents import purge_retention

logger = logging.getLogger("doc_extractor")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Execute startup and shutdown lifecycle events."""
    # 1. Initialize database schema
    try:
        init_db()
    except Exception as exc:
        logger.warning("Error running database initialization: %s", exc)

    # 2. Purge documents older than RETENTION_DAYS
    try:
        purge_retention()
    except Exception as exc:
        logger.warning("Error running retention purge: %s", exc)

    # 3. Run storage TTL cleanup for orphan folders
    try:
        cleanup_expired()
    except Exception as exc:
        logger.warning("Error running startup storage cleanup: %s", exc)
    yield


app = FastAPI(
    title="AI Document-to-Data Extractor",
    description="Backend API for document preprocessing and structured data extraction.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware allowing only FRONTEND_ORIGIN
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle known AppError exceptions with standard JSON error envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Transform FastAPI/Pydantic validation errors into standard JSON error envelope."""
    errors = exc.errors()
    code = "BAD_REQUEST"
    status_code = status.HTTP_400_BAD_REQUEST
    message = "Invalid request payload."

    if errors:
        first_err = errors[0]
        loc = first_err.get("loc", ())
        err_type = first_err.get("type", "")

        # Check if missing file upload parameter
        if "file" in loc or "body" in loc:
            if "missing" in err_type:
                code = "NO_FILE"
                status_code = status.HTTP_400_BAD_REQUEST
                message = "No file was uploaded."
            else:
                code = "NO_FILE"
                status_code = status.HTTP_400_BAD_REQUEST
                message = first_err.get("msg", "Invalid file upload.")
        else:
            message = first_err.get("msg", "Invalid request parameters.")

    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Transform Starlette/FastAPI HTTPExceptions into standard JSON error envelope."""
    code = "NOT_FOUND" if exc.status_code == status.HTTP_404_NOT_FOUND else "HTTP_ERROR"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": str(exc.detail)}},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unexpected errors; logs server-side and masks details from client."""
    logger.exception("Unhandled server exception processing request: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected internal server error occurred.",
            }
        },
    )


# Include API routers
app.include_router(extract_router)
app.include_router(files_router)
app.include_router(documents_router)


@app.get("/api/health", summary="Health Check")
def health_check() -> dict:
    """Return application health status."""
    return {"status": "ok"}
