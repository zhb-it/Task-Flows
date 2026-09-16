"""row level security backstop + runtime db role (TASK-095, §61.3)

Revision ID: b8d4f2a6c9e1
Revises: a9b7c5d3e1f0
Create Date: 2026-09-16

TASK-095 的 RLS 兜底层（纵深防御，项目规则 §6）：应用层统一作用域
（``app/core/tenant_context.py`` 的 ``do_orm_execute`` / ``before_flush``）
是主防线；本迁移让数据库在应用层出 bug 时仍然不越界：

- **app schema 两个 SQL 函数**：``app.current_tenant_id()`` 读取事务级 GUC
  ``app.tenant_id``（应用在每个事务开始时经 ``SET LOCAL`` 写入，见
  ``after_begin`` 事件）；``app.rls_bypass()`` 读取 ``app.tenant_bypass``——
  无租户上下文（登录前 / Celery / 系统任务）或显式出口
  （``bypass_tenant_scope()``）时放行。
- **12 张业务表 ENABLE + FORCE ROW LEVEL SECURITY + 策略 tenant_isolation**：
  USING/WITH CHECK 均为「``tenant_id = app.current_tenant_id()`` 或
  bypass」。FORCE 使非超管的表属主同样受策略约束；超级用户（postgres）
  按语义始终绕过 RLS——因此运行时应用连接必须使用本迁移创建的
  **taskflow_app 角色**（LOGIN，非超管），部署面（compose / DEPLOYMENT.md）
  已同步切换；迁移与测试夹具继续走超级用户。
- **taskflow_app 角色**：运行时最小化角色的落位——非超管、受 RLS 约束、
  仅授予 schema/表/序列操作权与默认权限（未来新表自动可访问）。
  密码为开发缺省 'taskflow_app'，生产经 ALTER ROLE 轮换（DEPLOYMENT.md）。

downgrade 按依赖逆序全量回退（策略 → RLS 开关 → app schema → 角色），
不做数据还原（本迁移无数据变更）。
"""

from alembic import op

revision = "b8d4f2a6c9e1"
down_revision = "a9b7c5d3e1f0"
branch_labels = None
depends_on = None

#: TASK-094 归属清单（与迁移 f1a2c3d4e5b6 一致）。
TENANT_TABLES = (
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

POLICY = """\
USING (tenant_id = app.current_tenant_id() OR app.rls_bypass())
WITH CHECK (tenant_id = app.current_tenant_id() OR app.rls_bypass())\
"""


def upgrade() -> None:
    # 1) app schema：GUC 读取函数（CREATE OR REPLACE 幂等，策略直接引用）。
    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.current_tenant_id() RETURNS integer
        AS $fn$
            SELECT NULLIF(current_setting('app.tenant_id', true), '')::integer
        $fn$
        LANGUAGE sql STABLE
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.rls_bypass() RETURNS boolean
        AS $fn$
            SELECT coalesce(current_setting('app.tenant_bypass', true), '') = 'on'
        $fn$
        LANGUAGE sql STABLE
        """
    )

    # 2) 运行时角色：非超管、受 RLS 约束。DO 块幂等（重放安全）。
    op.execute(
        """
        DO $do$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'taskflow_app') THEN
                CREATE ROLE taskflow_app LOGIN PASSWORD 'taskflow_app';
            END IF;
        END
        $do$
        """
    )
    op.execute(
        "DO $do$ BEGIN "
        "EXECUTE format('GRANT CONNECT ON DATABASE %I TO taskflow_app', "
        "current_database()); END $do$"
    )
    op.execute("GRANT USAGE ON SCHEMA public TO taskflow_app")
    op.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO taskflow_app")
    op.execute(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO taskflow_app"
    )
    # 未来迁移新建的表/序列对运行时角色自动可见（默认权限挂在 postgres 上）。
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT ALL PRIVILEGES ON TABLES TO taskflow_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO taskflow_app"
    )

    # 3) RLS：ENABLE + FORCE + 策略（DROP IF EXISTS 保证重放幂等）。
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{table}")
        op.execute(f"CREATE POLICY tenant_isolation ON public.{table} {POLICY}")


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{table}")
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP SCHEMA IF EXISTS app CASCADE")

    # 角色不拥有对象，但在本库持有表/序列/默认权限的 GRANT 依赖——
    # DROP ROLE 前必须先 DROP OWNED（等效 REVOKE 全部授权）。角色是
    # **集群级**对象：若同服务器其他数据库仍持有其授权（如本机同时存在
    # 开发库与探针库），DROP ROLE 会因跨库依赖失败——此处捕获该异常并
    # 保留角色（NOTICE 点名），当前库的授权已全部回收，其余对象完整回退。
    op.execute("DROP OWNED BY taskflow_app")
    op.execute(
        """
        DO $do$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'taskflow_app') THEN
                BEGIN
                    DROP ROLE taskflow_app;
                EXCEPTION
                    WHEN dependent_objects_still_exist THEN
                        RAISE NOTICE 'role taskflow_app kept: still has grants in other databases on this cluster';
                END;
            END IF;
        END
        $do$
        """
    )
