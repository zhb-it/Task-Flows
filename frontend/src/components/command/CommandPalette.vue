<script setup lang="ts">
/**
 * 命令面板（Phase B：⌘K / Ctrl+K）。
 *
 * 一个 Linear / Notion 式的全局命令面板：在任何页面按 ⌘K（macOS）或 Ctrl+K（Win）
 * 唤起，输入关键字即可跳转路由、切换主题、退出登录。纯客户端实现，不依赖任何
 * 后端接口——所有命令都是「导航」或「本地动作」。
 *
 * 交互细节：
 *   - 全局监听 ⌘K/Ctrl+K 切换开关；在输入框里按这两键也能切换（符合直觉）。
 *   - 非输入态下按 `?` 也能唤起（顺手暴露快捷键体系）。
 *   - 面板内：↑/↓ 移动高亮、↵ 执行、esc 关闭；选中项自动滚入视野。
 *   - 浮层用 <Teleport> 挂到 body，避免被布局的 overflow 裁剪。
 *
 * 命令来源（与侧边栏、主题、认证 store 同源，避免各写一套）：
 *   - 导航：复用 `MENU_ITEMS` + 设计系统页；
 *   - 外观：浅色 / 深色 / 跟随系统（useTheme）；
 *   - 操作：退出登录（useAuthStore，登出后跳登录页）。
 */

import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
  type Component,
} from 'vue'
import { useRouter } from 'vue-router'
import {
  Bell,
  Brush,
  Document,
  FolderOpened,
  HomeFilled,
  Lock,
  Moon,
  Search,
  Setting,
  Sunny,
  SwitchButton,
  Tickets,
  UserFilled,
} from '@element-plus/icons-vue'

import { useCommandPalette } from '@/composables/useCommandPalette'
import { useTheme, type ThemeMode } from '@/composables/useTheme'
import { useAuthStore } from '@/stores/auth'
import { MENU_ITEMS } from '@/router/routes'

const { isOpen, close, toggle } = useCommandPalette()
const router = useRouter()
const { setTheme } = useTheme()
const auth = useAuthStore()

interface Command {
  id: string
  title: string
  group: string
  icon: Component
  keywords?: string
  run: () => void | Promise<void>
}

/** 侧边栏图标名 → 组件（与 AppSidebar 同源，新增菜单项时同步即可）。 */
const ICONS: Record<string, Component> = {
  HomeFilled,
  Tickets,
  FolderOpened,
  UserFilled,
  Bell,
  Document,
  Lock,
}

const query = ref('')
const selected = ref(0)
const inputRef = ref<HTMLInputElement | null>(null)
const listRef = ref<HTMLElement | null>(null)

const commands = computed<Command[]>(() => {
  const nav: Command[] = MENU_ITEMS.map((m) => ({
    id: `nav:${m.path}`,
    title: m.title,
    group: '导航',
    icon: ICONS[m.icon] ?? HomeFilled,
    keywords: m.path,
    run: () => {
      void router.push(m.path)
    },
  }))

  const design: Command = {
    id: 'nav:design-system',
    title: '设计系统',
    group: '导航',
    icon: Brush,
    keywords: '/design-system 主题 token 配色',
    run: () => {
      void router.push('/design-system')
    },
  }

  const themeCmds: Command[] = (
    [
      ['light', '切换到浅色主题', Sunny],
      ['dark', '切换到深色主题', Moon],
      ['system', '跟随系统主题', Setting],
    ] as const
  ).map(([mode, title, icon]) => ({
    id: `theme:${mode}`,
    title,
    group: '外观',
    icon,
    keywords: 'theme dark light 主题 外观 暗色',
    run: () => setTheme(mode as ThemeMode),
  }))

  const actions: Command[] = [
    {
      id: 'action:logout',
      title: '退出登录',
      group: '操作',
      icon: SwitchButton,
      keywords: 'logout 登出 退出 账号',
      run: async () => {
        await auth.logout()
        await router.push('/login')
      },
    },
  ]

  return [...nav, design, ...themeCmds, ...actions]
})

const filtered = computed<Command[]>(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return commands.value
  return commands.value.filter((c) =>
    `${c.title} ${c.keywords ?? ''}`.toLowerCase().includes(q),
  )
})

/** 渲染用的扁平列表：分组标题与命令项交错，命令项带全局序号用于键盘定位。 */
const renderList = computed(() => {
  const out: (
    | { kind: 'header'; name: string }
    | { kind: 'item'; cmd: Command; index: number }
  )[] = []
  let idx = 0
  const groups = new Map<string, Command[]>()
  for (const c of filtered.value) {
    if (!groups.has(c.group)) groups.set(c.group, [])
    groups.get(c.group)!.push(c)
  }
  for (const [name, items] of groups) {
    out.push({ kind: 'header', name })
    for (const cmd of items) {
      out.push({ kind: 'item', cmd, index: idx })
      idx++
    }
  }
  return out
})

function runAt(index: number): void {
  const cmd = filtered.value[index]
  if (!cmd) return
  close()
  void cmd.run()
}

function onInputKeydown(e: KeyboardEvent): void {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    selected.value = Math.min(selected.value + 1, filtered.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    selected.value = Math.max(selected.value - 1, 0)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    runAt(selected.value)
  } else if (e.key === 'Escape') {
    e.preventDefault()
    close()
  }
}

function isTypingTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || el.isContentEditable
}

