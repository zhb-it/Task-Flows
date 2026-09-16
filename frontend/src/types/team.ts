/**
 * 团队类型（前端规格 §12 / §13 / §14 / §15）。
 *
 * 对齐 `app/schemas/team.py`：
 *
 * - `TeamRead`：`{id, name, description, owner_id, created_at, updated_at}`
 * - `TeamMemberRead`：`{id, team_id, user_id, username, role, joined_at}`
 *   —— 注意**没有 email 字段**，规格 §14 表格里的「邮箱」列后端不返回，前端不伪造。
 *
 * 字段名保持后端 snake_case（规格 §37 / docs/FRONTEND_API_MAPPING.md §5-2），
 * 不做驼峰转换——转换漏一个字段就是静默 bug。
 */

/** 团队角色（小写，来自 `TeamRole` 枚举名）。 */
export type TeamRole = 'owner' | 'admin' | 'member'

/** `GET /api/v1/teams` 列表项 / `GET /api/v1/teams/{id}` 详情。 */
export interface Team {
  id: number
  name: string
  description: string | null
  owner_id: number
  created_at: string
  updated_at: string
}

/** `POST /api/v1/teams` 请求体。 */
export interface TeamCreate {
  name: string
  description?: string | null
}

/** `PATCH /api/v1/teams/{id}` 请求体（全字段可选，部分更新）。 */
export interface TeamUpdate {
  name?: string | null
  description?: string | null
}

/** `POST /api/v1/teams/{id}/members` 请求体（按 user_id 邀请，非邮箱）。 */
export interface TeamMemberInvite {
  user_id: number
  /** 仅 admin / member；传 owner 后端 422（owner 只能经创建/转让获得）。 */
  role?: 'admin' | 'member'
}

/** `GET /api/v1/teams/{id}/members` 列表项。 */
export interface TeamMember {
  id: number
  team_id: number
  user_id: number
  username: string
  role: TeamRole
  joined_at: string
}
