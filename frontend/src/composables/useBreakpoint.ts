/**
 * 响应式断点（前端方案 Phase D・TASK-130）。
 *
 * 为什么单独抽一个 composable，而不是把 `window.innerWidth < 992` 写在布局组件里：
 *
 * 1. **断点值要有唯一来源**。它同时被布局（侧栏形态）、测试与文档引用，
 *    散落成字面量就会漂移；
 * 2. **断点逻辑要能被测**。这里只做「宽度 → 布尔」的映射与监听/清理，
 *    不依赖任何组件，测试可以直接 `effectScope()` 起来跑，不需要挂载整个布局；
 * 3. 布局组件里剩下的只有「布尔 → 抽屉 or 常驻侧栏」的渲染分支，读起来是纯视图逻辑。
 *
 * 使用：
 * ```ts
 * const isMobile = useIsMobile()          // 默认为 MOBILE_BREAKPOINT
 * const isNarrow = useIsMobile(768)       // 需要别的断点时显式传入
 * ```
 */

import { onScopeDispose, ref, type Ref } from 'vue'

/**
 * 侧栏从「常驻可折叠」切到「抽屉浮层」的宽度断点（px）。
 *
 * 992 来自前端规格 §73（`< 992` 视为窄屏）；选它同时与 Element Plus 的
 * `md` 断点（≥992）对齐，避免出现「EP 认为这是桌面、我们认为是移动」的错位。
 */
export const MOBILE_BREAKPOINT = 992

/** 抽屉宽度：与常驻侧栏同宽，形态切换时导航的位置感不变。 */
export const DRAWER_WIDTH = '240px'

/**
 * 当前视口是否窄于给定断点，并在 `resize` 时保持同步。
 *
 * 首帧就用 `window.innerWidth` 求值（不等到 `onMounted`），否则窄屏刷新会先
 * 画出一次桌面侧栏再跳成抽屉。SSR / 无 `window` 环境下退化为 `false`。
 * 监听器通过 `onScopeDispose` 清理，所以调用方不需要自己写卸载逻辑。
 */
export function useIsMobile(breakpoint: number = MOBILE_BREAKPOINT): Ref<boolean> {
  const matches = (): boolean =>
    typeof window === 'undefined' ? false : window.innerWidth < breakpoint

  const isMobile = ref(matches())

  if (typeof window !== 'undefined') {
    const onResize = (): void => {
      isMobile.value = matches()
    }
    window.addEventListener('resize', onResize)
    onScopeDispose(() => window.removeEventListener('resize', onResize))
  }

  return isMobile
}
