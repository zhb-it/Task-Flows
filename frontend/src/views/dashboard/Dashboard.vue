<script setup lang="ts">
/**
 * 首页工作台（Bento 布局）—— 前端规格 §11 / 阶段 5，TASK-129 重做。
 *
 * 真实端点：`GET /api/v1/users/me/overview`（TASK-129 新增，规格 §61.6
 * 「个人视图」）。**一次请求**取齐首页所需数字——不再像上一版那样为凑一屏
 * 连打四个端点、每块各自半屏闪烁。
 *
 * 与上一版的关键差别（也是本版存在的理由）：
 * - 上一版顶部挂了一条「任务统计依赖后端聚合端点，前端不编造」的提示条，
 *   四个卡片只能用「列表长度」冒充统计数（团队数 / 项目数 / 未读数 / 日志数）。
 *   现在后端有了真实聚合端点，提示条撤掉，换成**真实的**待办 / 逾期 /
 *   本周完成 / 任务状态分布。
 * - 数字全部来自后端聚合，前端不做二次统计（避免两套口径）。
 *
 * 仍然诚实的地方（不掩饰口径）：
 * - 「本周完成」后端用 `updated_at` 近似完成时刻（tasks 表无 completed_at），
 *   页面脚注写明；周起点直接用后端回传的 `week_start`，前端不自己推算。
 * - 统计口径的分母是「我所属团队下的项目」，脚注写明。
 * - 「我的待办」跳 `/tasks`（该页是项目上下文内的列表，见其页内说明），
 *   不是伪造的跨项目「我的任务」页。
 */

import { computed, onMounted, ref } from 'vue'

import { overviewApi } from '@/api/overview'
import { useAuthStore } from '@/stores/auth'
import type { MeOverview } from '@/types/overview'
import type { TaskStatus } from '@/types/task'
import { TASK_STATUS_LABELS, TASK_STATUS_ORDER } from '@/types/task'
import type { ApiError } from '@/utils/request'
import { formatDateTime, formatRelativeTime } from '@/utils/format'

import {
  ArrowRight,
  Bell,
  CircleCheck,
  FolderOpened,
  Refresh,
  Tickets,
  Timer,
  WarningFilled,
} from '@element-plus/icons-vue'

const authStore = useAuthStore()

const overview = ref<MeOverview | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

/** 状态分布条：按 TASK_STATUS_ORDER 排，颜色与「任务」模块标签保持一致。 */
const STATUS_BAR_COLORS: Record<TaskStatus, string> = {
  TODO: 'var(--el-color-info)',
  IN_PROGRESS: 'var(--brand-500)',
  REVIEW: 'var(--color-warning)',
  DONE: 'var(--color-success)',
  CANCELLED: 'var(--el-border-color-strong, var(--border-strong))',
}

const greeting = computed(() => {
  const hour = new Date().getHours()
  const period = hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好'
  return authStore.currentUser ? `${period}，${authStore.currentUser.username}` : period
})

/** 状态分布（含百分比）；total 为 0 时百分比一律 0，避免出现 NaN%。 */
const statusBars = computed(() => {
  const status = overview.value?.task_status
  const total = status?.total ?? 0
  return TASK_STATUS_ORDER.map((key) => {
    const count = status ? status[key] : 0
    return {
      key,
      label: TASK_STATUS_LABELS[key],
      count,
      color: STATUS_BAR_COLORS[key],
      percent: total > 0 ? Math.round((count / total) * 100) : 0,
    }
  })
})

