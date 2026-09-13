"""Application-level exceptions.

`ARCHITECTURE.md` assigns 异常 to the `core` module. Domain errors raised by the
Service layer carry the HTTP status they map to, so routers stay free of
business rules and a single handler renders the project's error envelope —
`{"detail": ...}` (项目文档 §26).
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for expected, client-facing application errors."""

    status_code: int = 500
    detail: str = "Internal server error"
    #: Optional extra HTTP response headers (e.g. ``WWW-Authenticate`` on 401).
    headers: dict[str, str] | None = None

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class UnauthorizedError(AppError):
    """401 Unauthorized — credentials missing, invalid, or token unusable."""

    status_code = 401
    detail = "Not authenticated"
    headers = {"WWW-Authenticate": "Bearer"}


class ForbiddenError(AppError):
    """403 Forbidden — authenticated but not permitted (or account disabled)."""

    status_code = 403
    detail = "Forbidden"


class ConflictError(AppError):
    """409 Conflict — request conflicts with existing data (duplicate identity)."""

    status_code = 409
    detail = "Resource conflict"


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    """Render domain errors with the project error envelope (项目文档 §26).

    Lives in core next to the exception types so any FastAPI app — the product
    `app.main` and test-harness apps alike — can register the same rendering.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )
