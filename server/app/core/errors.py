"""Error envelope helpers.

Every non-2xx response in HostelPass has the shape::

    { "error": { "code": "...", "message": "...", "details": {} } }

Domain code -> HTTP status mapping follows docs/API.md:
400 payload/validation · 401 auth · 403 policy/authorization · 404 not found ·
409 duplicate/conflict · 422 semantically unusable input · 429 rate limited ·
500 internal.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("hostelpass.errors")


class AppError(Exception):
    """Domain error carrying an HTTP status, a machine code and details."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def error_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the canonical error envelope body."""
    return {"error": {"code": code, "message": message, "details": details or {}}}


def error_response(status_code: int, code: str, message: str,
                   details: dict[str, Any] | None = None) -> JSONResponse:
    """Render the canonical error envelope as a JSON response."""
    return JSONResponse(status_code=status_code, content=error_payload(code, message, details))


# --- Convenience constructors for the codes used across the API -------------

def invalid_payload(message: str = "Request payload is invalid.",
                    details: dict[str, Any] | None = None) -> AppError:
    return AppError(400, "invalid_payload", message, details)


def invalid_credentials(message: str = "Incorrect email or roll number, or password.") -> AppError:
    return AppError(401, "invalid_credentials", message)


def token_invalid(message: str = "Authentication token is invalid.") -> AppError:
    return AppError(401, "token_invalid", message)


def token_revoked() -> AppError:
    return AppError(401, "token_revoked", "Token has been revoked. Please log in again.")


def forbidden(message: str = "You are not allowed to perform this action.") -> AppError:
    return AppError(403, "forbidden", message)


def not_found(resource: str = "Resource") -> AppError:
    return AppError(404, "not_found", f"{resource} not found.")


def conflict(message: str = "Conflicting state.", details: dict[str, Any] | None = None) -> AppError:
    return AppError(409, "conflict", message, details)


def duplicate_attendance(date_str: str) -> AppError:
    return AppError(
        409,
        "duplicate_attendance",
        f"Attendance already recorded for {date_str}.",
        {"date": date_str},
    )


def rate_limited(limit: int, window_seconds: int = 60) -> AppError:
    return AppError(
        429,
        "rate_limited",
        "Too many requests. Please wait a moment and try again.",
        {"limit": limit, "window_seconds": window_seconds},
    )


def internal_error() -> AppError:
    return AppError(500, "internal_error", "An unexpected error occurred.")


# HTTP status -> machine code for framework-raised HTTPExceptions.
_STATUS_CODES: dict[int, str] = {
    400: "invalid_payload",
    401: "token_invalid",
    403: "forbidden",
    404: "not_found",
    405: "not_found",
    409: "conflict",
    422: "invalid_payload",
    429: "rate_limited",
}


def _validation_details(exc: RequestValidationError) -> dict[str, Any]:
    """Flatten pydantic errors into serialisable details."""
    fields: list[dict[str, Any]] = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", [])]
        fields.append({
            "field": ".".join(loc[1:]) if loc and loc[0] in {"body", "query"} else ".".join(loc),
            "message": err.get("msg", "invalid"),
            "type": err.get("type", "value_error"),
        })
    return {"fields": fields}


def add_exception_handlers(app: FastAPI) -> None:
    """Register handlers that reshape every error into the envelope."""

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("AppError %s on %s %s: %s", exc.code, request.method, request.url.path, exc.message)
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(400, "invalid_payload", "Request payload is invalid.",
                              _validation_details(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "internal_error" if exc.status_code >= 500 else "invalid_payload")
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return error_response(exc.status_code, code, detail)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(500, "internal_error", "An unexpected error occurred.")
