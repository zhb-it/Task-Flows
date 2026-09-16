/**
 * 团队 API（前端规格 §12 / §13 / §14 / §15）。
 *
 * 对齐 `app/api/v1/teams.py`：
 *
 * | 函数           | 方法   | 端点                                | 功能级权限   |
 * | -------------- | ------ | ----------------------------------- | ------------ |
 * | `listTeams`    | GET    | `/teams`                            | `team:read`  |
 * | `createTeam`   | POST   | `/teams`                            | `team:create`|
 * | `getTeam`      | GET    | `/teams/{team_id}`                  | `team:read`  |
 * | `updateTeam`   | PATCH  | `/teams/{team_id}`                  | `team:update`（OWNER）|
 * | `deleteTeam`   | DELETE | `/teams/{team_id}`                  | `team:delete`（OWNER）|
 * | `listMembers`  | GET    | `/teams/{team_id}/members`          | `team:read`  |
 * | `inviteMember` | POST   | `/teams/{team_id}/members`          | `team:invite`（OWNER/ADMIN）|
 * | `removeMember` | DELETE | `/teams/{team_id}/members/{user_id}`| `team:invite`|
 *
 * 列表端点用的是后端统一的 `skip` / `limit`（`limit <= 100`），响应是裸数组、
 * 没有 `total`（见 docs/FRONTEND_API_MAPPING.md §4-D3）。
 */

import { http } from '@/utils/request'
import type { PaginationParams } from '@/types/common'
import type { Team, TeamCreate, TeamUpdate, TeamMember, TeamMemberInvite } from '@/types/team'

/** `GET /teams` —— 当前用户参与的团队。 */
function listTeams(params?: PaginationParams): Promise<Team[]> {
  return http.get<Team[]>('/teams', { params })
}

/** `POST /teams` —— 创建团队，创建者自动成为 owner。 */
function createTeam(payload: TeamCreate): Promise<Team> {
  return http.post<Team>('/teams', payload)
}

/** `GET /teams/{team_id}` —— 非成员返回 404（与「不存在」同文案，防 id 枚举）。 */
function getTeam(teamId: number): Promise<Team> {
  return http.get<Team>(`/teams/${teamId}`)
}

/** `PATCH /teams/{team_id}` —— 非 owner 返回 404（资源级拦截，不暴露「别人有这个团队」）。 */
function updateTeam(teamId: number, payload: TeamUpdate): Promise<Team> {
  return http.patch<Team>(`/teams/${teamId}`, payload)
}

/** `DELETE /teams/{team_id}` —— owner only；220（前端忽略 body）。 */
function deleteTeam(teamId: number): Promise<void> {
  return http.delete<void>(`/teams/${teamId}`)
}

/** `GET /teams/{team_id}/members` —— 团队成员可看。 */
function listMembers(teamId: number): Promise<TeamMember[]> {
  return http.get<TeamMember[]>(`/teams/${teamId}/members`)
}

/** `POST /teams/{team_id}/members` —— 邀请成员（user_id + role）。
 *  目标用户不存在 → 404；已是成员 → 409；role 传 owner → 422。 */
function inviteMember(teamId: number, payload: TeamMemberInvite): Promise<TeamMember> {
  return http.post<TeamMember>(`/teams/${teamId}/members`, payload)
}

/** `DELETE /teams/{team_id}/members/{user_id}` —— 层级 OWNER>ADMIN>MEMBER；owner 不可移除。 */
function removeMember(teamId: number, userId: number): Promise<void> {
  return http.delete<void>(`/teams/${teamId}/members/${userId}`)
}

export const teamApi = {
  listTeams,
  createTeam,
  getTeam,
  updateTeam,
  deleteTeam,
  listMembers,
  inviteMember,
  removeMember,
}
