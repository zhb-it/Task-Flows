"""tenant-scoped RBAC (TASK-096, §61.3.4)

Revision ID: c2d4e6f8a0b1
Revises: b8d4f2a6c9e1
Create Date: 2026-09-16

TASK-096 把 RBAC 从「全局」改造为「租户内」：

- ``roles`` / ``role_permissions`` / ``user_roles`` 三张表加 ``tenant_id``
  列（FK → ``tenants.id`` ON DELETE RESTRICT + 前导索引），写入经应用层
  ``before_flush`` 注入，查询经 ``do_orm_execute`` 自动过滤，越权由 RLS 兜底。
- ``roles.name`` 的全局 UNIQUE（``roles_name_key``）改为**租户内**唯一
  （``uq_roles_tenant_name`` = (tenant_id, name)）——不同租户可以存在同名角色。
- ``permissions`` 保持**全局目录**不变（权限定义不随租户复制）。
- 存量数据（种子迁移 0de65c197efc 插的 admin/member 及其绑定、e3a7c1f9b2d4
  回填的 user_roles）统一回填到默认租户（``slug='default'``），与 TASK-094 的
  回填口径一致——存量即「属于默认租户」这一事实的初始化。
- 三张表启用 RLS（ENABLE + FORCE + 策略 tenant_isolation）。``tenant:manage``
  平台权限只授予默认租户 admin（由 c7d1e8f4a2b6 绑定、回溯回填后归属默认租户），
  **不**进入本迁移或 ``seed_tenant_rbac`` 的播种集合，租户管理员因此无法越权。

downgrade：撤 RLS → 删 tenant_id 列/FK/索引 → 恢复 roles_name_key（数据回填
不还原，理由同 a9b7c5d3e1f0）。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d4e6f8a0b1"
down_revision: Union[str, None] = "b8d4f2a6c9e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: 三张需要租户化的 RBAC 表（permissions 不变）。
_RBAC_TABLES = ("roles", "role_permissions", "user_roles")

#: RLS 策略（与 b8d4f2a6c9e1 同源）：tenant_id 匹配当前事务 GUC 或 bypass。
POLICY = """\
USING (tenant_id = app.current_tenant_id() OR app.rls_bypass())
WITH CHECK (tenant_id = app.current_tenant_id() OR app.rls_bypass())\
"""


def _add_tenant_id(table: str) -> None:
    """加可空 tenant_id 列 + FK + 索引，再回填默认租户、置 NOT NULL。"""
    op.add_column(
        table,
        sa.Column("tenant_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        f"fk_{table}_tenant_id_tenants",
        table,
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"], unique=False)
    # 回填存量到默认租户（幂等：只补 NULL 行）。
    op.execute(
        sa.text(
            "UPDATE %(t)s SET tenant_id = "
            "(SELECT id FROM tenants WHERE slug = 'default') "
            "WHERE tenant_id IS NULL" % {"t": table}
        )
    )
    # 置 NOT NULL——PG 全表扫描校验，NULL 残留会让迁移失败（零孤儿断言）。
    op.alter_column(table, "tenant_id", existing_type=sa.BigInteger(), nullable=False)


def upgrade() -> None:
    # 1) 三张表加 tenant_id（可空 → 回填 → NOT NULL）。
    for table in _RBAC_TABLES:
        _add_tenant_id(table)

    # 2) roles.name 全局唯一 → 租户内唯一。先删旧约束（回填后无跨租户同名行，
    #    切换瞬间语义等价），再建复合 UNIQUE。DO 块保证重放幂等。
    op.execute("ALTER TABLE roles DROP CONSTRAINT IF EXISTS roles_name_key")
    op.execute(
        """
        DO $do$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_roles_tenant_name'
            ) THEN
                ALTER TABLE roles ADD CONSTRAINT uq_roles_tenant_name
                    UNIQUE (tenant_id, name);
            END IF;
        END
        $do$
        """
    )

    # 3) RLS：三张表 ENABLE + FORCE + 策略 tenant_isolation。
    for table in _RBAC_TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{table}")
        op.execute(f"CREATE POLICY tenant_isolation ON public.{table} {POLICY}")


def downgrade() -> None:
    # 1) 撤 RLS。
    for table in _RBAC_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{table}")
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")

    # 2) 恢复 roles 全局唯一约束（数据回填不还原）。
    op.execute(
        """
        DO $do$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'roles_name_key'
            ) THEN
                ALTER TABLE roles ADD CONSTRAINT roles_name_key UNIQUE (name);
            END IF;
        END
        $do$
        """
    )
    op.execute("ALTER TABLE roles DROP CONSTRAINT IF EXISTS uq_roles_tenant_name")

    # 3) 删 tenant_id 列 / 索引 / FK（数据留在原行，tenant_id 一并删除）。
    for table in _RBAC_TABLES:
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_constraint(
            f"fk_{table}_tenant_id_tenants", table, type_="foreignkey"
        )
        op.drop_column(table, "tenant_id")
