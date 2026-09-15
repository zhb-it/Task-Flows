/**
 * 团队 API（前端规格 §13 / §15）。
 *
 * 对齐 `app/api/v1/teams.py`：
 *
 * | 函数         | 端点             |
 * | ------------ | ---------------- |
 * | `listTeams`  | `GET   /teams`   |
 *
 * `GET /teams` 需要 `team:read` 权限，只返回「我参与的团队」；列表参数是
 * 后端统一的 `skip` / `limit`（`limit <= 100`），响应是裸数组、没有 `total`
 * （见 docs/FRONTEND_API_MAPPING.md §4-D3）。本阶段只取概览，传 `limit=5`。
 */

import { http } from '@/utils/request'
import type { PaginationParams } from '@/types/common'
import type { Team } from '@/types/team'

/** `GET /teams` —— 当前用户参与的团队，最新在前。 */
function listTeams(params?: PaginationParams): Promise<Team[]> {
  return http.get<Team[]>('/teams', { params })
}

export const teamApi = { listTeams }
