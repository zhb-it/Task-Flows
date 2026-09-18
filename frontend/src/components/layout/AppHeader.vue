<script setup lang="ts">
/**
 * 顶栏（前端规格 §6 / §61 / 方案 Phase D・TASK-130）。
 *
 * 四块内容：侧栏开关、命令面板入口、主题切换、通知铃铛与用户菜单。
 *
 * 侧栏状态由布局层（`BasicLayout`）持有，这里只通过 `props` 读、通过事件请求
 * 切换——子组件不直接改父组件的状态。同一个按钮在两种形态下语义不同（宽屏
 * 折叠 / 窄屏开抽屉），所以文案与 `aria-expanded` 都要跟着形态走，不能只换图标。
 *
 * 所有颜色/间距都取自 `assets/styles/tokens.css`。**这里曾经踩过坑**：早期用了
 * 一套从未定义过的 `--tf-border` / `--tf-bg` 等变量名，CSS 变量未定义时整条声明
 * 静默失效（不是报错），按钮于是变成「无边框、透明底、方角」的样子。现在由
 * `tests/unit/design-tokens.spec.ts` 兜底：引用了没定义的变量会直接测挂。
 */

import { computed, onMounted } from 'vue'
import { Expand, Fold, Menu, Moon, Search, Sunny } from '@element-plus/icons-vue'

import NotificationBell from '@/components/layout/NotificationBell.vue'
import UserMenu from '@/components/layout/UserMenu.vue'
import { useNotificationStore } from '@/stores/notification'
import { useTheme } from '@/composables/useTheme'
import { useCommandPalette } from '@/composables/useCommandPalette'

const props = defineProps<{
  /** 宽屏形态下侧栏是否折叠。 */
  collapsed: boolean
  /** 是否处于窄屏形态（侧栏是抽屉）。 */
  isMobile: boolean
  /** 窄屏形态下抽屉是否已展开（用于 `aria-expanded`）。 */
  drawerOpen: boolean
}>()

const emit = defineEmits<{ 'toggle-sidebar': [] }>()

const notifications = useNotificationStore()
const { isDark, toggleTheme } = useTheme()
const { open: openPalette } = useCommandPalette()

/** 修饰键提示：macOS 显示 ⌘，其余显示 Ctrl（命令面板全局快捷键语义一致）。 */
const modKey = computed(() =>
  typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
    ? '⌘'
    : 'Ctrl',
)

/** 同一按钮两种语义：窄屏是「开关导航抽屉」，宽屏是「折叠/展开侧栏」。 */
const toggleLabel = computed(() => {
  if (props.isMobile) {
    return props.drawerOpen ? '关闭导航菜单' : '打开导航菜单'
  }
  return props.collapsed ? '展开侧边栏' : '收起侧边栏'
})

const sidebarExpanded = computed(() =>
  props.isMobile ? props.drawerOpen : !props.collapsed,
)

// 进主框架时拉一次通知预览，让铃铛的未读角标一开始就是对的。
// 失败与否都不影响页面（store 内部静默处理）。
onMounted(() => {
  void notifications.loadPreview()
})
</script>

<template>
  <div class="tf-header">
    <el-button
      text
      class="tf-header__toggle"
      :aria-label="toggleLabel"
      :title="toggleLabel"
      :aria-expanded="sidebarExpanded"
      aria-controls="tf-sidebar"
      @click="emit('toggle-sidebar')"
    >
      <el-icon :size="18">
        <!-- 窄屏用汉堡（= 抽屉），宽屏用折叠箭头（= 宽度变化） -->
        <Menu v-if="props.isMobile" />
        <Expand v-else-if="props.collapsed" />
        <Fold v-else />
      </el-icon>
    </el-button>

    <div class="tf-header__spacer" />

    <button
      class="tf-header__search"
      type="button"
      aria-label="打开命令面板"
      @click="openPalette"
    >
      <el-icon><Search /></el-icon>
      <span class="tf-header__search-text">搜索或跳转</span>
      <kbd class="tf-header__kbd">{{ modKey }}K</kbd>
    </button>

    <el-tooltip
      :content="isDark ? '切换到浅色' : '切换到深色'"
      placement="bottom"
    >
      <el-button
        text
        class="tf-header__theme"
        :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'"
        @click="toggleTheme"
      >
        <el-icon :size="18">
          <Moon v-if="isDark" />
          <Sunny v-else />
        </el-icon>
      </el-button>
    </el-tooltip>

    <NotificationBell />
    <UserMenu />
  </div>
</template>

<style scoped>
.tf-header {
  display: flex;
  align-items: center;
  height: 100%;
  padding: 0 var(--space-4);
  gap: var(--space-2);
}

.tf-header__toggle {
  padding: 6px;
}

.tf-header__theme {
  padding: 6px;
}

.tf-header__search {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: 34px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  color: var(--text-tertiary);
  font-family: inherit;
  font-size: var(--text-sm);
  cursor: pointer;
  transition:
    border-color var(--motion-fast),
    color var(--motion-fast);
}

.tf-header__search:hover {
  border-color: var(--brand-400);
  color: var(--brand-600);
}

.tf-header__search:focus-visible {
  outline: 2px solid var(--brand-400);
  outline-offset: 1px;
}

.tf-header__search-text {
  white-space: nowrap;
}

.tf-header__kbd {
  padding: 1px 6px;
  font-size: 11px;
  font-family: inherit;
  color: var(--text-tertiary);
  background: var(--bg-surface-2);
  border: 1px solid var(--border-color);
  border-radius: 4px;
}

.tf-header__spacer {
  flex: 1;
}

/* 窄屏：搜索入口退化成纯图标按钮（「搜索或跳转」文案 + 快捷键提示在这里
   只会挤压通知与头像），但按钮本身保留——命令面板是窄屏下唯一的快速导航。 */
@media (max-width: 767px) {
  .tf-header {
    padding: 0 var(--space-3);
    gap: var(--space-1);
  }

  .tf-header__search {
    padding: 0 var(--space-2);
  }

  .tf-header__search-text,
  .tf-header__kbd {
    display: none;
  }
}
</style>
