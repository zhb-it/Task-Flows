<script setup lang="ts">
/**
 * 系统主框架（前端规格 §6 整体 UI 布局 / §61 第二阶段）。
 *
 * ```text
 * ┌──────────────────────────────────────────┐
 * │            顶栏（Header）                 │
 * ├──────────┬───────────────────────────────┤
 * │  侧边栏   │  面包屑 + 页面内容区           │
 * └──────────┴───────────────────────────────┘
 * ```
 *
 * 侧边栏折叠状态由本组件持有：顶栏的折叠按钮与侧边栏都要用它，放在共同父级
 * 是最短的传递路径（避免为一个布尔值引入 Pinia store）。
 *
 * 响应式（规格 §73）：窗口宽度小于 992px 时自动折叠。规格列出的目标分辨率
 * （1280 起）在折叠后都能容纳侧边栏 + 内容区，更窄的屏幕上手动展开即可。
 */

import { onBeforeUnmount, onMounted, ref } from 'vue'

import AppBreadcrumb from '@/components/layout/AppBreadcrumb.vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'

/** 小于此宽度（px）时自动折叠侧边栏。 */
const SIDEBAR_COLLAPSE_BREAKPOINT = 992

const collapsed = ref(false)

function toggleSidebar(): void {
  collapsed.value = !collapsed.value
}

function applyViewportRule(): void {
  if (window.innerWidth < SIDEBAR_COLLAPSE_BREAKPOINT) {
    collapsed.value = true
  }
}

onMounted(() => {
  applyViewportRule()
  window.addEventListener('resize', applyViewportRule)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', applyViewportRule)
})
</script>

<template>
  <el-container class="tf-layout">
    <el-aside :width="collapsed ? '64px' : '220px'" class="tf-layout__aside">
      <AppSidebar :collapsed="collapsed" />
    </el-aside>

    <el-container class="tf-layout__body">
      <el-header height="56px" class="tf-layout__header">
        <AppHeader :collapsed="collapsed" @toggle-sidebar="toggleSidebar" />
      </el-header>

      <el-main class="tf-layout__main">
        <AppBreadcrumb />
        <router-view v-slot="{ Component }">
          <transition name="tf-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.tf-layout {
  height: 100%;
}

.tf-layout__aside {
  background-color: #ffffff;
  border-right: 1px solid #e4e7ed;
  /* 折叠时宽度变化要平滑，否则整个内容区会「跳」一下。 */
  transition: width 0.2s ease;
  overflow: hidden;
}

.tf-layout__header {
  padding: 0;
  background-color: #ffffff;
  border-bottom: 1px solid #e4e7ed;
}

.tf-layout__main {
  padding: 16px;
  overflow-y: auto;
}
</style>