/** 全零 = 新账号：给引导态而不是六个空洞的 0。 */
const isEmpty = computed(() => {
  const data = overview.value
  if (!data) {
    return false
  }
  return (
    data.projects === 0 &&
    data.task_status.total === 0 &&
    data.unread_notifications === 0 &&
    data.my_tasks.assigned_open === 0
  )
})

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    overview.value = await overviewApi.getMyOverview({ recent_limit: 5 })
  } catch (err) {
    error.value = (err as ApiError).message
    overview.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="workbench">
    <!-- Hero -->
    <header class="hero">
      <div class="hero__text">
        <h2 class="hero__title">{{ greeting }}</h2>
        <p class="hero__subtitle">
          这是你的工作台。
          <template v-if="overview">
            本周自 {{ formatDateTime(overview.week_start) }} 起（UTC 口径）
          </template>
          <template v-else>正在载入你的待办与项目概况</template>
        </p>
      </div>
      <el-button
        class="hero__refresh"
        :icon="Refresh"
        :loading="loading"
        circle
        title="刷新工作台"
        @click="load"
      />
    </header>

    <!-- 错误态：整体失败只有一块，给重试而不是留半屏骨架 -->
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      show-icon
      class="workbench__alert"
    >
      <template #title>工作台加载失败</template>
      <span>{{ error }}</span>
      <el-button link type="primary" @click="load">重试</el-button>
    </el-alert>

    <!-- 加载态 -->
    <div v-else-if="loading" class="bento">
      <div v-for="n in 6" :key="n" class="bento__cell bento__cell--placeholder">
        <el-skeleton animated>
          <template #template>
            <el-skeleton-item variant="p" style="width: 40%" />
            <el-skeleton-item variant="h1" style="width: 60%; margin-top: 12px" />
          </template>
        </el-skeleton>
      </div>
    </div>

    <!-- 空态（新账号引导） -->
    <div v-else-if="isEmpty" class="empty">
      <el-empty description="还没有任何数据">
        <p class="empty__hint">
          加入或创建一个团队，再在团队下建项目、分任务——工作台会自动出现在这里。
        </p>
        <div class="empty__actions">
          <router-link to="/teams" class="empty__link">去团队</router-link>
          <router-link to="/projects" class="empty__link">去项目</router-link>
        </div>
      </el-empty>
    </div>

    <!-- Bento 主体 -->
    <div v-else-if="overview" class="bento">
      <!-- 我的待办：主卡，跨两行 -->
      <section class="bento__cell bento__cell--hero cell card--brand">
        <div class="cell__head">
          <span class="cell__label">我的待办</span>
          <el-icon class="cell__icon"><Tickets /></el-icon>
        </div>
        <p class="cell__value">{{ overview.my_tasks.assigned_open }}</p>
        <p class="cell__foot">
          分配给我、尚未完成
          <span v-if="overview.my_tasks.overdue > 0" class="cell__flag">
            其中 {{ overview.my_tasks.overdue }} 条已逾期
          </span>
        </p>
        <router-link to="/tasks" class="cell__cta">
          去处理<el-icon><ArrowRight /></el-icon>
        </router-link>
      </section>

      <!-- 逾期 -->
      <section
        class="bento__cell cell"
        :class="overview.my_tasks.overdue > 0 ? 'card--danger' : ''"
      >
        <div class="cell__head">
          <span class="cell__label">逾期</span>
          <el-icon class="cell__icon"><Timer /></el-icon>
        </div>
        <p class="cell__value cell__value--sm">{{ overview.my_tasks.overdue }}</p>
        <p class="cell__foot">
          <template v-if="overview.my_tasks.overdue > 0">
            <el-icon class="cell__warn"><WarningFilled /></el-icon> 已过截止时间
          </template>
          <template v-else>没有逾期，节奏不错</template>
        </p>
      </section>

      <!-- 本周完成 -->
      <section class="bento__cell cell card--success">
        <div class="cell__head">
          <span class="cell__label">本周完成</span>
          <el-icon class="cell__icon"><CircleCheck /></el-icon>
        </div>
        <p class="cell__value cell__value--sm">{{ overview.my_tasks.completed_this_week }}</p>
        <p class="cell__foot">状态流转为已完成</p>
      </section>

      <!-- 未读通知 -->
      <section class="bento__cell cell">
        <div class="cell__head">
          <span class="cell__label">未读通知</span>
          <el-icon class="cell__icon"><Bell /></el-icon>
        </div>
        <p class="cell__value cell__value--sm">{{ overview.unread_notifications }}</p>
        <router-link to="/notifications" class="cell__cta">
          查看收件箱<el-icon><ArrowRight /></el-icon>
        </router-link>
      </section>

      <!-- 项目数 -->
      <section class="bento__cell cell">
        <div class="cell__head">
          <span class="cell__label">我的项目</span>
          <el-icon class="cell__icon"><FolderOpened /></el-icon>
        </div>
        <p class="cell__value cell__value--sm">{{ overview.projects }}</p>
        <router-link to="/projects" class="cell__cta">
          查看全部<el-icon><ArrowRight /></el-icon>
        </router-link>
      </section>

      <!-- 任务状态分布 -->
      <section class="bento__cell bento__cell--wide cell">
        <div class="cell__head">
          <span class="cell__label">任务状态分布</span>
          <span class="cell__aside">共 {{ overview.task_status.total }} 条</span>
        </div>
        <div v-if="overview.task_status.total > 0" class="bars">
          <div class="bars__track">
            <span
              v-for="bar in statusBars"
              :key="bar.key"
              class="bars__seg"
              :style="{ width: bar.percent + '%', background: bar.color }"
              :title="`${bar.label} ${bar.count}`"
            />
          </div>
          <ul class="bars__legend">
            <li v-for="bar in statusBars" :key="bar.key" class="bars__item">
              <span class="bars__dot" :style="{ background: bar.color }" />
              <span class="bars__name">{{ bar.label }}</span>
              <span class="bars__num">{{ bar.count }}</span>
            </li>
          </ul>
        </div>
        <p v-else class="cell__foot">可见项目下还没有任务</p>
      </section>

      <!-- 最近项目 -->
      <section class="bento__cell bento__cell--wide cell">
        <div class="cell__head">
          <span class="cell__label">最近项目</span>
          <router-link to="/projects" class="cell__aside cell__aside--link">全部</router-link>
        </div>
        <el-empty
          v-if="overview.recent_projects.length === 0"
          description="暂无项目"
          :image-size="60"
        />
        <ul v-else class="projects">
          <li v-for="item in overview.recent_projects" :key="item.id" class="projects__item">
            <router-link :to="`/projects/${item.id}`" class="projects__link">
              <span class="projects__name">{{ item.name }}</span>
              <span class="projects__meta">{{ formatRelativeTime(item.updated_at) }}</span>
              <el-icon class="projects__go"><ArrowRight /></el-icon>
            </router-link>
          </li>
        </ul>
      </section>
    </div>

    <!-- 口径脚注：不掩饰近似，避免后来者以为是精确值 -->
    <footer v-if="overview" class="footnote">
      <span>
        统计口径：可见范围 = 你所属团队下的项目；「我的」口径为可见范围 ∩ 分配给你；
        「逾期」是「我的待办」的子集。
      </span>
      <span>
        「本周完成」用任务的最后更新时间近似完成时刻（后端暂无完成时间列），周起点为
        {{ formatDateTime(overview.week_start) }}。
      </span>
    </footer>
  </div>
</template>

<style scoped>
.workbench {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

/* ── Hero ─────────────────────────────────────────────────────────── */
.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
}

.hero__title {
  margin: 0;
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  letter-spacing: -0.02em;
  color: var(--text-primary);
}

.hero__subtitle {
  margin: var(--space-1) 0 0;
  font-size: var(--text-base);
  color: var(--text-secondary);
}

.hero__refresh {
  flex: none;
}

/* ── Bento 网格 ───────────────────────────────────────────────────── */
.bento {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-4);
}

