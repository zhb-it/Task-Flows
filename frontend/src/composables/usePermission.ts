/**
 * 当前用户的权限集合（前端规格 §34 / §35 / §4 的 `composables/` 约定）。
 *
 * TASK-084 起数据源是真实的：后端提供 `GET /users/me/permissions`（TASK-083，
 * 与 `require_permission` 同一数据源 `get_user_permissions`），auth store 在
 * 登录/刷新用户资料时并行拉取并存入 `permissions`。本 composable 只是 store
 * 的只读视图——**不要**在组件里各自造权限集合。
 *
 * 语义提醒（规格 §35）：「隐藏按钮 ≠ 安全」。`can/canAny` 只做展示层显隐；
 * 越权操作仍由后端 403 裁决。因此即便权限集合因故为空（拉取失败、尚未登录），
 * 页面入口也不应凭空隐藏——这与 DECISIONS 055 的结论一致，只是前提从
 * 「拿不到」变成了「有真实数据、失败时退化为空」。
 */

import { computed } from 'vue'

import { useAuthStore } from '@/stores/auth'
import { hasAnyPermission, hasPermission } from '@/utils/permission'

export function usePermission() {
  const store = useAuthStore()
  /** 当前用户权限集合（来自 `/users/me/permissions`，失败时为空）。 */
  const permissions = computed<readonly string[]>(() => store.permissions)
  /** AND 语义：是否持有全部所列权限。 */
  const can = (...required: string[]): boolean =>
    hasPermission(permissions.value, ...required)
  /** OR 语义：是否持有任一所列权限。 */
  const canAny = (...required: string[]): boolean =>
    hasAnyPermission(permissions.value, ...required)
  return { permissions, can, canAny }
}
