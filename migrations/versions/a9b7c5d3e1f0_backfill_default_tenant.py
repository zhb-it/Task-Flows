"""backfill default tenant and tenant-scoped unique constraints

Revision ID: a9b7c5d3e1f0
Revises: f1a2c3d4e5b6
Create Date: 2026-09-16

TASK-094（§61.3 多租户）第二步与第三步：

1. **回填**：创建默认租户（``slug='default'``），把全部存量业务行挂上去。
   回填前不存在租户概念，存量数据本来就是一个部署一份，整体归属默认租户
   是唯一诚实的映射（不存在按父表推导的问题）。插入用
   ``ON CONFLICT (slug) DO NOTHING``、UPDATE 只更新 ``tenant_id IS NULL``
   的行——整个迁移在已回填过的库上重放是 no-op（幂等）。

2. **唯一约束租户化**（§61.3 / §5 修订）：``users.username``、
   ``users.email`` 从全局 UNIQUE 改为 ``(tenant_id, username)`` /
   ``(tenant_id, email)`` 复合 UNIQUE——不同租户可以存在同名用户。
   全局约束的删除发生在回填**之后**，迁移窗口内不存在「跨租户同名行」，
   复合约束一次到位。原全局索引由普通索引替代（过渡期全局查询仍有索引；
   TASK-095 落租户作用域查询后按 ``(tenant_id, ...)`` 前导访问）。

   保持**全局**唯一的例外（DECISIONS 066）：``refresh_tokens.jti``、
   ``attachments.storage_path``、``tenants.slug``——三者都是系统生成的
   技术标识（JWT ID / 随机存储 key / 对外 slug），不是用户可见命名空间，
   全局唯一反而防跨租户标识混淆。

3. **置 NOT NULL**：回填后零孤儿（每张表 ``tenant_id IS NULL`` 计数为 0）
   是本迁移的隐含断言——PostgreSQL 在 ``SET NOT NULL`` 时全表扫描校验，
   任何 NULL 残留都会让迁移失败，数据库本身就是零孤儿断言的执行者。

**downgrade 显式 no-op**，理由：

- 回填把存量行挂到默认租户，是「这些数据属于哪个租户」这一事实的初始化，
  不存在可还原的原始状态（还原成什么？回填前的 NULL 在业务上不成立）；
- 本迁移删除的全局唯一约束是「单租户时代」的产物，恢复它反而与多租户
  语义冲突；
- 列结构与 FK 的回滚由前一迁移（f1a2c3d4e5b6）的 downgrade 承担，
  两级 downgrade 链仍然完整。
"""

import sqlalchemy as sa
from alembic import op

revision = "a9b7c5d3e1f0"
down_revision = "f1a2c3d4e5b6"
branch_labels = None
depends_on = None

#: 与 f1a2c3d4e5b6 的归属清单一致（不含 tenants 自身）。
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

DEFAULT_TENANT_SLUG = "default"


def upgrade() -> None:
    # 1) 默认租户（幂等：已存在则跳过）。
    op.execute(
        """
        INSERT INTO tenants (name, slug, status)
        VALUES ('Default Tenant', 'default', 'active')
        ON CONFLICT (slug) DO NOTHING
        """
    )

    # 2) 存量回填（幂等：只补 NULL 行）。
    for table in _TENANT_TABLES:
        op.execute(
            sa.text(
                f"UPDATE {table} SET tenant_id = "
                f"(SELECT id FROM tenants WHERE slug = '{DEFAULT_TENANT_SLUG}') "
                "WHERE tenant_id IS NULL"
            )
        )

    # 3) users 唯一约束租户化：先删全局 UNIQUE（回填后无跨租户同名行，
    #    约束切换瞬间语义等价），再建复合 UNIQUE。
    #
    #    全部幂等化（IF EXISTS / IF NOT EXISTS / DO 块）：本迁移的 downgrade
    #    不恢复旧全局约束（见 docstring），因此在降级过的库上重放 upgrade
    #    时旧约束已不存在、复合约束已存在——迁移必须可安全重放。
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key")
    op.execute(
        """
        DO $do$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_users_tenant_username'
            ) THEN
                ALTER TABLE users ADD CONSTRAINT uq_users_tenant_username
                    UNIQUE (tenant_id, username);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_users_tenant_email'
            ) THEN
                ALTER TABLE users ADD CONSTRAINT uq_users_tenant_email
                    UNIQUE (tenant_id, email);
            END IF;
        END
        $do$
        """
    )
    # 全局查询的过渡索引（复合唯一以 tenant_id 前导，覆盖不了按 username
    # 的全局查找；TASK-095 落作用域查询后再评估去留）。
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_username ON users (username)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)")

    # 4) 置 NOT NULL——PG 全表扫描校验，NULL 残留会让迁移失败（零孤儿断言）。
    for table in _TENANT_TABLES:
        op.alter_column(table, "tenant_id", existing_type=sa.BigInteger(), nullable=False)

    # 5) 写入桥接（TASK-094，TASK-095 落认证租户后退化为兜底）：列 DEFAULT
    #    调用 STABLE 函数查默认租户——INSERT 不带 tenant_id 时由 DB 归属
    #    默认租户，应用层零桥接；应用层显式赋值优先于列默认。
    op.execute(
        """
        CREATE OR REPLACE FUNCTION current_default_tenant_id() RETURNS BIGINT AS $fn$
            SELECT id FROM tenants WHERE slug = 'default' LIMIT 1
        $fn$ LANGUAGE sql STABLE
        """
    )
    for table in _TENANT_TABLES:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN tenant_id "
            "SET DEFAULT current_default_tenant_id()"
        )


def downgrade() -> None:
    # 列 DEFAULT 与函数回滚（结构性对象必须可逆）；**数据回填不还原**——
    # 理由见模块 docstring：存量行的归属是事实初始化，不存在可还原状态。
    for table in _TENANT_TABLES:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN tenant_id DROP DEFAULT"
        )
    op.execute("DROP FUNCTION IF EXISTS current_default_tenant_id()")
