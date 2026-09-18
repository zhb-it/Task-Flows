"""User schemas.

`UserRead` deliberately omits `password_hash` (project rule §5: API responses
must never expose the password hash). `UserCreate` carries the plain `password`
field as the inbound contract for registration (TASK-015); the CRUD layer only
ever persists the already-hashed value, so this schema is never persisted as-is.

TASK-082/083 adds the RBAC admin contracts: roles are exchanged as **name**
strings (the seed guarantees `admin` / `member` exist; names are stable and
human-readable, ids are not part of any contract).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserBase(BaseModel):
    username: str
    email: str


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserWithRolesRead(UserRead):
    """`UserRead` + 该用户的角色名列表（GET /users 列表用）。"""

    roles: list[str] = []


class UserRolesRead(BaseModel):
    """GET/PUT `/users/{user_id}/roles` 的契约体。"""

    user_id: int
    roles: list[str]


class RoleNamesUpdate(BaseModel):
    """PUT `/users/{user_id}/roles` 的请求体：全量替换语义（PUT，非 patch）。"""

    roles: list[str] = Field(max_length=50)


class MePermissionsRead(BaseModel):
    """GET `/users/me/permissions`：当前用户的有效权限名集合（去重、有序）。"""

    permissions: list[str]


# --- 个人工作台聚合（TASK-129，规格 §61.6「个人视图」+「统计」） ---------


class RecentProjectRead(BaseModel):
    """工作台「最近项目」卡片的一项（只带前端跳转与展示所需的最小字段）。"""

    id: int
    name: str
    team_id: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MyTaskSummary(BaseModel):
    """「我负责」的任务口径（分母：可见项目 ∩ 分配给我）。

    - ``assigned_open``：未完成且未取消（``TODO`` / ``IN_PROGRESS`` /
      ``REVIEW``）——工作台的「我的待办」。
    - ``overdue``：``assigned_open`` 中 ``due_at`` 已过期的**子集**。
    - ``completed_this_week``：状态为 ``DONE`` 且 ``updated_at`` 在本周内
      （UTC 周一起算；用 ``updated_at`` 近似完成时刻，口径全文见
      `app/services/overview.py` 模块文档）。
    """

    assigned_open: int = 0
    overdue: int = 0
    completed_this_week: int = 0


class TaskStatusSummary(BaseModel):
    """可见项目下全部任务的状态分布（团队概况口径，非「我的」口径）。"""

    TODO: int = 0
    IN_PROGRESS: int = 0
    REVIEW: int = 0
    DONE: int = 0
    CANCELLED: int = 0
    total: int = 0


class MeOverviewRead(BaseModel):
    """GET `/users/me/overview`：个人工作台聚合（一次请求取齐首页所需）。

    口径（分母定义）写在 `app/services/overview.py` 的模块文档里，前端与
    `docs/API_CONTRACT.md` 必须沿用同一套说法，不得各自解释。

    字段语义：

    - ``projects``：可见项目数（所属团队下的项目）。
    - ``unread_notifications``：未读通知条数。
    - ``my_tasks`` / ``task_status``：见各自的模型文档。
    - ``recent_projects``：按 ``updated_at`` 倒序的最新项目。
    - ``generated_at`` / ``week_start``：聚合时刻与本周起点（均 UTC）。
      返回它们是为了让前端能原样展示「统计口径」，而不是把 UTC 周界藏在
      后端——前端不该自己猜周起点。
    """

    generated_at: datetime
    week_start: datetime
    projects: int = 0
    unread_notifications: int = 0
    my_tasks: MyTaskSummary
    task_status: TaskStatusSummary
    recent_projects: list[RecentProjectRead] = []
