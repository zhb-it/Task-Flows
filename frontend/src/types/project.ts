/**
 * 项目类型（前端规格 §16 / §17 / §18 / §19）。
 *
 * 对齐 `app/schemas/project.py`：
 *
 * - `ProjectRead`：`{id, name, description, team_id, owner_id, created_at, updated_at}`
 *   —— **没有** `status` 字段，也没有成员数 / 任务数 / 进度字段。
 * - `ProjectCreate`：`{team_id, name, description?}`（不含 `owner_id`，创建者恒为调用者）。
 * - `ProjectUpdate`：全字段可选，部分更新。
 *
 * 规格 §16.1 卡片里的「成员：12 / 任务：56 / 78%」与「状态筛选」后端都不提供
 * （跨项目统计端点与 project.status 均不存在），前端不对这些做伪造，统一降级
 * （见 views/project/ProjectList.vue 顶部 `el-alert` 与 docs/FRONTEND_API_MAPPING.md）。
 *
 * 字段名保持后端 snake_case（规格 §37），不做驼峰转换。
 */

/** `GET /api/v1/projects` 列表项 / `GET /api/v1/projects/{id}` 详情。 */
export interface Project {
  id: number
  name: string
  description: string | null
  team_id: number
  owner_id: number
  created_at: string
  updated_at: string
}

/** `POST /api/v1/projects` 请求体。 */
export interface ProjectCreate {
  team_id: number
  name: string
  description?: string | null
}

/** `PATCH /api/v1/projects/{id}` 请求体（全字段可选）。 */
export interface ProjectUpdate {
  name?: string | null
  description?: string | null
}
