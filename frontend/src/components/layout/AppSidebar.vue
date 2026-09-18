<script setup lang="ts">
/**
 * 侧边栏（前端规格 §6 / §61）。
 *
 * 菜单项来自 `router/routes.ts` 的 `MENU_ITEMS` —— **唯一事实来源**。这样
 * 「菜单里有一个入口，但点进去是 404」这种问题在结构上不可能发生。
 *
 * 高亮规则：详情页应点亮它所属的列表项。`/teams/3` 不属于任何菜单项的精确
 * 路径，因此按「最长前缀匹配」回退到 `/teams`；`/tasks/board` 也会点亮
 * `/tasks`，符合「我还在任务这个板块里」的直觉。
 */

import type { Component } from 'vue'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  Bell,
  Brush,
  Document,
  FolderOpened,
  HomeFilled,
  Lock,
  Tickets,
  UserFilled,
} from '@element-plus/icons-vue'

import { APP_TITLE, MENU_ITEMS, type MenuItem } from '@/router/routes'
import { useAuthStore } from '@/stores/auth'
import { hasAnyPermission } from '@/utils/permission'

const props = defineProps<{ collapsed: boolean }>()

/** 菜单图标名 → 组件。不用全局注册：全量注册图标会把 300+ 个组件带进产物。 */
const ICONS: Record<string, Component> = {
  HomeFilled,
  Tickets,
  FolderOpened,
  UserFilled,
  Bell,
  Document,
  Lock,
  Brush,
}

function iconFor(name: string): Component {
  return ICONS[name] ?? Tickets
}

const route = useRoute()
const authStore = useAuthStore()

/**
 * 按权限过滤菜单（TASK-084）：声明了 `requiresAnyPermission` 的项只在当前
 * 用户持有其一（OR 语义）时显示。权限集合为空（拉取失败/未登录）时受控项
 * 隐藏——后端 403 仍然兜底，这里只管入口观感。
 */
const visibleMenuItems = computed<readonly MenuItem[]>(() =>
  MENU_ITEMS.filter(
    (item) =>
      !item.requiresAnyPermission ||
      hasAnyPermission(authStore.permissions, ...item.requiresAnyPermission),
  ),
)

const activePath = computed(() => {
  const matched = MENU_ITEMS.filter(
    (item) => route.path === item.path || route.path.startsWith(`${item.path}/`),
  )
  // 最长前缀优先：`/tasks/board` 同时匹配 `/tasks`，但只应该有一条被点亮。
  const longest = matched.reduce<string | null>(
    (acc, item) => (acc === null || item.path.length > acc.length ? item.path : acc),
    null,
  )
  return longest ?? route.path
})
</script>

<template>
  <div id="tf-sidebar" class="tf-sidebar">
    <div class="tf-sidebar__brand">
      <span class="tf-sidebar__logo">TF</span>
      <span v-if="!props.collapsed" class="tf-sidebar__brand-text">{{ APP_TITLE }}</span>
    </div>

    <el-menu
      :default-active="activePath"
      :collapse="props.collapsed"
      :collapse-transition="false"
      router
      class="tf-sidebar__menu"
    >
      <el-menu-item v-for="item in visibleMenuItems" :key="item.path" :index="item.path">
        <el-icon><component :is="iconFor(item.icon)" /></el-icon>
        <template #title>{{ item.title }}</template>
      </el-menu-item>
    </el-menu>
  </div>
</template>

<style scoped>
.tf-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.tf-sidebar__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: var(--tf-header-height);
  padding: 0 16px;
  border-bottom: 1px solid var(--border-color);
  white-space: nowrap;
  overflow: hidden;
  transition: border-color var(--motion-base);
}

.tf-sidebar__logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background-color: var(--brand-600);
  color: var(--text-on-brand);
  font-size: 13px;
  font-weight: 700;
  box-shadow: var(--shadow-brand);
}

.tf-sidebar__brand-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.tf-sidebar__menu {
  flex: 1;
  border-right: none;
}
</style>
