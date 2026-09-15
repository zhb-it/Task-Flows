/**
 * 项目类型（前端规格 §5 / §19）。
 *
 * 对齐 `app/schemas/project.py::ProjectRead`：
 * `{id, name, description, team_id, owner_id, created_at, updated_at}`。
 * 字段名保持后端 snake_case。
 */

/** `GET /api/v1/projects` 列表项。 */
export interface Project {
  id: number
  name: string
  description: string | null
  team_id: number
  owner_id: number
  created_at: string
  updated_at: string
}
