"""TASK-062：覆盖率审计暴露的**有业务价值**分支的补测。

## 这个文件为什么存在

TASK-062 用 ``pytest --cov=app`` 做了一次完整审计（结果与逐条归类见
``docs/QUALITY.md``）。审计结论是：总体覆盖率 97%，未覆盖的 66 行里**大部分
是防御性/框架边界代码**，但其中有一批**不是**——它们是安全与数据一致性路径，
只是正常流量走不到：

- 存储层路径守卫的拒绝分支（正常输入不会触发）；
- 附件元数据落库失败后的「回滚事务 + 删除已落盘文件」（只有 DB 出错才会走）；
- 并发注册时唯一约束兜底（只有两个请求同时通过前置检查才会走）；
- 非管理员移除成员 → 403（走得到，但既有测试只覆盖了「邀请」的非管理员分支）；
- Celery broker 不可达时的 best-effort 吞异常（只有 broker 挂掉才会走）。

按 §Phase14「不要为了追求数字而测试没有业务价值的代码」，本文件**只**补这一类；
``__repr__``、纯惰性初始化等无业务价值的行不在此列（理由与清单见 QUALITY.md）。

## 组织方式

- 需要 API 或数据库的：走本文件自带的引擎/夹具（与 ``test_attachment_security.py``
  同一惯例：RUN_TOKEN 前缀 + teardown 精确删除，绝不动开发库的其它行）。
- Celery 任务类的缺口（清理任务、通知任务、Redis 连接层）**就地补在各自既有
  测试文件里**，以复用那边的同步调用夹具（本文件不复刻那套 harness）。
"""

from __future__ import annotations

import asyncio
import importlib
import io
import logging
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, ConflictError, ForbiddenError
from app.core.security import create_access_token
from app.crud.project import is_project_visible
from app.crud.role import assign_role_to_user, get_role_by_name
from app.crud.user import create_user
from app.db.session import get_db
from app.main import app as fastapi_app
from app.main import lifespan
from app.models.attachment import Attachment
from app.models.notification import Notification
from app.models.operation_log import OperationLog
from app.models.project import Project
from app.models.task import Task
from app.models.team import Team
from app.models.user import User
from app.schemas.auth import LoginRequest
from app.schemas.team import TeamMemberInvite
from app.schemas.user import UserCreate
from app.services import attachment as attachment_service
from app.services import auth as auth_service
from app.services import storage as storage_service
from app.services import task as task_service
from app.services import team as team_service

import app.main as main_module

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"qg_{RUN_TOKEN}_{tag}"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def storage_root(tmp_path):
    """把存储根指向 tmp_path，隔离真实 storage/ 卷。"""
    previous = storage_service._backend
    storage_service._backend = storage_service.LocalStorageBackend(tmp_path)
    yield tmp_path
    storage_service._backend = previous


@pytest_asyncio.fixture
async def client():
    fastapi_app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    fastapi_app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    yield
    async with SessionFactory() as session:
        user_ids = select(User.id).where(User.username.like(f"qg_{RUN_TOKEN}%"))
        await session.execute(
            delete(Notification).where(Notification.user_id.in_(user_ids))
        )
        await session.execute(
            delete(OperationLog).where(OperationLog.user_id.in_(user_ids))
        )
        await session.execute(
            delete(Attachment).where(Attachment.uploader_id.in_(user_ids))
        )
        await session.execute(delete(Task).where(Task.title.like(f"qg {RUN_TOKEN}%")))
        await session.execute(
            delete(Project).where(Project.name.like(f"qg proj {RUN_TOKEN}%"))
        )
        await session.execute(delete(Team).where(Team.name.like(f"qg team {RUN_TOKEN}%")))
        await session.execute(
            delete(User).where(User.username.like(f"qg_{RUN_TOKEN}%"))
        )
        await session.commit()


async def _make_user(tag: str, role_names: list[str] | None = None) -> User:
    async with SessionFactory() as session:
        user = await create_user(
            session,
            username=_username(tag),
            email=f"{_username(tag)}@example.com",
            password_hash=PASSWORD_HASH,
        )
        for role_name in role_names or []:
            role = await get_role_by_name(session, role_name)
            assert role is not None, f"seed role {role_name!r} missing"
            await assign_role_to_user(session, user_id=user.id, role_id=role.id)
        await session.commit()
        await session.refresh(user)
        return user


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_project(owner: User, tag: str) -> Project:
    from app.crud.project import create_project
    from app.schemas.team import TeamCreate

    async with SessionFactory() as session:
        team = await team_service.create_team(
            session, owner, TeamCreate(name=f"qg team {RUN_TOKEN} {tag}")
        )
        project = await create_project(
            session,
            name=f"qg proj {RUN_TOKEN} {tag}",
            description=None,
            team_id=team.id,
            owner_id=owner.id,
        )
        await session.commit()
        await session.refresh(project)
        return project


