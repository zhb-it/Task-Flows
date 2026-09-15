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
