"""Offline tests for the User ORM model.

These tests only inspect the mapped columns and constraints on
:class:`app.models.user.User`; they do not require a running PostgreSQL.
Importing :mod:`app.models` also registers the table on
:data:`app.db.base.Base.metadata`, which Alembic relies on for autogenerate.
"""


from sqlalchemy import BigInteger, Boolean, DateTime, String

from app.db.base import Base
from app.models import User
import sqlalchemy as sa
from app.models.user import User as UserClass


def test_user_registered_on_metadata():
    assert "users" in Base.metadata.tables


def test_tablename():
    assert User.__tablename__ == "users"


def test_columns_present_and_named():
    expected = {
        "id",
        "tenant_id",
        "username",
        "email",
        "password_hash",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert set(User.__table__.columns.keys()) == expected


def test_id_is_bigint_primary_key():
    col = User.__table__.columns["id"]
    assert col.primary_key is True
    assert isinstance(col.type, BigInteger)


def test_username_unique_not_null():
    col = User.__table__.columns["username"]
    # TASK-094：唯一性租户化为 (tenant_id, username) 复合约束，列级
    # unique 已去（TASK-093 教训：显式命名约束防 autogenerate 漂移）。
    assert col.unique is not True
    assert col.nullable is False
    assert isinstance(col.type, String)
    cons = {
        c.name
        for c in User.__table__.constraints
        if isinstance(c, sa.UniqueConstraint)
    }
    assert "uq_users_tenant_username" in cons


def test_email_unique_not_null():
    col = User.__table__.columns["email"]
    # TASK-094：同 username，唯一性由 (tenant_id, email) 复合约束承担。
    assert col.unique is not True
    assert col.nullable is False
    assert isinstance(col.type, String)
    cons = {
        c.name
        for c in User.__table__.constraints
        if isinstance(c, sa.UniqueConstraint)
    }
    assert "uq_users_tenant_email" in cons


def test_password_hash_not_null():
    col = User.__table__.columns["password_hash"]
    assert col.nullable is False
    assert isinstance(col.type, String)


def test_is_active_boolean_with_defaults():
    col = User.__table__.columns["is_active"]
    assert isinstance(col.type, Boolean)
    assert col.nullable is False
    assert col.default is not None
    assert col.server_default is not None


def test_timestamps_timezone_aware():
    for name in ("created_at", "updated_at"):
        col = User.__table__.columns[name]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True
        assert col.nullable is False
        assert col.server_default is not None


def test_model_inherits_base():
    assert issubclass(UserClass, Base)


def test_mapped_annotations_resolved():
    # Mapped[str] / Mapped[int] / Mapped[bool] should resolve to concrete types.
    assert User.__mapper__.columns["username"].type.python_type is str
    assert User.__mapper__.columns["id"].type.python_type is int
    assert User.__mapper__.columns["is_active"].type.python_type is bool
