/**
 * 项目 API（前端规格 §16 / §17 / §18 / §19）。
 *
 * 对齐 `app/api/v1/projects.py`：
 *
 * | 函数              | 方法   | 端点                    | 功能级权限     | 资源级约束                         |
 * | ----------------- | ------ | ----------------------- | -------------- | ---------------------------------- |
 * | `listProjects`    | GET    | `/projects`             | `project:read` | 仅「我参与的团队」下的项目         |
 * | `createProject`   | POST   | `/projects`             | `project:create`（团队成员）| `team_id` 必须存在且我是成员，否则 404 |
 * | `getProject`      | GET    | `/projects/{id}`        | `project:read` | 非成员 → 404（与「不存在」同文案） |
 * | `updateProject`   | PATCH  | `/projects/{id}`        | `project:update` | 团队 OWNER/ADMIN，否则 404         |
 * | `deleteProject`   | DELETE | `/projects/{id}`        | `project:delete` | 团队 OWNER/ADMIN，否则 404         |
 *
 * 列表端点用后端统一的 `skip` / `limit`（`limit <= 100`），响应是裸数组、没有 `total`
 * （见 docs/FRONTEND_API_MAPPING.md §4-D3）。本模块列表一次性取 `limit:100` 全量，
 * 搜索 / 团队筛选 / 分页均在客户端做（后端无对应能力）。
 *
 * ⚠ 项目成员复用团队接口 `GET /teams/{team_id}/members`（项目没有自己的成员端点，
 * 成员关系挂在团队上），见 `getProject` 拿到 `team_id` 后再查团队。
 */

import { http } from '@/utils/request'
import type { PaginationParams } from '@/types/common'
import type { Project, ProjectCreate, ProjectUpdate } from '@/types/project'

/** `GET /projects` —— 当前用户可见的项目（所属团队下的），最新在前。 */
function listProjects(params?: PaginationParams): Promise<Project[]> {
  return http.get<Project[]>('/projects', { params })
}

/** `POST /projects` —— 在某团队下创建项目，创建者自动成为 owner。 */
function createProject(payload: ProjectCreate): Promise<Project> {
  return http.post<Project>('/projects', payload)
}

/** `GET /projects/{id}` —— 非团队成员返回 404（与「不存在」同文案，防 id 枚举）。 */
function getProject(projectId: number): Promise<Project> {
  return http.get<Project>(`/projects/${projectId}`)
}

/** `PATCH /projects/{id}` —— 非团队 OWNER/ADMIN 返回 404（资源级拦截）。 */
function updateProject(projectId: number, payload: ProjectUpdate): Promise<Project> {
  return http.patch<Project>(`/projects/${projectId}`, payload)
}

/** `DELETE /projects/{id}` —— 团队 OWNER/ADMIN；220（前端忽略 body）。 */
function deleteProject(projectId: number): Promise<void> {
  return http.delete<void>(`/projects/${projectId}`)
}

export const projectApi = {
  listProjects,
  createProject,
  getProject,
  updateProject,
  deleteProject,
}