function onGlobalKeydown(e: KeyboardEvent): void {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    toggle()
    return
  }
  if (e.key === '?' && !isTypingTarget(e.target) && !isOpen.value) {
    e.preventDefault()
    toggle()
  }
}

// 选中项滚入视野（面板内列表较长时高亮不会跑出可视区）。
watch(selected, async () => {
  await nextTick()
  const el = listRef.value?.querySelector<HTMLElement>(
    `[data-index="${selected.value}"]`,
  )
  el?.scrollIntoView({ block: 'nearest' })
})

// 打开即清空查询、重置高亮并聚焦输入框。
watch(isOpen, (open) => {
  if (open) {
    query.value = ''
    selected.value = 0
    void nextTick(() => inputRef.value?.focus())
  }
})

watch(filtered, () => {
  selected.value = 0
})

onMounted(() => window.addEventListener('keydown', onGlobalKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobalKeydown))
</script>

<template>
  <Teleport to="body">
    <Transition name="tf-palette">
      <div
        v-if="isOpen"
        class="tf-palette"
        role="dialog"
        aria-modal="true"
        aria-label="命令面板"
        @click.self="close"
      >
        <div class="tf-palette__panel">
          <div class="tf-palette__search">
            <el-icon class="tf-palette__search-icon"><Search /></el-icon>
            <input
              ref="inputRef"
              v-model="query"
              class="tf-palette__input"
              type="text"
              placeholder="搜索页面、切换主题、执行操作…"
              aria-label="搜索命令"
              @keydown="onInputKeydown"
            />
            <kbd class="tf-palette__esc">esc</kbd>
          </div>

          <div ref="listRef" class="tf-palette__list">
            <template v-for="(row, i) in renderList" :key="i">
              <div v-if="row.kind === 'header'" class="tf-palette__group">
                {{ row.name }}
              </div>
              <button
                v-else
                class="tf-palette__item"
                :class="{ 'is-active': row.index === selected }"
                :data-index="row.index"
                type="button"
                @mousemove="selected = row.index"
                @click="runAt(row.index)"
              >
                <el-icon class="tf-palette__item-icon"><component :is="row.cmd.icon" /></el-icon>
                <span class="tf-palette__item-title">{{ row.cmd.title }}</span>
                <span class="tf-palette__item-enter">↵</span>
              </button>
            </template>

            <div v-if="filtered.length === 0" class="tf-palette__empty">
              没有匹配的命令
            </div>
          </div>

          <div class="tf-palette__footer">
            <span><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
            <span><kbd>↵</kbd> 打开</span>
            <span><kbd>esc</kbd> 关闭</span>
            <span class="tf-palette__footer-spacer" />
            <span><kbd>⌘K</kbd> 命令面板 · <kbd>?</kbd> 快捷键</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.tf-palette {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 12vh;
  background: color-mix(in srgb, var(--tf-overlay) 55%, transparent);
  backdrop-filter: blur(2px);
}

.tf-palette__panel {
  width: min(560px, calc(100vw - 32px));
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  background: var(--tf-surface);
  border: 1px solid var(--tf-border);
  border-radius: var(--tf-radius-lg);
  box-shadow: var(--tf-shadow-lg);
  overflow: hidden;
}

.tf-palette__search {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--tf-border);
}

.tf-palette__search-icon {
  color: var(--tf-text-muted);
  font-size: 18px;
  flex: 0 0 auto;
}

.tf-palette__input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 15px;
  color: var(--tf-text);
}

.tf-palette__input::placeholder {
  color: var(--tf-text-muted);
}

.tf-palette__esc {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--tf-text-muted);
  border: 1px solid var(--tf-border);
  border-radius: 4px;
  padding: 1px 6px;
  background: var(--tf-bg);
}

.tf-palette__list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.tf-palette__group {
  padding: 8px 10px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--tf-text-muted);
}

.tf-palette__item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border: none;
  border-radius: var(--tf-radius-md);
  background: transparent;
  color: var(--tf-text);
  font-size: 14px;
  text-align: left;
  cursor: pointer;
}

.tf-palette__item.is-active {
  background: color-mix(in srgb, var(--brand-500) 14%, transparent);
  color: var(--brand-600);
}

.tf-palette__item-icon {
  font-size: 17px;
  flex: 0 0 auto;
}

.tf-palette__item-title {
  flex: 1;
}

.tf-palette__item-enter {
  opacity: 0;
  font-size: 13px;
  color: var(--tf-text-muted);
}

.tf-palette__item.is-active .tf-palette__item-enter {
  opacity: 1;
}

.tf-palette__empty {
  padding: 28px 12px;
  text-align: center;
  color: var(--tf-text-muted);
  font-size: 14px;
}

.tf-palette__footer {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  border-top: 1px solid var(--tf-border);
  font-size: 12px;
  color: var(--tf-text-muted);
}

.tf-palette__footer-spacer {
  flex: 1;
}

.tf-palette__footer kbd {
  display: inline-block;
  min-width: 18px;
  padding: 1px 5px;
  margin: 0 1px;
  font-size: 11px;
  text-align: center;
  color: var(--tf-text);
  background: var(--tf-bg);
  border: 1px solid var(--tf-border);
  border-radius: 4px;
}

/* 进出场动画：轻微缩放 + 淡入，呼应整体「克制微动效」基调。 */
.tf-palette-leave-active,
.tf-palette-enter-active {
  transition:
    opacity 0.15s ease,
    transform 0.15s ease;
}

.tf-palette-enter-from,
.tf-palette-leave-to {
  opacity: 0;
  transform: scale(0.98);
}
</style>