async def _create_task(client, owner: User, project: Project, tag: str) -> int:
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={"project_id": project.id, "title": f"qg {RUN_TOKEN} {tag}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


def _upload_file(filename: str = "a.txt", content: bytes = b"payload"):
    """构造一个 Service 层可直接消费的 UploadFile（不经 multipart 解析）。"""
    return StarletteUploadFile(file=io.BytesIO(content), filename=filename)


# =============================================================================
# 1. 附件落库失败的一致性：回滚事务 + 删除已落盘文件（不留孤儿）
# =============================================================================


async def test_metadata_integrity_error_rolls_back_and_deletes_the_file(
    storage_root, monkeypatch
):
    """``storage_path`` 唯一约束冲撞 → 事务回滚**且**物理文件被删。

    这条是模块 docstring「一致性设计 2」的可执行证据：只回滚事务会留下孤儿文件
    （DB 无记录 → 只能等 TASK-050 的清理任务），只删文件不回滚会留下半提交状态。
    两者必须同时发生。

    ``token_hex(16)`` 撞车概率极低，因此这里注入冲突来走这条路径——它的价值不在
    于「经常发生」，而在于「发生时数据仍然一致」。
    """
    owner = await _make_user("a1", ["admin"])
    project = await _make_project(owner, "a1")
    async with SessionFactory() as session:
        task = Task(
            project_id=project.id,
            title=f"qg {RUN_TOKEN} a1",
            priority="MEDIUM",
            creator_id=owner.id,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = task.id

    async def _conflict(*args, **kwargs):
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    monkeypatch.setattr(attachment_service, "create_attachment_crud", _conflict)

    async with SessionFactory() as session:
        fresh_owner = await session.get(User, owner.id)
        with pytest.raises(AppError) as excinfo:
            await attachment_service.upload_attachment(
                session, fresh_owner, task_id, _upload_file(content=b"payload")
            )
        assert excinfo.value.detail == "Failed to persist attachment metadata"
        # 回滚后 Session 仍可用（否则后续清理/日志都会连带失败）
        assert await session.scalar(select(1)) == 1

    leftovers = [p for p in storage_root.rglob("*") if p.is_file()]
    assert leftovers == [], [str(p) for p in leftovers]

    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(Attachment).where(Attachment.task_id == task_id)
            )
        ).scalars().all()
    assert rows == []


async def test_metadata_unexpected_error_is_reraised_without_orphan(
    storage_root, monkeypatch
):
    """非 ``IntegrityError`` 的意外故障：同样回滚并删文件，但**异常原样上抛**。

    为什么不能吞：这是未预期的程序错误，吞掉会把它伪装成「上传失败」的普通
    业务结果（§50 明确禁止 ``except Exception: return {...}`` 式掩盖）。
    与上一条的分工：IntegrityError 是可预期的冲突 → 中性文案；其它 → 保留堆栈。
    """

    owner = await _make_user("a2", ["admin"])
    project = await _make_project(owner, "a2")
    async with SessionFactory() as session:
        task = Task(
            project_id=project.id,
            title=f"qg {RUN_TOKEN} a2",
            priority="MEDIUM",
            creator_id=owner.id,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = task.id

    async def _boom(*args, **kwargs):
        raise RuntimeError("connection reset by peer")

    monkeypatch.setattr(attachment_service, "create_attachment_crud", _boom)

    async with SessionFactory() as session:
        fresh_owner = await session.get(User, owner.id)
        with pytest.raises(RuntimeError, match="connection reset"):
            await attachment_service.upload_attachment(
                session, fresh_owner, task_id, _upload_file(content=b"payload")
            )

    assert [p for p in storage_root.rglob("*") if p.is_file()] == []


# =============================================================================
# 2. 注册的唯一约束兜底（§5 username/email 唯一）
# =============================================================================


async def test_duplicate_registration_is_translated_when_both_pass_the_precheck(
    monkeypatch,
):
    """两个请求同时通过前置检查 → DB 唯一约束兜底 → 409 而不是 500。

    前置检查（先查用户名/邮箱是否存在）与 INSERT 之间存在**固有**的竞争窗口，
    因此唯一约束才是真正的守卫。这里把两个 CRUD 查询打成 ``None`` 来稳定复现
    「两边都通过了检查」的窗口，验证 Service 确实把这个 IntegrityError 翻译成
    业务冲突，而不是让它变成 500。
    """

    from app.models.user import User as UserModel

    async def _missing(*args, **kwargs):
        return None

    async def _insert_directly(session, **kwargs):
        # 绕过 Service 的前置检查，直接落库（模拟并发中的另一个请求已插入）
        user = UserModel(
            username=kwargs["username"],
            email=kwargs["email"],
            password_hash=kwargs["password_hash"],
        )
        session.add(user)
        await session.flush()
        return user

    payload = UserCreate(
        username=_username("d1"),
        email=f"{_username('d1')}@example.com",
        password="Passw0rd!23",
    )

    async with SessionFactory() as other:
        await _insert_directly(
            other,
            username=payload.username,
            email=payload.email,
            password_hash=PASSWORD_HASH,
        )
        await other.commit()

    monkeypatch.setattr(auth_service, "get_user_by_username", _missing)
    monkeypatch.setattr(auth_service, "get_user_by_email", _missing)

    async with SessionFactory() as session:
        with pytest.raises(ConflictError) as excinfo:
            await auth_service.register_user(session, payload)
        assert "already registered" in excinfo.value.detail
        assert excinfo.value.status_code == 409
        assert await session.scalar(select(1)) == 1  # 回滚后可用

    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(User).where(User.username == payload.username)
            )
        ).scalars().all()
    assert len(rows) == 1, "冲突请求不得写入第二行"


