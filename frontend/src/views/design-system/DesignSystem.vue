<script setup lang="ts">
/**
 * 设计系统展示页（Phase A 验证载体，非业务页面）。
 *
 * 目的：把 `tokens.css` 的设计令牌「看得见、摸得着」——配色、字体、间距、圆角、
 * 阴影、Element Plus 组件，以及一张「首页 Bento 布局」预览。改 tokens.css 后这里
 * 会即时反映，是调主题时最省事的对照面板。
 *
 * 注意：下方 Bento 区块是**布局预览**，数字均为示例，不代表真实接口数据（真实
 * 聚合端点属于后续后端 TASK，前端不伪造接口）。
 */

import { computed } from 'vue'
import { Brush } from '@element-plus/icons-vue'

import { useTheme, type ThemeMode } from '@/composables/useTheme'

const { theme, setTheme } = useTheme()

// 主题单选框的双向绑定模型（get/set 转接到 useTheme）。
const themeModel = computed<ThemeMode>({
  get: () => theme.value,
  set: (v) => setTheme(v),
})

const themeOptions: { label: string; value: ThemeMode }[] = [
  { label: '浅色', value: 'light' },
  { label: '深色', value: 'dark' },
  { label: '跟随系统', value: 'system' },
]

// 品牌色阶（与 tokens.css 一一对应，用于色卡渲染）。
const brandScale: { name: string; varName: string }[] = [
  { name: '50', varName: '--brand-50' },
  { name: '100', varName: '--brand-100' },
  { name: '200', varName: '--brand-200' },
  { name: '300', varName: '--brand-300' },
  { name: '400', varName: '--brand-400' },
  { name: '500', varName: '--brand-500' },
  { name: '600', varName: '--brand-600' },
  { name: '700', varName: '--brand-700' },
  { name: '800', varName: '--brand-800' },
  { name: '900', varName: '--brand-900' },
]

const semanticColors: { name: string; varName: string }[] = [
  { name: 'primary', varName: '--el-color-primary' },
  { name: 'success', varName: '--color-success' },
  { name: 'warning', varName: '--color-warning' },
  { name: 'danger', varName: '--color-danger' },
  { name: 'info', varName: '--color-info' },
]

const neutralColors: { name: string; varName: string }[] = [
  { name: 'bg-page', varName: '--bg-page' },
  { name: 'bg-surface', varName: '--bg-surface' },
  { name: 'bg-surface-2', varName: '--bg-surface-2' },
  { name: 'border', varName: '--border-color' },
  { name: 'text-primary', varName: '--text-primary' },
  { name: 'text-secondary', varName: '--text-secondary' },
  { name: 'text-tertiary', varName: '--text-tertiary' },
]

const spacingScale: { name: string; varName: string }[] = [
  { name: '1', varName: '--space-1' },
  { name: '2', varName: '--space-2' },
  { name: '3', varName: '--space-3' },
  { name: '4', varName: '--space-4' },
  { name: '6', varName: '--space-6' },
  { name: '8', varName: '--space-8' },
  { name: '12', varName: '--space-12' },
]

const radiusScale: { name: string; varName: string }[] = [
  { name: 'sm', varName: '--radius-sm' },
  { name: 'md', varName: '--radius-md' },
  { name: 'lg', varName: '--radius-lg' },
  { name: 'xl', varName: '--radius-xl' },
]

const shadowScale: { name: string; varName: string }[] = [
  { name: 'sm', varName: '--shadow-sm' },
  { name: 'md', varName: '--shadow-md' },
  { name: 'lg', varName: '--shadow-lg' },
  { name: 'brand', varName: '--shadow-brand' },
]

function cssVar(name: string): string {
  return `var(${name})`
}

// Bento 预览用的示例卡片（非真实数据）。
const bentoCards = computed(() => [
  { title: '我的待办', value: '12', hint: '进行中', accent: 'var(--brand-600)', span: 1 },
  { title: '逾期', value: '3', hint: '需关注', accent: 'var(--color-danger)', span: 1 },
  { title: '本周完成', value: '8', hint: '↑ 较上周 +2', accent: 'var(--color-success)', span: 1 },
  { title: '进行中项目', value: '5', hint: '2 个临近里程碑', accent: 'var(--color-info)', span: 2 },
])
</script>

