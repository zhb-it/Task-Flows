"""Declarative base shared by every ORM model.

All `models` import `Base` from here so they share one metadata registry
and Alembic can autogenerate migrations against it.
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()