async def test_concurrent_registrations_let_exactly_one_win():
    """真实并发（无 mock）：N 个同名注册只有一个成功，其余全部 409。

    这条不依赖 mock——它验证的是「DB 唯一约束 + Service 翻译」这对组合在**真并发**
    下的行为。无论冲突是被前置检查还是被 IntegrityError 拦下，对外都必须是
    ConflictError（而不是 500，也不是多出一个用户）。用户名的唯一性是 §5 的硬要求。
    """

    payload = UserCreate(
        username=_username("d2"),
        email=f"{_username('d2')}@example.com",
        password="Passw0rd!23",
    )

    async def _attempt():
        async with SessionFactory() as session:
            try:
                return await auth_service.register_user(session, payload)
            except ConflictError as exc:
                return exc

    results = await asyncio.gather(*(_attempt() for _ in range(5)))

    assert sum(isinstance(r, User) for r in results) == 1
    assert sum(isinstance(r, ConflictError) for r in results) == 4

    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(User).where(User.username == payload.username)
            )
        ).scalars().all()
    assert len(rows) == 1


async def test_account_still_usable_after_a_lost_race(monkeypatch):
    """输掉竞争的一方回滚后，胜出者的账号仍然可正常登录。

    验证的是「冲突处理的副作用边界」：``register_user`` 在 IntegrityError 分支里
    调用 ``rollback``——如果它误伤了胜出者已提交的行（或连接池层把状态搞坏），
    这里会立刻表现为登录失败。
    """
    payload = UserCreate(
        username=_username("d3"),
        email=f"{_username('d3')}@example.com",
        password="Passw0rd!23",
    )

    async with SessionFactory() as session:
        winner = await auth_service.register_user(session, payload)

    async def _missing(*args, **kwargs):
        return None

    monkeypatch.setattr(auth_service, "get_user_by_username", _missing)
    monkeypatch.setattr(auth_service, "get_user_by_email", _missing)
    async with SessionFactory() as session:
        with pytest.raises(ConflictError):
            await auth_service.register_user(session, payload)

    monkeypatch.undo()  # 恢复真实查询，让登录能正常找到这一行

    async with SessionFactory() as session:
        authenticated = await auth_service.authenticate_user(
            session,
            LoginRequest(username=payload.username, password=payload.password),
        )
    assert authenticated.id == winner.id


# =============================================================================
# 3. 非管理员不能移除成员（§35 Team 明确列出的验收点）
# =============================================================================


async def test_remove_member_requires_owner_or_admin():
    """普通成员移除他人 → 403，且**无副作用**（目标仍在团队里）。

    §35 的 Team 清单里同时列了「重复成员」和「非管理员不能邀请」，但
    「非管理员**移除**」是权限层级里更危险的一侧（邀请是加法，移除是减法），
    既有测试只覆盖了前者的 403。
    """
    from app.crud.team import get_team_member
    from app.schemas.team import TeamCreate

    owner = await _make_user("t1", ["admin"])
    member = await _make_user("t2", ["member"])
    target = await _make_user("t3", ["member"])

    async with SessionFactory() as session:
        team = await team_service.create_team(
            session, owner, TeamCreate(name=f"qg team {RUN_TOKEN} t1")
        )
        await team_service.invite_member(
            session, owner, team.id, TeamMemberInvite(user_id=member.id, role="member")
        )
        await team_service.invite_member(
            session, owner, team.id, TeamMemberInvite(user_id=target.id, role="member")
        )

    async with SessionFactory() as session:
        fresh_member = await session.get(User, member.id)
        with pytest.raises(ForbiddenError) as excinfo:
            await team_service.remove_member(session, fresh_member, team.id, target.id)
        assert excinfo.value.status_code == 403

        # 403 不应产生任何副作用
        still_there = await get_team_member(
            session, team_id=team.id, user_id=target.id
        )
        assert still_there is not None


