/**
 * 任务类型（前端规格 §21 / §22 / §20 / §23 / §24 / §25 / §26 / §27）。
 *
 * 对齐 `app/schemas/task.py` 与 `app/models/task.py`：
 *
 * - `TaskRead`：`{id, project_id, title, description, status, priority,
 *   creator_id, due_at, created_at, updated_at, assignees}`（assignees 内嵌）。
 * - `TaskCreate`：不含 `status`（新任务恒为 TODO，状态流转只能走 transition 端点）、
 *   不含 `creator_id`/`assignee`（创建者恒为调用者，负责人通过 `POST /tasks/{id}/assignees` 添加）。
 * - `TaskUpdate`：全字段可选，且**不含 status**（更新走 transition）。
 *
 * 状态 / 优先级枚举与中文标签集中在此（规格 §22：「前端必须统一使用枚举，
 * 禁止在不同页面自行定义状态文本」）。后端为 5 态（含 CANCELLED）与 4 档优先级
 * （含 URGENT）—— 规格 §21/§22 图示仅列 4 态 / 3 档，这里以真实契约为准补齐。
 *
 * 字段名保持后端 snake_case（规格 §37），不做驼峰转换。
 */

/** 任务状态（对齐 `app/models/task.py::TaskStatus`，字面字符串与 DB CHECK 一致）。 */
export type TaskStatus = 'TODO' | 'IN_PROGRESS' | 'REVIEW' | 'DONE' | 'CANCELLED'

/** 任务优先级（对齐 `app/models/task.py::TaskPriority`）。 */
export type TaskPriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'URGENT'

/** 列表排序字段（对齐 `app/schemas/task.py::TaskSortField`）。 */
export type TaskSortField = 'id' | 'created_at' | 'due_at' | 'priority'

/** 排序方向（对齐 `app/schemas/task.py::TaskSortOrder`）。 */
export type TaskSortOrder = 'asc' | 'desc'

/** 状态中文标签（规格 §21）。 */
export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  TODO: '待处理',
  IN_PROGRESS: '进行中',
  REVIEW: '待审核',
  DONE: '已完成',
  CANCELLED: '已取消',
}

/** 优先级中文标签（规格 §22）。 */
export const TASK_PRIORITY_LABELS: Record<TaskPriority, string> = {
  LOW: '低',
  MEDIUM: '中',
  HIGH: '高',
  URGENT: '紧急',
}

/** 看板列顺序（含 CANCELLED：规格 §23 图示仅列 4 列，但后端数据为 5 态，不隐藏）。 */
export const TASK_STATUS_ORDER: TaskStatus[] = [
  'TODO',
  'IN_PROGRESS',
  'REVIEW',
  'DONE',
  'CANCELLED',
]

/** 优先级下拉顺序（高 → 低）。 */
export const TASK_PRIORITY_ORDER: TaskPriority[] = ['URGENT', 'HIGH', 'MEDIUM', 'LOW']

/**
 * 合法状态流转表（对齐 `app/services/state_machine.py::TRANSITIONS`）。
 *
 * 仅用于前端展示「可流转目标」与看板拖拽白名单；规格 §24 明确要求最终以
 * 后端为准（后端还会叠加 `task:transition` 功能级权限，普通成员无此权限 → 403，
 * 见 `docs/FRONTEND_API_MAPPING.md` §4-D11）。因此本表只做「前端友好提示」，
 * 绝不替代后端校验。
 */
export const TASK_TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  TODO: ['IN_PROGRESS', 'CANCELLED'],
  IN_PROGRESS: ['REVIEW', 'CANCELLED'],
  REVIEW: ['DONE', 'CANCELLED'],
  DONE: [],
  CANCELLED: [],
}

/** 任务负责人（TaskRead.assignees 内嵌项，对齐 `TaskAssigneeRead`）。 */
export interface TaskAssignee {
  user_id: number
  username: string
  assigned_at: string
}

/** 任务（对齐 `TaskRead`）。 */
export interface Task {
  id: number
  project_id: number
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  creator_id: number
  due_at: string | null
  created_at: string
  updated_at: string
  assignees: TaskAssignee[]
}

/** `POST /tasks` 请求体（对齐 `TaskCreate`；不含 status）。 */
export interface TaskCreate {
  project_id: number
  title: string
  description?: string | null
  priority?: TaskPriority
  due_at?: string | null
}

/** `PATCH /tasks/{id}` 请求体（对齐 `TaskUpdate`；不含 status）。 */
export interface TaskUpdate {
  title?: string | null
  description?: string | null
  priority?: TaskPriority
  due_at?: string | null
}

/** `POST /tasks/{id}/transition` 请求体。 */
export interface TaskTransition {
  to_status: TaskStatus
}

/** `GET /tasks` 查询参数（`project_id` 必填，对齐 `app/api/v1/tasks.py`）。 */
export interface TaskListParams {
  project_id: number
  status?: TaskStatus
  priority?: TaskPriority
  keyword?: string
  assignee_id?: number
  skip?: number
  limit?: number
  sort?: TaskSortField
  order?: TaskSortOrder
}
