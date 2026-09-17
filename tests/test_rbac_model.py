"""TASK-021：RBAC 四表 ORM 模型的离线测试。

只检查映射的列与约束，不需要运行中的 PostgreSQL。导入 `app.models` 会把
四张表注册到 `app.db.base.Base.metadata`，供 Alembic autogenerate 使用。

列集依据 TASK-021 的确认决策（docs/DB_SCHEMA.md 已登记）：
- roles / permissions：id + name UNIQUE + 可空 description + 双时间戳
- user_roles / role_permissions：id 主键 + 双 FK CASCADE（带索引）+ 复合 UNIQUE
"""

from sqlalchemy import BigInteger, DateTime, String, UniqueConstraint

from app.db.base import Base
from app.models import Permission, Role, RolePermission, UserRole


# --- metadata 注册 ---------------------------------------------------------


def test_all_four_tables_registered_on_metadata():
    for table in ("roles", "permissions", "user_roles", "role_permissions"):
        assert table in Base.metadata.tables, table


# --- roles -----------------------------------------------------------------


def test_role_tablename():
    assert Role.__tablename__ == "roles"


def test_role_columns():
    assert set(Role.__table__.columns.keys()) == {
        "id",
        "tenant_id",
        "name",
        "description",
        "created_at",
        "updated_at",
    }


def test_role_id_is_bigint_primary_key():
    col = Role.__table__.columns["id"]
    assert col.primary_key is True
    assert isinstance(col.type, BigInteger)


def test_role_name_unique_not_null():
    col = Role.__table__.columns["name"]
    # TASK-096：name 在租户内唯一（uq_roles_tenant_name），不再是列级全局 unique。
    # 唯一约束改为表级 UniqueConstraint，因此列对象的 .unique 为 None（而非 False）。
    assert col.unique is None
    assert col.nullable is False
    assert isinstance(col.type, String)
    # 复合唯一约束 (tenant_id, name) 必须在位，且 name 收窄为 String(64)。
    constraints = [
        c for c in Role.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    pairs = {tuple(c.columns.keys()) for c in constraints}
    assert ("tenant_id", "name") in pairs
    assert col.type.length == 64


def test_role_description_nullable():
    col = Role.__table__.columns["description"]
    assert col.nullable is True


def test_role_timestamps_timezone_aware():
    for name in ("created_at", "updated_at"):
        col = Role.__table__.columns[name]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True
        assert col.nullable is False
        assert col.server_default is not None


# --- permissions ------------------------------------------------------------


def test_permission_tablename():
    assert Permission.__tablename__ == "permissions"


def test_permission_columns():
    assert set(Permission.__table__.columns.keys()) == {
        "id",
        "name",
        "description",
        "created_at",
        "updated_at",
    }


def test_permission_name_unique_not_null():
    col = Permission.__table__.columns["name"]
    assert col.unique is True
    assert col.nullable is False
    assert isinstance(col.type, String)


def test_permission_name_fits_resource_action_format():
    """`user:read` / `task:assign` 这类 §6 示例长度必须能装进列宽。"""
    assert Permission.__table__.columns["name"].type.length >= 100


def test_permission_timestamps_timezone_aware():
    for name in ("created_at", "updated_at"):
        col = Permission.__table__.columns[name]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True


# --- user_roles --------------------------------------------------------------


def test_user_role_tablename():
    assert UserRole.__tablename__ == "user_roles"


def test_user_role_columns():
    assert set(UserRole.__table__.columns.keys()) == {
        "id",
        "tenant_id",
        "user_id",
        "role_id",
    }


def test_user_role_composite_unique():
    constraints = [
        c for c in UserRole.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    pairs = {tuple(c.columns.keys()) for c in constraints}
    assert ("user_id", "role_id") in pairs


def test_user_role_fks_cascade_and_indexed():
    for name, target in (("user_id", "users.id"), ("role_id", "roles.id")):
        col = UserRole.__table__.columns[name]
        fk = list(col.foreign_keys)[0]
        assert fk.target_fullname == target
        assert fk.ondelete == "CASCADE"
        assert col.index is True


# --- role_permissions --------------------------------------------------------


def test_role_permission_tablename():
    assert RolePermission.__tablename__ == "role_permissions"


def test_role_permission_columns():
    assert set(RolePermission.__table__.columns.keys()) == {
        "id",
        "tenant_id",
        "role_id",
        "permission_id",
    }


def test_role_permission_composite_unique():
    constraints = [
        c
        for c in RolePermission.__table__.constraints
        if isinstance(c, UniqueConstraint)
    ]
    pairs = {tuple(c.columns.keys()) for c in constraints}
    assert ("role_id", "permission_id") in pairs


def test_role_permission_fks_cascade_and_indexed():
    for name, target in (
        ("role_id", "roles.id"),
        ("permission_id", "permissions.id"),
    ):
        col = RolePermission.__table__.columns[name]
        fk = list(col.foreign_keys)[0]
        assert fk.target_fullname == target
        assert fk.ondelete == "CASCADE"
        assert col.index is True


# --- 模型链完整性 ------------------------------------------------------------


def test_model_chain_tables_reference_each_other():
    """§6 模型链 User → UserRole → Role → RolePermission → Permission 的外键指向。"""
    assert UserRole.__table__.columns["user_id"].foreign_keys
    assert UserRole.__table__.columns["role_id"].foreign_keys
    assert RolePermission.__table__.columns["role_id"].foreign_keys
    assert RolePermission.__table__.columns["permission_id"].foreign_keys


def test_repr_variants():
    assert "admin" in repr(Role(id=1, name="admin"))
    assert "user:read" in repr(Permission(id=1, name="user:read"))
    assert "user_id=2" in repr(UserRole(id=1, user_id=2, role_id=3))
    assert "permission_id=5" in repr(RolePermission(id=1, role_id=4, permission_id=5))
