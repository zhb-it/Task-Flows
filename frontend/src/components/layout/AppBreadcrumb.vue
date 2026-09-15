<script setup lang="ts">
/**
 * 面包屑（前端规格 §61）。
 *
 * 轨迹从两个来源拼出来，而不是靠给每条路由手写 `breadcrumb` 字段：
 *
 * - **板块层**：用当前路径在 `MENU_ITEMS` 里做最长前缀匹配（`/teams/3` → 「团队」）。
 * - **当前层**：`route.meta.title`（详情页自己的标题）。
 *
 * 这样新增路由时只需要写 `meta.title`，面包屑自动正确；漏写 title 时也不会有
 * 半截路径，只是少一层。
 *
 * 首页（`/dashboard`）自己就是根，不再重复显示「首页 / 首页」。
 */

import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { MENU_ITEMS } from '@/router/routes'

interface Crumb {
  title: string
  /** 可点击时的目标路径；最后一级（当前页）不带 to。 */
  to?: string
}

const route = useRoute()

const isHome = computed(() => route.name === 'dashboard')

const crumbs = computed<Crumb[]>(() => {
  if (isHome.value) {
    return []
  }

  const items: Crumb[] = []
  const section = MENU_ITEMS.filter((item) => route.path.startsWith(`${item.path}/`)).reduce<
    (typeof MENU_ITEMS)[number] | null
  >((acc, item) => (acc === null || item.path.length > acc.path.length ? item : acc), null)

  if (section) {
    items.push({ title: section.title, to: section.path })
  }

  const title = typeof route.meta.title === 'string' ? route.meta.title : ''
  if (title && title !== section?.title) {
    items.push({ title })
  }

  return items
})
</script>

<template>
  <el-breadcrumb separator="/" class="tf-breadcrumb">
    <el-breadcrumb-item :to="{ name: 'dashboard' }">首页</el-breadcrumb-item>
    <el-breadcrumb-item v-for="crumb in crumbs" :key="crumb.title" :to="crumb.to">
      {{ crumb.title }}
    </el-breadcrumb-item>
  </el-breadcrumb>
</template>

<style scoped>
.tf-breadcrumb {
  margin-bottom: 12px;
}
</style>
