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
  Document,
  FolderOpened,
  HomeFilled,
  Tickets,
  UserFilled,
} from '@element-plus/icons-vue'

import { APP_TITLE, MENU_ITEMS } from '@/router/routes'

const props = defineProps<{ collapsed: boolean }>()

/** 菜单图标名 → 组件。不用全局注册：全量注册图标会把 300+ 个组件带进产物。 */
const ICONS: Record<string, Component> = {
  HomeFilled,
  Tickets,
  FolderOpened,
  UserFilled,
  Bell,
  Document,
}

function iconFor(name: string): Component {
  return ICONS[name] ?? Tickets
}

const route = useRoute()

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
  <div class="tf-sidebar">
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
      <el-menu-item v-for="item in MENU_ITEMS" :key="item.path" :index="item.path">
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
  height: 56px;
  padding: 0 16px;
  border-bottom: 1px solid #e4e7ed;
  white-space: nowrap;
  overflow: hidden;
}

.tf-sidebar__logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background-color: #409eff;
  color: #ffffff;
  font-size: 13px;
  font-weight: 700;
}

.tf-sidebar__brand-text {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.tf-sidebar__menu {
  flex: 1;
  border-right: none;
}
</style>