<template>
  <div class="ds">
    <!-- 页头：标题 + 主题切换（实时验证双主题） -->
    <div class="ds__head tf-page__toolbar">
      <div>
        <h1 class="ds__title">
          <el-icon class="ds__title-icon"><Brush /></el-icon>
          设计系统
        </h1>
        <p class="ds__subtitle">TaskFlow Pro 视觉令牌与组件预览 · Phase A 验证载体</p>
      </div>
      <el-radio-group v-model="themeModel">
        <el-radio-button v-for="opt in themeOptions" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </el-radio-button>
      </el-radio-group>
    </div>

    <!-- 配色 -->
    <section class="ds__section">
      <h2 class="ds__h2">品牌色阶</h2>
      <div class="ds__swatches">
        <div v-for="c in brandScale" :key="c.varName" class="ds__swatch">
          <div class="ds__swatch-color" :style="{ background: cssVar(c.varName) }" />
          <div class="ds__swatch-meta">
            <span class="ds__swatch-name">{{ c.name }}</span>
            <code class="ds__swatch-var">{{ c.varName }}</code>
          </div>
        </div>
      </div>
    </section>

    <div class="ds__grid">
      <section class="ds__section">
        <h2 class="ds__h2">语义色</h2>
        <div class="ds__row">
          <div v-for="c in semanticColors" :key="c.varName" class="ds__chip">
            <span class="ds__chip-dot" :style="{ background: cssVar(c.varName) }" />
            {{ c.name }}
          </div>
        </div>
      </section>

      <section class="ds__section">
        <h2 class="ds__h2">中性色</h2>
        <div class="ds__row">
          <div v-for="c in neutralColors" :key="c.varName" class="ds__chip">
            <span class="ds__chip-dot" :style="{ background: cssVar(c.varName) }" />
            {{ c.name }}
          </div>
        </div>
      </section>
    </div>

    <!-- 字体 -->
    <section class="ds__section">
      <h2 class="ds__h2">字体排印</h2>
      <div class="ds__type">
        <p class="ds__type-3xl">标题 30px · 粗体</p>
        <p class="ds__type-2xl">标题 24px · 半粗</p>
        <p class="ds__type-xl">小标题 20px</p>
        <p class="ds__type-base">正文 14px · 这是一段用于观察行高与可读性的示例文字，中文与 Latin 混排时不应出现拥挤或溢出。</p>
        <p class="ds__type-sm">辅助文字 13px</p>
        <p class="ds__type-xs">占位/标注 12px</p>
      </div>
    </section>

    <!-- 间距 / 圆角 / 阴影 -->
    <div class="ds__grid">
      <section class="ds__section">
        <h2 class="ds__h2">间距（8px 网格）</h2>
        <div class="ds__row ds__row--baseline">
          <div v-for="s in spacingScale" :key="s.varName" class="ds__space">
            <span class="ds__space-box" :style="{ width: cssVar(s.varName), height: cssVar(s.varName) }" />
            <code class="ds__space-label">{{ s.varName.replace('--space-', 'sp-') }}</code>
          </div>
        </div>
      </section>

      <section class="ds__section">
        <h2 class="ds__h2">圆角</h2>
        <div class="ds__row ds__row--baseline">
          <div v-for="r in radiusScale" :key="r.varName" class="ds__radius">
            <span
              class="ds__radius-box"
              :style="{ borderRadius: cssVar(r.varName), borderColor: 'var(--border-strong)' }"
            />
            <code class="ds__space-label">{{ r.name }}</code>
          </div>
        </div>
      </section>
    </div>

    <section class="ds__section">
      <h2 class="ds__h2">阴影</h2>
      <div class="ds__row">
        <div v-for="s in shadowScale" :key="s.varName" class="ds__shadow">
          <span class="ds__shadow-box" :style="{ boxShadow: cssVar(s.varName) }" />
          <code class="ds__space-label">{{ s.varName.replace('--shadow-', '') }}</code>
        </div>
      </div>
    </section>

    <!-- Element Plus 组件预览 -->
    <section class="ds__section">
      <h2 class="ds__h2">组件（Element Plus）</h2>
      <div class="ds__components">
        <div class="ds__comp-group">
          <el-button>默认</el-button>
          <el-button type="primary">主要</el-button>
          <el-button type="success">成功</el-button>
          <el-button type="warning">警告</el-button>
          <el-button type="danger">危险</el-button>
          <el-button plain>朴素</el-button>
          <el-button text>文字</el-button>
        </div>
        <div class="ds__comp-group">
          <el-tag>默认</el-tag>
          <el-tag type="primary">主要</el-tag>
          <el-tag type="success">成功</el-tag>
          <el-tag type="warning">警告</el-tag>
          <el-tag type="danger">危险</el-tag>
          <el-tag type="info">信息</el-tag>
        </div>
        <div class="ds__comp-group">
          <el-input placeholder="输入框" style="width: 200px" />
          <el-switch />
          <el-progress type="dashboard" :percentage="68" :width="80" />
        </div>
      </div>
    </section>

    <!-- Bento 首页布局预览（示例数据，非真实接口） -->
    <section class="ds__section">
      <h2 class="ds__h2">首页 Bento 布局预览</h2>
      <p class="ds__note">布局示意 · 数字为示例，不代表真实接口数据</p>
      <div class="ds__bento">
        <el-card
          v-for="(card, i) in bentoCards"
          :key="i"
          class="ds__bento-card"
          :style="{ gridColumn: `span ${card.span}` }"
          shadow="hover"
        >
          <div class="ds__bento-title">{{ card.title }}</div>
          <div class="ds__bento-value" :style="{ color: card.accent }">{{ card.value }}</div>
          <div class="ds__bento-hint">{{ card.hint }}</div>
        </el-card>
      </div>
    </section>
  </div>
