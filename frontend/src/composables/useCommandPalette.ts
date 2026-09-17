/**
 * 命令面板状态（Phase B：⌘K / Ctrl+K 命令面板）。
 *
 * 用模块级单例 ref 持有「是否打开」，这样顶栏的触发按钮、全局快捷键监听器、
 * 以及面板组件本身都能共享同一份状态，无需 Pinia 也不需要 provide/inject。
 *
 * 用法：
 *   const { isOpen, open, close, toggle } = useCommandPalette()
 */

import { ref } from 'vue'

const isOpen = ref(false)

function open(): void {
  isOpen.value = true
}

function close(): void {
  isOpen.value = false
}

function toggle(): void {
  isOpen.value = !isOpen.value
}

export function useCommandPalette(): {
  isOpen: typeof isOpen
  open: () => void
  close: () => void
  toggle: () => void
} {
  return { isOpen, open, close, toggle }
}
