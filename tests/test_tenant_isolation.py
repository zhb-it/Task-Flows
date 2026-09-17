"""TASK-095：租户上下文与数据访问作用域测试（多租户隔离保证核心）.

五组：

1. **离线接线**——12 个业务模型 + RBAC 角色/授权关联表（Role/UserRole/
   RolePermission）继承 ``TenantScoped``；permissions 与 tenants 是全局/平台
   实体不继承；作用域事件函数在位（行为在 2/3 组实证）；``bypass_tenant_scope``
   进入/离开与审计日志。
2. **应用层统一作用域**（真实库）——ContextVar 有租户时 ORM SELECT 自动
   过滤（CRUD 零改动）；无上下文不过滤；显式出口放开；``before_flush``
   写入注入与显式赋值优先。
3. **事务级 GUC**——``after_begin`` 按上下文写入 ``app.tenant_id`` /
   ``app.tenant_bypass``，跨事务持续生效；``enforce_tenant_guc`` 在已开启
   事务内翻转（认证依赖的接线语义）。
4. **ContextVar 并发不串号**——两个协程并发持有不同租户，作用域查询
   互不可见（asyncio task 各持 context 副本）。
5. **RLS 兜底实证**（SET ROLE taskflow_app）——非超管角色下：漏加条件的
   查询仍被策略过滤；无 GUC 时 fail closed；越租户 INSERT 被 WITH CHECK
   拒绝；越租户 UPDATE 静默零行；bypass GUC 放行。
6. **API 跨租户越权矩阵**——B 租户令牌对 A 租户的 team/project/task 做
   读/改/删/评论全部 404（与「不存在」不可区分，§49/§61.3）；A 租户
   自身访问 200 正向对照。

写入采用「本次运行唯一前缀 + teardown 按租户精确删除」（同
test_tenant_columns）。RLS 用例以 postgres 超管连接后 ``SET ROLE``
taskflow_app（超管可切换至任意角色）——运行时部署以该角色连接
（compose 已切换）；CI/夹具保持超管，以免 1170+ 用例的清理被
fail-closed 拦截。
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import create_access_token
from app.core.tenant_context import (
    GUC_SCOPE_BYPASS,
    GUC_TENANT_ID,
    TenantScoped,
    bypass_tenant_scope,
    enforce_tenant_guc,
    get_current_tenant_id,
    reset_current_tenant_id,
    scope_bypassed,
    set_current_tenant_id,
)
from app.crud.role import assign_role_to_user, get_role_by_name
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Attachment,
    Comment,
    Notification,
    OperationLog,
    OperationLogArchive,
    Permission,
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
from app.models.task import TaskPriority, TaskStatus
from app.models.team_member import TeamRole

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
_PREFIX = f"tiso{RUN_TOKEN}"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"{_PREFIX}_{tag}"


def _slug(tag: str) -> str:
    return f"{_PREFIX}-{tag}"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


async def _cleanup_rows() -> None:
    """按本运行前缀精确删除：先子后父，最后删租户（FK RESTRICT）。"""
    async with SessionFactory() as session:
        tenant_ids = (
            (
                await session.execute(
                    select(Tenant.id).where(Tenant.slug.like(f"{_PREFIX}%"))
                )
            )
            .scalars()
            .all()
        )
        if not tenant_ids:
            return
        user_ids = (
            (
                await session.execute(
                    select(User.id).where(User.username.like(f"{_PREFIX}%"))
                )
            )
            .scalars()
            .all()
        )
        for model in (
            Comment,
            Attachment,
            TaskAssignee,
            Notification,
            OperationLogArchive,
            OperationLog,
            Task,
            Project,
            TeamMember,
            Team,
            RefreshToken,
            RolePermission,
            Role,
        ):
            await session.execute(delete(model).where(model.tenant_id.in_(tenant_ids)))
        # RBAC 关联表无租户列，按本运行创建的用户删。
        await session.execute(delete(UserRole).where(UserRole.user_id.in_(user_ids)))
        await session.execute(delete(User).where(User.username.like(f"{_PREFIX}%")))
        await session.execute(delete(Tenant).where(Tenant.slug.like(f"{_PREFIX}%")))
        await session.commit()


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    yield
    await _cleanup_rows()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- 1. 离线接线 --------------------------------------------------------------


def test_all_tenant_business_models_inherit_mixin():
    """12 个业务模型全部继承 TenantScoped（漏挂即漏作用域）。"""
    for model in (
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
    ):
        assert issubclass(model, TenantScoped), model.__name__


def test_rbac_and_tenant_models_do_not_inherit_mixin():
    """permissions 与 tenants 是全局/平台实体——不得被作用域过滤。

    而 Role / UserRole / RolePermission 自 TASK-096 起带 tenant_id（每租户
    独立授权），必须继承 TenantScoped。
    """
    for model in (Permission, Tenant):
        assert not issubclass(model, TenantScoped), model.__name__
    for model in (Role, UserRole, RolePermission):
        assert issubclass(model, TenantScoped), model.__name__


def test_scope_event_functions_present_and_session_module_imports_context():
    """三个事件函数在位，且 app.db.session 导入即注册（TASK-094 约定）。"""
    from app.core import tenant_context as tc

    assert hasattr(tc, "_scope_orm_select")
    assert hasattr(tc, "_apply_rls_guc_on_begin")
    assert hasattr(tc, "_inject_tenant_on_flush")
    import app.db.session  # noqa: F401 — 导入即注册

    # 所有具体 mapper 都能被注册表枚举到（作用域实现依赖这一点）。
    mapped = {m.class_ for m in Base.registry.mappers}
    assert Task in mapped and User in mapped


def test_bypass_scope_enter_leave_and_audit(caplog):
    assert scope_bypassed() is False
    with caplog.at_level("WARNING", logger="app.core.tenant_context"):
        with bypass_tenant_scope():
            assert scope_bypassed() is True
            assert get_current_tenant_id() is None  # 出口不伪装租户身份
        assert scope_bypassed() is False
    assert any("tenant scope bypass" in r.getMessage() for r in caplog.records)


def test_bypass_scope_restores_after_exception():
    try:
        with bypass_tenant_scope():
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert scope_bypassed() is False


# --- 1b. 分支补充（离线，不连库） ----------------------------------------------


class _FakeDialect:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeConnection:
    def __init__(self, name: str) -> None:
        self.dialect = _FakeDialect(name)
        self.executed: list[str] = []

    def exec_driver_sql(self, sql: str) -> None:
        self.executed.append(sql)


class _FakeBind:
    def __init__(self, name: str) -> None:
        self.dialect = _FakeDialect(name)


class _FakeSession:
    def __init__(self, bind) -> None:
        self.bind = bind


def test_after_begin_skips_non_postgresql_dialect():
    """非 PG 方言（内存单测）直接跳过，不发 SET LOCAL。"""
    conn = _FakeConnection("sqlite")
    from app.core import tenant_context as tc

    tc._apply_rls_guc_on_begin(None, None, conn)
    assert conn.executed == []


def test_after_begin_bypass_branch_records_guc():
    """无上下文 → 写 bypass GUC（假连接上断言 SQL 文本）。"""
    conn = _FakeConnection("postgresql")
    from app.core import tenant_context as tc

    tc._apply_rls_guc_on_begin(None, None, conn)
    assert conn.executed == [f"SET LOCAL {GUC_SCOPE_BYPASS} = 'on'"]


async def test_enforce_tenant_guc_noop_paths():
    """非 PG bind 或无上下文 → 不执行 set_config。"""
    calls: list = []

    class _ExecSession:
        bind = _FakeBind("sqlite")

        async def execute(self, stmt, params=None):
            calls.append((stmt, params))

    await enforce_tenant_guc(_ExecSession())  # 非 PG → no-op
    assert calls == []

    class _PgSession:
        bind = _FakeBind("postgresql")

        async def execute(self, stmt, params=None):
            calls.append((stmt, params))

    await enforce_tenant_guc(_PgSession())  # 无上下文 → no-op
    assert calls == []


# --- 2. 应用层统一作用域（真实库） --------------------------------------------


async def _seed_two_tenants_with_tasks() -> tuple[int, int, int, int]:
    """建 A/B 两租户 + 各自用户/项目/任务。

    返回 (a_id, b_id, a_task, b_task, user_id)。
    """
    async with SessionFactory() as session:
        ta = Tenant(slug=_slug("a"), name=f"A {_PREFIX}")
        tb = Tenant(slug=_slug("b"), name=f"B {_PREFIX}")
        session.add_all([ta, tb])
        await session.flush()
        a_id, b_id = ta.id, tb.id

        ua = User(
            username=_username("ua"),
            email=f"{_username('ua')}@example.com",
            password_hash="h",
            tenant_id=a_id,
        )
        session.add(ua)
        await session.flush()

        team = Team(name=f"{_PREFIX} team", owner_id=ua.id, tenant_id=a_id)
        session.add(team)
        await session.flush()

        pa = Project(
            name=f"{_PREFIX} pa", description=None, team_id=team.id,
            owner_id=ua.id, tenant_id=a_id,
        )
        pb = Project(
            name=f"{_PREFIX} pb", description=None, team_id=team.id,
            owner_id=ua.id, tenant_id=b_id,
        )
        session.add_all([pa, pb])
        await session.flush()
        t1 = Task(
            project_id=pa.id,
            title=f"{_PREFIX} task-a",
            priority=TaskPriority.HIGH,
            status=TaskStatus.TODO,
            creator_id=ua.id,
            tenant_id=a_id,
        )
        t2 = Task(
            project_id=pb.id,
            title=f"{_PREFIX} task-b",
            priority=TaskPriority.LOW,
            status=TaskStatus.TODO,
            creator_id=ua.id,
            tenant_id=b_id,
        )
        session.add_all([t1, t2])
        await session.commit()
        await session.refresh(t1)
        await session.refresh(t2)
        return a_id, b_id, t1.id, t2.id, ua.id


async def test_orm_select_auto_scoped_by_context():
    """ContextVar 有租户 → ORM SELECT 自动过滤（CRUD 零改动）。"""
    a_id, b_id, a_task, b_task, _uid = await _seed_two_tenants_with_tasks()
    async with SessionFactory() as session:
        token = set_current_tenant_id(a_id)
        try:
            rows = (await session.execute(select(Task))).scalars().all()
        finally:
            reset_current_tenant_id(token)
        ids = [r.id for r in rows]
        assert a_task in ids
        assert b_task not in ids
        assert all(r.tenant_id == a_id for r in rows)


async def test_orm_select_unfiltered_without_context():
    """无上下文（登录前/后台任务语义）→ 应用层不过滤。"""
    a_id, b_id, a_task, b_task, _uid = await _seed_two_tenants_with_tasks()
    async with SessionFactory() as session:
        rows = (await session.execute(select(Task))).scalars().all()
        ids = [r.id for r in rows]
        assert a_task in ids and b_task in ids


async def test_orm_select_unfiltered_inside_explicit_bypass():
    """显式出口内：即使持有租户上下文也不过滤（跨租户查询的唯一通路）。"""
    a_id, b_id, a_task, b_task, _uid = await _seed_two_tenants_with_tasks()
    async with SessionFactory() as session:
        token = set_current_tenant_id(a_id)
        try:
            with bypass_tenant_scope():
                rows = (await session.execute(select(Task))).scalars().all()
        finally:
            reset_current_tenant_id(token)
        ids = [r.id for r in rows]
        assert a_task in ids and b_task in ids


async def test_flush_injects_tenant_from_context():
    """写入注入：新对象未赋 tenant_id → 从 ContextVar 注入。"""
    a_id, b_id, _, _, user_id = await _seed_two_tenants_with_tasks()
    async with SessionFactory() as session:
        token = set_current_tenant_id(a_id)
        try:
            n = Notification(
                user_id=user_id,
                type="task_assigned",
                title=f"{_PREFIX} notif",
            )
            session.add(n)
            await session.flush()
            assert n.tenant_id == a_id
        finally:
            reset_current_tenant_id(token)
            await session.rollback()


async def test_flush_explicit_assignment_wins():
    """显式赋值优先（如归档拷贝）：已赋值对象不被注入覆盖。"""
    a_id, b_id, _, _, user_id = await _seed_two_tenants_with_tasks()
    async with SessionFactory() as session:
        token = set_current_tenant_id(a_id)
        try:
            n = Notification(
                user_id=user_id,
                type="task_assigned",
                title=f"{_PREFIX} notif2",
                tenant_id=b_id,  # 显式指定（跨租户拷贝场景）
            )
            session.add(n)
            await session.flush()
            assert n.tenant_id == b_id
        finally:
            reset_current_tenant_id(token)
            await session.rollback()


# --- 3. 事务级 GUC ------------------------------------------------------------


async def test_after_begin_sets_tenant_guc_and_survives_commit():
    """after_begin：新事务写 app.tenant_id；commit 后新事务仍持续生效。"""
    a_id, *_ = await _seed_two_tenants_with_tasks()
    async with SessionFactory() as session:
        token = set_current_tenant_id(a_id)
        try:
            first = (
                await session.execute(
                    text("SELECT current_setting(:g, true)"), {"g": GUC_TENANT_ID}
                )
            ).scalar()
            assert first == str(a_id)
            await session.commit()
            second = (
                await session.execute(
                    text("SELECT current_setting(:g, true)"), {"g": GUC_TENANT_ID}
                )
            ).scalar()
            assert second == str(a_id)  # 新事务由 after_begin 重新写入
        finally:
            reset_current_tenant_id(token)


async def test_after_begin_sets_bypass_guc_without_context():
    """无上下文事务 → app.tenant_bypass=on、tenant_id 未设。"""
    async with SessionFactory() as session:
        tid_setting = (
            await session.execute(
                text("SELECT current_setting(:g, true)"), {"g": GUC_TENANT_ID}
            )
        ).scalar()
        bypass = (
            await session.execute(
                text("SELECT current_setting(:g, true)"), {"g": GUC_SCOPE_BYPASS}
            )
        ).scalar()
        assert tid_setting in (None, "")
        assert bypass == "on"


async def test_enforce_tenant_guc_flips_open_transaction():
    """enforce_tenant_guc：把已开启的 bypass 事务翻转为 tenant 过滤。"""
    a_id, *_ = await _seed_two_tenants_with_tasks()
    async with SessionFactory() as session:
        # 先做一次无上下文查询（认证查询语义）→ 事务以 bypass 开启
        await session.execute(select(Tenant).limit(1))
        token = set_current_tenant_id(a_id)
        try:
            await enforce_tenant_guc(session)
            tid_setting = (
                await session.execute(
                    text("SELECT current_setting(:g, true)"), {"g": GUC_TENANT_ID}
                )
            ).scalar()
            bypass = (
                await session.execute(
                    text("SELECT current_setting(:g, true)"), {"g": GUC_SCOPE_BYPASS}
                )
            ).scalar()
            assert tid_setting == str(a_id)
            assert bypass == "off"
        finally:
            reset_current_tenant_id(token)


# --- 4. ContextVar 并发不串号 -------------------------------------------------


async def test_contextvar_concurrent_tasks_no_cross_talk():
    a_id, b_id, a_task, b_task, _uid = await _seed_two_tenants_with_tasks()

    async def scoped_query(tenant_id: int, want: int, forbidden: int) -> None:
        token = set_current_tenant_id(tenant_id)
        try:
            await asyncio.sleep(0.01)  # 制造两协程交错
            async with SessionFactory() as session:
                rows = (await session.execute(select(Task))).scalars().all()
                ids = [r.id for r in rows]
                assert want in ids
                assert forbidden not in ids
        finally:
            reset_current_tenant_id(token)

    await asyncio.gather(
        scoped_query(a_id, a_task, b_task),
        scoped_query(b_id, b_task, a_task),
    )
    # 并发结束后主协程上下文未被污染
    assert get_current_tenant_id() is None


# --- 5. RLS 兜底实证（SET ROLE taskflow_app） ---------------------------------


async def test_rls_filters_unfiltered_select_for_runtime_role():
    """漏加条件的全表查询在运行时角色下仍只返回本租户行。"""
    a_id, b_id, a_task, b_task, _uid = await _seed_two_tenants_with_tasks()
    conn = await engine.connect()
    await conn.execute(sa.text("SET ROLE taskflow_app"))
    await conn.execute(sa.text(f"SET LOCAL app.tenant_id = '{a_id}'"))
    rows = (await conn.execute(sa.text("SELECT id, tenant_id FROM tasks"))).all()
    assert rows, "expected at least the seeded tenant A task"
    assert all(r[1] == a_id for r in rows)
    assert b_task not in [r[0] for r in rows]
    await conn.close()


async def test_rls_fail_closed_without_guc():
    """无任何 GUC：运行时角色一行不可见（fail closed，策略两分支均假）。"""
    await _seed_two_tenants_with_tasks()
    conn = await engine.connect()
    await conn.execute(sa.text("SET ROLE taskflow_app"))
    count = (await conn.execute(sa.text("SELECT count(*) FROM tasks"))).scalar()
    assert count == 0
    await conn.close()


async def test_rls_with_check_blocks_cross_tenant_insert():
    """WITH CHECK：不写 tenant_id 的 INSERT（列默认=默认租户 ≠ 当前租户）被拒。"""
    a_id, *_ = await _seed_two_tenants_with_tasks()
    conn = await engine.connect()
    await conn.execute(sa.text("SET ROLE taskflow_app"))
    await conn.execute(sa.text(f"SET LOCAL app.tenant_id = '{a_id}'"))
    project_id = (
        await conn.execute(sa.text("SELECT project_id FROM tasks ORDER BY id LIMIT 1"))
    ).scalar()
    creator_id = (
        await conn.execute(
            sa.text(
                "SELECT creator_id FROM tasks WHERE tenant_id = :t ORDER BY id LIMIT 1"
            ),
            {"t": a_id},
        )
    ).scalar()
    with pytest.raises(sa.exc.DBAPIError) as excinfo:
        await conn.execute(
            sa.text(
                "INSERT INTO tasks (project_id, title, priority, status, creator_id) "
                "VALUES (:pid, :title, 'LOW', 'TODO', :uid)"
            ),
            {"pid": project_id, "title": f"{_PREFIX} rls-ins", "uid": creator_id},
        )
    assert "row-level security policy" in str(excinfo.value)
    await conn.rollback()
    # 显式带对租户的 tenant_id → 放行（回滚，不留数据）
    await conn.execute(
        sa.text(
            "INSERT INTO tasks (project_id, title, priority, status, creator_id, tenant_id) "
            "VALUES (:pid, :title, 'LOW', 'TODO', :uid, :tid)"
        ),
        {
            "pid": project_id,
            "title": f"{_PREFIX} rls-ins-ok",
            "uid": creator_id,
            "tid": a_id,
        },
    )
    await conn.rollback()
    await conn.close()


async def test_rls_blocks_cross_tenant_update():
    """USING：越租户 UPDATE 静默匹配 0 行（不报错、不可探测）。"""
    a_id, b_id, a_task, _, _uid = await _seed_two_tenants_with_tasks()
    conn = await engine.connect()
    await conn.execute(sa.text("SET ROLE taskflow_app"))
    await conn.execute(sa.text(f"SET LOCAL app.tenant_id = '{b_id}'"))
    result = await conn.execute(
        sa.text("UPDATE tasks SET title = :t WHERE id = :id"),
        {"t": f"{_PREFIX} hacked", "id": a_task},
    )
    assert result.rowcount == 0
    await conn.rollback()
    await conn.close()


async def test_rls_bypass_guc_opens_scope():
    """bypass GUC（显式出口的 DB 侧对应物）：策略放行全部行。"""
    a_id, b_id, a_task, b_task, _uid = await _seed_two_tenants_with_tasks()
    conn = await engine.connect()
    await conn.execute(sa.text("SET ROLE taskflow_app"))
    await conn.execute(sa.text(f"SET LOCAL app.tenant_id = '{a_id}'"))
    await conn.execute(sa.text("SET LOCAL app.tenant_bypass = 'on'"))
    rows = (await conn.execute(sa.text("SELECT id FROM tasks"))).all()
    ids = [r[0] for r in rows]
    assert a_task in ids and b_task in ids
    await conn.close()


# --- 6. API 跨租户越权矩阵 ----------------------------------------------------


async def _seed_cross_tenant_world():
    """A/B 租户 + 各自 admin 用户 + A 租户的 team/project/task 链。

    返回 (ua_id, ub_id, team_id, project_id, task_id)。

    TASK-096 后角色/授权是租户内实体：每个新建租户必须先播种自己的 admin/
    member 角色（``seed_tenant_rbac``），否则 ``get_role_by_name("admin")``
    在该租户内为空。播种与用户建连按「每租户独立提交」进行，保证租户上下文
    （ContextVar）与事务级 GUC（``app.tenant_id``）始终一致——二者错位会被
    RLS 的 WITH CHECK 拒绝写入。
    """
    from app.services.rbac_seed import seed_tenant_rbac

    async with SessionFactory() as session:
        ta = Tenant(slug=_slug("a"), name=f"A {_PREFIX}")
        tb = Tenant(slug=_slug("b"), name=f"B {_PREFIX}")
        session.add_all([ta, tb])
        await session.commit()
        ta_id, tb_id = ta.id, tb.id

        # 每租户各自播种 RBAC（独立提交 → GUC 与 ContextVar 一致）。
        await seed_tenant_rbac(session, ta_id)
        await session.commit()
        await seed_tenant_rbac(session, tb_id)
        await session.commit()

        async def _user(tag: str, tenant_id: int) -> User:
            token = set_current_tenant_id(tenant_id)
            try:
                u = User(
                    username=_username(tag),
                    email=f"{_username(tag)}@example.com",
                    password_hash="h",
                    tenant_id=tenant_id,
                )
                session.add(u)
                await session.flush()
                role = await get_role_by_name(session, "admin")
                assert role is not None, f"admin role missing for tenant {tenant_id}"
                await assign_role_to_user(session, user_id=u.id, role_id=role.id)
                return u
            finally:
                reset_current_tenant_id(token)

        ua = await _user("ua", ta_id)
        await session.commit()
        ub = await _user("ub", tb_id)
        await session.commit()

        team = Team(name=f"{_PREFIX} team", owner_id=ua.id, tenant_id=ta_id)
        session.add(team)
        await session.flush()
        session.add(
            TeamMember(
                team_id=team.id,
                user_id=ua.id,
                role_id=TeamRole.OWNER,
                tenant_id=ta_id,
            )
        )
        project = Project(
            name=f"{_PREFIX} proj",
            description=None,
            team_id=team.id,
            owner_id=ua.id,
            tenant_id=ta_id,
        )
        session.add(project)
        await session.flush()
        task = Task(
            project_id=project.id,
            title=f"{_PREFIX} task",
            priority=TaskPriority.HIGH,
            status=TaskStatus.TODO,
            creator_id=ua.id,
            tenant_id=ta_id,
        )
        session.add(task)
        await session.commit()
        await session.refresh(team)
        await session.refresh(project)
        await session.refresh(task)
        return ua.id, ub.id, team.id, project.id, task.id


#: (method, path, body)——body 必须过 FastAPI 校验（否则 422 先于 404）。
MATRIX = [
    ("GET", "/api/v1/teams/{team_id}", None),
    ("GET", "/api/v1/projects/{project_id}", None),
    ("PATCH", "/api/v1/projects/{project_id}", {"name": "x"}),
    ("DELETE", "/api/v1/projects/{project_id}", None),
    ("GET", "/api/v1/tasks/{task_id}", None),
    ("PATCH", "/api/v1/tasks/{task_id}", {"title": "x"}),
    ("DELETE", "/api/v1/tasks/{task_id}", None),
    ("POST", "/api/v1/tasks/{task_id}/comments", {"content": "hi"}),
]


@pytest.mark.parametrize(("method", "path", "body"), MATRIX)
async def test_cross_tenant_matrix_b_token_gets_404(client, method, path, body):
    """跨租户越权矩阵：B 令牌访问 A 资源一律 404（与不存在不可区分）。"""
    ua_id, ub_id, team_id, project_id, task_id = await _seed_cross_tenant_world()
    url = path.format(team_id=team_id, project_id=project_id, task_id=task_id)
    resp = await client.request(
        method,
        url,
        headers=_bearer(create_access_token(ub_id)),
        json=body,
    )
    assert resp.status_code == 404, f"{method} {url}: {resp.status_code} {resp.text}"


async def test_cross_tenant_list_hides_other_tenant_resources(client):
    """列表端点不泄露他租户资源 id（防枚举）。"""
    ua_id, ub_id, team_id, project_id, task_id = await _seed_cross_tenant_world()
    headers = _bearer(create_access_token(ub_id))
    projects = (await client.get("/api/v1/projects", headers=headers)).json()["data"]
    assert all(p["id"] != project_id for p in projects)
    # 项目本身不可见 → 任务列表同样为空/404（服务层先解析项目）
    tasks_resp = await client.get(
        f"/api/v1/tasks?project_id={project_id}", headers=headers
    )
    assert tasks_resp.status_code == 404 or tasks_resp.json().get("data") in (None, [])


async def test_same_tenant_access_still_works(client):
    """正向对照：A 令牌访问 A 资源 200——作用域没有误伤本租户。"""
    ua_id, ub_id, team_id, project_id, task_id = await _seed_cross_tenant_world()
    headers = _bearer(create_access_token(ua_id))
    assert (
        await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    ).status_code == 200
    assert (
        await client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    ).status_code == 200
    assert (
        await client.get(f"/api/v1/teams/{team_id}", headers=headers)
    ).status_code == 200
