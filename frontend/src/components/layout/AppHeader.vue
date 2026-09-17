<script setup lang="ts">
/**
 * 顶栏（前端规格 §6 / §61）。
 *
 * 三块内容：折叠按钮、右侧的用户菜单与通知铃铛。
 *
 * 折叠状态由布局层（`BasicLayout`）持有，这里只通过 `props` 读、通过事件请求切换
 * ——子组件不直接改父组件的状态。
 */

import { computed, onMounted } from 'vue'
import { Expand, Fold, Moon, Search, Sunny } from '@element-plus/icons-vue'

import NotificationBell from '@/components/layout/NotificationBell.vue'
import UserMenu from '@/components/layout/UserMenu.vue'
import { useNotificationStore } from '@/stores/notification'
import { useTheme } from '@/composables/useTheme'
import { useCommandPalette } from '@/composables/useCommandPalette'

const props = defineProps<{ collapsed: boolean }>()

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

// 进主框架时拉一次通知预览，让铃铛的未读角标一开始就是对的。
// 失败与否都不影响页面（store 内部静默处理）。
onMounted(() => {
  void notifications.loadPreview()
})
</script>

<template>
  <div class="tf-header">
    <el-button text class="tf-header__toggle" @click="emit('toggle-sidebar')">
      <el-icon :size="18">
        <Expand v-if="props.collapsed" />
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
  padding: 0 16px;
  gap: 8px;
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
  gap: 8px;
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--tf-border);
  border-radius: var(--tf-radius-md);
  background: var(--tf-bg);
  color: var(--tf-text-muted);
  font-size: 13px;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    color 0.15s ease;
}

.tf-header__search:hover {
  border-color: var(--brand-400);
  color: var(--brand-600);
}

.tf-header__search-text {
  white-space: nowrap;
}

.tf-header__kbd {
  padding: 1px 6px;
  font-size: 11px;
  font-family: inherit;
  color: var(--tf-text-muted);
  background: var(--tf-surface);
  border: 1px solid var(--tf-border);
  border-radius: 4px;
}

.tf-header__spacer {
  flex: 1;
}
</style>
