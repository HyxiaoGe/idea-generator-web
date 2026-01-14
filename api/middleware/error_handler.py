"""
Global exception handlers for the API.
"""

import logging
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError as PydanticValidationError

from core.exceptions import AppException

logger = logging.getLogger(__name__)


def setup_exception_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers with the FastAPI app.

    Args:
        app: FastAPI application instance
    """

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        """Handle custom application exceptions."""
        logger.warning(
            f"AppException: {exc.error_code} - {exc.message}",
            extra={"path": request.url.path, "details": exc.details}
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": exc.to_dict(),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError
    ) -> JSONResponse:
        """Handle request validation errors."""
        errors = []
        for error in exc.errors():
            loc = " -> ".join(str(x) for x in error["loc"])
            errors.append({
                "field": loc,
                "message": error["msg"],
                "type": error["type"],
            })

        logger.warning(
            f"Validation error on {request.url.path}",
            extra={"errors": errors}
        )

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": {"errors": errors},
                },
            },
        )

    @app.exception_handler(PydanticValidationError)
    async def pydantic_exception_handler(
        request: Request,
        exc: PydanticValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors."""
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "validation_error",
                    "message": "Data validation failed",
                    "details": {"errors": exc.errors()},
                },
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle all unhandled exceptions."""
        logger.exception(
            f"Unhandled exception on {request.url.path}: {exc}",
        )

        # In production, hide internal error details
        from core.config import get_settings
        settings = get_settings()

        if settings.is_production:
            message = "An unexpected error occurred"
            details = None
        else:
            message = str(exc)
            details = {"type": type(exc).__name__}

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "internal_error",
                    "message": message,
                    "details": details,
                },
            },
        )