async def test_team_admin_cannot_remove_the_owner():
    """层级 OWNER > ADMIN > MEMBER：admin 移除 owner → 403（有专属守卫，不靠兜底）。"""
    from app.schemas.team import TeamCreate

    owner = await _make_user("t4", ["admin"])
    admin = await _make_user("t5", ["member"])

    async with SessionFactory() as session:
        team = await team_service.create_team(
            session, owner, TeamCreate(name=f"qg team {RUN_TOKEN} t4")
        )
        await team_service.invite_member(
            session, owner, team.id, TeamMemberInvite(user_id=admin.id, role="admin")
        )

    async with SessionFactory() as session:
        fresh_admin = await session.get(User, admin.id)
        with pytest.raises(ForbiddenError, match="owner cannot be removed"):
            await team_service.remove_member(session, fresh_admin, team.id, owner.id)


# =============================================================================
# 4. 可见性判定的边界（§49 资源级权限）
# =============================================================================


async def test_is_project_visible_returns_false_for_missing_project():
    """项目不存在 → False（而不是抛异常）。

    这条分支是归属链判定的「第一跳」：调用方（task/project Service）用它来把
    「项目不存在」与「项目存在但我不在链上」**收敛成同一个 404**，从而实现
    §49 的 IDOR 防枚举。它必须返回 False 而不是抛错，否则两种失败会分叉。
    """
    async with SessionFactory() as session:
        assert (
            await is_project_visible(
                session, project_id=2_000_000_000, user_id=1
            )
            is False
        )


async def test_is_project_visible_is_false_for_a_non_member_and_true_for_a_member():
    """同一项目：成员 True、非成员 False（认证 ≠ 授权）。"""
    from app.crud.team import add_team_member
    from app.models.team_member import TeamRole

    owner = await _make_user("v1", ["admin"])
    outsider = await _make_user("v2", ["admin"])
    project = await _make_project(owner, "v1")

    async with SessionFactory() as session:
        assert (
            await is_project_visible(
                session, project_id=project.id, user_id=owner.id
            )
            is True
        )
        assert (
            await is_project_visible(
                session, project_id=project.id, user_id=outsider.id
            )
            is False
        )

        # 之后再入队 → 立刻变为可见（判定是实时查询，不缓存结论）
        await add_team_member(
            session,
            team_id=project.team_id,
            user_id=outsider.id,
            role_id=TeamRole.MEMBER.value,
        )
        await session.commit()

    async with SessionFactory() as session:
        assert (
            await is_project_visible(
                session, project_id=project.id, user_id=outsider.id
            )
            is True
        )


# =============================================================================
# 5. 通知派发的 best-effort 语义（§24）
# =============================================================================


def test_dispatch_notification_swallows_broker_failure_but_logs_it(
    monkeypatch, caplog
):
    """broker 不可达时派发**不得**向上抛，但必须在日志里留下痕迹。

    两条要求缺一不可：

    - 不抛：派发发生在主业务 commit **之后**，让通知故障回滚已提交的业务是
      错的（§24「主业务失败不产生错误通知」的对称面）；
    - 留痕但不冒泡：静默吞掉会让「通知全丢了」在生产里完全不可见，所以必须
      warning + 堆栈。

    为什么要 reload 模块：``tests/conftest.py`` 的 autouse 夹具把
    ``_dispatch_notification`` 换成了 no-op（其余测试不关心派发），这里需要
    **真实实现**。reload 拿回它，且不影响其它用例（模块对象身份不变，
    下一用例的 autouse 夹具会重新打上 no-op）。
    """
    module = importlib.reload(task_service)

    class _DeadBroker:
        def delay(self, *args, **kwargs):
            raise ConnectionError("broker unreachable")

    monkeypatch.setattr(module, "create_notification", _DeadBroker())

    with caplog.at_level(logging.WARNING, logger=module.__name__):
        module._dispatch_notification(
            user_id=7,
            ntype="task_assigned",
            title="你被分配到任务",
            content=None,
            idempotency_key="qg-key-1",
        )  # 不得抛出

    messages = [record.getMessage() for record in caplog.records]
    warnings = [m for m in messages if "notification dispatch failed" in m]
    assert warnings, messages
    # 「不静默」要求堆栈也被保留（exc_info=True）——否则生产里只看到一句
    # 「派发失败」，看不到是 broker 不可达还是序列化错误。
    record = next(
        r for r in caplog.records if "notification dispatch failed" in r.getMessage()
    )
    assert record.exc_info is not None
    assert "broker unreachable" in str(record.exc_info[1])


# =============================================================================
# 6. 限流开关关闭时是「直放行」，不是「换个方式限流」
# =============================================================================


