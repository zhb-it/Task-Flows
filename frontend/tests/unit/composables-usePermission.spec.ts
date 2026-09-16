/**
 * `composables/usePermission.ts` 的单元测试（前端规格 §71 单元测试重点「composables」）。
 *
 * TASK-084 起数据源是真实的：auth store 持有 `/users/me/permissions` 拉到的
 * 权限集合，composable 是它的只读视图。本测试钉住三条契约：
 * 1. `can`（AND）/`canAny`（OR）的判定与集合一致（对齐后端 require_permission）；
 * 2. 集合为空（拉取失败/未登录）时对任何具体权限返回 false，不猜测不虚构；
 * 3. 集合变化是响应式的（store 更新后 `can` 的结果跟随变化）。
 */

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { usePermission } from '@/composables/usePermission'
import { useAuthStore } from '@/stores/auth'

describe('usePermission（store 驱动的权限判定，TASK-084）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('未登录 / 权限未拉取时集合为空，对任何具体权限返回 false', () => {
    const { permissions, can, canAny } = usePermission()
    expect(permissions.value).toEqual([])
    expect(can('task:read')).toBe(false)
    expect(canAny('team:create')).toBe(false)
  })

  it('can（AND 语义）：持有全部所列权限才为 true', () => {
    const store = useAuthStore()
    store.permissions = ['task:read', 'task:update']

    const { can } = usePermission()
    expect(can('task:read')).toBe(true)
    expect(can('task:read', 'task:update')).toBe(true)
    expect(can('task:read', 'task:delete')).toBe(false)
  })

  it('canAny（OR 语义）：持有任一所列权限即为 true', () => {
    const store = useAuthStore()
    store.permissions = ['task:read']

    const { canAny } = usePermission()
    expect(canAny('task:read', 'task:delete')).toBe(true)
    expect(canAny('team:create', 'team:delete')).toBe(false)
  })

  it('can / canAny 不传参数时的行为稳定（与后端 AND 语义对齐）', () => {
    const store = useAuthStore()
    store.permissions = ['task:read']

    const { can, canAny } = usePermission()
    // 空要求 AND = 恒真（没有要求就不拦）；OR 空要求 = 恒假（无可命中）
    expect(can()).toBe(true)
    expect(canAny()).toBe(false)
  })

  it('响应式：store 权限集合更新后，判定结果跟随变化', async () => {
    const store = useAuthStore()
    const { can } = usePermission()
    expect(can('user:update')).toBe(false)

    store.permissions = ['user:update', 'user:read']
    expect(can('user:update')).toBe(true)

    store.clearSession()
    expect(can('user:update')).toBe(false)
  })
})
