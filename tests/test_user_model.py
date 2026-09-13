"""Offline tests for the User ORM model.

These tests only inspect the mapped columns and constraints on
:class:`app.models.user.User`; they do not require a running PostgreSQL.
Importing :mod:`app.models` also registers the table on
:data:`app.db.base.Base.metadata`, which Alembic relies on for autogenerate.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String
from sqlalchemy.orm import Mapped

from app.db.base import Base
from app.models import User
from app.models.user import User as UserClass


def test_user_registered_on_metadata():
    assert "users" in Base.metadata.tables


def test_tablename():
    assert User.__tablename__ == "users"


def test_columns_present_and_named():
    expected = {
        "id",
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
    assert col.unique is True
    assert col.nullable is False
    assert isinstance(col.type, String)


def test_email_unique_not_null():
    col = User.__table__.columns["email"]
    assert col.unique is True
    assert col.nullable is False
    assert isinstance(col.type, String)


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
