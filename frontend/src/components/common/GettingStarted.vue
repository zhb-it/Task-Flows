<script setup lang="ts">
/**
 * 新账号引导（前端方案 Phase D・TASK-130）。
 *
 * 触发条件由调用方判断（首页在 `teams / projects / tasks / 未读` 全为 0 时渲染），
 * 本组件只负责把「从零到一个能干活的工作台」这件事拆成三步讲清楚：
 *
 * ```text
 *  ① 建团队  →  ② 建项目  →  ③ 分任务
 * ```
 *
 * 三步的完成状态**来自后端聚合的真实计数**（`GET /users/me/overview` 的
 * `teams` / `projects` / `task_status.total`），不是本地标记——所以「我已经建过
 * 团队了」不会因为换了浏览器或清了缓存又被要求做一遍。也因此本组件不引入任何
 * 假数据或假进度。
 *
 * 只强调**当前该做的那一步**（主按钮），其余步骤给次级链接：一屏里出现三个
 * 同等醒目的按钮，等于没有重点。
 */

import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, CircleCheckFilled, FolderOpened, Tickets, UserFilled } from '@element-plus/icons-vue'

const router = useRouter()

const props = defineProps<{
  /** 我加入的团队数。 */
  teams: number
  /** 可见项目数。 */
  projects: number
  /** 可见项目下的任务总数。 */
  tasks: number
}>()

interface Step {
  key: string
  title: string
  desc: string
  to: string
  /** 主按钮文案（仅当前步骤使用）。 */
  cta: string
  done: boolean
}

const steps = computed<Step[]>(() => [
  {
    key: 'team',
    title: '建一个团队',
    desc: '团队是权限与可见范围的边界：你能看到的内容 = 你所属团队下的内容。',
    to: '/teams',
    cta: '创建团队',
    done: props.teams > 0,
  },
  {
    key: 'project',
    title: '在团队下建项目',
    desc: '任务是挂在项目下的，项目又挂在团队下——先把容器准备好。',
    to: '/projects',
    cta: '创建项目',
    done: props.projects > 0,
  },
  {
    key: 'task',
    title: '拆出第一个任务并分配',
    desc: '任务有负责人、优先级与截止时间；分配给自己就会出现在本页「我的待办」。',
    to: '/tasks',
    cta: '新建任务',
    done: props.tasks > 0,
  },
])

/** 第一个未完成的步骤 = 用户此刻该做的事；都完成了则没有当前步。 */
const currentIndex = computed(() => steps.value.findIndex((s) => !s.done))

const doneCount = computed(() => steps.value.filter((s) => s.done).length)

function go(to: string): void {
  void router.push(to)
}
</script>

<template>
  <section class="tf-start" aria-labelledby="tf-start-title">
    <header class="tf-start__head">
      <div>
        <h3 id="tf-start-title" class="tf-start__title">三步开始使用</h3>
        <p class="tf-start__sub">
          工作台的数据来自你实际做的事，现在还是空的——完成后这里的数字会自动出现。
        </p>
      </div>
      <span class="tf-start__progress">
        <span class="tf-start__progress-num">{{ doneCount }}</span>
        <span class="tf-start__progress-total">/ {{ steps.length }}</span>
      </span>
    </header>

    <ol class="tf-start__steps">
      <li
        v-for="(step, index) in steps"
        :key="step.key"
        class="tf-start__step"
        :class="{
          'tf-start__step--done': step.done,
          'tf-start__step--current': index === currentIndex,
        }"
      >
        <span class="tf-start__badge" aria-hidden="true">
          <el-icon v-if="step.done" class="tf-start__badge-icon"><CircleCheckFilled /></el-icon>
          <template v-else>{{ index + 1 }}</template>
        </span>

        <div class="tf-start__body">
          <p class="tf-start__step-title">
            {{ step.title }}
            <span v-if="step.done" class="tf-start__done-tag">已完成</span>
          </p>
          <p class="tf-start__step-desc">{{ step.desc }}</p>
        </div>

        <div class="tf-start__action">
          <el-button
            v-if="index === currentIndex"
            type="primary"
            :icon="step.key === 'team' ? UserFilled : step.key === 'project' ? FolderOpened : Tickets"
            @click="go(step.to)"
          >
            {{ step.cta }}
          </el-button>
          <el-button v-else-if="!step.done" text type="primary" @click="go(step.to)">
            去处理<el-icon class="tf-start__arrow"><ArrowRight /></el-icon>
          </el-button>
        </div>
      </li>
    </ol>

    <p class="tf-start__hint">
      小提示：随时按 <kbd>⌘K</kbd> / <kbd>Ctrl K</kbd> 打开命令面板，搜索或跳转到任意页面。
    </p>
  </section>
</template>

<style scoped>
.tf-start {
  padding: var(--space-6);
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.tf-start__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.tf-start__title {
  margin: 0;
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.tf-start__sub {
  margin: var(--space-1) 0 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.tf-start__progress {
  flex: none;
  display: inline-flex;
  align-items: baseline;
  gap: 2px;
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-full);
  background: var(--bg-surface-2);
  font-variant-numeric: tabular-nums;
}

.tf-start__progress-num {
  font-size: var(--text-lg);
  font-weight: var(--font-bold);
  color: var(--brand-600);
}

.tf-start__progress-total {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.tf-start__steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.tf-start__step {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  transition:
    border-color var(--motion-base),
    background-color var(--motion-base);
}

/* 当前步：品牌色描边 + 淡底，视觉上只有一个「下一步」 */
.tf-start__step--current {
  border-color: var(--brand-400);
  background: color-mix(in srgb, var(--brand-500) 6%, var(--bg-surface));
}

.tf-start__step--done {
  background: var(--bg-surface-2);
}

.tf-start__badge {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  background: var(--bg-surface-2);
  border: 1px solid var(--border-color);
}

.tf-start__step--current .tf-start__badge {
  color: var(--text-on-brand);
  background: var(--brand-600);
  border-color: transparent;
}

.tf-start__step--done .tf-start__badge {
  color: var(--color-success);
  background: transparent;
  border-color: transparent;
}

.tf-start__badge-icon {
  font-size: 20px;
}

.tf-start__body {
  flex: 1;
  min-width: 0;
}

.tf-start__step-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.tf-start__done-tag {
  padding: 0 var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--color-success);
  background: color-mix(in srgb, var(--color-success) 12%, transparent);
}

.tf-start__step-desc {
  margin: var(--space-1) 0 0;
  font-size: var(--text-sm);
  line-height: 1.6;
  color: var(--text-tertiary);
}

.tf-start__action {
  flex: none;
}

.tf-start__arrow {
  margin-left: var(--space-1);
}

.tf-start__hint {
  margin: var(--space-5) 0 0;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.tf-start__hint kbd {
  padding: 1px 6px;
  font-family: inherit;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  background: var(--bg-surface-2);
  border: 1px solid var(--border-color);
  border-radius: 4px;
}

/* 窄屏：按钮换到下一行，避免描述被压成一条 */
@media (max-width: 767px) {
  .tf-start {
    padding: var(--space-4);
  }

  .tf-start__step {
    flex-wrap: wrap;
  }

  .tf-start__action {
    width: 100%;
    padding-left: calc(28px + var(--space-3));
  }
}
</style>
