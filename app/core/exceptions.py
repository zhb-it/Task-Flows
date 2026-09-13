"""Application-level exceptions.

`ARCHITECTURE.md` assigns 异常 to the `core` module. Domain errors raised by the
Service layer carry the HTTP status they map to, so routers stay free of
business rules and a single handler (registered in `app/main.py`) renders the
project's error envelope — `{"detail": ...}` (项目文档 §26).
"""


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
