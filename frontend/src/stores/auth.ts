/**
 * 认证状态（前端规格 §9 / §51）。
 *
 * Pinia 只保存「跨页面共享且需要长期一致」的东西（规格 §51）：当前登录用户与
 * 登录态。任务列表、评论列表这类页面数据由页面自己管理，不进 store。
 *
 * 令牌的**值**不在 store 里：请求拦截器需要在任意时刻读到最新令牌，而刷新
 * （`utils/request.ts`）发生在 store 之外。若 store 再存一份副本，两处就会漂移
 * ——例如刷新轮换后 store 里仍是旧 Refresh Token，登出时用它去撤销，撤销的是
 * 已失效的那个，真正有效的那一个反而活了下来。所以令牌的唯一事实来源是
 * `utils/storage.ts`，store 只保存由它派生的登录态。
 */

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { authApi } from '@/api/auth'
import type { LoginRequest } from '@/types/auth'
import type { User } from '@/types/user'
import { tokenStorage } from '@/utils/storage'

export const useAuthStore = defineStore('auth', () => {
  /** 当前登录用户；未登录或尚未拉取时为 null。 */
  const currentUser = ref<User | null>(null)

  /** 登录态标记：只表达「本地是否持有 Access Token」，不校验其有效性。 */
  const hasToken = ref(tokenStorage.getAccessToken() !== null)

  /** 登录请求进行中（页面用它禁用按钮，防止重复提交，规格 §42）。 */
  const loggingIn = ref(false)

  const isAuthenticated = computed(() => hasToken.value)

  const username = computed(() => currentUser.value?.username ?? '')

  function applyTokens(): void {
    hasToken.value = tokenStorage.getAccessToken() !== null
  }

  /**
   * 登录：换取令牌 → 记录登录态 → 拉取当前用户。
   *
   * 为什么登录后立刻拉 `/users/me`：登录响应只有令牌，没有用户资料；而布局层
   * 需要用户名（顶栏、用户菜单），先拉一次可以让后续页面直接用
   * `currentUser`，避免每个页面各自判断「用户信息取了没」。
   */
  async function login(payload: LoginRequest): Promise<User> {
    loggingIn.value = true
    try {
      const pair = await authApi.login(payload)
      tokenStorage.save(pair)
      applyTokens()
      return await fetchCurrentUser()
    } catch (error) {
      // 登录失败要保证不留下半截状态：令牌没写、登录态为假。
      clearSession()
      throw error
    } finally {
      loggingIn.value = false
    }
  }

  /** 拉取当前用户资料（路由守卫在「已登录但还没有用户信息」时调用）。 */
  async function fetchCurrentUser(): Promise<User> {
    const user = await authApi.fetchCurrentUser()
    currentUser.value = user
    return user
  }

  /**
   * 登出：先请求后端撤销 Refresh Token，再无条件清理本地状态。
   *
   * Refresh Token 从 `tokenStorage` 现取而不是从某个 ref 读——理由见文件头注释。
   * 后端撤销是幂等的（`logout_user`：Token 本来就不可用则静默成功），所以
   * 网络失败也不阻塞本地清理：用户点了登出就应该登出。
   */
  async function logout(): Promise<void> {
    const refreshToken = tokenStorage.getRefreshToken()
    try {
      if (refreshToken) {
        await authApi.logout(refreshToken)
      }
    } catch {
      // 故意吞掉：撤销失败只意味着服务端可能还留着一条可用凭证，但客户端
      // 已经登出。把这个异常冒泡给调用方只会让「登出按钮点了没反应」。
    } finally {
      clearSession()
    }
  }

  /** 仅清理本地会话（登出、刷新失败、账号被禁用时使用）。 */
  function clearSession(): void {
    tokenStorage.clear()
    hasToken.value = false
    currentUser.value = null
  }

  return {
    currentUser,
    isAuthenticated,
    loggingIn,
    username,
    login,
    logout,
    fetchCurrentUser,
    clearSession,
  }
})