.bento__cell--hero {
  grid-column: span 2;
  grid-row: span 2;
}

.bento__cell--wide {
  grid-column: span 2;
}

.cell {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-5);
  min-height: 132px;
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  transition:
    box-shadow var(--motion-base),
    transform var(--motion-base),
    border-color var(--motion-base);
}

.cell:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--border-strong);
  transform: translateY(-2px);
}

.bento__cell--placeholder {
  min-height: 132px;
  padding: var(--space-5);
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
}

/* 主卡：品牌渐变，整块反色 */
.card--brand {
  position: relative;
  overflow: hidden;
  color: var(--text-on-brand);
  background: linear-gradient(135deg, var(--brand-600), var(--brand-500) 60%, var(--brand-400));
  border-color: transparent;
  box-shadow: var(--shadow-brand);
}

.card--brand .cell__label,
.card--brand .cell__foot,
.card--brand .cell__icon {
  color: rgba(255, 255, 255, 0.85);
}

.card--brand .cell__cta {
  color: #fff;
}

.card--brand:hover {
  border-color: transparent;
}

/* 语义色卡：只给左上一抹淡色，不整块染色（避免暗色模式下刺眼） */
.card--danger {
  background: color-mix(in srgb, var(--color-danger) 8%, var(--bg-surface));
  border-color: color-mix(in srgb, var(--color-danger) 35%, var(--border-color));
}