async def test_disabled_rate_limit_passes_through_without_headers(client, monkeypatch):
    """``rate_limit_enabled=False`` → 直接放行、**完全不碰 Redis**、不带任何限流响应头。

    与「限流打开时带 X-RateLimit-*」成对断言（后者见 ``tests/test_rate_limit.py``，
    那里有真正的 Redis 夹具）：这条区分了「开关真的关掉了」与「开关关了但中间件还在
    算配额」——后者会让开发环境出现莫名其妙的 429，也会白白多一次 Redis 往返。

    **离线可判定**：把 ``check_rate_limit`` 换成「一被调用就炸」的哨兵，把「关掉开关
    即零 Redis 往返」这条契约变成硬断言。早先这里写的是「重新打开开关再断言响应头
    存在」，那会真的连 Redis，在 pytest-asyncio「每个用例一个新事件循环」的环境下
    复用上一循环缓存的连接池会抛 ``RuntimeError: Event loop is closed``——测试因此
    变得依赖执行顺序，且它想验证的性质（打开时带响应头）已被限流套件覆盖。
    """
    from app.core import middleware as middleware_module

    settings: Settings = get_settings()
    owner = await _make_user("l1", ["admin"])
    headers = _bearer(create_access_token(owner.id))

    called: list[str] = []

    async def _sentinel(*args, **kwargs):
        called.append("check_rate_limit")
        raise AssertionError("rate_limit_enabled=False 时不应调用 check_rate_limit")

    monkeypatch.setattr(middleware_module, "check_rate_limit", _sentinel)
    monkeypatch.setattr(settings, "rate_limit_enabled", False, raising=False)

    resp = await client.get("/api/v1/users/me", headers=headers)
    assert resp.status_code == 200, resp.text
    assert called == [], "限流已关闭，中间件却仍去检查配额（白白多一次 Redis 往返）"
    lowered = {k.lower() for k in resp.headers}
    assert "x-ratelimit-limit" not in lowered
    assert "x-ratelimit-remaining" not in lowered


# =============================================================================
# 7. 应用生命周期与依赖探测（进程级）
# =============================================================================


async def test_lifespan_releases_the_redis_pool_on_shutdown(monkeypatch):
    """shutdown 时必须调用 ``close_redis``，且启动阶段什么都不做。

    没有这一步，每次热重载/滚动重启都会泄漏一个连接池（Uvicorn 的 `--reload`
    在开发期会频繁触发）。断言「yield 之前不关」是为了防止有人把释放提前到
    启动阶段——那会让第一次请求拿到已关闭的客户端。
    """
    calls: list[str] = []

    async def _fake_close() -> None:
        calls.append("closed")

    monkeypatch.setattr(main_module, "close_redis", _fake_close)

    async with lifespan(fastapi_app):
        assert calls == [], "启动阶段不得释放连接池"

    assert calls == ["closed"]


async def test_health_degrades_to_200_instead_of_500_when_dependencies_are_down(
    monkeypatch,
):
    """依赖挂掉时 ``/health`` 返回 200 + ``degraded``，绝不再是 500。

    这是 liveness 与 readiness 的分工：进程活着就必须能答 200（否则编排器会
    直接杀容器），依赖状态放 body 里给上游判断。若探测函数把异常冒泡出去，
    ``/health`` 自己就会 500——最需要它的时刻恰好不可用。
    """

    class _DeadEngine:
        def connect(self):
            raise RuntimeError("postgres is down")

    class _DeadRedis:
        async def ping(self):
            raise RuntimeError("redis is down")

    monkeypatch.setattr(main_module, "engine", _DeadEngine())
    monkeypatch.setattr(main_module, "get_redis_client", lambda: _DeadRedis())

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        resp = await c.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["database"] == "down"
    assert body["redis"] == "down"


# =============================================================================
# 8. 「我的任务」数据原语（跨项目，§10 多人分配的另一半）
# =============================================================================


