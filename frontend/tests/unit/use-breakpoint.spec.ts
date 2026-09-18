/**
 * 响应式断点逻辑的单元测试（TASK-130）。
 *
 * 断点不能只写在 CSS 里：侧栏「常驻 ↔ 抽屉」是**两种 DOM 结构**（`el-aside`
 * 与 `el-drawer`），必须有 JS 参与决策。这里测的就是那段决策逻辑——它被
 * `BasicLayout` 用来选渲染分支，改错会导致「窄屏下侧栏直接消失」这种最笨重
 * 也最难在宽屏开发机上发现的故障。
 *
 * `MOBILE_BREAKPOINT = 992` 同时被规格 §73 与 Element Plus 的 `md` 断点引用，
 * 因此在这里钉死它的值：改断点可以，但必须是一次显式修改（顺带更新文档与
 * 本断言），而不是某次重构里被悄悄改成别的数。
 */

import { effectScope, type Ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { DRAWER_WIDTH, MOBILE_BREAKPOINT, useIsMobile } from '@/composables/useBreakpoint'

/** 设置视口宽度并触发 resize（jsdom 不会自己改 innerWidth）。 */
function setViewport(width: number): void {
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: width,
  })
  window.dispatchEvent(new Event('resize'))
}

/** 在独立 effectScope 里调用 composable，返回 ref 与销毁函数（验证清理逻辑）。 */
function inScope<T>(fn: () => T): { value: T; stop: () => void } {
  const scope = effectScope()
  const value = scope.run(fn)
  if (value === undefined) {
    throw new Error('effectScope().run 未返回值')
  }
  return { value, stop: () => scope.stop() }
}

describe('useIsMobile', () => {
  it('断点值固定为 992，抽屉宽度与常驻侧栏一致', () => {
    expect(MOBILE_BREAKPOINT).toBe(992)
    expect(DRAWER_WIDTH).toBe('240px')
  })

  it('首帧就按当前宽度求值（窄屏不会先闪一下桌面侧栏）', () => {
    setViewport(600)
    const { value: isMobile, stop } = inScope((): Ref<boolean> => useIsMobile())

    expect(isMobile.value).toBe(true)
    stop()
  })

  it('宽屏为 false，并在跨过断点时跟随 resize 变化', () => {
    setViewport(1440)
    const { value: isMobile, stop } = inScope((): Ref<boolean> => useIsMobile())
    expect(isMobile.value).toBe(false)

    setViewport(991) // 断点内侧：仍算窄屏
    expect(isMobile.value).toBe(true)

    setViewport(992) // 断点本身算宽屏（`< 992` 才是抽屉）
    expect(isMobile.value).toBe(false)

    setViewport(480)
    expect(isMobile.value).toBe(true)
    stop()
  })

  it('作用域销毁后注销 resize 监听（避免热更新/多次挂载后重复监听）', () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    const removeSpy = vi.spyOn(window, 'removeEventListener')

    const { stop } = inScope(() => useIsMobile())
    const resizeCall = addSpy.mock.calls.find((call) => call[0] === 'resize')
    expect(resizeCall).toBeDefined()
    const handler = resizeCall?.[1]

    stop()

    expect(removeSpy).toHaveBeenCalledWith('resize', handler)
  })

  it('支持自定义断点（列表/看板等更窄的场景可单独指定）', () => {
    setViewport(760)
    const { value: isNarrow, stop } = inScope((): Ref<boolean> => useIsMobile(768))
    expect(isNarrow.value).toBe(true)

    setViewport(800)
    expect(isNarrow.value).toBe(false)
    stop()
  })
})
