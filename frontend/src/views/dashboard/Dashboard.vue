<script setup lang="ts">
/**
 * 首页 Dashboard（前端规格 §11 / 阶段 5，对应 TASK-069）。
 *
 * 真实端点（见 docs/FRONTEND_API_MAPPING.md §3）：
 *   - `GET /api/v1/teams`      我的团队概览（需 `team:read`）
 *   - `GET /api/v1/projects`   我的项目概览（需 `project:read`）
 *   - `GET /api/v1/notifications` 通知（仅自己收件箱）
 *   - `GET /api/v1/logs`       我的操作时间线（需 `log:read`）
 *
 * 为什么没有「任务统计」和「最近任务」卡片（规格 §11.2）：
 * 后端 `GET /tasks` 把 `project_id` 声明为**必填**，且没有跨项目的聚合/统计端点
 * （map §4-D7 / D8、§6-Q2）。这两块属于「需要后端补端点」的未决项，
 * 按规格 §57「禁止猜 API / 编造接口」——本页不伪造它们，改用四个真实概览替代，
 * 并把限制写在页面顶部的提示条里，避免后来者以为是漏做。
 *
 * 每个概览独立加载、独立容错：某项权限不足（403）或缺数据，只让那一块显示错误态，
 * 不影响其余卡片（前端拿不到权限集合，无法预知哪块会 403，见 map §4-D4）。
 */

import { computed, onMounted, reactive } from 'vue'

import { useAuthStore } from '@/stores/auth'
import { teamApi } from '@/api/team'
import { projectApi } from '@/api/project'
import { notificationApi } from '@/api/notification'
import { logApi } from '@/api/log'
import type { ApiError } from '@/utils/request'
import type { Team } from '@/types/team'
import type { Project } from '@/types/project'
import type { Notification } from '@/types/notification'
import type { OperationLog } from '@/types/log'
import { formatDateTime, formatRelativeTime } from '@/utils/format'

import { UserFilled as TeamIcon, Folder, Bell, Document, ArrowRight } from '@element-plus/icons-vue'

const authStore = useAuthStore()

interface Section<T> {
  loading: boolean
  error: string | null
  items: T[]
}

const teams = reactive<Section<Team>>({ loading: true, error: null, items: [] })
const projects = reactive<Section<Project>>({ loading: true, error: null, items: [] })
const notifications = reactive<Section<Notification>>({ loading: true, error: null, items: [] })
const logs = reactive<Section<OperationLog>>({ loading: true, error: null, items: [] })

const greeting = computed(() =>
  authStore.currentUser ? `欢迎回来，${authStore.currentUser.username}` : '欢迎回来',
)

const unreadCount = computed(
  () => notifications.items.filter((item) => !item.is_read).length,
)

async function loadTeams(): Promise<void> {
  teams.loading = true
  teams.error = null
  try {
    teams.items = await teamApi.listTeams({ limit: 5 })
  } catch (error) {
    teams.error = (error as ApiError).message
    teams.items = []
  } finally {
    teams.loading = false
  }
}

async function loadProjects(): Promise<void> {
  projects.loading = true
  projects.error = null
  try {
    projects.items = await projectApi.listProjects({ limit: 5 })
  } catch (error) {
    projects.error = (error as ApiError).message
    projects.items = []
  } finally {
    projects.loading = false
  }
}

async function loadNotifications(): Promise<void> {
  notifications.loading = true
  notifications.error = null
  try {
    notifications.items = await notificationApi.listNotifications({ limit: 5 })
  } catch (error) {
    notifications.error = (error as ApiError).message
    notifications.items = []
  } finally {
    notifications.loading = false
  }
}

async function loadLogs(): Promise<void> {
  logs.loading = true
  logs.error = null
  try {
    logs.items = await logApi.listMyLogs({ limit: 5 })
  } catch (error) {
    logs.error = (error as ApiError).message
    logs.items = []
  } finally {
    logs.loading = false
  }
}

onMounted(() => {
  // 四个概览互不依赖，各自容错；失败只影响本卡片。
  void loadTeams()
  void loadProjects()
  void loadNotifications()
  void loadLogs()
})
</script>

