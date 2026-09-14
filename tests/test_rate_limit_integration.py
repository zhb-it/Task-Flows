"""TASK-047：限流整合验收测试（纯测试任务，未改应用代码）。

定位与 TASK-040 / TASK-044 一致——**不是**重复 TASK-046 的细粒度断言，而是补上
「限流与系统其它部分放在一起才暴露」的跨模块验收链路：

- **限流 × 认证**（TESTING 优先级 #1）：登录暴力破解是否被挡、限流会不会泄露
  账号是否存在、匿名洪水是否被挡在认证层之前、换 IP 能否绕过 user 维度；
- **限流 × 业务副作用**（优先级 #3）：被限流的**写**请求是否真的没执行、被限流
  的请求会不会污染审计日志；
- **限流 × 运维**（TASK-045 的 Key 约定在第 046 上的交叉）：限流键是否留在自己
  的命名空间、是否有 TTL、会不会永久驻留；
- **限流 × 错误契约**（§26 / §48）：429 与 401/403/404 用同一个信封，且不泄露
  内部标识。

已覆盖面（不在此重复）：`tests/test_rate_limit.py`（TASK-046，22 项）已覆盖
Lua 语义、中间件维度判定、429 信封与 `Retry-After`、fail-open、延迟上界。本文件
只测那些**必须借助真实用户 / 真实业务端点 / 真实审计表**才能观察到的性质。

方法论同 TASK-043/044：先跑探测脚本拿到真实观测，再据此写断言。本轮探测确认
限流在十个交叉面上均行为正确（未发现缺陷），因此本文件的价值是**固化契约**
而不是修 bug——后续任何重构（例如「顺手改成按端点限流」「顺手给限流加审计」）
都会立刻失败。
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.redis_keys import KEY_PREFIX, PURPOSE_RATE_LIMIT
from app.core.security import create_access_token
from app.crud.project import create_project
from app.crud.role import assign_role_to_user, get_role_by_name
from app.crud.user import create_user
from app.db import redis as redis_db
from app.db.session import get_db
from app.main import app
from app.models.operation_log import OperationLog
from app.models.project import Project
from app.models.task import Task
from app.models.team import Team
from app.models.user import User
from app.schemas.team import TeamCreate
from app.services.team import create_team as create_team_service

#: 宿主映射端口（compose 中 6389:6379 / 5433:5432）。
REDIS_URL = "redis://127.0.0.1:6389/0"
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

#: 默认额度刻意取小值，让「超限」在几次请求内发生，测试不依赖长窗口或 sleep。
DEFAULT_LIMIT = 3

_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(_engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"rlflow_{RUN_TOKEN}_{tag}"


def _bearer(user_id: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _iso_ip() -> str:
    """每个用例一个独占 IP，避免 IP 维度额度在用例间泄漏（TASK-046 的教训）。"""
    return f"10.77.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _Env:
    """限流测试环境：独占 IP 的客户端 + Redis 键精确回收。"""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self._before: set[str] = set()
        self._new: set[str] = set()
        self.users: list[User] = []

    async def snapshot(self) -> None:
        self._before = {k async for k in self.redis.scan_iter(match=f"{KEY_PREFIX}:*", count=500)}

    def new_keys(self) -> set[str]:
        """本次用例新产生的键（用于「限流键不越界」的断言）。"""
        return self._new

    async def refresh_keys(self) -> None:
        now = {k async for k in self.redis.scan_iter(match=f"{KEY_PREFIX}:*", count=500)}
        self._new = now - self._before

    def client(self, ip: str | None = None) -> AsyncClient:
        transport = ASGITransport(app=app, client=(ip or _iso_ip(), 0))
        return AsyncClient(transport=transport, base_url="http://testserver")

    async def make_user(self, tag: str, role_names: list[str] | None = None) -> User:
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
        self.users.append(user)
        return user

    async def make_team_project(self, owner: User, tag: str) -> tuple[Team, Project]:
        async with SessionFactory() as session:
            team = await create_team_service(
                session, owner, TeamCreate(name=f"rlflow team {RUN_TOKEN} {tag}")
            )
            project = await create_project(
                session,
                name=f"rlflow proj {RUN_TOKEN} {tag}",
                description=None,
                team_id=team.id,
                owner_id=owner.id,
            )
            await session.commit()
            await session.refresh(team)
            await session.refresh(project)
            return team, project


@pytest_asyncio.fixture
async def env():
    """限流开启 + 真实 Redis + 真实开发库；结束时精确回收本次产生的键与数据。"""
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await redis.ping()
    except Exception as exc:  # pragma: no cover - 环境缺失时跳过
        await redis.aclose()
        pytest.skip(f"Redis not reachable at {REDIS_URL}: {exc}")

    original = redis_db._client
    redis_db._client = redis
    app.dependency_overrides[get_db] = _override_get_db
    e = _Env(redis)
    await e.snapshot()
    try:
        yield e
    finally:
        # 只删本次用例新增的键——不 FLUSHDB（会误删他人数据）
        await e.refresh_keys()
        for key in e._new:
            await redis.delete(key)
        app.dependency_overrides.pop(get_db, None)
        await redis.aclose()
        redis_db._client = original


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_db():
    """审计日志 → 任务 → 项目 → 团队 → 用户（RESTRICT 全链精确拆除）。"""
    yield
    async with SessionFactory() as session:
        await session.execute(
            delete(OperationLog).where(
                OperationLog.user_id.in_(
                    select(User.id).where(User.username.like(f"rlflow_{RUN_TOKEN}%"))
                )
            )
        )
        await session.execute(delete(Task).where(Task.title.like(f"rlflow task {RUN_TOKEN}%")))
        await session.execute(
            delete(Project).where(Project.name.like(f"rlflow proj {RUN_TOKEN}%"))
        )
        await session.execute(delete(Team).where(Team.name.like(f"rlflow team {RUN_TOKEN}%")))
        await session.execute(delete(User).where(User.username.like(f"rlflow_{RUN_TOKEN}%")))
        await session.commit()


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    yield
    get_settings.cache_clear()


def _enable(monkeypatch, *, limit: int = DEFAULT_LIMIT, window: int = 60) -> None:
    """conftest 默认关闭限流，这里显式打开（DECISIONS 021）。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_requests", limit)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", window)


