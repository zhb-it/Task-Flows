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


class ResourceNotFoundError(AppError):
    """404 Not Found — 资源不存在，或不在调用者的归属链上。

    开发文档 §49 IDOR 防护（TASK-024 决策）：跨团队访问他人资源与资源不存在
    统一以 404 呈现——客户端无法通过 403/404 差异枚举资源 id。功能级权限
    缺失（不针对具体资源）仍用 `ForbiddenError`(403)，见 TASK-023 契约。
    """

    status_code = 404
    detail = "Resource not found"


class RateLimitExceededError(AppError):
    """429 Too Many Requests — 滑动窗口内请求数超过配额（项目文档 §22 / §26）。

    `Retry-After` 告诉客户端还要等多久（秒），符合 RFC 9110 对 429 的建议；
    没有它客户端只能盲目重试，反而加剧限流。
    """

    status_code = 429
    detail = "Too many requests"

    def __init__(self, detail: str | None = None, retry_after: int | None = None) -> None:
        super().__init__(detail)
        if retry_after is not None:
            # 不允许 0 或负数——那会让客户端立刻重试并再次被拒。
            self.headers = {"Retry-After": str(max(1, int(retry_after)))}


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
