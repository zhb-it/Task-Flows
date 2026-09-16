/**
 * `composables/usePermission.ts` 的单元测试（前端规格 §71 单元测试重点「composables」）。
 *
 * 这个 composable 的**契约**就是文件头注释里那条现状：后端没有权限查询端点
 * （§4-D4），前端权限集合恒为空。测试把它钉住——凡是有人把 `grantedPermissions`
 * 改成「造出来的假集合」，这里立刻红：那正是 DECISIONS 055 判定过的
 * 「比不做更危险」的改动。
 */

import { describe, expect, it } from 'vitest'

import { usePermission } from '@/composables/usePermission'

describe('usePermission（权限集合恒为空，§4-D4）', () => {
  it('permissions 是空集合', () => {
    const { permissions } = usePermission()
    expect(permissions.value).toEqual([])
  })

  it('can（AND 语义）：空集合对任何权限都返回 false', () => {
    const { can } = usePermission()
    expect(can('task:read')).toBe(false)
    expect(can('task:read', 'task:update')).toBe(false)
  })

  it('canAny（OR 语义）：空集合对任何权限都返回 false', () => {
    const { canAny } = usePermission()
    expect(canAny('team:create')).toBe(false)
    expect(canAny('team:create', 'team:delete')).toBe(false)
  })

  it('can / canAny 不传参数时的行为稳定', () => {
    const { can, canAny } = usePermission()
    // 空集合 AND 空要求 = 恒真（没有要求就不拦）；OR 空要求 = 恒假（无可命中）
    expect(can()).toBe(true)
    expect(canAny()).toBe(false)
  })
})
