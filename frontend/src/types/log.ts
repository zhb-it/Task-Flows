/**
 * 操作日志类型（前端规格 §44）。
 *
 * 对齐 `app/schemas/operation_log.py::OperationLogRead`：
 * `{id, user_id, resource_type, resource_id, action, payload, created_at}`。
 *
 * ⚠ `payload` 是不定结构（不同 action 字段随业务演进，schema 不约束形状），
 * 前端按 `Record<string, unknown>` 接收，展示时要按 `action` 做类型收窄，
 * 不能假定里面有某个固定字段。
 */

/** `GET /api/v1/logs` 列表项。 */
export interface OperationLog {
  id: number
  user_id: number
  resource_type: string
  resource_id: number
  action: string
  payload: Record<string, unknown>
  created_at: string
}

/**
 * 后端当前实际写入的 action（审计埋点逐业务接入，前端已知三种）：
 * - `task:transition`（`app/services/task.py`，payload `{old_status, new_status}`）
 * - `comment:delete`（`app/services/comment.py`，payload `{task_id, comment_id}`）
 * - `attachment:delete`（`app/services/attachment.py`，payload `{task_id, attachment_id, filename}`）
 *
 * 后续后端接入新埋点时此处同步补充；未知 action 原样展示、payload 走 JSON 兜底。
 */
export type OperationLogAction = 'task:transition' | 'comment:delete' | 'attachment:delete'

/** action 中文标签。 */
export const OPERATION_ACTION_LABELS: Record<OperationLogAction, string> = {
  'task:transition': '任务状态流转',
  'comment:delete': '删除评论',
  'attachment:delete': '删除附件',
}

/** 未知 action 的展示兜底：原样返回 action 字符串。 */
export function operationActionLabel(action: string): string {
  return (OPERATION_ACTION_LABELS as Record<string, string>)[action] ?? action
}

/** 资源类型中文标签（后端当前只有 task / comment / attachment 三种）。 */
export function resourceTypeLabel(resourceType: string): string {
  const map: Record<string, string> = {
    task: '任务',
    comment: '评论',
    attachment: '附件',
  }
  return map[resourceType] ?? resourceType
}
