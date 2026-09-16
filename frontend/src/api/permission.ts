/**
 * RBAC API（TASK-084；端点逐一对齐 `app/api/v1/users.py` / `permissions.py`）：
 *
 * | 函数              | 端点                          | 授权                  |
 * | ----------------- | ----------------------------- | --------------------- |
 * | `fetchMyPermissions` | `GET /users/me/permissions` | 仅需登录              |
 * | `fetchMatrix`     | `GET /permissions`            | user:update（admin）  |
 * | `listUsers`       | `GET /users`                  | user:read             |
 * | `fetchUserRoles`  | `GET /users/{id}/roles`       | user:read             |
 * | `replaceUserRoles`| `PUT /users/{id}/roles`       | user:update（admin）  |
 */

import { http } from '@/utils/request'
import type {
  MePermissions,
  PermissionMatrixRole,
  RoleNamesUpdate,
  UserRoles,
  UserWithRoles,
} from '@/types/permission'

/** `GET /users/me/permissions` —— 当前用户的有效权限名集合（去重、字典序）。 */
function fetchMyPermissions(): Promise<MePermissions> {
  return http.get<MePermissions>('/users/me/permissions')
}

/** `GET /permissions` —— 角色-权限矩阵（admin 视图；member 调用得到 403）。 */
function fetchMatrix(): Promise<PermissionMatrixRole[]> {
  return http.get<PermissionMatrixRole[]>('/permissions')
}

/** `GET /users` —— 用户列表（含角色名），skip/limit 分页与后端一致。 */
function listUsers(skip = 0, limit = 100): Promise<UserWithRoles[]> {
  return http.get<UserWithRoles[]>('/users', { params: { skip, limit } })
}

/** `GET /users/{user_id}/roles` —— 指定用户的角色名列表。 */
function fetchUserRoles(userId: number): Promise<UserRoles> {
  return http.get<UserRoles>(`/users/${userId}/roles`)
}

/** `PUT /users/{user_id}/roles` —— 全量替换用户角色（PUT 语义；后端禁止操作自己）。 */
function replaceUserRoles(userId: number, payload: RoleNamesUpdate): Promise<UserRoles> {
  return http.put<UserRoles>(`/users/${userId}/roles`, payload)
}

export const permissionApi = {
  fetchMyPermissions,
  fetchMatrix,
  listUsers,
  fetchUserRoles,
  replaceUserRoles,
}