async def _logs_for(user_id: int) -> list[OperationLog]:
    async with SessionFactory() as session:
        result = await session.execute(
            select(OperationLog).where(OperationLog.user_id == user_id)
        )
        return list(result.scalars().all())


async def _task_count() -> int:
    async with SessionFactory() as session:
        result = await session.execute(
            select(Task).where(Task.title.like(f"rlflow task {RUN_TOKEN}%"))
        )
        return len(list(result.scalars().all()))


# ===========================================================================
# 1. 限流 × 认证（TESTING 优先级 #1）
# ===========================================================================


async def test_login_brute_force_is_throttled(env, monkeypatch):
    """连续失败的登录被限流挡住（§安全清单「暴力破解」的落位点）。

    §22 未给登录单独配额，但限流中间件覆盖 `/api/v1` 全部端点，因此**登录天然
    受保护**：同一个 IP 在额度用尽后连「尝试」都发不出去，这是防暴力破解的第一道
    闸门（密码哈希强度是第二道）。
    """
    _enable(monkeypatch, limit=3)
    victim = await env.make_user("brute", ["admin"])

    async with env.client() as c:
        codes = []
        for _ in range(5):
            r = await c.post(
                "/api/v1/auth/login",
                json={"username": victim.username, "password": "definitely-wrong"},
            )
            codes.append(r.status_code)
    assert codes == [401, 401, 401, 429, 429], codes