<template>
  <div class="dashboard">
    <header class="dashboard__header">
      <h2 class="dashboard__title">首页</h2>
      <p class="dashboard__subtitle">{{ greeting }}</p>
    </header>

    <el-alert type="info" :closable="false" show-icon class="dashboard__notice">
      <template #title>概览范围说明（来自真实后端契约，非前端缺做）</template>
      <span>
        规格 §11.2 的「任务统计」与全局「最近任务」依赖后端聚合接口，但当前后端
        <code>GET /tasks</code> 要求 <code>project_id</code> 必填、且无跨项目统计端点
        （见 <code>docs/FRONTEND_API_MAPPING.md</code> §4-D7 / D8 / §6-Q2）。本页不编造接口，
        以「我的团队 / 我的项目 / 通知 / 操作日志」四个真实概览替代；任务统计待后端补端点后再做。
      </span>
    </el-alert>

    <el-row :gutter="16" class="dashboard__stats">
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <el-icon class="stat-card__icon stat-card__icon--team"><TeamIcon /></el-icon>
          <el-statistic title="我的团队" :value="teams.items.length" />
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <el-icon class="stat-card__icon stat-card__icon--project"><Folder /></el-icon>
          <el-statistic title="我的项目" :value="projects.items.length" />
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <el-icon class="stat-card__icon stat-card__icon--bell"><Bell /></el-icon>
          <el-statistic title="未读通知" :value="unreadCount" />
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <el-icon class="stat-card__icon stat-card__icon--log"><Document /></el-icon>
          <el-statistic title="近期操作" :value="logs.items.length" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="dashboard__lists">
      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="list-card">
          <template #header>
            <div class="list-card__header">
              <span>最近通知</span>
              <router-link to="/notifications" class="list-card__more">
                查看全部<el-icon><ArrowRight /></el-icon>
              </router-link>
            </div>
          </template>

          <el-skeleton v-if="notifications.loading" :rows="4" animated />
          <el-alert
            v-else-if="notifications.error"
            type="warning"
            :closable="false"
            :title="notifications.error"
          />
          <el-empty v-else-if="notifications.items.length === 0" description="暂无通知" />
          <ul v-else class="entity-list">
            <li v-for="item in notifications.items" :key="item.id" class="entity-list__item">
              <div class="entity-list__main">
                <span class="entity-list__title">{{ item.title }}</span>
                <el-tag v-if="!item.is_read" size="small" type="danger">未读</el-tag>
              </div>
              <span class="entity-list__meta">{{ formatRelativeTime(item.created_at) }}</span>
            </li>
          </ul>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12">
        <el-card shadow="never" class="list-card">
          <template #header>
            <div class="list-card__header">
              <span>最近项目</span>
              <router-link to="/projects" class="list-card__more">
                查看全部<el-icon><ArrowRight /></el-icon>
              </router-link>
            </div>
          </template>

          <el-skeleton v-if="projects.loading" :rows="4" animated />
          <el-alert
            v-else-if="projects.error"
            type="warning"
            :closable="false"
            :title="projects.error"
          />
          <el-empty v-else-if="projects.items.length === 0" description="暂无项目" />
          <ul v-else class="entity-list">
            <li v-for="item in projects.items" :key="item.id" class="entity-list__item">
              <router-link :to="`/projects/${item.id}`" class="entity-list__link">
                <div class="entity-list__main">
                  <span class="entity-list__title">{{ item.name }}</span>
                  <el-icon class="entity-list__go"><ArrowRight /></el-icon>
                </div>
                <span class="entity-list__meta">
                  {{ item.description || '暂无描述' }} · {{ formatDateTime(item.created_at) }}
                </span>
              </router-link>
            </li>
          </ul>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.dashboard__header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dashboard__title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.dashboard__subtitle {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.dashboard__notice {
  line-height: 1.7;
}

.dashboard__notice code {
  background: var(--el-fill-color-light);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 12px;
}

.dashboard__stats {
  margin-top: 0;
}

.stat-card {
  position: relative;
  overflow: hidden;
}

.stat-card__icon {
  position: absolute;
  top: 16px;
  right: 16px;
  font-size: 22px;
  opacity: 0.55;
}

.stat-card__icon--team {
  color: var(--el-color-primary);
}

.stat-card__icon--project {
  color: var(--el-color-success);
}

.stat-card__icon--bell {
  color: var(--el-color-warning);
}

.stat-card__icon--log {
  color: var(--el-color-info);
}

.list-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

.list-card__more {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 13px;
  font-weight: 400;
  color: var(--el-color-primary);
  text-decoration: none;
}

.entity-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.entity-list__item {
  padding: 8px 4px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.entity-list__item:last-child {
  border-bottom: none;
}

.entity-list__link {
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-decoration: none;
  color: inherit;
}

.entity-list__main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.entity-list__title {
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.entity-list__go {
  color: var(--el-text-color-placeholder);
}

.entity-list__meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
