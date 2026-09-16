"""add tenant_id columns to business tables

Revision ID: f1a2c3d4e5b6
Revises: c7d1e8f4a2b6
Create Date: 2026-09-16

TASK-094（§61.3 多租户）第一步：给全部需要归属的业务表加**可空**的
``tenant_id`` 列 + FK → ``tenants.id``（ON DELETE RESTRICT）+ 以
``tenant_id`` 为前导列的索引。

为什么是三步（加列 → 回填 → 置 NOT NULL）：

- 生产库不能直接加 NOT NULL 无默认值列——存量行没有租户归属，必须先
  回填（迁移 a9b7c5d3e1f0）再置 NOT NULL。本迁移只做第一步。

- FK ``ON DELETE RESTRICT``：租户的「删除」是状态而非物理删除（TASK-093，
  DECISIONS 065），租户行永不物理删除；RESTRICT 让任何绕过状态机的物理
  删除尝试立刻失败，而不是级联清光整个租户的数据。

- 归属清单（12 张）：users、refresh_tokens、teams、team_members、projects、
  tasks、task_assignees、comments、attachments、operation_logs、
  operation_logs_archive、notifications。RBAC 四表（roles / user_roles /
  role_permissions）与 permissions 的租户化属 TASK-096（RBAC 租户化），
  本迁移不动。

- 唯一约束的租户化（users.username / users.email → 复合唯一）放在回填
  迁移里完成——必须先回填，否则存量行与新约束的对应关系不成立。

downgrade：删除本迁移创建的索引、FK 与列，完全可逆。
"""

import sqlalchemy as sa
from alembic import op

revision = "f1a2c3d4e5b6"
down_revision = "c7d1e8f4a2b6"
branch_labels = None
depends_on = None

#: (表名, 索引名)。索引一律以 tenant_id 为前导列（TASK-094 实现要求 ④）；
#: 单列索引已满足前导语义，(tenant_id, ...) 查询复合索引由 TASK-095 落
#: 作用域查询时按需补建。
_TENANT_TABLES = (
    "users",
    "refresh_tokens",
    "teams",
    "team_members",
    "projects",
    "tasks",
    "task_assignees",
    "comments",
    "attachments",
    "operation_logs",
    "operation_logs_archive",
    "notifications",
)


def upgrade() -> None:
    for table in _TENANT_TABLES:
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
        op.create_index(
            f"ix_{table}_tenant_id", table, ["tenant_id"], unique=False
        )


def downgrade() -> None:
    for table in _TENANT_TABLES:
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_constraint(
            f"fk_{table}_tenant_id_tenants", table, type_="foreignkey"
        )
        op.drop_column(table, "tenant_id")
