/**
 * `utils/permission.ts` 的单元测试。
 *
 * 语义对齐后端 `app/core/deps.py` 的 `require_permission(*permissions)`：
 * **多值 AND**。这是本模块唯一需要与后端保持一致的地方，所以正反用例都要有。
 */

import { describe, expect, it } from 'vitest'

import { hasAnyPermission, hasPermission } from '@/utils/permission'

const GRANTED = ['task:read', 'task:update', 'comment:create']

describe('hasPermission（AND 语义）', () => {
  it('单个权限命中', () => {
    expect(hasPermission(GRANTED, 'task:read')).toBe(true)
  })

  it('单个权限未命中', () => {
    expect(hasPermission(GRANTED, 'task:delete')).toBe(false)
  })

  it('多个权限全部命中才算通过', () => {
    expect(hasPermission(GRANTED, 'task:read', 'task:update')).toBe(true)
  })

  it('多个权限缺一个就不通过', () => {
    expect(hasPermission(GRANTED, 'task:read', 'task:delete')).toBe(false)
  })

  it('不要求任何权限时恒为 true', () => {
    expect(hasPermission([])).toBe(true)
    expect(hasPermission(GRANTED)).toBe(true)
  })

  it('接受 Set 作为权限集合', () => {
    expect(hasPermission(new Set(GRANTED), 'comment:create')).toBe(true)
    expect(hasPermission(new Set(GRANTED), 'project:delete')).toBe(false)
  })

  it('空集合对任何具体权限都不通过', () => {
    // 这正是当前前端的真实状态：后端没有权限查询端点（见 usePermission.ts）。
    expect(hasPermission([], 'task:read')).toBe(false)
  })
})

describe('hasAnyPermission（OR 语义）', () => {
  it('命中任意一个即通过', () => {
    expect(hasAnyPermission(GRANTED, 'project:create', 'comment:create')).toBe(true)
  })

  it('一个都没命中则不通过', () => {
    expect(hasAnyPermission(GRANTED, 'project:create', 'team:delete')).toBe(false)
  })

  it('不列出任何权限时恒为 false（与 AND 版本相反，避免误用）', () => {
    expect(hasAnyPermission(GRANTED)).toBe(false)
  })
})
