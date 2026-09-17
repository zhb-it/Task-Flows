/**
 * 主题管理组合式（Phase A：双主题底座）。
 *
 * 三种模式：
 *   - 'light'  强制浅色
 *   - 'dark'   强制深色
 *   - 'system' 跟随系统 `prefers-color-scheme`（默认，最省心）
 *
 * 实现要点：
 *   - 单一真相：`<html>` 上挂 `dark` class 即深色；其余样式全部由 CSS 变量驱动。
 *   - 持久化：用户选择存 `localStorage`，刷新不丢失；'system' 时实时监听系统切换。
 *   - 不引入任何依赖，纯 DOM class 操作，零运行时成本。
 *
 * 用法：
 *   const { theme, isDark, setTheme, toggle } = useTheme()
 *   onMounted(initTheme)  // 在 App.vue 里只调一次
 */

import { ref, watch, type Ref } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'tf-theme-mode'

const theme = ref<ThemeMode>('system')
const isDark = ref(false)

let mediaQuery: MediaQueryList | null = null

function systemPrefersDark(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  )
}

/** 根据当前 mode 计算并落 DOM class。 */
function apply(): void {
  const dark =
    theme.value === 'dark' || (theme.value === 'system' && systemPrefersDark())
  isDark.value = dark
  document.documentElement.classList.toggle('dark', dark)
}

function onSystemChange(): void {
  // 仅 'system' 模式下跟随系统变化。
  if (theme.value === 'system') apply()
}

/** 在应用入口（App.vue onMounted）调用一次：读存储 + 初始化 + 监听系统。 */
export function initTheme(): void {
  const saved = localStorage.getItem(STORAGE_KEY) as ThemeMode | null
  if (saved === 'light' || saved === 'dark' || saved === 'system') {
    theme.value = saved
  }
  apply()

  mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  // 兼容旧浏览器（addEventListener 在 MediaQueryList 上较新）。
  if (mediaQuery.addEventListener) {
    mediaQuery.addEventListener('change', onSystemChange)
  } else if (mediaQuery.addListener) {
    mediaQuery.addListener(onSystemChange)
  }
}

/** 切换三种模式，落存储并即时生效。 */
export function setTheme(mode: ThemeMode): void {
  theme.value = mode
  localStorage.setItem(STORAGE_KEY, mode)
  apply()
}

/** 在 light/dark 间切换（system 会被显式覆盖为具体值）。 */
export function toggleTheme(): void {
  setTheme(isDark.value ? 'light' : 'dark')
}

// 响应式：theme 变化时同步 isDark（供模板直接读）。
watch(theme, apply)

export function useTheme(): {
  theme: Ref<ThemeMode>
  isDark: Ref<boolean>
  setTheme: (mode: ThemeMode) => void
  toggleTheme: () => void
  initTheme: () => void
} {
  return { theme, isDark, setTheme, toggleTheme, initTheme }
}
