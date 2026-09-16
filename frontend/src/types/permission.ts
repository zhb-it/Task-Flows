/**
 * RBAC 类型（TASK-084，对齐 `app/schemas/user.py` / `app/schemas/role.py`）。
 *
 * 角色在契约中以 **name** 为标识（后端种子保证 `admin` / `member` 存在），
 * id 只透传不参与判断；权限名是 `resource:action` 字符串，与后端
 * `require_permission` 判定用同一份清单。
 */

/** `GET /permissions` 的单个角色条目（权限名已按字典序）。 */
export interface PermissionMatrixRole {
  id: number
  name: string
  description: string | null
  permissions: string[]
}

/** `GET /users` 的条目：UserRead + 角色名列表。 */
export interface UserWithRoles {
  id: number
  username: string
  email: string
  is_active: boolean
  created_at: string
  updated_at: string
  roles: string[]
}

/** `GET|PUT /users/{user_id}/roles` 的响应体。 */
export interface UserRoles {
  user_id: number
  roles: string[]
}

/** `PUT /users/{user_id}/roles` 的请求体（全量替换语义）。 */
export interface RoleNamesUpdate {
  roles: string[]
}

/** `GET /users/me/permissions` 的响应体。 */
export interface MePermissions {
  permissions: string[]
}
