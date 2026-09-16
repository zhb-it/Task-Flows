/**
 * `stores/auth.ts` 的单元测试（前端规格 §71 单元测试重点「stores」）。
 *
 * store 里真正值得钉住的**契约**有四条，都来自文件头注释的决策：
 * 1. 令牌唯一事实来源是 `utils/storage.ts`——store 只派生 `hasToken`，不存副本；
 * 2. 登录失败不留下半截状态（令牌没写、登录态为假）；
 * 3. 登出的后端撤销**失败也不阻塞**本地清理（幂等语义，用户点了就该登出）；
 * 4. 登出用的 Refresh Token 从 storage 现取。
 * API 层用 `vi.mock` 整体替换——store 的逻辑与请求实现解耦，这里只测前者。
 */

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  login: vi.fn(),
  fetchCurrentUser: vi.fn(),
  logout: vi.fn(),
  fetchMyPermissions: vi.fn(),
}))


vi.mock('@/api/auth', () => ({
  authApi: {
    login: mocks.login,
    fetchCurrentUser: mocks.fetchCurrentUser,
    logout: mocks.logout,
  },
}))

vi.mock('@/api/permission', () => ({
  permissionApi: {
    fetchMyPermissions: mocks.fetchMyPermissions,
  },
}))

import { useAuthStore } from '@/stores/auth'
import { tokenStorage } from '@/utils/storage'

const PAIR = { access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' }

const USER = {
  id: 1,
  username: 'alice',
  email: 'alice@example.com',
  is_active: true,
  created_at: '2026-09-01T00:00:00+00:00',
  updated_at: '2026-09-01T00:00:00+00:00',
}

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
    vi.clearAllMocks()
  })

  it('初始态：没有令牌时 isAuthenticated 为假、username 为空', () => {
    const store = useAuthStore()
    expect(store.isAuthenticated).toBe(false)
    expect(store.currentUser).toBeNull()
    expect(store.username).toBe('')
  })

  it('login 成功：令牌写入 storage、登录态翻转、拉取并保存用户与权限集合', async () => {
    mocks.login.mockResolvedValueOnce(PAIR)
    mocks.fetchCurrentUser.mockResolvedValueOnce(USER)
    mocks.fetchMyPermissions.mockResolvedValueOnce({ permissions: ['task:read'] })

    const store = useAuthStore()
    const user = await store.login({ username: 'alice', password: 'secret' })

    expect(user).toEqual(USER)
    expect(store.currentUser).toEqual(USER)
    expect(store.permissions).toEqual(['task:read'])
    expect(store.isAuthenticated).toBe(true)
    expect(store.username).toBe('alice')
    expect(store.loggingIn).toBe(false)
    expect(tokenStorage.getAccessToken()).toBe('access-1')
  })

  it('fetchCurrentUser：权限拉取失败不阻塞用户资料（归空集合，TASK-084）', async () => {
    tokenStorage.save(PAIR)
    mocks.fetchCurrentUser.mockResolvedValueOnce(USER)
    mocks.fetchMyPermissions.mockRejectedValueOnce(new Error('boom'))

    const store = useAuthStore()
    const user = await store.fetchCurrentUser()

    expect(user).toEqual(USER)
    expect(store.currentUser).toEqual(USER)
    expect(store.permissions).toEqual([])
  })

  it('login 失败：不留下半截状态，异常原样冒泡', async () => {
    mocks.login.mockRejectedValueOnce(new Error('bad credentials'))

    const store = useAuthStore()
    await expect(store.login({ username: 'alice', password: 'wrong' })).rejects.toThrow(
      'bad credentials',
    )

    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(store.currentUser).toBeNull()
    expect(store.loggingIn).toBe(false)
  })

  it('logout：用 storage 里的 Refresh Token 撤销，并清理本地会话', async () => {
    tokenStorage.save(PAIR)
    mocks.logout.mockResolvedValueOnce(undefined)

    const store = useAuthStore()
    expect(store.isAuthenticated).toBe(true)
    await store.logout()

    expect(mocks.logout).toHaveBeenCalledWith('refresh-1')
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(store.currentUser).toBeNull()
  })

  it('logout：后端撤销失败也照样清理本地（不阻塞登出）', async () => {
    tokenStorage.save(PAIR)
    mocks.logout.mockRejectedValueOnce(new Error('network down'))

    const store = useAuthStore()
    await expect(store.logout()).resolves.toBeUndefined()

    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(store.isAuthenticated).toBe(false)
  })

  it('logout：本地没有令牌时不发起撤销请求', async () => {
    const store = useAuthStore()
    await store.logout()

    expect(mocks.logout).not.toHaveBeenCalled()
    expect(store.isAuthenticated).toBe(false)
  })

  it('clearSession：清令牌、用户与权限集合，登录态归假', () => {
    tokenStorage.save(PAIR)

    const store = useAuthStore()
    store.currentUser = USER
    store.permissions = ['task:read']
    store.clearSession()

    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(store.currentUser).toBeNull()
    expect(store.permissions).toEqual([])
    expect(store.isAuthenticated).toBe(false)
  })
})
