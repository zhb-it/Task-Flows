/**
 * 路由守卫（前端规格 §36 路由权限 / §10 Token 失效处理）。
 *
 * 判定流程就是规格里的那张图：
 *
 * ```text
 * 访问页面 → 需要登录吗？
 *   否 → 放行（已登录时把 /login、/register 顶回首页）
 *   是 → 有 Access Token 吗？ 否 → /login?redirect=<原地址>
 *        是 → 有当前用户资料吗？ 否 → 拉一次 /users/me
 *             拉取失败（令牌其实已失效）→ 清凭证 → /login?redirect=<原地址>
 * ```
 *
 * 「是否有权限」这一档（规格 §36 的 `/403`）目前无法在守卫里判定：后端不提供
 * 权限集合（见 `composables/usePermission.ts`）。真正的权限拒绝由后端返回 403，
 * 页面按需跳 `/403`。这是有意的留白，不是漏做。
 */

import type { Router } from 'vue-router'

import { APP_TITLE } from '@/router/routes'
import { useAuthStore } from '@/stores/auth'
import { onUnauthorized } from '@/utils/request'

/** 标签页标题（`index.html` 的注释承诺由这里统一覆盖）。 */
function applyTitle(title: unknown): void {
  document.title = typeof title === 'string' && title ? `${title} · ${APP_TITLE}` : APP_TITLE
}

export function registerGuards(router: Router): void {
  // 会话彻底失效（Refresh Token 也不可用）时由请求层回调到这里：
  // 清凭证 + 跳登录，并带上回跳地址。注册在本模块而不是 `utils/request.ts`，
  // 是为了让请求层不必 import router（否则循环依赖）。
  onUnauthorized(() => {
    useAuthStore().clearSession()
    const current = router.currentRoute.value
    if (current.name !== 'login') {
      void router.replace({ name: 'login', query: { redirect: current.fullPath } })
    }
  })

  router.beforeEach(async (to) => {
    applyTitle(to.meta.title)

    const auth = useAuthStore()

    if (to.meta.requiresAuth === false) {
      // 已登录用户不该再看到登录/注册页。
      if (auth.isAuthenticated && (to.name === 'login' || to.name === 'register')) {
        return { name: 'dashboard' }
      }
      return true
    }

    if (!auth.isAuthenticated) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }

    // 刷新页面后 store 是空的（令牌在 localStorage，用户资料不在），
    // 这里补一次拉取。失败说明令牌已失效，交给上面的失效流程。
    if (!auth.currentUser) {
      try {
        await auth.fetchCurrentUser()
      } catch {
        auth.clearSession()
        return { name: 'login', query: { redirect: to.fullPath } }
      }
    }

    return true
  })
}
