"""TASK-040：Phase 6 状态机与审计验收链路测试（纯测试任务，未改应用代码）。

对开发文档 §35「Task 重点测试」与 §56 Phase 8「状态机」验收条款逐条核对后，
补上 TASK-037/038/039 分散模块未整合的验收链路：

- **§56 Phase 8 完整链路演示**：一次跑通 `TODO → IN_PROGRESS → REVIEW → DONE`
  并演示 `DONE -> TODO` 被拒绝（规格原文两条）；
- **§35 Task** 状态正常流转 / 非法状态流转 / DONE 不允许回退——验收面整合；
- **§55.3 事务原子性**（TESTING.md 优先级 #3「事务与数据一致性」）：
  状态变更与写 OperationLog **必须同事务提交**——写日志失败时状态变更
  一并回滚（不出现「状态变了但没日志」或反之）；
- **审计 ⇄ 状态一致性**：每次成功流转恰好一条日志，且日志序列的
  `old_status`/`new_status` 与任务状态链严格衔接；被拒流转不产生日志。

沿用 test_task_transition_api.py 的「真实产品应用 + 真实 Token + 本次运行
唯一前缀 + teardown 精确删除」模式（含 RESTRICT 全链与审计日志清理）。
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import create_access_token
from app.crud.role import assign_role_to_user, get_role_by_name
from app.crud.user import create_user
from app.db.session import get_db
from app.main import app
from app.models.operation_log import OperationLog
from app.models.project import Project
from app.models.task import Task
from app.models.team import Team
from app.models.user import User

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"smkflow_{RUN_TOKEN}_{tag}"


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


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    yield
    async with SessionFactory() as session:
        await session.execute(
            delete(OperationLog).where(
                OperationLog.user_id.in_(
                    select(User.id).where(User.username.like(f"smkflow_{RUN_TOKEN}%"))
                )
            )
        )
        await session.execute(
            delete(Task).where(Task.title.like(f"smkflow {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"smkflow proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"smkflow team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"smkflow_{RUN_TOKEN}%"))
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
    from app.services.team import create_team as create_team_service

    async with SessionFactory() as session:
        team = await create_team_service(
            session, owner, TeamCreate(name=f"smkflow team {RUN_TOKEN} {tag}")
        )
        project = await create_project(
            session,
            name=f"smkflow proj {RUN_TOKEN} {tag}",
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
        json={"project_id": project.id, "title": f"smkflow {RUN_TOKEN} {tag}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _db_task_status(task_id: int) -> str:
    async with SessionFactory() as session:
        result = await session.execute(select(Task.status).where(Task.id == task_id))
        return result.scalar_one()


async def _db_logs(task_id: int) -> list[OperationLog]:
    async with SessionFactory() as session:
        result = await session.execute(
            select(OperationLog)
            .where(
                OperationLog.resource_type == "task",
                OperationLog.resource_id == task_id,
            )
            .order_by(OperationLog.id)
        )
        return list(result.scalars().all())


async def _transition(client, user: User, task_id: int, to: str) -> int:
    resp = await client.post(
        f"/api/v1/tasks/{task_id}/transition",
        headers=_bearer(create_access_token(user.id)),
        json={"to_status": to},
    )
    return resp.status_code


# --- §56 Phase 8：完整链路演示 + DONE -> TODO 被拒 ---------------------------


async def test_phase8_full_chain_demo_and_reverse_rejected(client):
    """规格 §56 Phase 8 原文两条演示：前进链跑通 + DONE→TODO 被拒绝。"""
    owner = await _make_user("owner1", ["admin"])
    project = await _make_project(owner, "p8")
    task_id = await _create_task(client, owner, project, "p8")

    # 演示链：TODO -> IN_PROGRESS -> REVIEW -> DONE
    for step in ("IN_PROGRESS", "REVIEW", "DONE"):
        assert await _transition(client, owner, task_id, step) == 200
    assert await _db_task_status(task_id) == "DONE"

    # 演示：DONE -> TODO 被拒绝，状态不变
    assert await _transition(client, owner, task_id, "TODO") == 409
    assert await _db_task_status(task_id) == "DONE"


# --- §35 Task：状态正常流转 / 非法流转 / DONE 不允许回退 ----------------------


async def test_spec35_legal_transitions_chain(client):
    """§35「状态正常流转」：前进链每一跳 200 且状态真实持久化。"""
    owner = await _make_user("owner2", ["admin"])
    project = await _make_project(owner, "s35")
    task_id = await _create_task(client, owner, project, "s35")

    assert await _db_task_status(task_id) == "TODO"
    for step in ("IN_PROGRESS", "REVIEW", "DONE"):
        assert await _transition(client, owner, task_id, step) == 200
        assert await _db_task_status(task_id) == step


async def test_spec35_illegal_and_done_no_rollback(client):
    """§35「非法状态流转」+「DONE 不允许回退」：409 且状态不动。"""
    owner = await _make_user("owner3", ["admin"])
    project = await _make_project(owner, "ill")
    task_id = await _create_task(client, owner, project, "ill")

    # TODO 起步：跨级 / 同状态均非法
    for target in ("REVIEW", "DONE", "TODO"):
        assert await _transition(client, owner, task_id, target) == 409
        assert await _db_task_status(task_id) == "TODO"

    # 推进到 DONE 后：回退与任何出边全拒
    for step in ("IN_PROGRESS", "REVIEW", "DONE"):
        assert await _transition(client, owner, task_id, step) == 200
    for target in ("TODO", "IN_PROGRESS", "REVIEW", "CANCELLED", "DONE"):
        assert await _transition(client, owner, task_id, target) == 409
    assert await _db_task_status(task_id) == "DONE"


# --- 审计 ⇄ 状态一致性：每次成功流转恰好一条日志，链路严格衔接 ----------------


async def test_audit_log_sequence_matches_status_chain(client):
    """审计与状态一致：三次成功流转 → 三条日志，old/new 严格衔接。"""
    owner = await _make_user("owner4", ["admin"])
    project = await _make_project(owner, "seq")
    task_id = await _create_task(client, owner, project, "seq")

    for step in ("IN_PROGRESS", "REVIEW", "DONE"):
        assert await _transition(client, owner, task_id, step) == 200

    logs = await _db_logs(task_id)
    assert len(logs) == 3
    expected = [
        ("TODO", "IN_PROGRESS"),
        ("IN_PROGRESS", "REVIEW"),
        ("REVIEW", "DONE"),
    ]
    for log, (old, new) in zip(logs, expected):
        assert log.action == "task:transition"
        assert log.payload == {"old_status": old, "new_status": new}
        assert log.user_id == owner.id


async def test_rejected_transition_writes_no_log(client):
    """被拒流转不产生审计日志（失败动作不落审计）。"""
    owner = await _make_user("owner5", ["admin"])
    project = await _make_project(owner, "rej")
    task_id = await _create_task(client, owner, project, "rej")

    assert await _transition(client, owner, task_id, "DONE") == 409
    assert await _transition(client, owner, task_id, "TODO") == 409

    assert await _db_logs(task_id) == []

    # 合法流转后恰好只有这一条
    assert await _transition(client, owner, task_id, "IN_PROGRESS") == 200
    logs = await _db_logs(task_id)
    assert len(logs) == 1
    assert logs[0].payload == {"old_status": "TODO", "new_status": "IN_PROGRESS"}


# --- §55.3 事务原子性：状态变更与写日志同事务 ---------------------------------


async def test_transition_atomic_rollback_when_log_write_fails(
    client, monkeypatch
):
    """§55.3：写 OperationLog 失败 → 状态变更一并回滚（同事务）。

    monkeypatch 让 ``write_operation_log`` 在 flush 时抛异常——模拟审计写入
    失败。断言任务状态**未被提交**（仍 TODO）且库中零日志，证明
    「状态变更 + 写日志 + 提交」在同一事务内，任一环节失败整体回滚。
    """
    owner = await _make_user("owner6", ["admin"])
    project = await _make_project(owner, "atomic")
    task_id = await _create_task(client, owner, project, "atomic")

    from app.services import task as task_service

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated audit write failure")

    # task 模块以 `from ... import write_operation_log` 绑定到自己的命名空间，
    # 必须 patch 该模块内引用（patch operation_log 模块的同名符号不会生效）。
    monkeypatch.setattr(task_service, "write_operation_log", _boom)

    with pytest.raises(RuntimeError, match="simulated audit write failure"):
        await _transition(client, owner, task_id, "IN_PROGRESS")

    # 事务未提交：状态与日志都无残留
    assert await _db_task_status(task_id) == "TODO"
    assert await _db_logs(task_id) == []
