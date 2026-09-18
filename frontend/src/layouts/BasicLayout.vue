<script setup lang="ts">
/**
 * 系统主框架（前端规格 §6 整体 UI 布局 / §61 第二阶段 / 方案 Phase D・TASK-130）。
 *
 * ```text
 * ┌──────────────────────────────────────────┐
 * │            顶栏（Header）                 │
 * ├──────────┬───────────────────────────────┤
 * │  侧边栏   │  面包屑 + 页面内容区           │
 * └──────────┴───────────────────────────────┘
 * ```
 *
 * ## 两套侧栏形态（窄屏是**抽屉**，不只是「折叠」）
 *
 * 规格 §73 原本的做法是「宽度 < 992px 就自动折叠成 64px 图标条」。图标条在
 * 1280 级别的小窗口里够用，但到平板/手机宽度就站不住了：64px 的固定占位 +
 * 内容区的最小宽度会直接挤出横向滚动条，图标也失去可读性（只剩图形没有文字，
 * 对不熟悉产品的人等于没有导航）。
 *
 * 因此这里按宽度分成两种形态，各自内部一致：
 *
 * | 宽度 | 侧栏形态 | 顶栏按钮行为 |
 * | --- | --- | --- |
 * | `>= 992` | 常驻，可在 240px / 64px 间折叠 | 折叠 / 展开 |
 * | `< 992` | **抽屉浮层**（带遮罩，覆盖内容） | 打开 / 关闭抽屉 |
 *
 * 断点值以 `composables/useBreakpoint.ts` 的 `MOBILE_BREAKPOINT` 为唯一来源；
 * `tests/unit/use-breakpoint.spec.ts` 直接测断点逻辑，`tests/unit/responsive.spec.ts`
 * 断言「窄屏分支渲染抽屉、宽屏分支渲染常驻侧栏」的契约——避免「有人改了断点却
 * 漏改另一套形态」这类只靠肉眼发现的漂移。
 *
 * 抽屉在两个时机关闭：路由变化（点了菜单就该看到目标页）与窗口变宽
 * （已经不需要浮层了）。Esc 关闭由 `el-drawer` 自带行为提供。
 */

import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import AppBreadcrumb from '@/components/layout/AppBreadcrumb.vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import { DRAWER_WIDTH, useIsMobile } from '@/composables/useBreakpoint'

const route = useRoute()

/** 是否处于窄屏形态（抽屉）。 */
const isMobile = useIsMobile()
/** 桌面形态下侧栏是否折叠成图标条。 */
const collapsed = ref(false)
/** 窄屏形态下抽屉是否展开。 */
const drawerOpen = ref(false)

function toggleSidebar(): void {
  if (isMobile.value) {
    drawerOpen.value = !drawerOpen.value
    return
  }
  collapsed.value = !collapsed.value
}

// 从窄屏回到宽屏时，直接给完整侧栏（用户刚在抽屉里点过导航，继续给图标条会
// 让人以为菜单坏了）；进入窄屏时抽屉自带宽度，「折叠」状态在那里没有意义。
watch(isMobile, (mobile) => {
  drawerOpen.value = false
  if (!mobile) {
    collapsed.value = false
  }
})

// 路由变化后收起抽屉：抽屉是浮层，停留在目标页面上会挡住刚打开的内容。
watch(
  () => route.fullPath,
  () => {
    drawerOpen.value = false
  },
)
</script>

<template>
  <el-container class="tf-layout">
    <!-- 窄屏：抽屉浮层（不占布局宽度，内容区拿回全宽） -->
    <el-drawer
      v-if="isMobile"
      v-model="drawerOpen"
      class="tf-layout__drawer"
      direction="ltr"
      :size="DRAWER_WIDTH"
      :with-header="false"
      aria-label="主导航"
    >
      <AppSidebar :collapsed="false" />
    </el-drawer>

    <!-- 宽屏：常驻侧栏，可折叠 -->
    <el-aside
      v-else
      :width="collapsed ? 'var(--tf-sidebar-collapsed-width)' : 'var(--tf-sidebar-width)'"
      class="tf-layout__aside"
    >
      <AppSidebar :collapsed="collapsed" />
    </el-aside>

    <el-container class="tf-layout__body">
      <el-header :height="`var(--tf-header-height)`" class="tf-layout__header">
        <AppHeader
          :collapsed="collapsed"
          :is-mobile="isMobile"
          :drawer-open="drawerOpen"
          @toggle-sidebar="toggleSidebar"
        />
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
  background-color: var(--bg-surface);
  border-right: 1px solid var(--border-color);
  /* 折叠时宽度变化要平滑，否则整个内容区会「跳」一下。 */
  transition:
    width var(--motion-base),
    background-color var(--motion-base),
    border-color var(--motion-base);
  overflow: hidden;
}

.tf-layout__header {
  padding: 0;
  background-color: var(--bg-surface);
  border-bottom: 1px solid var(--border-color);
  transition:
    background-color var(--motion-base),
    border-color var(--motion-base);
}

.tf-layout__main {
  padding: var(--space-4);
  overflow-y: auto;
  background-color: var(--bg-page);
  transition: background-color var(--motion-base);
}

/* 窄屏：内容区拿到全宽后，内边距也收紧，给正文多留一点横向空间。 */
@media (max-width: 767px) {
  .tf-layout__main {
    padding: var(--space-3);
  }
}
</style>

<style>
/* 抽屉内边距清零：`AppSidebar` 自带品牌区与菜单的分隔线，外面再套一层
   默认的 20px 会让导航看起来缩在中间。（非 scoped：目标是 el-drawer 的
   内部元素，作用于本组件渲染出的抽屉实例。） */
.tf-layout__drawer .el-drawer__body {
  padding: 0;
}
</style>
