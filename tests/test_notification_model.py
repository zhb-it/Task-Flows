"""TASK-052：Notification Model 检查项测试。

建模（Notification Model + 迁移 ``b7d2e9a4c6f8``）已在 TASK-049 提前完成
（DECISIONS 029 明确「TASK-052 届时为检查项」）。本 TASK 不产生新应用代码，
只把「建模完整性」固化为可回归测试——对齐 TASK-021/026/031 的 Model TASK 惯例
（那些 TASK 都含离线模型测试）。

源开发文档 §18 定义 notifications 七字段：id / user_id / type / title /
content / is_read / created_at。TASK-049 已按 §18 + 用户确认决策落地（见
``app/models/notification.py`` docstring 与 DECISIONS 029）；本文件逐一钉死：

1. 离线模型测试——只检查映射的列、类型、约束、索引、默认值、repr，不需要
   PostgreSQL（沿用 TASK-026 模式）。
2. 数据库约束集成测试——真实 PostgreSQL（宿主 5433）上验证 DB 级兜底行为：
   七字段 roundtrip、content 可空、is_read 默认 false、created_at 自动、
   user_id FK→users ON DELETE CASCADE（删用户清通知）、按接收人查询主访问
   路径。写入采用「本次运行唯一前缀 + teardown 精确删除」，删用户时通知行随
   级联清理（与 comments 同惯例）。
"""

from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.models import Notification, User

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"
RUN_TOKEN = "ntf_" + __import__("uuid").uuid4().hex[:10]

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


# --- 1. 离线模型测试 -----------------------------------------------------------


def test_notification_table_registered_on_metadata():
    assert "notifications" in Base.metadata.tables


def test_notification_tablename():
    assert Notification.__tablename__ == "notifications"


def test_notification_columns_match_spec_18():
    """§18 七字段（id / user_id / type / title / content / is_read / created_at）。"""
    assert set(Notification.__table__.columns.keys()) == {
        "id",
        "user_id",
        "type",
        "title",
        "content",
        "is_read",
        "created_at",
    }


def test_notification_id_is_bigint_primary_key():
    col = Notification.__table__.columns["id"]
    assert col.primary_key is True
    assert isinstance(col.type, BigInteger)


def test_notification_user_id_fk_cascade_with_index():
    col = Notification.__table__.columns["user_id"]
    assert col.nullable is False
    assert isinstance(col.type, BigInteger)
    fk = next(f for f in Notification.__table__.foreign_keys if f.parent is col)
    assert fk.column.table.name == "users"
    assert fk.ondelete == "CASCADE"
    # 单列索引 ix_notifications_user_id 存在
    assert any(
        ix.columns[0].name == "user_id" and len(ix.columns) == 1
        for ix in Notification.__table__.indexes
    )


def test_notification_type_and_title_not_null_strings():
    t = Notification.__table__.columns["type"]
    title = Notification.__table__.columns["title"]
    assert isinstance(t.type, String) and t.type.length == 50 and t.nullable is False
    assert isinstance(title.type, String) and title.type.length == 255 and title.nullable is False


def test_notification_content_nullable_text():
    """content 可空（TASK-049 决策：标题自足，正文允许缺省）。"""
    col = Notification.__table__.columns["content"]
    assert isinstance(col.type, Text)
    assert col.nullable is True


def test_notification_is_read_not_null_default_false():
    """is_read NOT NULL 默认 false（通知产生时必然未读，§18 语义）。"""
    col = Notification.__table__.columns["is_read"]
    assert isinstance(col.type, Boolean)
    assert col.nullable is False
    assert col.server_default is not None
    # server_default 指向 false（PostgreSQL 布尔字面）
    assert "false" in str(col.server_default.arg).lower()


def test_notification_created_at_timezone_aware_default_now():
    col = Notification.__table__.columns["created_at"]
    assert isinstance(col.type, DateTime)
    assert col.type.timezone is True
    assert col.nullable is False
    assert col.server_default is not None
    assert "now()" in str(col.server_default.arg).lower()


def test_notification_composite_index_user_created_at():
    """主访问路径 (user_id, created_at) 复合索引（§25.8 GET /notifications）。"""
    found = [
        ix
        for ix in Notification.__table__.indexes
        if [c.name for c in ix.columns] == ["user_id", "created_at"]
    ]
    assert len(found) == 1
    assert found[0].name == "ix_notifications_user_id_created_at"


def test_repr_contains_identity():
    assert "Notification" in repr(
        Notification(id=1, user_id=2, type="task_assigned", title="任务 X")
    )


# --- 2. 数据库约束集成测试 -------------------------------------------------------


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    yield
    # user_id FK CASCADE：删用户时通知行随级联清理，teardown 只需删前缀用户
    async with SessionFactory() as session:
        await session.execute(
            User.__table__.delete().where(
                User.username.like(f"{RUN_TOKEN}%")
            )
        )
        await session.commit()


async def _make_user(tag: str) -> User:
    async with SessionFactory() as session:
        user = User(
            username=f"{RUN_TOKEN}_{tag}",
            email=f"{RUN_TOKEN}_{tag}@example.com",
            password_hash="h",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _make_notification(
    user: User,
    type_: str,
    title: str,
    content=None,
) -> Notification:
    async with SessionFactory() as session:
        n = Notification(
            user_id=user.id, type=type_, title=title, content=content
        )
        session.add(n)
        await session.commit()
        await session.refresh(n)
        return n


async def test_insert_notification_seven_fields_roundtrip():
    user = await _make_user("round")
    n = await _make_notification(user, "task_assigned", "任务已分配", "详情内容")

    async with SessionFactory() as session:
        loaded = await session.get(Notification, n.id)
        assert loaded.user_id == user.id
        assert loaded.type == "task_assigned"
        assert loaded.title == "任务已分配"
        assert loaded.content == "详情内容"
        assert loaded.is_read is False
        assert isinstance(loaded.created_at, datetime)


async def test_content_nullable_omitted():
    """content 不传 → 插入成功且为 None（可空决策）。"""
    user = await _make_user("nullc")
    n = await _make_notification(user, "task_commented", "有人评论")

    async with SessionFactory() as session:
        loaded = await session.get(Notification, n.id)
        assert loaded.content is None
        assert loaded.is_read is False  # 默认值生效


async def test_is_read_and_created_at_have_db_defaults():
    user = await _make_user("def")
    n = await _make_notification(user, "team_invited", "团队邀请")

    async with SessionFactory() as session:
        loaded = await session.get(Notification, n.id)
        assert loaded.is_read is False
        assert loaded.created_at is not None


async def test_deleting_user_cascades_notifications():
    """user_id FK CASCADE：删用户 → 其通知行一并消失。"""
    user = await _make_user("casc")
    n = await _make_notification(user, "task_assigned", "任务已分配")

    async with SessionFactory() as session:
        assert await session.get(Notification, n.id) is not None
        u = await session.get(User, user.id)
        await session.delete(u)
        await session.commit()

    async with SessionFactory() as session:
        assert await session.get(Notification, n.id) is None


async def test_list_notifications_by_recipient_is_main_access_path():
    """§25.8 GET /notifications 按接收人 + 时间序查询的主访问路径。"""
    user = await _make_user("list")
    await _make_notification(user, "task_assigned", "分配")
    await _make_notification(user, "task_commented", "评论")

    async with SessionFactory() as session:
        rows = await session.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
        )
        rows = list(rows)
        assert len(rows) == 2
        assert all(r.user_id == user.id for r in rows)
        assert rows[0].created_at >= rows[1].created_at
