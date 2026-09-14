"""Task status machine rules (TASK-037).

规格 §5 / Decision 005：状态变更必须经过专用 transition API（TASK-038），
普通 PATCH 不允许触达 status。本模块承载状态机的纯规则层：

- 前进链严格线性：``TODO → IN_PROGRESS → REVIEW → DONE``（用户确认决策 1：
  不允许相邻回退，IN_PROGRESS→TODO、REVIEW→IN_PROGRESS 均非法）；
- 非终态任意 → CANCELLED（含 TODO/IN_PROGRESS/REVIEW）；
- 终态完全封死（决策 2）：``DONE`` / ``CANCELLED`` 没有任何出边——
  「任意状态 → CANCELLED」理解为任意**非终态**，与规格
  「DONE/CANCELLED 不允许继续流转」无矛盾；
- 非法流转（含同状态重复流转，如 TODO→TODO）→ ``ConflictError``(409)
  （决策 3），由 TASK-038 transition API 消费呈现。

本模块不依赖数据库/Session，可离线单测；error type 用 core 的
``ConflictError``，HTTP 语义由全局异常处理器统一渲染。
"""

from app.core.exceptions import ConflictError
from app.models.task import TaskStatus

#: 合法流转表：from -> 允许的 to 集合。终态（DONE/CANCELLED）无出边。
TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.TODO: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.REVIEW, TaskStatus.CANCELLED}),
    TaskStatus.REVIEW: frozenset({TaskStatus.DONE, TaskStatus.CANCELLED}),
    TaskStatus.DONE: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

#: 终态集合（无出边）。
TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.DONE, TaskStatus.CANCELLED}
)

INVALID_TRANSITION = "Invalid status transition"


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    """当前状态是否允许流转到目标状态（纯查询，不抛异常）。"""
    return target in TRANSITIONS[current]


def validate_transition(current: TaskStatus, target: TaskStatus) -> None:
    """校验一次状态流转；非法 → ``ConflictError``(409)。

    同状态重复流转（current == target）同样视为非法——流转必须真实
    改变状态，幂等语义由 TASK-038 API 层决定是否上抛前拦截。
    """
    if not can_transition(current, target):
        raise ConflictError(INVALID_TRANSITION)


def allowed_targets(current: TaskStatus) -> frozenset[TaskStatus]:
    """当前状态的合法目标集合（前端渲染可用操作/看板拖拽白名单）。"""
    return TRANSITIONS[current]
