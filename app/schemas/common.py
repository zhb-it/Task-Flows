"""Shared response envelopes (项目文档 §26).

Success responses are `{"data": ..., "message": "success"}`; error responses are
`{"detail": ...}` and are rendered by the `AppError` handler in `app/main.py`.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    """Single-resource success envelope."""

    data: T
    message: str = "success"
