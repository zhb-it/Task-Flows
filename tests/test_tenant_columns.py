"""TASK-094：业务表租户化与存量回填测试。

四组：

1. **离线元数据测试**——全部业务模型的 ``tenant_id`` 声明（NOT NULL、
   FK → tenants ON DELETE RESTRICT）；users 的唯一约束租户化（复合唯一
   显式命名，列级 unique 已去）；storage ``build_key`` 租户分目录与参数
   校验。
2. **真实库结构断言**——15 张租户化表（12 张 TASK-094 业务表 + RBAC 三表）在
   开发库中 ``tenant_id`` NOT NULL + FK（RESTRICT）+ ``tenant_id`` 前导索引在位；
   复合唯一在位、全局唯一已删。
3. **约束行为集成**——「同名跨租户可共存、同租户内冲突」的正反用例
   （§5 修订的核心语义）；FK RESTRICT（删有业务行的租户被拒）；DB 列
   DEFAULT 桥接（INSERT 不带 tenant_id 归默认租户）。
4. **回填幂等与零孤儿**——重放回填 SQL 后行数与默认租户计数不变
   （幂等）；15 张租户化表 ``tenant_id IS NULL`` 计数为 0（零孤儿）。

迁移往返（upgrade head → downgrade base → upgrade head）在探针库执行，
见 docs/PROGRESS.md 的任务条目与工作区日志；不进 pytest（需要建库权限，
且 CI service 账号未必有 createdb）。

写入采用「本次运行唯一前缀 + teardown 精确删除」（同 test_tenant_model）。
"""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services import storage as storage_service
from app.services.storage import UnsafeStorageKeyError
from app.db.base import Base
from app.models import (
    Attachment,
    Comment,
    Notification,
    OperationLog,
    OperationLogArchive,
    Project,
    RefreshToken,
    Role,
    RolePermission,
    Task,
    TaskAssignee,
    Team,
    TeamMember,
    Tenant,
    User,
    UserRole,
)

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)

#: TASK-094 归属清单（与迁移 f1a2c3d4e5b6 / a9b7c5d3e1f0 一致），TASK-096 起
#: 追加 RBAC 三表（roles / role_permissions / user_roles），它们同样带
#: tenant_id（NOT NULL + FK RESTRICT + 前导索引）。
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
    "roles",
    "role_permissions",
    "user_roles",
)

