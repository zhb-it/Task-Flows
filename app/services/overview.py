"""个人工作台聚合服务（TASK-129，规格 §61.6「个人视图」+「统计」）。

规格依据（开发文档 §61.6）：

- **个人视图（新增）**：提供跨项目的「我的任务」与工作台聚合。
- **统计（新增）**：项目与团队提供真实的任务统计与进度口径（**分母定义必须写明**）。

本模块只做**读聚合**（无写路径），因此不需要事务边界——与项目规则 §4
「写路径的事务边界在 Service 层」不冲突。

## 口径（分母定义，前端与文档必须沿用）

**可见项目** = 当前用户作为 `team_members` 成员所属团队下的全部项目
（沿用 `crud.project.list_projects_for_user` 的可见性判定，即
PROJECT_SPEC §5「用户只能访问其所属团队链路下的资源」）。租户隔离由
`TenantScoped` + RLS 兜底自动生效（TASK-094/095），本模块不重复加条件。

- `projects`：可见项目数。
- `task_status.*`：可见项目下**全部任务**按状态分档计数；`total` 为其合计
  ——这是「团队概况」口径（前端 Dashboard 顶部数据卡片与状态分布图）。
- `my_tasks.*`：可见项目下**分配给我**的任务——这是「个人视图」口径。
  - `assigned_open`：状态属于未完成/未取消（`TODO` / `IN_PROGRESS` /
    `REVIEW`）。
  - `overdue`：`assigned_open` 中 `due_at` 早于当前时刻的子集（**是
    `assigned_open` 的子集，不是并列口径**）。
  - `completed_this_week`：状态为 `DONE` 且 `updated_at` 不早于本周一
    00:00:00 UTC。
- `unread_notifications`：当前用户收件箱中 `is_read = false` 的条数。
- `recent_projects`：可见项目中 `updated_at` 最新的若干个（默认 5）。

## 已知近似与边界（必须记录，不得静默）

1. **「本周完成」用 `updated_at` 近似完成时间**——`tasks` 表没有
   `completed_at` 列。可行性依据是状态机（TASK-037）：`DONE` 是终态，
   任务进入 `DONE` 后不能再流转，因此「最后一次更新」在绝大多数情况下
   就是「完成时刻」。残留误差：进入 `DONE` 之后又被普通 PATCH 修改标题
   等字段，会把完成时刻推后。若将来要求精确，需新增 `completed_at` 列
   （迁移 + 回填），届时应显式决策而非顺手改口径。
2. **周起点按 UTC**（`datetime.now(timezone.utc)` 往后退到本周一
   00:00）。全站时间口径目前统一为 UTC（令牌签发、维护任务同此），
   租户时区是 §61 待落地能力（TASK-099 附近），本模块不提前引入。
3. **聚合不缓存**：工作台要求「刚做完的事立刻可见」，缓存带来的陈旧感
   比这几条 `COUNT(*)` 的成本更伤体验；若将来可见项目规模增长到需要
   缓存，必须作为一次显式决策记录。
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, desc, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Exists

from app.models.notification import Notification
from app.models.project import Project
from app.models.task import OPEN_STATUSES, Task, TaskStatus
from app.models.task_assignee import TaskAssignee
from app.models.team_member import TeamMember
from app.models.user import User

#: 最近项目的默认返回条数（前端 Bento 卡片放得下的量）。
RECENT_PROJECT_LIMIT = 5


def _member_exists(user_id: int) -> Exists:
    """「该项目所属团队有 ``user_id`` 这个成员」的 EXISTS 谓词。

    绑定到外层查询的 ``projects``（未指定 FROM 的列引用由 SQLAlchemy
    自动关联到最近的外层 ``projects``），因此既可直接用作
    ``select(Project).where(...)`` 的过滤条件，也可嵌进子查询。
    """
    return exists(
        select(TeamMember.id).where(
            TeamMember.team_id == Project.team_id,
            TeamMember.user_id == user_id,
        )
    )


def _visible_project_ids(user_id: int) -> Select:
    """可见项目 id 子查询（自足：内层自带 ``projects`` FROM）。"""
    return select(Project.id).where(_member_exists(user_id))


def _week_start_utc(now: datetime) -> datetime:
    """``now`` 所在自然周的周一 00:00:00（UTC，周一起算）。"""
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_of_day - timedelta(days=start_of_day.weekday())


def _assigned_to(user_id: int) -> Exists:
    """「该任务分配给了 ``user_id``」的 EXISTS 谓词。

    选列用 ``task_id``：`task_assignees` 是复合主键 ``(task_id, user_id)``，
    **没有单列 ``id``**（规格 §5），EXISTS 只看行是否存在，选哪一列都一样。
    """
    return exists(
        select(TaskAssignee.task_id).where(
            TaskAssignee.task_id == Task.id,
            TaskAssignee.user_id == user_id,
        )
    )


def _empty_status_counts() -> dict[str, int]:
    return {str(s): 0 for s in TaskStatus}


async def get_my_overview(
    db: AsyncSession,
    user: User,
    *,
    recent_limit: int = RECENT_PROJECT_LIMIT,
    now: datetime | None = None,
) -> dict:
    """聚合当前用户的个人工作台数据。

    Args:
        db: 数据库会话。
        user: 当前登录用户（已由 `CurrentUser` 依赖校验过账号状态）。
        recent_limit: 最近项目返回条数。
        now: 注入的当前时刻（仅测试使用，用于固定「本周 / 逾期」边界）。

    Returns:
        与 `MeOverviewRead` 字段一一对应的原始字典（Router 负责校验与
        包装信封；本层不依赖 Schema，保持 Service 与 HTTP 契约解耦）。
    """
    moment = now or datetime.now(timezone.utc)
    week_start = _week_start_utc(moment)
    visible = _visible_project_ids(user.id)
    assigned = _assigned_to(user.id)

    projects = await db.scalar(
        select(func.count(Project.id)).where(_member_exists(user.id))
    )

    status_rows = (
        await db.execute(
            select(Task.status, func.count(Task.id))
            .where(Task.project_id.in_(visible))
            .group_by(Task.status)
        )
    ).all()
    counts = _empty_status_counts()
    for status, n in status_rows:
        counts[str(status)] = int(n)

    # 个人口径：可见项目 ∩ 分配给我。三个计数各自独立——`overdue` 是
    # `assigned_open` 的子集而非并列集合，分开查比在应用层做集合运算更
    # 直接，也让每个谓词都能命中既有索引。
    base_where = (Task.project_id.in_(visible), assigned)

    assigned_open = await db.scalar(
        select(func.count(Task.id)).where(*base_where, Task.status.in_(OPEN_STATUSES))
    )
    overdue = await db.scalar(
        select(func.count(Task.id)).where(
            *base_where,
            Task.status.in_(OPEN_STATUSES),
            Task.due_at.is_not(None),
            Task.due_at < moment,
        )
    )
    completed_this_week = await db.scalar(
        select(func.count(Task.id)).where(
            *base_where,
            Task.status == TaskStatus.DONE,
            Task.updated_at >= week_start,
        )
    )

    unread = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            Notification.is_read.is_(False),
        )
    )

    recent = (
        (
            await db.execute(
                select(Project)
                .where(_member_exists(user.id))
                .order_by(desc(Project.updated_at), desc(Project.id))
                .limit(recent_limit)
            )
        )
        .scalars()
        .all()
    )

    return {
        "generated_at": moment,
        "week_start": week_start,
        "projects": int(projects or 0),
        "unread_notifications": int(unread or 0),
        "my_tasks": {
            "assigned_open": int(assigned_open or 0),
            "overdue": int(overdue or 0),
            "completed_this_week": int(completed_this_week or 0),
        },
        "task_status": {
            **{k: int(v) for k, v in counts.items()},
            "total": int(sum(counts.values())),
        },
        "recent_projects": list(recent),
    }
