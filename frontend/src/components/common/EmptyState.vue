<script setup lang="ts">
/**
 * 空状态组件（前端方案 §5「空状态组件 EmptyState.vue」，TASK-130 落地）。
 *
 * 为什么要自研而不是直接用 `el-empty`：本项目大量列表页的空态是**两种完全
 * 不同的事**，用同一句话表达会让人不知道下一步做什么——
 *
 * - 「还没有数据」：账号/项目刚建立，应该给**创建**动作；
 * - 「筛选后没有结果」：数据存在但被自己的筛选条件排除了，应该给**清除筛选**
 *   动作，而不是让人以为数据没了（旧版 `ProjectList` 把两者合成一句
 *   「还没有项目，或筛选无匹配」，用户无法判断到底是哪种）。
 *
 * 所以本组件只负责「把空态讲清楚并给出出口」这一件事：标题说清是什么，
 * 描述说清为什么/怎么办，`#actions` 槽放一个明确的主行动。**插画是内联 SVG**
 * （不引外部图片，随主题换色、不增加请求）。
 *
 * 用法：
 * ```vue
 * <EmptyState
 *   :icon="Search"
 *   title="没有匹配的项目"
 *   description="试着换个关键字，或清空筛选条件。"
 * >
 *   <el-button type="primary" @click="resetFilters">清除筛选</el-button>
 * </EmptyState>
 * ```
 */

import type { Component } from 'vue'
import { computed } from 'vue'
import { Box } from '@element-plus/icons-vue'

const props = withDefaults(
  defineProps<{
    /** 主标题（必填）：一句话说清「这里为什么是空的」。 */
    title: string
    /** 补充说明：为什么空、下一步可以做什么。 */
    description?: string
    /** 图标组件（`@element-plus/icons-vue` 里的任意一个）。 */
    icon?: Component
    /**
     * 尺寸：`md` 用于整页/整块内容区，`sm` 用于卡片内或表格内的小空态。
     * 文案与间距随之收紧，避免小容器里出现一个占半屏的巨幅空态。
     */
    size?: 'sm' | 'md'
  }>(),
  { description: '', icon: undefined, size: 'md' },
)

const iconComponent = computed<Component>(() => props.icon ?? Box)
</script>

<template>
  <div class="tf-empty" :class="`tf-empty--${props.size}`" role="status">
    <span class="tf-empty__art" aria-hidden="true">
      <!-- 内联 SVG：外圈柔光 + 主题色的面板图形，随明暗主题自动换色 -->
      <svg class="tf-empty__svg" viewBox="0 0 96 72" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="8" y="10" width="80" height="52" rx="10" class="tf-empty__svg-panel" />
        <path d="M22 26h30" class="tf-empty__svg-line" />
        <path d="M22 36h20" class="tf-empty__svg-line" />
        <path d="M22 46h26" class="tf-empty__svg-line" />
      </svg>
      <el-icon class="tf-empty__icon"><component :is="iconComponent" /></el-icon>
    </span>

    <p class="tf-empty__title">{{ props.title }}</p>
    <p v-if="props.description" class="tf-empty__desc">{{ props.description }}</p>

    <div v-if="$slots.actions" class="tf-empty__actions">
      <slot name="actions" />
    </div>
    <div v-else-if="$slots.default" class="tf-empty__actions">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.tf-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--space-10) var(--space-4);
}

.tf-empty--sm {
  padding: var(--space-6) var(--space-3);
}

.tf-empty__art {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 96px;
  height: 72px;
  margin-bottom: var(--space-4);
}

.tf-empty--sm .tf-empty__art {
  width: 64px;
  height: 48px;
  margin-bottom: var(--space-3);
}

.tf-empty__svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0.55;
}

.tf-empty__svg-panel {
  fill: var(--bg-surface-2);
  stroke: var(--border-color);
}

.tf-empty__svg-line {
  stroke: var(--border-strong);
  stroke-width: 2;
  stroke-linecap: round;
}

.tf-empty__icon {
  position: relative;
  font-size: 26px;
  color: var(--brand-500);
}

.tf-empty--sm .tf-empty__icon {
  font-size: 20px;
}

.tf-empty__title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.tf-empty--sm .tf-empty__title {
  font-size: var(--text-base);
}

.tf-empty__desc {
  margin: var(--space-2) 0 0;
  max-width: 42ch;
  font-size: var(--text-sm);
  line-height: 1.7;
  color: var(--text-tertiary);
}

.tf-empty__actions {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-top: var(--space-5);
}
</style>
