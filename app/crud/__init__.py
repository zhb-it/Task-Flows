"""Data-access layer.

Each module here owns one model's database operations. Per the project
architecture the CRUD layer is responsible for *database operations only*;
business rules, authorization and transaction boundaries live in the Service
layer (introduced in later tasks). Write helpers therefore `flush`/`refresh`
but leave `commit` to the caller.
"""

from app.crud.user import (
    create_user,
    get_user,
    get_user_by_email,
    get_user_by_username,
    get_users,
)

__all__ = [
    "create_user",
    "get_user",
    "get_user_by_username",
    "get_user_by_email",
    "get_users",
]
