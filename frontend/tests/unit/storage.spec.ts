/**
 * `utils/storage.ts` 的单元测试。
 *
 * 这几条用例的价值不在「getItem 能不能用」，而在于把**契约**钉住：
 * 键名、save/clear 的成对语义，以及「存储不可用时不抛异常」这条降级约定。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { tokenStorage } from '@/utils/storage'

const PAIR = { access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' }

describe('tokenStorage', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('没有令牌时两个读取方法都返回 null', () => {
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })

  it('save 之后可以读回同一个令牌对', () => {
    tokenStorage.save(PAIR)

    expect(tokenStorage.getAccessToken()).toBe('access-1')
    expect(tokenStorage.getRefreshToken()).toBe('refresh-1')
  })

  it('save 覆盖旧值（刷新轮换后不应该读到旧令牌）', () => {
    tokenStorage.save(PAIR)
    tokenStorage.save({ ...PAIR, access_token: 'access-2', refresh_token: 'refresh-2' })

    expect(tokenStorage.getAccessToken()).toBe('access-2')
    expect(tokenStorage.getRefreshToken()).toBe('refresh-2')
  })

  it('clear 同时移除两个键，不会留下半个会话', () => {
    tokenStorage.save(PAIR)
    tokenStorage.clear()

    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })

  it('localStorage 写入抛异常时静默降级（不冒泡给调用方）', () => {
    // 隐私模式 / 配额耗尽都会走到这条路径：登出流程不应该因为存储失败而中断。
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })

    expect(() => tokenStorage.save(PAIR)).not.toThrow()

    spy.mockRestore()
  })
})
