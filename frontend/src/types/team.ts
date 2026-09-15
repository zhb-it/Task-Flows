/**
 * 团队类型（前端规格 §13 / §15）。
 *
 * 对齐 `app/schemas/team.py::TeamRead`：
 * `{id, name, description, owner_id, created_at, updated_at}`。
 * 字段名保持后端 snake_case（规格 §37 / docs/FRONTEND_API_MAPPING.md §5-2），
 * 不做驼峰转换——转换漏一个字段就是静默 bug。
 */

/** `GET /api/v1/teams` 列表项。 */
export interface Team {
  id: number
  name: string
  description: string | null
  owner_id: number
  created_at: string
  updated_at: string
}