async def test_throttling_does_not_reveal_account_existence(env, monkeypatch):
    """限流前后都不泄露「账号是否存在」。

    未超限时：存在的用户 + 错密码 与 不存在的用户 都是 401 且**文案一致**
    （认证层契约，此处只固化它不被限流改变）。超限后：两者都是 429 且文案一致。
    两者合起来说明攻击者无法用 401/429 的差异枚举账号。
    """
    _enable(monkeypatch, limit=3)
    existing = await env.make_user("exists", ["admin"])

    async def _probe(username: str) -> tuple[list[int], list[str]]:
        codes, details = [], []
        async with env.client() as c:
            for _ in range(4):
                r = await c.post(
                    "/api/v1/auth/login",
                    json={"username": username, "password": "wrong"},
                )
                codes.append(r.status_code)
                details.append(r.json().get("detail", ""))
        return codes, details

    real_codes, real_details = await _probe(existing.username)
    fake_codes, fake_details = await _probe("no-such-user-" + RUN_TOKEN)

    assert real_codes == fake_codes == [401, 401, 401, 429]
    assert real_details[:3] == fake_details[:3], "未超限时账号存在性不可区分"
    assert real_details[3] == fake_details[3], "超限后同样不可区分"


async def test_anonymous_flood_is_throttled_before_authentication(env, monkeypatch):
    """匿名洪水在**认证之前**被挡：429 先于 401。

    限流是中间件，认证是路由依赖，因此未认证的洪水同样吃配额——这正是想要的：
    否则攻击者只要不带 Token 就能无限打认证端点，限流形同虚设。
    """
    _enable(monkeypatch, limit=3)
    async with env.client() as c:
        codes = []
        for _ in range(5):
            r = await c.delete("/api/v1/tasks/999999")  # 写操作更能说明问题
            codes.append(r.status_code)
    assert codes == [401, 401, 401, 429, 429], codes


async def test_changing_ip_does_not_bypass_user_quota(env, monkeypatch):
    """换 IP 绕不过 user 维度限流（§22「IP / User」的安全价值所在）。

    已认证请求按 `sub` 取键，因此同一个用户换再多来源地址都落回同一个 ZSET。
    若这条退化成按 IP 计数，攻击者用一组代理就能把额度放大 N 倍。
    """
    _enable(monkeypatch, limit=3)
    user = await env.make_user("roam", ["admin"])

    codes = []
    for _ in range(5):
        async with env.client(_iso_ip()) as c:  # 每次请求换一个 IP
            r = await c.get("/api/v1/users/me", headers=_bearer(user.id))
            codes.append(r.status_code)
    assert codes == [200, 200, 200, 429, 429], codes


# ===========================================================================
# 2. 限流 × 业务副作用（TESTING 优先级 #3）
# ===========================================================================


async def test_throttled_write_requests_have_no_side_effects(env, monkeypatch):
    """被限流的**写**请求零落库——429 是真的挡住了执行，不是「先做再报错」。

    TASK-046 只断言了状态码是 429；这里断言**副作用**：库里的任务数恰好等于
    放行次数。若将来有人把限流改成「先执行后计数」或在 `call_next` 之后才判定，
    这里会立刻失败。
    """
    _enable(monkeypatch, limit=3)
    owner = await env.make_user("side", ["admin"])
    _, project = await env.make_team_project(owner, "side")

    async with env.client() as c:
        codes = []
        for i in range(5):
            r = await c.post(
                "/api/v1/tasks",
                headers=_bearer(owner.id),
                json={"project_id": project.id, "title": f"rlflow task {RUN_TOKEN} {i}"},
            )
            codes.append(r.status_code)
    assert codes == [201, 201, 201, 429, 429], codes
    assert await _task_count() == 3, "库中的任务数必须等于放行次数"