</template>

<style scoped>
.ds {
  max-width: 1080px;
  margin: 0 auto;
}

.ds__head {
  margin-bottom: var(--space-6);
}

.ds__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.ds__title-icon {
  color: var(--brand-600);
}

.ds__subtitle {
  margin: 4px 0 0;
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.ds__section {
  margin-bottom: var(--space-8);
}

.ds__h2 {
  margin: 0 0 var(--space-4);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.ds__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--space-6);
}

.ds__swatches {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: var(--space-3);
}

.ds__swatch-color {
  height: 56px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
}

.ds__swatch-meta {
  display: flex;
  flex-direction: column;
  margin-top: var(--space-2);
}

.ds__swatch-name {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.ds__swatch-var,
.ds__space-label {
  font-size: 11px;
  color: var(--text-tertiary);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.ds__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  align-items: center;
}

.ds__row--baseline {
  align-items: flex-end;
}

.ds__chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.ds__chip-dot {
  width: 14px;
  height: 14px;
  border-radius: var(--radius-full);
  border: 1px solid var(--border-color);
}

.ds__type p {
  margin: 0 0 var(--space-3);
  color: var(--text-primary);
}

.ds__type-3xl {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
}
.ds__type-2xl {
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
}
.ds__type-xl {
  font-size: var(--text-xl);
}
.ds__type-base {
  font-size: var(--text-base);
  line-height: 1.7;
  color: var(--text-secondary);
  max-width: 640px;
}
.ds__type-sm {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.ds__type-xs {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.ds__space {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

.ds__space-box {
  background: var(--brand-600);
  border-radius: var(--radius-sm);
}

.ds__radius {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

.ds__radius-box {
  width: 48px;
  height: 48px;
  background: var(--bg-surface);
  border: 2px solid var(--border-strong);
}

.ds__shadow {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

.ds__shadow-box {
  width: 64px;
  height: 40px;
  background: var(--bg-surface);
  border-radius: var(--radius-md);
}

.ds__components {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.ds__comp-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.ds__note {
  margin: 0 0 var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.ds__bento {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
}

.ds__bento-card {
  border-radius: var(--radius-lg);
}

.ds__bento-title {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.ds__bento-value {
  margin: var(--space-2) 0;
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
}

.ds__bento-hint {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

@media (max-width: 992px) {
  .ds__bento {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
