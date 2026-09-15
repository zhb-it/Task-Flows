/**
 * 项目 API（前端规格 §19）。
 *
 * 对齐 `app/api/v1/projects.py`：
 *
 * | 函数            | 端点               |
 * | --------------- | ------------------ |
 * | `listProjects`  | `GET   /projects`  |
 *
 * `GET /projects` 需要 `project:read` 权限，只返回「我参与的团队下的项目」；
 * 列表参数是后端统一的 `skip` / `limit`，响应裸数组无 `total`。本阶段只取概览，
 * 传 `limit=5`。
 */

import { http } from '@/utils/request'
import type { PaginationParams } from '@/types/common'
import type { Project } from '@/types/project'

/** `GET /projects` —— 当前用户可见的项目，最新在前。 */
function listProjects(params?: PaginationParams): Promise<Project[]> {
  return http.get<Project[]>('/projects', { params })
}

export const projectApi = { listProjects }
