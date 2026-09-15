/**
 * 当前用户的权限集合（前端规格 §34 / §35 / §4 的 `composables/` 约定）。
 *
 * ⚠ 现状必须说清楚：**后端没有提供权限查询端点**。
 * `docs/API_CONTRACT.md` 在「授权机制」一节写明这是「内部机制，无独立端点」，
 * 而 `GET /users/me` 返回的 `UserRead` 只有 `id/username/email/is_active/
 * created_at/updated_at`。因此前端**无法得知**当前用户持有哪些权限
 * （`team:create` 之类），本 composable 目前恒定得到空集合。
 *
 * 为什么仍然保留它：规格 §34 要求前端有 RBAC 的落点，未来的做法有两条，任选其一
 * 之前都不应该在页面里散落 `hasPermission` 判断——
 *
 * 1. 后端新增一个「返回当前用户权限集合」的端点（最干净，推荐）；
 * 2. 前端按团队角色推断（`TeamMemberRead.role` 确实返回了 `owner|admin|member`，
 *    但那是**资源级**角色，只能回答「在这个团队里我是什么」，不能回答
 *    「我能否创建团队」这类功能级问题）。
 *
 * 在事实缺失的前提下，按规格 §35 的原则「隐藏按钮 ≠ 安全」，正确做法是
 * **不隐藏**入口、让后端的 403 来裁决；凭空造一份权限表才是真正危险的
 * ——那会让开发者误以为前端已经守住了权限。
 */

import { computed } from 'vue'

import { hasAnyPermission, hasPermission } from '@/utils/permission'

/** 后端权限查询端点落地前，前端始终持空集合。 */
const grantedPermissions = computed<readonly string[]>(() => [])

export function usePermission() {
  return {
    /** 当前用户权限集合（当前恒为空，见文件头注释）。 */
    permissions: grantedPermissions,
    /** AND 语义：是否持有全部所列权限。 */
    can: (...required: string[]): boolean => hasPermission(grantedPermissions.value, ...required),
    /** OR 语义：是否持有任一所列权限。 */
    canAny: (...required: string[]): boolean =>
      hasAnyPermission(grantedPermissions.value, ...required),
  }
}