async def test_filter_tasks_by_assignee_across_projects():
    """``filter_tasks_by_assignee`` 只返回分配给我的任务，且分页参数生效。

    这是 §10「我的任务」视图的数据原语（尚未开放端点），也是 ``assignee_id``
    过滤之外唯一按「人」聚合任务的入口——把它测掉，避免以后接端点时才发现
    它只对单个项目有效或缺分页。
    """
    from app.crud.task import create_task as create_task_crud
    from app.crud.task_assignee import add_task_assignee, filter_tasks_by_assignee

    owner = await _make_user("f1", ["admin"])
    other = await _make_user("f2", ["admin"])
    project_a = await _make_project(owner, "f1")
    project_b = await _make_project(owner, "f2")

    async with SessionFactory() as session:
        mine: list[int] = []
        for index in range(3):
            task = await create_task_crud(
                session,
                project_id=project_a.id if index < 2 else project_b.id,
                title=f"qg {RUN_TOKEN} f1-{index}",
                description=None,
                priority="MEDIUM",
                creator_id=owner.id,
            )
            await add_task_assignee(
                session, task_id=task.id, user_id=owner.id, assigned_by_id=owner.id
            )
            mine.append(task.id)

        theirs = await create_task_crud(
            session,
            project_id=project_a.id,
            title=f"qg {RUN_TOKEN} f2-only",
            description=None,
            priority="MEDIUM",
            creator_id=owner.id,
        )
        await add_task_assignee(
            session, task_id=theirs.id, user_id=other.id, assigned_by_id=owner.id
        )
        await session.commit()

        found = await filter_tasks_by_assignee(session, owner.id, skip=0, limit=100)
        found_ids = [t.id for t in found]
        assert found_ids == sorted(mine), "跨项目、按 id 升序、不含他人的任务"

        page = await filter_tasks_by_assignee(session, owner.id, skip=1, limit=1)
        assert [t.id for t in page] == [sorted(mine)[1]]


# =============================================================================
# 9. TASK-062 覆盖率收尾：把剩余未覆盖行里「有业务/安全价值」的分支补齐
# =============================================================================
#
# 覆盖率测量显示全部产品代码只剩 10 处未覆盖语句，本节逐条判过：下面这些是**有
# 真实语义**的（安全边界 / 错误映射 / 幂等 / 纵深防御），值得固化成断言；另有少数
# 属于「为数字而测」的排除项，清单与理由见 docs/QUALITY.md「刻意排除的代码」。


def _make_request(headers: dict[str, str], client=("203.0.113.9", 12345)):
    """按给定请求头构造一个最小 Starlette Request（供纯计算的内部函数使用）。"""
    from starlette.requests import Request

    raw = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/users/me",
            "headers": raw,
            "query_string": b"",
            "client": client,
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


# --- 9.1 文件名净化：空输入 + 「扩展名不可用」时的截断 ------------------------


def test_sanitize_filename_rejects_blank_input():
    """空 / None 文件名必须显式拒绝（§9 文件上传 / §48）。

    端点层也会拦（`test_degenerate_filenames_are_rejected_consistently`），但
    `sanitize_filename` 是**唯一**的入口净化函数：将来多一条上传路径（批量导入、
    Webhook 收附件）复用它时，兜底必须在这里成立，而不是依赖调用方先校验。
    """
    from app.services.attachment import (
        EMPTY_FILENAME,
        InvalidUploadError,
        sanitize_filename,
    )

    for blank in ("", None):
        with pytest.raises(InvalidUploadError) as excinfo:
            sanitize_filename(blank)
        assert excinfo.value.detail == EMPTY_FILENAME
        assert excinfo.value.status_code == 400


def test_sanitize_filename_truncates_when_extension_is_unusable():
    """超长文件名且**没有可用扩展名**时退化为朴素截断（§9）。

    两条子分支：①完全没有点（`ext` 为空）；②有点但「扩展名」超过 20 字符
    （不是真扩展名，例如 `file.` + 40 个随机字符）。与「保留扩展名」那条
    （`test_filename_is_truncated_preserving_extension`）成对——合起来才说明
    「截断保留扩展名」是**有条件**的策略，而不是碰巧对某个输入成立。
    """
    from app.services.attachment import MAX_FILENAME_LENGTH, sanitize_filename

    no_dot = "a" * (MAX_FILENAME_LENGTH + 50)
    assert sanitize_filename(no_dot) == "a" * MAX_FILENAME_LENGTH

    long_tail = "b" * 40  # 40 > 20 → 不视为扩展名
    dotted = "c" * (MAX_FILENAME_LENGTH + 50) + "." + long_tail
    out = sanitize_filename(dotted)
    assert out == "c" * MAX_FILENAME_LENGTH, "超长「扩展名」不应被当作扩展名保留"


# --- 9.2 附件落盘失败的错误映射：超限是 413，其它 IO 故障是 500 ---------------