async def test_throttled_requests_do_not_write_operation_logs(env, monkeypatch):
    """被限流的请求不写审计日志——只有**真正执行**的业务才写（§15/§16 语义边界）。

    与 TASK-044 固化「创建评论 / 上传附件不写日志」同理：审计表记录的是发生过的
    业务动作。若限流也写日志，一次洪水就会把 `operation_logs` 灌满，反而淹没
    真正的审计线索；同时也会让人误以为那个动作真的执行了。
    """
    _enable(monkeypatch, limit=4)
    owner = await env.make_user("audit", ["admin"])
    _, project = await env.make_team_project(owner, "audit")

    async with env.client() as c:
        created = await c.post(
            "/api/v1/tasks",
            headers=_bearer(owner.id),
            json={"project_id": project.id, "title": f"rlflow task {RUN_TOKEN} audit"},
        )
        assert created.status_code == 201
        task_id = created.json()["data"]["id"]

        first = await c.post(
            f"/api/v1/tasks/{task_id}/transition",
            headers=_bearer(owner.id),
            json={"to_status": "IN_PROGRESS"},
        )
        assert first.status_code == 200

        # 此后额度耗尽（已用 2/4），再打 6 次：其中 2 次会到达业务层（409 重复流转），
        # 其余全部 429。
        throttled = []
        for _ in range(6):
            r = await c.post(
                f"/api/v1/tasks/{task_id}/transition",
                headers=_bearer(owner.id),
                json={"to_status": "IN_PROGRESS"},
            )
            throttled.append(r.status_code)
    assert 429 in throttled, throttled

    # 只有那一次成功的流转留下了日志
    logs = await _logs_for(owner.id)
    assert [log.action for log in logs] == ["task:transition"], [log.action for log in logs]


async def test_quota_is_shared_across_all_api_endpoints(env, monkeypatch):
    """同一身份的额度在**所有** `/api/v1` 端点间共享（§22 一个身份一个 ZSET）。

    §22 的链路是 `IP / User → Redis ZSET`，没有端点维度，因此配额天然是全局的。
    这条断言把该语义钉住：将来若有人「顺手」改成按端点限流，语义就变了（同一
    用户可以对每个端点各打 60 次），必须是一个**有意识的决定**而不是重构副产物。
    """
    _enable(monkeypatch, limit=3)
    user = await env.make_user("shared", ["admin"])

    async with env.client() as c:
        a = await c.get("/api/v1/users/me", headers=_bearer(user.id))
        b = await c.get("/api/v1/teams", headers=_bearer(user.id))
        d = await c.get("/api/v1/users/me", headers=_bearer(user.id))
        # 换一个**没访问过**的端点，依然没额度
        e = await c.get("/api/v1/teams", headers=_bearer(user.id))
    assert [a.status_code, b.status_code, d.status_code] == [200, 200, 200]
    assert e.status_code == 429, "额度是身份级的，不因换端点而重置"


async def test_two_users_have_independent_quotas(env, monkeypatch):
    """两个用户的额度互相独立——同一 NAT / 同一 IP 后不会互相挤兑。

    这是 §22 选择「User 维度」而非只按 IP 的直接收益：按 IP 计数会让整个公司
    共用一份额度。
    """
    _enable(monkeypatch, limit=3)
    alice = await env.make_user("alice", ["admin"])
    bob = await env.make_user("bob", ["admin"])

    async with env.client() as c:
        alice_codes = [
            (await c.get("/api/v1/users/me", headers=_bearer(alice.id))).status_code
            for _ in range(4)
        ]
        # alice 已耗尽；bob 应当不受任何影响
        bob_codes = [
            (await c.get("/api/v1/users/me", headers=_bearer(bob.id))).status_code
            for _ in range(4)
        ]
    assert alice_codes == [200, 200, 200, 429], alice_codes
    assert bob_codes == [200, 200, 200, 429], bob_codes