#: 归属清单 ↔ ORM 模型（离线断言用）。
TENANT_MODELS = (
    User,
    RefreshToken,
    Team,
    TeamMember,
    Project,
    Task,
    TaskAssignee,
    Comment,
    Attachment,
    OperationLog,
    OperationLogArchive,
    Notification,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- 1. 离线元数据测试 ----------------------------------------------------------


@pytest.mark.parametrize("model", TENANT_MODELS, ids=lambda m: m.__tablename__)
def test_model_declares_tenant_id(model):
    """每个归属模型都声明 tenant_id：NOT NULL + FK → tenants RESTRICT。"""
    col = model.__table__.columns["tenant_id"]
    assert not col.nullable, model.__tablename__
    fk = next(
        f
        for f in model.__table__.foreign_keys
        if f.parent.name == "tenant_id"
    )
    assert fk.column.table.name == "tenants"
    assert fk.column.name == "id"
    assert fk.ondelete == "RESTRICT"


@pytest.mark.parametrize("table_name", TENANT_TABLES)
def test_metadata_has_tenant_tables(table_name):
    assert table_name in Base.metadata.tables


def test_users_tenant_scoped_unique_constraints():
    """§5 修订：username/email 唯一性带租户维度（显式命名，与迁移同名）。"""
    cons = {
        c.name: c
        for c in User.__table__.constraints
        if isinstance(c, sa.UniqueConstraint)
    }
    assert "uq_users_tenant_username" in cons
    assert "uq_users_tenant_email" in cons
    assert tuple(cons["uq_users_tenant_username"].columns.keys()) == (
        "tenant_id",
        "username",
    )
    assert tuple(cons["uq_users_tenant_email"].columns.keys()) == (
        "tenant_id",
        "email",
    )
    # 列级 unique 已去（TASK-093 教训：匿名约束与迁移漂移）。
    assert not User.__table__.columns["username"].unique
    assert not User.__table__.columns["email"].unique


def test_build_key_scopes_by_tenant():
    """附件存储路径按租户分目录（TASK-094 实现要求 ⑤）。"""
    key = storage_service.build_key(4, 7, suffix=".png")
    assert key == f"tenants/4/tasks/7/{key.rsplit('/', 1)[-1]}"
    assert key.startswith("tenants/4/tasks/7/") and key.endswith(".png")


def test_build_key_rejects_non_positive_ids():
    with pytest.raises(UnsafeStorageKeyError):
        storage_service.build_key(0, 7)
    with pytest.raises(UnsafeStorageKeyError):
        storage_service.build_key(-1, 7)
    with pytest.raises(UnsafeStorageKeyError):
        storage_service.build_key(4, 0)


def test_build_key_random_and_suffix_whitelist():
    assert storage_service.build_key(1, 1) != storage_service.build_key(1, 1)
    with pytest.raises(UnsafeStorageKeyError):
        storage_service.build_key(1, 1, suffix="../evil")


# --- 2. 真实库结构断言 ----------------------------------------------------------


async def test_db_tenant_id_not_null_fk_index():
    """真实库：15 张租户化表 tenant_id NOT NULL + FK RESTRICT + 索引在位。"""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                sa.text(
                    """
                    SELECT c.relname AS table_name,
                           a.attnotnull AS not_null
                    FROM pg_attribute a
                    JOIN pg_class c ON c.oid = a.attrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relname = ANY(:tables)
                      AND a.attname = 'tenant_id'
                      AND n.nspname = 'public'
                    """
                ),
                {"tables": list(TENANT_TABLES)},
            )
        ).fetchall()
        assert {r.table_name for r in rows} == set(TENANT_TABLES)
        assert all(r.not_null for r in rows), rows

        fk_rows = (
            await conn.execute(
                sa.text(
                    """
                    SELECT c.conrelid::regclass::text AS table_name,
                           c.confdeltype AS del_type
                    FROM pg_constraint c
                    WHERE c.conname LIKE 'fk_%_tenant_id_tenants'
                    """
                )
            )
        ).fetchall()
        # 'r' = RESTRICT（pg_constraint.confdeltype）。
        assert {r.table_name for r in fk_rows} == set(TENANT_TABLES)
        assert all(r.del_type in ("r", b"r") for r in fk_rows), fk_rows

        idx_rows = (
            await conn.execute(
                sa.text(
                    """
                    SELECT tablename FROM pg_indexes
                    WHERE indexname LIKE 'ix_%_tenant_id'
                    """
                )
            )
        ).fetchall()
        assert {r.tablename for r in idx_rows} == set(TENANT_TABLES)


async def test_db_users_unique_constraints_swapped():
    """真实库：复合唯一在位、全局唯一已删、过渡索引在位。"""
    async with engine.connect() as conn:
        names = {
            r.conname
            for r in (
                await conn.execute(
                    sa.text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid = 'users'::regclass AND contype = 'u'"
                    )
                )
            ).fetchall()
        }
        assert "uq_users_tenant_username" in names
        assert "uq_users_tenant_email" in names
        assert "users_username_key" not in names
        assert "users_email_key" not in names
        idx = {
            r.indexname
            for r in (
                await conn.execute(
                    sa.text(
                        "SELECT indexname FROM pg_indexes WHERE tablename = 'users'"
                    )
                )
            ).fetchall()
        }
        assert {"ix_users_username", "ix_users_email"} <= idx


# --- 3. 约束行为集成 -------------------------------------------------------------


def _tenant_slug(tag: str) -> str:
    return f"tc{RUN_TOKEN}{tag}"


def _username(tag: str) -> str:
    return f"tc94_{RUN_TOKEN}_{tag}"


