/**
 * 任务 API（前端规格 §20 / §23 / §24 / §25 / §26 / §27）。
 *
 * 对齐 `app/api/v1/tasks.py`：
 *
 * | 函数           | 方法   | 端点                                  | 功能级权限        |
 * | -------------- | ------ | ------------------------------------- | ----------------- |
 * | `listTasks`    | GET    | `/tasks?project_id=…`                 | `task:read`       |
 * | `createTask`   | POST   | `/tasks`                              | `task:create`     |
 * | `getTask`      | GET    | `/tasks/{id}`                         | `task:read`       |
 * | `updateTask`   | PATCH  | `/tasks/{id}`                         | `task:update`     |
 * | `deleteTask`   | DELETE | `/tasks/{id}`                         | `task:delete`     |
 * | `transitionTask`| POST  | `/tasks/{id}/transition`              | `task:transition` |
 * | `assignTask`   | POST   | `/tasks/{id}/assignees`               | `task:update`     |
 * | `unassignTask` | DELETE | `/tasks/{id}/assignees/{user_id}`     | `task:update`     |
 *
 * ⚠ `GET /tasks` 的 `project_id` 必填（无默认值）；响应是裸数组、无 `total`
 * （分页用 skip/limit，见 docs/FRONTEND_API_MAPPING.md §4-D3）。
 *
 * 状态流转必须经 `transitionTask`；`updateTask` 的请求体不含 status（决策 005 /
 * TASK-038），直接 PATCH status 会被后端拒绝。
 */

import { http } from '@/utils/request'
import type { Task, TaskCreate, TaskUpdate, TaskListParams, TaskAssignee, TaskStatus } from '@/types/task'

/** `GET /tasks` —— 项目的任务列表（project_id 必填）。 */
function listTasks(params: TaskListParams): Promise<Task[]> {
  return http.get<Task[]>('/tasks', { params })
}

/** `POST /tasks` —— 创建任务（creator = 调用者，status 恒为 TODO）。 */
function createTask(payload: TaskCreate): Promise<Task> {
  return http.post<Task>('/tasks', payload)
}

/** `GET /tasks/{id}` —— 非团队成员 → 404（防 id 枚举）。 */
function getTask(taskId: number): Promise<Task> {
  return http.get<Task>(`/tasks/${taskId}`)
}

/** `PATCH /tasks/{id}` —— 部分更新（不含 status）。 */
function updateTask(taskId: number, payload: TaskUpdate): Promise<Task> {
  return http.patch<Task>(`/tasks/${taskId}`, payload)
}

/** `DELETE /tasks/{id}` —— 团队 owner/admin only；220（前端忽略 body）。 */
function deleteTask(taskId: number): Promise<void> {
  return http.delete<void>(`/tasks/${taskId}`)
}

/** `POST /tasks/{id}/transition` —— 状态机流转；非法 → 409，无权限 → 403。 */
function transitionTask(taskId: number, toStatus: TaskStatus): Promise<Task> {
  return http.post<Task>(`/tasks/${taskId}/transition`, { to_status: toStatus })
}

/** `POST /tasks/{id}/assignees` —— 指派负责人（团队成员即可，可否自领）。 */
function assignTask(taskId: number, userId: number): Promise<TaskAssignee> {
  return http.post<TaskAssignee>(`/tasks/${taskId}/assignees`, { user_id: userId })
}

/** `DELETE /tasks/{id}/assignees/{user_id}` —— 移除负责人。 */
function unassignTask(taskId: number, userId: number): Promise<void> {
  return http.delete<void>(`/tasks/${taskId}/assignees/${userId}`)
}

export const taskApi = {
  listTasks,
  createTask,
  getTask,
  updateTask,
  deleteTask,
  transitionTask,
  assignTask,
  unassignTask,
}