async def test_concurrent_requests_from_two_users_respect_each_quota(env, monkeypatch):
    """并发下两个用户**各自**恰好放行 `limit` 次（原子性 × 隔离性同时成立）。

    TASK-046 的并发原子性用例只针对单个键；这里把它与多用户隔离叠加：20 个并发
    请求分属两个用户，若限流被击穿（判定/写入竞态）或维度串了（都落到同一把键），
    放行数都不会是 ``(3, 3)``。
    """
    _enable(monkeypatch, limit=3)
    alice = await env.make_user("calice", ["admin"])
    bob = await env.make_user("cbob", ["admin"])

    import asyncio

    async with env.client() as c:

        async def _burst(user_id: int) -> list[int]:
            results = await asyncio.gather(
                *[c.get("/api/v1/users/me", headers=_bearer(user_id)) for _ in range(10)]
            )
            return [r.status_code for r in results]

        alice_codes, bob_codes = await asyncio.gather(_burst(alice.id), _burst(bob.id))

    assert alice_codes.count(200) == 3, alice_codes
    assert bob_codes.count(200) == 3, bob_codes
    assert alice_codes.count(429) == 7 and bob_codes.count(429) == 7


# ===========================================================================
# 3. 限流 × 运维（TASK-045 的 Key 约定在第 046 上的交叉）
# ===========================================================================


async def test_rate_limit_keys_live_in_own_namespace_and_expire(env, monkeypatch):
    """限流只用 `taskflow:ratelimit:*`，且每个键都带 TTL（不永久驻留）。

    这是 TASK-045 的 Key 约定与 TASK-046 的交叉点：
    - **命名空间**：所有新键都在 `ratelimit` 用途段下，不会与将来的 `jwt` /
      `celery` 用途互相覆盖，也让 `SCAN taskflow:ratelimit:*` 成为安全的运维操作；
    - **TTL**：§22 第 5 步要求设过期时间。若哪天 TTL 漏了，被攻击产生的大量键会
      永久占住内存——这条断言会在那之前拦住。
    """
    _enable(monkeypatch, limit=2)
    user = await env.make_user("keys", ["admin"])

    async with env.client() as c:
        for _ in range(4):
            await c.get("/api/v1/users/me", headers=_bearer(user.id))
        await c.get("/api/v1/users/me")  # 再产生一个 IP 维度的键

    await env.refresh_keys()
    new_keys = env.new_keys()
    assert new_keys, "本次用例应至少产生一个限流键"

    prefix = f"{KEY_PREFIX}:{PURPOSE_RATE_LIMIT}:"
    offenders = [k for k in new_keys if not k.startswith(prefix)]
    assert not offenders, f"限流写出了约定命名空间之外的键：{offenders}"

    for key in new_keys:
        ttl = await env.redis.ttl(key)
        assert ttl is not None and ttl > 0, f"{key} 没有 TTL，会永久驻留"


async def test_unknown_paths_also_consume_quota(env, monkeypatch):
    """不存在的路径同样吃配额——否则可以用随机路径无限枚举/探测。

    中间件按**前缀**判定而非按已注册路由，因此 404 也计入。这是防盲打的性质：
    若只对存在的端点计数，攻击者扫路径就不受任何约束。
    """
    _enable(monkeypatch, limit=3)
    async with env.client() as c:
        codes = [
            (await c.get(f"/api/v1/no-such-resource-{i}")).status_code for i in range(5)
        ]
    assert codes == [404, 404, 404, 429, 429], codes


# ===========================================================================
# 4. 限流 × 错误契约（§26 / §48）
# ===========================================================================


async def test_throttled_response_leaks_no_internal_identifiers(env, monkeypatch):
    """429 响应不泄露内部标识（§48 敏感信息泄露）。

    响应体里出现 IP、user id、Redis key 或堆栈，等于把限流的实现细节（以及
    被限者的身份标识）交给攻击者——后者还可用于确认「某个 id 确实存在」。
    """
    _enable(monkeypatch, limit=1)
    user = await env.make_user("leak", ["admin"])
    ip = _iso_ip()

    async with env.client(ip) as c:
        await c.get("/api/v1/users/me", headers=_bearer(user.id))
        r = await c.get("/api/v1/users/me", headers=_bearer(user.id))

    assert r.status_code == 429
    body = r.text
    for secret in (str(user.id), ip, KEY_PREFIX, "Traceback"):
        assert secret not in body, f"429 响应体泄露了 {secret!r}: {body}"
    assert "Rate limit exceeded" in body