async def test_upload_re_raises_non_limit_storage_failures(monkeypatch):
    """存储层**非超限**的 IO 故障必须原样上抛（→ 500），不得伪装成 413。

    `upload_attachment` 用消息区分两种 `StorageError`：含 "exceeds the limit" →
    413 业务错误；其余（磁盘满、权限不足、对象存储 5xx）是环境故障。把后者吞掉或
    归成 413，等于把「服务端坏了」讲成「你的文件太大」——排障方向直接跑偏，而且
    客户端会一直重试一个永远不会好的上传。
    """
    owner = await _make_user("su1", ["admin"])
    project = await _make_project(owner, "su1")
    async with SessionFactory() as session:
        task = Task(
            project_id=project.id,
            title=f"qg {RUN_TOKEN} su1",
            priority="MEDIUM",
            creator_id=owner.id,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = task.id

    class _BrokenBackend:
        def save(self, key, data, *, max_size):
            raise storage_service.StorageError("disk exploded")

        def delete(self, key):  # pragma: no cover - 绝不应被调用
            raise AssertionError("save 失败后不应再去删除一个不存在的文件")

    monkeypatch.setattr(storage_service, "_backend", _BrokenBackend())

    async with SessionFactory() as session:
        fresh_owner = await session.get(User, owner.id)
        with pytest.raises(storage_service.StorageError) as excinfo:
            await attachment_service.upload_attachment(
                session, fresh_owner, task_id, _upload_file()
            )

    assert not isinstance(excinfo.value, attachment_service.FileTooLargeError), (
        "非超限的 IO 故障被错误地映射为 413"
    )
    assert "disk exploded" in str(excinfo.value), "原始异常信息必须保留（§50 不掩盖）"


# --- 9.3 限流错误的 Retry-After 语义 ------------------------------------------


def test_rate_limit_error_omits_retry_after_when_it_is_not_known():
    """没给出 ``retry_after`` 时不加头；给了则必须 ≥1（0/负数无意义）。

    `Retry-After: 0` 会让客户端**立刻**重试并再次被拒——比不给更糟。因此
    `max(1, ...)` 的下界是契约的一部分，这里把它钉死。
    """
    from app.core.exceptions import RateLimitExceededError

    assert RateLimitExceededError("slow down").headers is None

    for raw, expected in ((0, "1"), (-5, "1"), (7, "7")):
        assert RateLimitExceededError("slow down", retry_after=raw).headers == {
            "Retry-After": expected
        }


# --- 9.4 可信代理判定：对端地址不可解析时必须 fail-safe -----------------------


def test_trusted_proxy_check_fails_safe_on_an_unparseable_peer():
    """对端地址无法解析成 IP → **不信任**（fail-safe），但正常可信对端仍要放行。

    若这里返回 True，一个畸形/伪造的对端字符串就能让「只信任内网网段」的边界失效，
    XFF 头随之被采信，客户端即可自选限流身份（§31）。后一条断言同时防止「改成恒
    返回 False」这种把功能彻底关掉的假修复。
    """
    import ipaddress

    from app.core.client_ip import _peer_is_trusted

    trusted = (ipaddress.ip_network("10.0.0.0/8"),)
    assert _peer_is_trusted("not-an-ip", trusted) is False
    assert _peer_is_trusted("", trusted) is False
    assert _peer_is_trusted("10.1.2.3", trusted) is True, "可信网段内的正常对端必须放行"


# --- 9.5 限流中间件：非 /api/v1 路径直通 + 身份解析的降级 ---------------------


async def test_non_api_paths_bypass_the_rate_limiter(client, monkeypatch):
    """只有 `/api/v1` 前缀受限流约束；`/` 等路径必须**完全不触发** Redis（§22）。

    没有这条边界，一个探活/静态请求也会消耗配额，甚至把健康检查打成 429——而
    编排器会据此判定实例不健康。断言「零 Redis 往返」比「返回 200」更强：后者在
    「算了配额但放行」的实现下同样成立。
    """
    from app.core import middleware as middleware_module

    settings: Settings = get_settings()
    called: list[str] = []

    async def _sentinel(*args, **kwargs):
        called.append("check_rate_limit")
        raise AssertionError("非 /api/v1 路径不应触发限流")

    monkeypatch.setattr(middleware_module, "check_rate_limit", _sentinel)
    monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)

    resp = await client.get("/")
    assert resp.status_code == 200, resp.text
    assert called == [], "非 /api/v1 路径触发了限流判定"


def test_rate_limit_identity_degrades_to_ip_for_every_unusable_bearer_form(monkeypatch):
    """拿不到可信身份时一律退化为 IP 维度，而不是抛错或漏放（§22）。

    四种形态：①压根没有 Authorization 头；②`Bearer` 后为空；③Token 解码失败；
    ④解码成功但 `sub` 为 null。前三种走「退化」，第四种最容易写错——`sub` 存在但
    为空时若直接 `str(None)` 会得到字面量 `"None"`，把所有这类请求折叠进**同一个**
    配额桶（等于给全站开了个共享的 60/分钟）。
    """
    from app.core import middleware as middleware_module
    from app.core.redis_keys import RATE_LIMIT_SCOPE_IP

    def _identity(headers):
        return middleware_module._rate_limit_identity(_make_request(headers))

    assert _identity({}) == (RATE_LIMIT_SCOPE_IP, "203.0.113.9")
    assert _identity({"Authorization": "Bearer "}) == (RATE_LIMIT_SCOPE_IP, "203.0.113.9")
    assert _identity({"Authorization": "Bearer garbage"}) == (
        RATE_LIMIT_SCOPE_IP,
        "203.0.113.9",
    )

    monkeypatch.setattr(
        middleware_module, "decode_access_token", lambda _t: {"sub": None}
    )
    assert _identity({"Authorization": "Bearer looks-valid"}) == (
        RATE_LIMIT_SCOPE_IP,
        "203.0.113.9",
    )

    monkeypatch.setattr(middleware_module, "decode_access_token", lambda _t: {"sub": "42"})
    assert _identity({"Authorization": "Bearer looks-valid"}) == ("user", "42")