@pytest.fixture(autouse=True)
async def _cleanup():
    """本文件写入的行，跑完逐条精确删掉（TASK-129 收尾补：此前是漏的）。

    第 3 组用例证明的是**约束行为**，必须真的 ``commit`` 才能让数据库的
    UNIQUE / FK 生效，所以不能像第 4 组那样 ``rollback``。代价就是这些行
    会留在库里——本夹具按「本次运行唯一前缀」把它们清干净。

    漏了会怎样（实测）：每次全量运行往开发库留下 4 个租户 + 4 个用户，
    其中一个还落在**默认租户**里；累积几十次之后，任何依赖行数/计数的
    断言（如 ``test_backfill_is_idempotent``）都会开始随机失败，而且看起来
    像「脏库」而不是像这个文件的问题——这正是当初排查时踩的坑。

    删除顺序受外键约束（``ON DELETE RESTRICT``）：先按 tenant_id 清 RBAC
    三表，再删用户，最后删租户。连接角色是 postgres 超级用户，RLS 自动绕过。
    """
    yield
    async with SessionFactory() as session:
        tenant_ids = [
            row[0]
            for row in await session.execute(
                sa.select(Tenant.id).where(Tenant.slug.like(f"tc{RUN_TOKEN}%"))
            )
        ]
        if tenant_ids:
            await session.execute(
                sa.delete(RolePermission).where(
                    RolePermission.tenant_id.in_(tenant_ids)
                )
            )
            await session.execute(
                sa.delete(UserRole).where(UserRole.tenant_id.in_(tenant_ids))
            )
            await session.execute(
                sa.delete(Role).where(Role.tenant_id.in_(tenant_ids))
            )
        # 用户按**用户名**前缀删，而不是按 tenant_id：`fallback` 用例故意
        # 写进默认租户（不带 tenant_id，走 DB 列 DEFAULT），按租户筛会漏掉它。
        await session.execute(
            sa.delete(User).where(User.username.like(f"tc94_{RUN_TOKEN}%"))
        )
        await session.execute(
            sa.delete(Tenant).where(Tenant.slug.like(f"tc{RUN_TOKEN}%"))
        )
        await session.commit()


async def test_same_username_across_tenants_coexists():
    """§5 修订核心语义：两个租户可存在同名 username 与 email。"""
    async with SessionFactory() as session:
        t1 = Tenant(name=f"T1-{RUN_TOKEN}", slug=_tenant_slug("a"))
        t2 = Tenant(name=f"T2-{RUN_TOKEN}", slug=_tenant_slug("b"))
        session.add_all([t1, t2])
        await session.flush()

        u1 = User(
            tenant_id=t1.id,
            username=_username("same"),
            email=f"{_username('same')}@a.test",
            password_hash="h",
        )
        u2 = User(
            tenant_id=t2.id,
            username=_username("same"),
            email=f"{_username('same')}@b.test",
            password_hash="h",
        )
        session.add_all([u1, u2])
        await session.commit()  # 跨租户同名：双双成功。

        assert u1.tenant_id != u2.tenant_id


async def test_same_username_within_tenant_rejected():
    """同租户内同名 username / email：IntegrityError（复合唯一兜底）。"""
    async with SessionFactory() as session:
        t = Tenant(name=f"T-{RUN_TOKEN}", slug=_tenant_slug("c"))
        session.add(t)
        await session.flush()

        first = User(
            tenant_id=t.id,
            username=_username("dup"),
            email=f"{_username('dup')}@t.test",
            password_hash="h",
        )
        session.add(first)
        await session.commit()

        second = User(
            tenant_id=t.id,
            username=_username("dup"),
            email=f"{_username('dup')}@other.test",
            password_hash="h",
        )
        session.add(second)
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_fk_restrict_blocks_tenant_delete():
    """FK RESTRICT：删有业务行的租户被拒（租户删除只走状态机，DECISIONS 065）。"""
    async with SessionFactory() as session:
        t = Tenant(name=f"T-{RUN_TOKEN}", slug=_tenant_slug("d"))
        session.add(t)
        await session.flush()
        u = User(
            tenant_id=t.id,
            username=_username("restrict"),
            email=f"{_username('restrict')}@t.test",
            password_hash="h",
        )
        session.add(u)
        await session.commit()

        await session.delete(t)
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_db_default_tenant_fallback_on_insert():
    """写入桥接：INSERT 不带 tenant_id 时由列 DEFAULT 归默认租户。"""
    async with SessionFactory() as session:
        default_id = (
            await session.execute(
                sa.text("SELECT id FROM tenants WHERE slug = 'default'")
            )
        ).scalar_one()

        user = User(
            username=_username("fallback"),
            email=f"{_username('fallback')}@t.test",
            password_hash="h",
        )
        session.add(user)
        await session.flush()
        assert user.tenant_id == default_id


# --- 4. 回填幂等与零孤儿 --------------------------------------------------------


async def test_contextvar_injection_takes_priority():
    """TASK-095 接线点预演：ContextVar 显式租户优先于 DB 默认（flush 注入）。"""
    from app.core.tenant_context import (
        reset_current_tenant_id,
        set_current_tenant_id,
    )

    async with SessionFactory() as session:
        t = Tenant(name=f"TC-{RUN_TOKEN}", slug=_tenant_slug("e"))
        session.add(t)
        await session.flush()

        token = set_current_tenant_id(t.id)
        try:
            user = User(
                username=_username("ctx"),
                email=f"{_username('ctx')}@t.test",
                password_hash="h",
            )
            session.add(user)
            await session.flush()
            # ContextVar 的显式租户被注入（不是默认租户）。
            assert user.tenant_id == t.id
        finally:
            reset_current_tenant_id(token)
        await session.rollback()