async def test_429_envelope_matches_other_client_error_envelopes(env, monkeypatch):
    """429 与 401/403/404 用同一个 `{"detail": ...}` 信封（§26）。

    前端要靠统一逻辑展示错误，任何一类给不同形状都会逼出特判。TASK-046 已验证
    429 自身的信封；这里把它和**其它**客户端错误的信封放在一起比对。
    """
    _enable(monkeypatch, limit=50)  # 先给足额度，避免收集过程中被打断
    admin = await env.make_user("env_admin", ["admin"])
    norole = await env.make_user("env_norole")  # 无角色 → 功能级 403

    bodies = {}
    async with env.client() as c:
        bodies[401] = (await c.get("/api/v1/users/me")).json()
        bodies[403] = (await c.get("/api/v1/teams", headers=_bearer(norole.id))).json()
        bodies[404] = (
            await c.get("/api/v1/teams/99999999", headers=_bearer(admin.id))
        ).json()

    # 换一个独占 IP 并把额度调到 1，取得 429
    monkeypatch.setattr(get_settings(), "rate_limit_requests", 1)
    async with env.client() as c:
        await c.get("/api/v1/users/me")
        r = await c.get("/api/v1/users/me")
    assert r.status_code == 429
    bodies[429] = r.json()

    assert set(bodies) == {401, 403, 404, 429}, f"未收集齐各类错误：{sorted(bodies)}"
    for code, body in bodies.items():
        assert set(body.keys()) == {"detail"}, f"{code} 的信封不一致：{body}"


async def test_allowed_requests_keep_business_result_and_quota_headers(env, monkeypatch):
    """放行的请求：业务结果正确 **且** 配额头齐全——限流不干扰业务。

    只断言「没被限流」是不够的：中间件改写响应的过程（加响应头）本身可能破坏
    业务响应。这里用一个 201 创建请求同时验证两件事。
    """
    _enable(monkeypatch, limit=10)
    owner = await env.make_user("passthru", ["admin"])
    _, project = await env.make_team_project(owner, "passthru")

    async with env.client() as c:
        r = await c.post(
            "/api/v1/tasks",
            headers=_bearer(owner.id),
            json={"project_id": project.id, "title": f"rlflow task {RUN_TOKEN} passthru"},
        )
    assert r.status_code == 201
    assert r.json()["data"]["title"].startswith("rlflow task")
    assert r.headers["X-RateLimit-Limit"] == "10"
    assert r.headers["X-RateLimit-Remaining"] == "9"


async def test_disabling_rate_limit_restores_access_immediately(env, monkeypatch):
    """关掉限流后，已被限死的身份立刻恢复——开关是有效的逃生舱。

    限流一旦误伤（例如阈值配错、上游代理把所有流量变成一个来源地址），运维需要
    一个**不改代码、不重启**就能恢复的手段。`RATE_LIMIT_ENABLED=false` 就是它，
    这条断言保证该开关真的作用于判定路径而不只是个摆设。
    """
    _enable(monkeypatch, limit=1)
    user = await env.make_user("toggle", ["admin"])

    async with env.client() as c:
        assert (await c.get("/api/v1/users/me", headers=_bearer(user.id))).status_code == 200
        assert (await c.get("/api/v1/users/me", headers=_bearer(user.id))).status_code == 429

        monkeypatch.setattr(get_settings(), "rate_limit_enabled", False)
        codes = [
            (await c.get("/api/v1/users/me", headers=_bearer(user.id))).status_code
            for _ in range(3)
        ]
    assert codes == [200, 200, 200], codes
