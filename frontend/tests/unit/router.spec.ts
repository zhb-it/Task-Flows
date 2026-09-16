/**
 * 路由表与路由守卫的单元测试（前端规格 §36）。
 *
 * 这里盯住的是「结构性错误」——菜单项指向不存在的路由、受保护页面漏挂守卫、
 * 未登录被跳转时丢掉回跳地址。这类问题在浏览器里往往表现为「某个菜单点了白屏」，
 * 单靠人点很难全量覆盖，用测试固定下来更可靠。
 */

import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchCurrentUser: vi.fn(),
  fetchMyPermissions: vi.fn(),
}))

vi.mock('@/api/auth', () => ({
  authApi: {
    fetchCurrentUser: mocks.fetchCurrentUser,
    login: vi.fn(),
    logout: vi.fn(),
    register: vi.fn(),
  },
}))

// 路由守卫拉用户资料时会并行拉权限集合（TASK-084）；这里固定为成功但不给
// 权限，让守卫测试只关注路由行为本身。
vi.mock('@/api/permission', () => ({
  permissionApi: { fetchMyPermissions: mocks.fetchMyPermissions },
}))

import { registerGuards } from '@/router/guards'
import { MENU_ITEMS, routes } from '@/router/routes'
import { tokenStorage } from '@/utils/storage'

const TOKEN_PAIR = {
  access_token: 'access-1',
  refresh_token: 'refresh-1',
  token_type: 'bearer',
}

const USER = {
  id: 1,
  username: 'alice',
  email: 'alice@example.com',
  is_active: true,
  created_at: '2026-01-01T00:00:00+00:00',
  updated_at: '2026-01-01T00:00:00+00:00',
}

function buildRouter(): Router {
  const router = createRouter({ history: createMemoryHistory(), routes })
  registerGuards(router)
  return router
}

describe('路由表', () => {
  it('侧边栏的每个菜单项都能解析到真实路由（不是 catch-all）', () => {
    const router = buildRouter()

    for (const item of MENU_ITEMS) {
      const resolved = router.resolve(item.path)
      expect(resolved.name, `菜单项 ${item.path} 未匹配到路由`).not.toBe('not-found')
      expect(resolved.matched.length).toBeGreaterThan(0)
    }
  })

  it('菜单项全部位于需要登录的主框架子树内', () => {
    const router = buildRouter()

    for (const item of MENU_ITEMS) {
      expect(router.resolve(item.path).meta.requiresAuth, `${item.path} 未受登录保护`).toBe(true)
    }
  })

  it('嵌套路由的 meta 是合并的：详情页继承父级的登录要求', () => {
    const router = buildRouter()

    expect(router.resolve('/teams/12').meta.requiresAuth).toBe(true)
    expect(router.resolve('/teams/12').meta.title).toBe('团队详情')
  })

  it('登录与注册页不需要登录', () => {
    const router = buildRouter()

    expect(router.resolve('/login').meta.requiresAuth).toBe(false)
    expect(router.resolve('/register').meta.requiresAuth).toBe(false)
  })

  it('错误页不需要登录（未登录时访问错误地址不应被弹回登录页）', () => {
    const router = buildRouter()

    for (const path of ['/403', '/500', '/definitely-not-a-page']) {
      expect(router.resolve(path).meta.requiresAuth).toBe(false)
    }
  })
})

describe('路由守卫', () => {
  beforeEach(() => {
    window.localStorage.clear()
    mocks.fetchCurrentUser.mockReset()
    mocks.fetchMyPermissions.mockReset()
    mocks.fetchMyPermissions.mockResolvedValue({ permissions: [] })
    setActivePinia(createPinia())
  })

  it('未登录访问受保护页面 → 跳登录页并带上回跳地址', async () => {
    const router = buildRouter()

    await router.push('/projects')

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/projects')
  })

  it('未登录访问详情页时回跳地址保留参数', async () => {
    const router = buildRouter()

    await router.push('/teams/12/members')

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/teams/12/members')
  })

  it('未登录可以正常打开登录页，不产生重定向', async () => {
    const router = buildRouter()

    await router.push('/login')

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBeUndefined()
  })

  it('未登录访问不存在的地址 → 显示 404，而不是跳登录页', async () => {
    const router = buildRouter()

    await router.push('/definitely-not-a-page')

    expect(router.currentRoute.value.name).toBe('not-found')
  })

  it('已登录时访问登录页被顶回首页，并拉取当前用户', async () => {
    tokenStorage.save(TOKEN_PAIR)
    mocks.fetchCurrentUser.mockResolvedValue(USER)
    const router = buildRouter()

    await router.push('/login')

    expect(router.currentRoute.value.name).toBe('dashboard')
    expect(mocks.fetchCurrentUser).toHaveBeenCalled()
  })

  it('令牌失效（/users/me 失败）时清空本地凭证并跳登录页', async () => {
    tokenStorage.save(TOKEN_PAIR)
    mocks.fetchCurrentUser.mockRejectedValue(new Error('401'))
    const router = buildRouter()

    await router.push('/dashboard')

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/dashboard')
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })

  it('标签页标题按「页面名 · 站点名」拼接', async () => {
    const router = buildRouter()

    await router.push('/login')

    expect(document.title).toContain('登录')
  })
})
