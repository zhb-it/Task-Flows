/**
 * 前端权限判定的**纯函数**部分（前端规格 §34 / §35）。
 *
 * ⚠ 重要前提：后端 `docs/API_CONTRACT.md` 明确写着授权机制「无独立端点」，
 * `GET /api/v1/users/me` 返回的 `UserRead` 里也没有角色或权限字段。也就是说
 * **前端目前拿不到当前用户的权限集合**。规格 §34 列出的 `task:create` 这类
 * 权限名是后端内部的判定依据，不是可查询的接口数据。
 *
 * 因此本模块只提供「给定权限集合，判断是否满足要求」的纯逻辑；权限集合从哪来
 * 由调用方决定（当前恒为空集合，见 `src/composables/usePermission.ts`）。
 * 规格 §35 的原则本身就是「隐藏按钮 ≠ 安全」——真正的权限永远由后端校验，
 * 所以前端拿不到权限集合时，正确做法是**不隐藏**功能入口，而不是猜一个。
 */

/** 权限集合的两种常见载体。 */
export type PermissionSource = readonly string[] | ReadonlySet<string>

function toSet(source: PermissionSource): ReadonlySet<string> {
  return source instanceof Set ? source : new Set(source)
}

/**
 * 判断是否持有**全部**required 权限（AND 语义，与后端
 * `require_permission(*permissions)` 一致）。
 *
 * @param granted  当前用户已持有的权限集合
 * @param required 需要的权限名（一个或多个）
 */
export function hasPermission(granted: PermissionSource, ...required: string[]): boolean {
  if (required.length === 0) {
    return true
  }
  const owned = toSet(granted)
  return required.every((name) => owned.has(name))
}

/**
 * 判断是否持有**任一**required 权限（OR 语义）。
 *
 * 后端 `require_permission` 只有 AND 语义，保留这个函数是为了「多个可选入口
 * 满足其一即可显示」这类纯展示场景，不用于表达后端的授权规则。
 */
export function hasAnyPermission(granted: PermissionSource, ...required: string[]): boolean {
  if (required.length === 0) {
    return false
  }
  const owned = toSet(granted)
  return required.some((name) => owned.has(name))
}
