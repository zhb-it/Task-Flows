/**
 * 用户类型（前端规格 §39）。
 *
 * 字段逐一对齐 `app/schemas/user.py::UserRead`：
 * `id / username / email / is_active / created_at / updated_at`。
 *
 * ⚠ 后端**不返回** `password_hash`（项目规则 §5），也**不返回** 角色或权限集合
 * （`docs/API_CONTRACT.md` 明确「授权机制（TASK-023 / TASK-024，内部机制，
 * 无独立端点）」）。因此前端拿不到「当前用户有哪些权限」这个事实，
 * 见 `src/composables/usePermission.ts` 的说明。
 */

/** `GET /api/v1/users/me` 的 `data`。 */
export interface User {
  id: number
  username: string
  email: string
  is_active: boolean
  /** ISO 8601 字符串（Pydantic `datetime` 序列化结果）。 */
  created_at: string
  updated_at: string
}