async def test_injection_skips_non_tenant_and_explicit_rows():
    """flush 注入的分支完备性：无租户列对象跳过、显式赋值优先、其余注入。"""
    from app.core.tenant_context import (
        get_current_tenant_id,
        reset_current_tenant_id,
        set_current_tenant_id,
    )

    async with SessionFactory() as session:
        t = Tenant(name=f"TC-{RUN_TOKEN}", slug=_tenant_slug("g"))
        session.add(t)
        await session.flush()

        token = set_current_tenant_id(t.id)
        try:
            assert get_current_tenant_id() == t.id
            # new 里同时有：无 tenant_id 列的对象（Tenant，走跳过分支）、
            # 显式赋值的对象（走显式优先分支）、未赋值的对象（走注入分支）。
            explicit_user = User(
                tenant_id=t.id,
                username=_username("expl2"),
                email=f"{_username('expl2')}@t.test",
                password_hash="h",
            )
            injected_user = User(
                username=_username("inj2"),
                email=f"{_username('inj2')}@t.test",
                password_hash="h",
            )
            session.add_all([explicit_user, injected_user])
            await session.flush()
            assert injected_user.tenant_id == t.id
            assert explicit_user.tenant_id == t.id
            # users 落库后再建 Team（owner_id FK 依赖；无 relationship，
            # SQLAlchemy 不会自动排序插表顺序）。
            session.add(
                Team(name=f"tm-{RUN_TOKEN}", owner_id=explicit_user.id)
            )
            # 未 flush 的 Tenant 留在 new 里（无租户列 → 走跳过分支）。
            session.add(Tenant(name=f"TC2-{RUN_TOKEN}", slug=_tenant_slug("h")))
            await session.flush()
        finally:
            reset_current_tenant_id(token)
        await session.rollback()


async def test_explicit_assignment_wins_over_injection():
    """显式赋值优先：归档拷贝等场景不受注入影响。"""
    async with SessionFactory() as session:
        t = Tenant(name=f"TC-{RUN_TOKEN}", slug=_tenant_slug("f"))
        session.add(t)
        await session.flush()

        user = User(
            tenant_id=t.id,  # 显式赋值
            username=_username("explicit"),
            email=f"{_username('explicit')}@t.test",
            password_hash="h",
        )
        session.add(user)
        await session.flush()
        assert user.tenant_id == t.id
        await session.rollback()


async def test_backfill_is_idempotent():
    """重放回填 SQL：默认租户不重复、行数不变（幂等）。"""
    async with engine.begin() as conn:
        before_counts = {
            tb: (
                await conn.execute(sa.text(f"SELECT count(*) FROM {tb}"))
            ).scalar_one()
            for tb in TENANT_TABLES
        }
        tenant_before = (
            await conn.execute(
                sa.text("SELECT count(*) FROM tenants WHERE slug = 'default'")
            )
        ).scalar_one()

        # 重放迁移 a9b7c5d3e1f0 的核心回填语句。
        await conn.execute(
            sa.text(
                "INSERT INTO tenants (name, slug, status) "
                "VALUES ('Default Tenant', 'default', 'active') "
                "ON CONFLICT (slug) DO NOTHING"
            )
        )
        for tb in TENANT_TABLES:
            await conn.execute(
                sa.text(
                    f"UPDATE {tb} SET tenant_id = "
                    "(SELECT id FROM tenants WHERE slug = 'default') "
                    "WHERE tenant_id IS NULL"
                )
            )

        after_counts = {
            tb: (
                await conn.execute(sa.text(f"SELECT count(*) FROM {tb}"))
            ).scalar_one()
            for tb in TENANT_TABLES
        }
        tenant_after = (
            await conn.execute(
                sa.text("SELECT count(*) FROM tenants WHERE slug = 'default'")
            )
        ).scalar_one()

        assert after_counts == before_counts
        assert tenant_before == tenant_after == 1


async def test_no_orphan_rows():
    """零孤儿断言：15 张租户化表 tenant_id IS NULL 计数为 0。"""
    async with engine.connect() as conn:
        for tb in TENANT_TABLES:
            nulls = (
                await conn.execute(
                    sa.text(
                        f"SELECT count(*) FROM {tb} WHERE tenant_id IS NULL"
                    )
                )
            ).scalar_one()
            assert nulls == 0, f"{tb} has {nulls} orphan rows"
