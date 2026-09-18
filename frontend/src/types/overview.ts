/**
 * 个人工作台聚合类型（TASK-129，规格 §61.6「个人视图」+「统计」）。
 *
 * 逐一对齐 `app/schemas/user.py::MeOverviewRead` 与
 * `app/services/overview.py` 的返回字典——**字段名不做驼峰改写**，后端用
 * 下划线命名，前端沿用同名字段，避免多一层映射带来的「改了后端忘改前端」。
 *
 * 口径（分母定义）以 `app/services/overview.py` 的模块文档为准：
 * - 可见范围 = 当前用户所属团队下的项目；
 * - `my_tasks` = 可见范围 ∩ 分配给我；
 * - `overdue` 是 `assigned_open` 的**子集**；
 * - `completed_this_week` 用 `updated_at` 近似完成时刻，周起点为 UTC 周一
 *   00:00（后端回传 `week_start`，前端不得自己推算）。
 */

/** 「我负责」的任务口径。 */
export interface MyTaskSummary {
  /** 分配给我、且未进入终态（TODO / IN_PROGRESS / REVIEW）。 */
  assigned_open: number
  /** `assigned_open` 中 `due_at` 已过期的子集。 */
  overdue: number
  /** 状态为 DONE 且 `updated_at` 在本周内。 */
  completed_this_week: number
}

/** 可见项目下**全部**任务的状态分布（团队概况口径，非「我的」口径）。 */
export interface TaskStatusSummary {
  TODO: number
  IN_PROGRESS: number
  REVIEW: number
  DONE: number
  CANCELLED: number
  total: number
}

/** 工作台「最近项目」卡片的一项。 */
export interface RecentProject {
  id: number
  name: string
  team_id: number
  /** ISO 8601 字符串（Pydantic `datetime` 序列化结果）。 */
  updated_at: string
}

/** `GET /api/v1/users/me/overview` 的 `data`。 */
export interface MeOverview {
  /** 聚合时刻（UTC）。 */
  generated_at: string
  /** 本周起点（UTC 周一 00:00）——前端展示「本周」边界时必须用它。 */
  week_start: string
  /** 我加入的团队数（TASK-130 新增）。与 `projects` 不同：刚建团队还没建项目时为 `1 / 0`。 */
  teams: number
  /** 可见项目数。 */
  projects: number
  /** 未读通知条数。 */
  unread_notifications: number
  my_tasks: MyTaskSummary
  task_status: TaskStatusSummary
  recent_projects: RecentProject[]
}