.card--success {
  background: color-mix(in srgb, var(--color-success) 8%, var(--bg-surface));
  border-color: color-mix(in srgb, var(--color-success) 30%, var(--border-color));
}

.cell__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.cell__label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
}

.cell__aside {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.cell__aside--link {
  color: var(--el-color-primary);
  text-decoration: none;
}

.cell__icon {
  font-size: 18px;
  color: var(--text-tertiary);
}

.cell__value {
  margin: 0;
  font-size: 56px;
  line-height: 1.05;
  font-weight: var(--font-bold);
  letter-spacing: -0.03em;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.card--brand .cell__value {
  color: #fff;
}

.cell__value--sm {
  font-size: 32px;
}

.cell__foot {
  margin: auto 0 0;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.cell__flag {
  color: var(--color-danger);
}

.cell__warn {
  color: var(--color-danger);
}

.cell__cta {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  margin-top: auto;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--el-color-primary);
  text-decoration: none;
}

/* ── 状态分布条 ───────────────────────────────────────────────────── */
.bars {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-top: auto;
}

.bars__track {
  display: flex;
  height: 10px;
  border-radius: var(--radius-full);
  overflow: hidden;
  background: var(--bg-surface-2);
}

.bars__seg {
  height: 100%;
  transition: width var(--motion-base);
}

.bars__legend {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
  margin: 0;
  padding: 0;
}

.bars__item {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.bars__dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
}

.bars__num {
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
  font-weight: var(--font-medium);
}

/* ── 最近项目 ─────────────────────────────────────────────────────── */
.projects {
  list-style: none;
  margin: auto 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.projects__item + .projects__item {
  border-top: 1px solid var(--border-color);
}

.projects__link {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  text-decoration: none;
  color: inherit;
}

.projects__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-base);
  color: var(--text-primary);
}

.projects__meta {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.projects__go {
  color: var(--text-tertiary);
  font-size: 14px;
}

/* ── 空态与脚注 ───────────────────────────────────────────────────── */
.empty {
  padding: var(--space-8) 0;
}

.empty__hint {
  margin: var(--space-2) 0 var(--space-3);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.empty__actions {
  display: flex;
  justify-content: center;
  gap: var(--space-4);
}

.empty__link {
  color: var(--el-color-primary);
  text-decoration: none;
  font-size: var(--text-sm);
}

.footnote {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--text-xs);
  line-height: 1.7;
  color: var(--text-tertiary);
}

.workbench__alert {
  align-items: flex-start;
}

/* ── 响应式：Bento 逐级降级（≥1200 四列 / ≥768 两列 / 单列）───────── */
@media (max-width: 1199px) {
  .bento {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .bento__cell--hero,
  .bento__cell--wide {
    grid-column: span 2;
    grid-row: auto;
  }
}

@media (max-width: 767px) {
  .bento {
    grid-template-columns: minmax(0, 1fr);
  }

  .bento__cell--hero,
  .bento__cell--wide {
    grid-column: span 1;
  }

  .cell__value {
    font-size: 44px;
  }

  .hero__title {
    font-size: var(--text-2xl);
  }
}
</style>