def test_access_log_user_id_is_none_for_every_unusable_token_form(monkeypatch):
    """访问日志的 `user_id` 在拿不到身份时记 null，绝不因畸形 Token 抛异常（§33/§34）。

    这是日志层最重要的一条性质：**日志不能成为新的故障源**。一个畸形 `sub`
    （如 `{"sub": "abc"}`）若让 `int()` 冒泡，这一次请求就会因为「打日志」而 500。
    """
    from app.core import middleware as middleware_module

    assert middleware_module._user_id_from_request(_make_request({})) is None
    assert middleware_module._user_id_from_request(
        _make_request({"Authorization": "Bearer "})
    ) is None
    assert middleware_module._user_id_from_request(
        _make_request({"Authorization": "Bearer garbage"})
    ) is None
    assert middleware_module._user_id_from_request(
        _make_request({"Authorization": "Token abc"})
    ) is None

    for payload in ({"sub": None}, {"sub": "abc"}, {"sub": "3.5"}, {"sub": []}):
        monkeypatch.setattr(
            middleware_module, "decode_access_token", lambda _t, _p=payload: _p
        )
        assert (
            middleware_module._user_id_from_request(
                _make_request({"Authorization": "Bearer looks-valid"})
            )
            is None
        )

    monkeypatch.setattr(middleware_module, "decode_access_token", lambda _t: {"sub": "9"})
    assert (
        middleware_module._user_id_from_request(
            _make_request({"Authorization": "Bearer looks-valid"})
        )
        == 9
    )


# --- 9.6 登出幂等：payload 没有可用 jti 时不产生任何写操作 --------------------


async def test_logout_is_idempotent_when_the_token_carries_no_usable_jti(monkeypatch):
    """Refresh Token 解出的 payload 无可用 `jti` → 幂等成功且**零写操作**（§19）。

    登出的目标是「让这个 Token 不可用」。一个连 jti 都没有的 Token 本来就无法撤销，
    报错只会让客户端无法无条件清理本地凭证。反过来，「静默成功」也**不能**演变成
    「顺手把别的 token 撤了」——所以这里同时断言查库与撤销都没发生。
    """
    from app.services import auth as auth_service_module

    calls: list[str] = []

    async def _spy_lookup(db, jti):
        calls.append(f"lookup:{jti}")
        return None

    async def _spy_revoke(db, jti):
        calls.append(f"revoke:{jti}")

    monkeypatch.setattr(auth_service_module, "get_refresh_token_by_jti", _spy_lookup)
    monkeypatch.setattr(auth_service_module, "revoke_refresh_token", _spy_revoke)

    user = await _make_user("lo1", ["admin"])

    for payload in ({"sub": str(user.id)}, {"sub": str(user.id), "jti": 123}, {"sub": str(user.id), "jti": ""}):
        monkeypatch.setattr(
            auth_service_module, "decode_refresh_token", lambda _t, _p=payload: _p
        )
        async with SessionFactory() as session:
            await auth_service_module.logout_user(session, user, "whatever")

    assert calls == [], f"无可用 jti 的登出不应触库或撤销任何 token：{calls}"


# --- 9.7 存储：删除「根级对象」绝不能尝试 rmdir 存储根 ------------------------


def test_deleting_a_root_level_object_never_prunes_the_storage_root(tmp_path):
    """删掉存储根下的对象后，存储根本身必须依然存在（纵深防御）。

    `build_key` 产出的 key 恒为 `<task_id>/<name>` 形态，因此「父目录就是根」这条
    分支在正常流程里走不到——但它是**可达**的：`validate_key` 只禁止 `..` 穿越，
    并不要求 key 必须有两级，任何直接调用 `backend.delete(key)` 的代码（如清理任务
    的兜底路径）都可能传入根级 key。若这里少了 `parent != root` 的守卫，
    `rmdir()` 会作用在存储根上——那是一个「一次误删整卷」的隐患。
    """
    from app.services.storage import LocalStorageBackend

    backend = LocalStorageBackend(tmp_path)
    backend.save("plain.bin", io.BytesIO(b"data"), max_size=100)
    assert backend.exists("plain.bin")

    backend.delete("plain.bin")

    assert not backend.exists("plain.bin")
    assert backend.root.is_dir(), "删除根级对象后存储根被误删"
    assert list(backend.root.iterdir()) == []
